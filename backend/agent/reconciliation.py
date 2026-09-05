"""
The Resync reconciliation agent.

A LangGraph state machine with four stages, matching the buildathon spec:

  1. fetch_anomalies    - diff Razorpay captured payments against local DB
                          orders to find phantom transactions.
  2. log_forensics      - for each anomaly, send the unresolved crash log to
                          Groq (llama-3.3-70b-versatile) and extract
                          structured facts (email, amount, failure_reason).
  3. safety_gate        - verify email match, amount ceiling, and LLM
                          confidence before allowing any autonomous action.
  4. execute_and_audit  - auto-heal (fulfill) or auto-refund when the gate
                          passes; escalate to a human when it doesn't. Every
                          decision, pass or fail, is written to AuditLog.

Each anomaly runs through the full graph independently; `run_reconciliation`
drives the graph once per anomaly and aggregates the results.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph

from config import get_settings
from db.mongo import audit_logs_collection, orders_collection, server_logs_collection
from models.schemas import ActionTaken, LogForensicsResult, OrderStatus
from services.razorpay_client import fetch_recent_captured_payments, refund_payment
from utils.ids import new_id


# --------------------------------------------------------------------------
# Graph state
# --------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    # anomaly identity
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_amount_inr: float
    order_id: Optional[str]
    db_order: Optional[dict[str, Any]]

    # log forensics
    raw_log_text: Optional[str]
    log_id: Optional[str]
    forensics: Optional[LogForensicsResult]

    # safety gate
    email_match: bool
    amount_within_limit: bool
    confidence_sufficient: bool
    safety_gate_passed: bool
    reasoning_steps: list[str]

    # outcome
    action_taken: Optional[ActionTaken]
    audit_id: Optional[str]


# --------------------------------------------------------------------------
# Groq client + structured forensics chain
# --------------------------------------------------------------------------

_FORENSICS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a forensic log analyst for a payments platform. You will be given "
            "a raw server crash-dump log that contains an unprocessed Razorpay webhook "
            "payload. Extract the customer's email, the payment amount in INR, and a "
            "concise failure_reason describing why the local database update never "
            "happened. Set confidence_score to reflect how certain you are that the "
            "extracted email and amount are correct and complete based on the log text. "
            "If a field is not present in the log, leave it null rather than guessing.",
        ),
        ("human", "{raw_log_text}"),
    ]
)


def _get_forensics_chain():
    settings = get_settings()
    llm = ChatGroq(
        model=settings.groq_model_name,
        api_key=settings.groq_api_key,
        temperature=0,
    )
    structured_llm = llm.with_structured_output(LogForensicsResult)
    return _FORENSICS_PROMPT | structured_llm


# --------------------------------------------------------------------------
# Node 1: fetch_anomalies (used once, up-front, to build the work list --
# see find_anomalies() below. Not a graph node itself since it produces the
# *list* of states the graph then runs one at a time.)
# --------------------------------------------------------------------------

async def find_anomalies() -> list[AgentState]:
    """Diff Razorpay's captured payments against local DB orders.

    Returns one AgentState per phantom transaction: a captured Razorpay
    payment whose corresponding local order is not FULFILLED.
    """
    captured_payments = fetch_recent_captured_payments(hours=24)

    anomalies: list[AgentState] = []
    for payment in captured_payments:
        payment_id = payment["id"]
        razorpay_order_id = payment.get("order_id", "")
        amount_inr = payment.get("amount", 0) / 100.0

        db_order = await orders_collection().find_one(
            {"$or": [{"razorpay_payment_id": payment_id}, {"razorpay_order_id": razorpay_order_id}]}
        )

        if db_order is not None and db_order.get("status") == OrderStatus.FULFILLED.value:
            continue  # already reconciled, nothing to do

        if db_order is not None:
            # Mark it DESYNCHRONIZED so the admin dashboard can surface it
            # even before the agent finishes healing it.
            await orders_collection().update_one(
                {"order_id": db_order["order_id"]},
                {"$set": {"status": OrderStatus.DESYNCHRONIZED.value}},
            )

        anomalies.append(
            AgentState(
                razorpay_payment_id=payment_id,
                razorpay_order_id=razorpay_order_id,
                razorpay_amount_inr=amount_inr,
                order_id=db_order["order_id"] if db_order else None,
                db_order=db_order,
                reasoning_steps=[
                    f"Anomaly detected: Razorpay payment {payment_id} is captured "
                    f"(INR {amount_inr:.2f}) but local order "
                    f"{'is ' + db_order['status'] if db_order else 'was not found'}."
                ],
            )
        )

    return anomalies


# --------------------------------------------------------------------------
# Node 2: log_forensics
# --------------------------------------------------------------------------

async def log_forensics_node(state: AgentState) -> AgentState:
    if state.get("order_id") is None:
        state["reasoning_steps"].append(
            "No matching local order found at all — cannot run log forensics without an order_id."
        )
        state["raw_log_text"] = None
        return state

    log_doc = await server_logs_collection().find_one(
        {"order_id": state["order_id"], "resolved": False}
    )

    if log_doc is None:
        state["reasoning_steps"].append(
            "No unresolved crash log found for this order — cannot run forensics."
        )
        state["raw_log_text"] = None
        return state

    state["log_id"] = log_doc["log_id"]
    state["raw_log_text"] = log_doc["raw_log_text"]

    chain = _get_forensics_chain()
    result: LogForensicsResult = await chain.ainvoke({"raw_log_text": log_doc["raw_log_text"]})
    state["forensics"] = result

    state["reasoning_steps"].append(
        f"Groq log forensics extracted email={result.customer_email}, "
        f"amount={result.amount}, failure_reason='{result.failure_reason}', "
        f"confidence={result.confidence_score:.2f}."
    )
    return state


# --------------------------------------------------------------------------
# Node 3: safety_gate
# --------------------------------------------------------------------------

async def safety_gate_node(state: AgentState) -> AgentState:
    settings = get_settings()
    forensics = state.get("forensics")
    db_order = state.get("db_order")

    if forensics is None or db_order is None:
        state["email_match"] = False
        state["amount_within_limit"] = False
        state["confidence_sufficient"] = False
        state["safety_gate_passed"] = False
        state["reasoning_steps"].append(
            "Safety gate: FAILED — missing forensics result or local order record."
        )
        return state

    email_match = (
        forensics.customer_email is not None
        and forensics.customer_email.lower() == db_order.get("customer_email", "").lower()
    )
    amount_within_limit = state["razorpay_amount_inr"] <= settings.safety_max_amount_inr
    confidence_sufficient = forensics.confidence_score >= settings.safety_min_confidence

    state["email_match"] = email_match
    state["amount_within_limit"] = amount_within_limit
    state["confidence_sufficient"] = confidence_sufficient
    state["safety_gate_passed"] = email_match and amount_within_limit and confidence_sufficient

    state["reasoning_steps"].append(
        "Safety gate check 1 (email match): "
        f"{'PASS' if email_match else 'FAIL'} "
        f"(log email='{forensics.customer_email}' vs order email='{db_order.get('customer_email')}')."
    )
    state["reasoning_steps"].append(
        "Safety gate check 2 (amount <= "
        f"INR {settings.safety_max_amount_inr:.2f}): "
        f"{'PASS' if amount_within_limit else 'FAIL'} (amount=INR {state['razorpay_amount_inr']:.2f})."
    )
    state["reasoning_steps"].append(
        "Safety gate check 3 (confidence >= "
        f"{settings.safety_min_confidence:.2f}): "
        f"{'PASS' if confidence_sufficient else 'FAIL'} (confidence={forensics.confidence_score:.2f})."
    )
    state["reasoning_steps"].append(
        f"Safety gate overall: {'PASSED' if state['safety_gate_passed'] else 'FAILED'}."
    )
    return state


# --------------------------------------------------------------------------
# Node 4: execute_and_audit
# --------------------------------------------------------------------------

async def execute_and_audit_node(state: AgentState) -> AgentState:
    db_order = state.get("db_order")
    forensics = state.get("forensics")
    confidence = forensics.confidence_score if forensics else 0.0

    if state.get("safety_gate_passed") and db_order is not None:
        await orders_collection().update_one(
            {"order_id": db_order["order_id"]},
            {"$set": {"status": OrderStatus.FULFILLED.value}},
        )
        state["action_taken"] = ActionTaken.AUTO_FULFILL
        state["reasoning_steps"].append(
            f"Action: AUTO_FULFILL — order {db_order['order_id']} updated to FULFILLED."
        )
    else:
        if db_order is not None:
            await orders_collection().update_one(
                {"order_id": db_order["order_id"]},
                {"$set": {"status": OrderStatus.DESYNCHRONIZED.value}},
            )
        state["action_taken"] = ActionTaken.HUMAN_ESCALATION
        state["reasoning_steps"].append(
            "Action: HUMAN_ESCALATION — safety gate did not pass, order left DESYNCHRONIZED "
            "for manual review."
        )

    if state.get("log_id"):
        await server_logs_collection().update_one(
            {"log_id": state["log_id"]}, {"$set": {"resolved": True}}
        )

    audit_id = new_id("aud")
    await audit_logs_collection().insert_one(
        {
            "audit_id": audit_id,
            "order_id": state.get("order_id") or "UNKNOWN",
            "razorpay_payment_id": state["razorpay_payment_id"],
            "action_taken": state["action_taken"].value,
            "confidence_score": confidence,
            "reasoning": "\n".join(state["reasoning_steps"]),
            "safety_gate_passed": bool(state.get("safety_gate_passed")),
            "timestamp": datetime.now(timezone.utc),
        }
    )
    state["audit_id"] = audit_id
    return state


# --------------------------------------------------------------------------
# Graph assembly
# --------------------------------------------------------------------------

def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("log_forensics", log_forensics_node)
    graph.add_node("safety_gate", safety_gate_node)
    graph.add_node("execute_and_audit", execute_and_audit_node)

    graph.set_entry_point("log_forensics")
    graph.add_edge("log_forensics", "safety_gate")
    graph.add_edge("safety_gate", "execute_and_audit")
    graph.add_edge("execute_and_audit", END)

    return graph.compile()


_compiled_graph = None


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


# --------------------------------------------------------------------------
# Public entrypoint used by the FastAPI route
# --------------------------------------------------------------------------

async def run_reconciliation() -> dict[str, Any]:
    anomalies = await find_anomalies()
    graph = get_compiled_graph()

    auto_healed = 0
    escalated = 0
    audit_log_ids: list[str] = []

    for anomaly_state in anomalies:
        final_state = await graph.ainvoke(anomaly_state)
        if final_state.get("action_taken") == ActionTaken.AUTO_FULFILL:
            auto_healed += 1
        else:
            escalated += 1
        if final_state.get("audit_id"):
            audit_log_ids.append(final_state["audit_id"])

    return {
        "scanned_payments": len(anomalies),
        "anomalies_found": len(anomalies),
        "auto_healed": auto_healed,
        "escalated": escalated,
        "audit_log_ids": audit_log_ids,
    }
