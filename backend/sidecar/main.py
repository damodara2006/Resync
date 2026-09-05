"""
Resync WAL Sidecar -- standalone forward-proxy + local Write-Ahead Log.

Run this as its own process, completely independent of the main Resync
backend:

    uvicorn sidecar.main:app --port 9000

Resync's backend is configured to send its Razorpay API calls to this
sidecar's base URL (see backend/services/razorpay_client.py) instead of
directly to https://api.razorpay.com. This process:

  1. Receives the outbound request Resync intended for Razorpay.
  2. Writes it to a local SQLite WAL FIRST (durably, synchronously) --
     this is the moment that survives even if Resync's own process
     crashes immediately afterward.
  3. Forwards the request on to the real Razorpay API.
  4. Writes Razorpay's reply to the WAL too, then relays it back to
     Resync -- if Resync is dead by this point, the relay simply fails,
     but the WAL entry already exists independent of that outcome.

This process has no dependency on Resync's own FastAPI app, database, or
models -- it is a fully separate deployable unit, as a real sidecar
would be.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from sidecar import wal_db
from sidecar.config import get_sidecar_settings
from sidecar.healing_agent import run_wal_healing
from sidecar.mongo import audit_logs_collection

RAZORPAY_UPSTREAM = get_sidecar_settings().razorpay_upstream_url


@asynccontextmanager
async def lifespan(app: FastAPI):
    wal_db.init_wal_db()
    yield


app = FastAPI(
    title="Resync WAL Sidecar",
    description=(
        "Forward-proxy sitting between Resync's backend and Razorpay. "
        "Logs every request/response to a local SQLite Write-Ahead Log "
        "before relaying it, so the record survives even if Resync's own "
        "process crashes mid-request."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# The WAL Sidecar frontend page (frontend/src/pages/WalSidecarPage.jsx) talks
# to this process directly from the browser -- separate from the main
# backend's own CORS setup, since this is a fully independent process.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "upstream": RAZORPAY_UPSTREAM}


@app.get("/wal/entries")
async def list_wal_entries(limit: int = 200) -> list[dict[str, Any]]:
    return wal_db.all_entries(limit=limit)


@app.post("/wal/heal")
async def heal_from_wal() -> dict[str, Any]:
    """Approach B's self-healing trigger: scan the local WAL for payments
    Razorpay confirmed captured that MongoDB has ZERO record of at all,
    verify them with Groq, and reconstruct the missing order if the
    safety gate passes. Fully independent of Approach A's reconciliation
    agent in the main backend."""
    return await run_wal_healing()


@app.get("/wal/orphans")
async def list_current_orphans() -> list[dict[str, Any]]:
    """Preview which WAL-witnessed payments currently have no MongoDB
    order at all, without triggering healing."""
    from sidecar.healing_agent import scan_wal_for_orphans

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
    """Audit trail written by this sidecar's own healing agent."""
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
    forward_headers = {
        k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")
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

    # --- Log Razorpay's actual reply too, independent of whether Resync
    # survives to receive it. ---
    wal_db.record_entry(
        direction="response",
        razorpay_path=request_path,
        raw_payload=response_payload,
        **merged_fields,
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
