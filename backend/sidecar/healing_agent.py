"""
Approach B: the WAL Sidecar's self-healing agent.

This solves the harder "Zero-DB-Footprint Orphaned Payment" case: the
merchant's server crashed so early that NOT EVEN a PENDING order row was
ever written to MongoDB. Approach A (backend/agent/reconciliation.py) has
no way to safety-check an order it has zero local record of, so it can
only escalate to a human in that situation.

This agent closes that gap using a completely independent detection
mechanism: the local WAL this sidecar already captured, purely by having
sat in the middle of the Resync -> Razorpay conversation. It never reads
Resync's own database writes or crash logs -- everything it needs (the
internal order_id, the Razorpay order/payment ids, the amount, the
customer email) was already witnessed directly off the wire.

Pipeline (LangGraph state machine, four stages -- mirroring Approach A's
shape so the two are easy to compare side by side, but fully independent
in implementation):

  1. scan_wal_for_orphans   - find WAL entries whose Razorpay payment was
                              captured, but MongoDB has zero order record
                              at all (not PENDING, not anything -- absent).
  2. groq_identity_check    - ask Groq to cross-check the WAL's own
                              request-side and response-side records
                              agree with each other (same email/amount
                              reported at both ends of the same
                              transaction), and to explain its reasoning.
  3. safety_gate            - amount ceiling + Groq confidence threshold.
                              (No local order to check email against --
                              there never was one -- so this gate instead
                              verifies internal WAL self-consistency.)
  4. reconstruct_and_audit  - if the gate passes, INSERT (not update) a
                              brand new order document directly into
                              MongoDB with status FULFILLED_VIA_LOCAL_WAL,
                              and write the full reasoning trail to
                              AuditLog.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, TypedDict
from uuid import uuid4

logger = logging.getLogger("sidecar.healing_agent")

from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, EmailStr, Field

from sidecar import wal_db
from sidecar.config import get_sidecar_settings
from sidecar.mongo import audit_logs_collection, orders_collection


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


# --------------------------------------------------------------------------
# Structured Groq output
# --------------------------------------------------------------------------

class WalIdentityCheckResult(BaseModel):
    """Groq's read of the WAL's response-side record.

    Deliberately minimal: amount/identity consistency between the request
    and response WAL entries is objectively checkable and is done in plain
    Python (see `_check_wal_consistency`) rather than asked of the model --
    a richer schema with multiple boolean judgment fields proved unreliable
    for tool-calling on some Groq models. This schema asks the LLM only for
    what genuinely needs judgment: recovering the customer email and
    explaining its confidence.
    """

    customer_email: Optional[EmailStr] = Field(
        default=None, description="Customer email recovered from the WAL record, if present"
    )
    reasoning: str = Field(description="Concise explanation of the confidence score below")
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="Confidence (0-1) that this WAL record is trustworthy"
    )


_IDENTITY_CHECK_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a forensic auditor for a payments platform's local Write-Ahead Log (WAL). "
            "You will be given the raw JSON body of a captured payment that the WAL sidecar saw "
            "directly on the network wire. The merchant's own database has ZERO record of this "
            "order -- it likely crashed before writing anything. Recover the customer email if "
            "present, and set confidence_score to reflect how certain you are that this record "
            "is complete and trustworthy enough to reconstruct an order from.",
        ),
        ("human", "WAL payment record:\n{response_payload}"),
    ]
)


def _check_wal_consistency(
    request_entry: Optional[dict[str, Any]], response_entry: dict[str, Any]
) -> tuple[bool, bool]:
    """Deterministic (non-LLM) checks the safety gate relies on:
    does the amount match between the request and response WAL entries,
    and is the order/payment identity linkage coherent. These are plain
    equality checks -- no judgment call needed, so no reason to route them
    through an LLM tool call."""
    amount_consistent = True
    if request_entry and request_entry.get("amount") is not None:
        amount_consistent = request_entry.get("amount") == response_entry.get("amount")

    identity_consistent = bool(response_entry.get("razorpay_order_id")) and bool(
        response_entry.get("razorpay_payment_id")
    )

    return amount_consistent, identity_consistent


def _get_identity_check_chain():
    settings = get_sidecar_settings()
    llm = ChatGroq(model=settings.groq_model_name, api_key=settings.groq_api_key, temperature=0)
    return _IDENTITY_CHECK_PROMPT | llm.with_structured_output(WalIdentityCheckResult)


# --------------------------------------------------------------------------
# Graph state
# --------------------------------------------------------------------------

class HealingState(TypedDict, total=False):
    order_id: Optional[str]
    razorpay_order_id: Optional[str]
    razorpay_payment_id: Optional[str]
    amount_inr: Optional[float]
    wal_request_entry: Optional[dict[str, Any]]
    wal_response_entry: Optional[dict[str, Any]]

    identity_check: Optional[WalIdentityCheckResult]
    amount_consistent: bool
    identity_consistent: bool
    amount_within_limit: bool
    confidence_sufficient: bool
    safety_gate_passed: bool
    reasoning_steps: list[str]

    action_taken: str
    audit_id: Optional[str]


# --------------------------------------------------------------------------
# Node 1 (pre-graph): find zero-DB-footprint orphans from the WAL
# --------------------------------------------------------------------------

async def scan_wal_for_orphans() -> list[HealingState]:
    """Find WAL-witnessed payments that MongoDB has NO order record for at all.

    This is the harder case than Approach A's anomaly detection: here the
    local order document does not exist -- not PENDING, not anything.
    """
    entries = wal_db.all_entries(limit=500)

    # Group WAL rows by razorpay_order_id so we can pair up the
    # request-side and response-side records for the same transaction.
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for entry in entries:
        rzp_order_id = entry.get("razorpay_order_id")
        if not rzp_order_id:
            continue
        grouped.setdefault(rzp_order_id, {"request": [], "response": []})
        grouped[rzp_order_id][entry["direction"]].append(entry)

    orphans: list[HealingState] = []
    for rzp_order_id, sides in grouped.items():
        # Only interested in transactions where Razorpay actually
        # confirmed a captured payment (visible on the response side).
        payment_response = next(
            (
                e
                for e in sides["response"]
                if e.get("razorpay_payment_id")
            ),
            None,
        )
        if payment_response is None:
            continue

        order_id = payment_response.get("order_id") or next(
            (e.get("order_id") for e in sides["request"] if e.get("order_id")), None
        )

        existing_order = None
        if order_id:
            existing_order = await orders_collection().find_one({"order_id": order_id})
        if existing_order is None:
            existing_order = await orders_collection().find_one(
                {"razorpay_order_id": rzp_order_id}
            )

        if existing_order is not None:
            continue  # MongoDB already has a record -- not a zero-footprint case.

        request_entry = sides["request"][0] if sides["request"] else None

        orphans.append(
            HealingState(
                order_id=order_id,
                razorpay_order_id=rzp_order_id,
                razorpay_payment_id=payment_response.get("razorpay_payment_id"),
                amount_inr=payment_response.get("amount"),
                wal_request_entry=request_entry,
                wal_response_entry=payment_response,
                reasoning_steps=[
                    f"Zero-DB-footprint anomaly: Razorpay order {rzp_order_id} / payment "
                    f"{payment_response.get('razorpay_payment_id')} was witnessed captured "
                    f"directly in the WAL sidecar's traffic log, but MongoDB has NO order "
                    f"record at all (not PENDING, not anything) -- the merchant backend "
                    f"likely crashed before writing any row."
                ],
            )
        )

    return orphans


# --------------------------------------------------------------------------
# Node 2: groq_identity_check
# --------------------------------------------------------------------------

_RELEVANT_PAYMENT_FIELDS = (
    "id",
    "order_id",
    "amount",
    "currency",
    "status",
    "captured",
    "email",
    "contact",
    "notes",
    "created_at",
)


def _trim_payload_for_groq(raw_payload_json: str) -> str:
    """Strip a raw Razorpay JSON body down to only the fields relevant to
    the identity check, before it ever reaches the LLM.

    The full payment object includes card metadata, bank/acquirer details,
    and (for failed attempts) verbose error fields -- none of which the
    identity check needs, and which in practice made the tool-calling
    schema unreliable on some Groq models (large, noisy inputs increased
    the odds of a malformed structured-output response).
    """
    try:
        payload = json.loads(raw_payload_json)
    except (TypeError, ValueError):
        return raw_payload_json

    if not isinstance(payload, dict):
        return raw_payload_json

    trimmed = {k: payload[k] for k in _RELEVANT_PAYMENT_FIELDS if k in payload}
    return json.dumps(trimmed)


async def groq_identity_check_node(state: HealingState) -> HealingState:
    request_entry = state.get("wal_request_entry")
    response_entry = state.get("wal_response_entry")

    if response_entry is None:
        state["reasoning_steps"].append(
            "No response-side WAL record available -- cannot verify identity."
        )
        state["identity_check"] = None
        return state

    # Amount/identity consistency are objectively checkable -- compute them
    # deterministically rather than asking the LLM to judge them (see
    # _check_wal_consistency's docstring for why).
    amount_consistent, identity_consistent = _check_wal_consistency(request_entry, response_entry)
    state["amount_consistent"] = amount_consistent
    state["identity_consistent"] = identity_consistent

    chain = _get_identity_check_chain()
    try:
        result: WalIdentityCheckResult = await chain.ainvoke(
            {
                "response_payload": _trim_payload_for_groq(
                    response_entry.get("raw_payload", "{}")
                ),
            }
        )
    except Exception as exc:  # Groq tool-call/schema failures, rate limits, etc.
        logger.exception("Groq identity check failed for a WAL orphan")
        error_detail = str(exc)[:300]
        state["identity_check"] = None
        state["reasoning_steps"].append(
            f"Groq WAL identity check FAILED to produce a valid result ({exc.__class__.__name__}: "
            f"{error_detail}) -- treating as unverifiable rather than guessing; this orphan will "
            "be escalated."
        )
        return state

    state["identity_check"] = result

    state["reasoning_steps"].append(
        f"Deterministic WAL consistency check: amount_consistent={amount_consistent}, "
        f"identity_consistent={identity_consistent}."
    )
    state["reasoning_steps"].append(
        f"Groq WAL identity check: email={result.customer_email}, "
        f"confidence={result.confidence_score:.2f}. Reasoning: {result.reasoning}"
    )
    return state


# --------------------------------------------------------------------------
# Node 3: safety_gate
# --------------------------------------------------------------------------

async def safety_gate_node(state: HealingState) -> HealingState:
    settings = get_sidecar_settings()
    identity_check = state.get("identity_check")
    amount_inr = state.get("amount_inr") or 0.0

    if identity_check is None:
        state["amount_within_limit"] = False
        state["confidence_sufficient"] = False
        state["safety_gate_passed"] = False
        state["reasoning_steps"].append("Safety gate: FAILED -- no identity check result.")
        return state

    amount_within_limit = amount_inr <= settings.safety_max_amount_inr
    confidence_sufficient = identity_check.confidence_score >= settings.safety_min_confidence
    internally_consistent = bool(state.get("amount_consistent")) and bool(
        state.get("identity_consistent")
    )

    state["amount_within_limit"] = amount_within_limit
    state["confidence_sufficient"] = confidence_sufficient
    state["safety_gate_passed"] = (
        amount_within_limit and confidence_sufficient and internally_consistent
    )

    state["reasoning_steps"].append(
        f"Safety gate check 1 (amount <= INR {settings.safety_max_amount_inr:.2f}): "
        f"{'PASS' if amount_within_limit else 'FAIL'} (amount=INR {amount_inr:.2f})."
    )
    state["reasoning_steps"].append(
        f"Safety gate check 2 (WAL internal consistency): "
        f"{'PASS' if internally_consistent else 'FAIL'}."
    )
    state["reasoning_steps"].append(
        f"Safety gate check 3 (confidence >= {settings.safety_min_confidence:.2f}): "
        f"{'PASS' if confidence_sufficient else 'FAIL'} (confidence={identity_check.confidence_score:.2f})."
    )
    state["reasoning_steps"].append(
        f"Safety gate overall: {'PASSED' if state['safety_gate_passed'] else 'FAILED'}."
    )
    return state


# --------------------------------------------------------------------------
# Node 4: reconstruct_and_audit
# --------------------------------------------------------------------------

async def reconstruct_and_audit_node(state: HealingState) -> HealingState:
    identity_check = state.get("identity_check")
    confidence = identity_check.confidence_score if identity_check else 0.0
    reconstructed_order_id = state.get("order_id") or new_id("ord")

    if state.get("safety_gate_passed"):
        await orders_collection().insert_one(
            {
                "order_id": reconstructed_order_id,
                "razorpay_order_id": state["razorpay_order_id"],
                "razorpay_payment_id": state["razorpay_payment_id"],
                "amount": state.get("amount_inr") or 0.0,
                "customer_email": (identity_check.customer_email if identity_check else None)
                or "unknown@recovered-via-wal.local",
                "status": "FULFILLED_VIA_LOCAL_WAL",
                "created_at": datetime.now(timezone.utc),
            }
        )
        state["action_taken"] = "AUTO_FULFILL_VIA_WAL"
        state["reasoning_steps"].append(
            f"Action: AUTO_FULFILL_VIA_WAL -- reconstructed order {reconstructed_order_id} "
            f"directly from the local WAL and inserted it into MongoDB with status "
            f"FULFILLED_VIA_LOCAL_WAL."
        )
    else:
        state["action_taken"] = "HUMAN_ESCALATION"
        state["reasoning_steps"].append(
            "Action: HUMAN_ESCALATION -- safety gate did not pass; the zero-footprint "
            "payment is left for manual review rather than blindly reconstructed."
        )

    audit_id = new_id("aud")
    await audit_logs_collection().insert_one(
        {
            "audit_id": audit_id,
            "order_id": reconstructed_order_id,
            "razorpay_payment_id": state.get("razorpay_payment_id") or "UNKNOWN",
            "action_taken": state["action_taken"],
            "confidence_score": confidence,
            "reasoning": "\n".join(state["reasoning_steps"]),
            "safety_gate_passed": bool(state.get("safety_gate_passed")),
            "source": "wal_sidecar",
            "timestamp": datetime.now(timezone.utc),
        }
    )
    state["audit_id"] = audit_id
    return state


# --------------------------------------------------------------------------
# Graph assembly
# --------------------------------------------------------------------------

def build_healing_graph():
    graph = StateGraph(HealingState)
    graph.add_node("groq_identity_check", groq_identity_check_node)
    graph.add_node("safety_gate", safety_gate_node)
    graph.add_node("reconstruct_and_audit", reconstruct_and_audit_node)

    graph.set_entry_point("groq_identity_check")
    graph.add_edge("groq_identity_check", "safety_gate")
    graph.add_edge("safety_gate", "reconstruct_and_audit")
    graph.add_edge("reconstruct_and_audit", END)

    return graph.compile()


_compiled_graph = None


def get_compiled_healing_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_healing_graph()
    return _compiled_graph


# --------------------------------------------------------------------------
# Public entrypoint
# --------------------------------------------------------------------------

async def run_wal_healing() -> dict[str, Any]:
    orphans = await scan_wal_for_orphans()
    graph = get_compiled_healing_graph()

    healed = 0
    escalated = 0
    audit_log_ids: list[str] = []

    for orphan_state in orphans:
        try:
            final_state = await graph.ainvoke(orphan_state)
        except Exception:
            # One orphan failing (Groq hiccup, transient Mongo error, etc.)
            # should not take down the whole batch -- count it as escalated
            # and move on to the rest.
            escalated += 1
            continue
        if final_state.get("action_taken") == "AUTO_FULFILL_VIA_WAL":
            healed += 1
        else:
            escalated += 1
        if final_state.get("audit_id"):
            audit_log_ids.append(final_state["audit_id"])

    return {
        "orphans_found": len(orphans),
        "healed_via_wal": healed,
        "escalated": escalated,
        "audit_log_ids": audit_log_ids,
    }
