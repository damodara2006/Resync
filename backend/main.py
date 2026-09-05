"""
Resync backend: storefront checkout + WAL-based self-healing.

Run:

    uvicorn main:app --port 9000

This process serves the storefront checkout endpoints (see checkout.py)
and durably logs every outbound call it makes to Razorpay before making
it:

  1. Build an outbound request to Razorpay (order.create, etc.).
  2. Write it to a local SQLite WAL FIRST (durably, synchronously) -- this
     is the moment that survives even if this process crashes immediately
     afterward (e.g. an OOM kill), because the write already landed on
     disk before the network call even started.
  3. Send the request to the real Razorpay API.
  4. Write Razorpay's reply to the WAL too.

The catch-all proxy route below lets any Razorpay-shaped HTTP call be
relayed and logged this same way, so the same durability mechanism covers
the healing agent's own payment.all() verification calls as well as
checkout's.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

import wal_db
from checkout import router as checkout_router
from config import get_settings
from healing_agent import run_wal_healing
from mongo import audit_logs_collection

RAZORPAY_UPSTREAM = get_settings().razorpay_upstream_url


@asynccontextmanager
async def lifespan(app: FastAPI):
    wal_db.init_wal_db()
    yield


app = FastAPI(
    title="Resync",
    description=(
        "Storefront checkout backend with a Write-Ahead Log in front of "
        "every Razorpay call. Logs each request/response to local SQLite "
        "before relaying it, so the record survives even if this process "
        "crashes mid-request, and a healing agent uses that log to "
        "reconstruct any order MongoDB never recorded."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Storefront checkout endpoints, registered BEFORE the catch-all proxy
# route below -- otherwise the proxy would swallow these paths first.
app.include_router(checkout_router)


def _extract_order_fields(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort extraction of the fields the healing agent cares about,
    from whatever shape of Razorpay request/response body we're looking at."""
    fields: dict[str, Any] = {
        "order_id": None,
        "razorpay_order_id": None,
        "razorpay_payment_id": None,
        "amount": None,
        "customer_email": None,
    }

    notes = payload.get("notes") or {}
    if isinstance(notes, dict):
        fields["order_id"] = notes.get("internal_order_id") or fields["order_id"]

    if "/orders" in path:
        fields["razorpay_order_id"] = payload.get("id")
    if "/payments" in path:
        fields["razorpay_payment_id"] = payload.get("id")
        fields["razorpay_order_id"] = payload.get("order_id") or fields["razorpay_order_id"]

    if payload.get("amount") is not None:
        try:
            fields["amount"] = float(payload["amount"]) / 100.0
        except (TypeError, ValueError):
            pass

    fields["customer_email"] = payload.get("email") or payload.get("customer_email")

    return fields


def _extract_payment_items(path: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """`GET /v1/payments` (payment.all(), used by the healing scan) returns
    a collection `{"entity": "collection", "items": [...]}`, not a single
    payment object -- _extract_order_fields alone finds nothing useful in
    that shape, since a collection has no top-level id/order_id. This pulls
    per-payment fields out of each item so every captured payment the scan
    happens to see gets its own durable WAL record, exactly as if it had
    been witnessed individually."""
    if "/payments" not in path or not isinstance(payload.get("items"), list):
        return []
    return [_extract_order_fields(path, item) for item in payload["items"]]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "upstream": RAZORPAY_UPSTREAM}


@app.get("/wal/entries")
async def list_wal_entries(limit: int = 200) -> list[dict[str, Any]]:
    return wal_db.all_entries(limit=limit)


@app.post("/wal/heal")
async def heal_from_wal() -> dict[str, Any]:
    """Scan the local WAL for payments Razorpay confirmed captured that
    MongoDB has ZERO record of at all, verify them with Groq, and
    reconstruct the missing order if the safety gate passes."""
    return await run_wal_healing()


@app.get("/wal/orphans")
async def list_current_orphans() -> list[dict[str, Any]]:
    """Preview which WAL-witnessed payments currently have no MongoDB
    order at all, without triggering healing."""
    from healing_agent import scan_wal_for_orphans

    orphans = await scan_wal_for_orphans()
    return [
        {
            "order_id": o.get("order_id"),
            "razorpay_order_id": o.get("razorpay_order_id"),
            "razorpay_payment_id": o.get("razorpay_payment_id"),
            "amount_inr": o.get("amount_inr"),
        }
        for o in orphans
    ]


@app.get("/wal/audit-logs")
async def wal_audit_logs(limit: int = 200) -> list[dict[str, Any]]:
    """Audit trail written by the healing agent."""
    cursor = audit_logs_collection().find({"source": "wal_sidecar"}).sort("timestamp", -1)
    docs = await cursor.to_list(length=limit)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
        if isinstance(doc.get("timestamp"), datetime):
            doc["timestamp"] = doc["timestamp"].isoformat()
    return docs


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy(full_path: str, request: Request) -> Response:
    body_bytes = await request.body()
    try:
        request_payload = json.loads(body_bytes) if body_bytes else {}
    except json.JSONDecodeError:
        request_payload = {}

    request_path = f"/{full_path}"
    request_fields = _extract_order_fields(request_path, request_payload)

    # --- Durable log FIRST, before this process attempts anything else. ---
    wal_db.record_entry(
        direction="request",
        razorpay_path=request_path,
        raw_payload=request_payload,
        **request_fields,
    )

    # --- Now relay the request on to the real Razorpay API. ---
    upstream_url = f"{RAZORPAY_UPSTREAM}{request_path}"
    # Strip whitespace from header values -- some client libraries (e.g. the
    # Razorpay Python SDK's User-Agent) emit trailing whitespace that
    # `requests` tolerates but httpx rejects outright as an illegal header
    # value, crashing the relay before it ever reaches Razorpay.
    forward_headers = {
        k: v.strip()
        for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        upstream_response = await client.request(
            request.method,
            upstream_url,
            content=body_bytes,
            headers=forward_headers,
            params=dict(request.query_params),
        )

    try:
        response_payload = upstream_response.json()
    except ValueError:
        response_payload = {}

    response_fields = _extract_order_fields(request_path, response_payload)
    # Merge: prefer identifiers seen in the response (Razorpay's own IDs),
    # but keep anything only present on the request side (e.g. internal
    # order_id passed in `notes`).
    merged_fields = {**request_fields, **{k: v for k, v in response_fields.items() if v}}

    # --- Log Razorpay's actual reply too, independent of whether this
    # process survives long enough to receive it. ---
    wal_db.record_entry(
        direction="response",
        razorpay_path=request_path,
        raw_payload=response_payload,
        **merged_fields,
    )

    # payment.all() (used by the healing scan) returns a collection of
    # payments in one response -- log each one as its own WAL entry so
    # scan_wal_for_orphans() can see which specific payments Razorpay has
    # actually captured, not just that a scan happened.
    for item_fields in _extract_payment_items(request_path, response_payload):
        if item_fields.get("razorpay_payment_id"):
            wal_db.record_entry(
                direction="response",
                razorpay_path=f"{request_path}/{item_fields['razorpay_payment_id']}",
                raw_payload=next(
                    (
                        item
                        for item in response_payload.get("items", [])
                        if item.get("id") == item_fields["razorpay_payment_id"]
                    ),
                    {},
                ),
                **item_fields,
            )

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers={
            k: v
            for k, v in upstream_response.headers.items()
            if k.lower() not in ("content-length", "transfer-encoding", "content-encoding")
        },
    )
