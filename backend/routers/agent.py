"""Endpoint that triggers the LangGraph reconciliation agent scan."""
from __future__ import annotations

from fastapi import APIRouter

from agent.reconciliation import run_reconciliation
from models.api import RunReconciliationResponse

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/run-reconciliation", response_model=RunReconciliationResponse)
async def run_reconciliation_endpoint() -> RunReconciliationResponse:
    result = await run_reconciliation()
    return RunReconciliationResponse(**result)
