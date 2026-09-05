"""
Local Write-Ahead Log (WAL) storage for the WAL sidecar.

This is a plain SQLite file living on the same machine as the sidecar
process. It is intentionally simple and synchronous: every write here is
committed to disk before the sidecar does anything else (like forwarding
the request onward to Razorpay), so the record survives even if the main
Resync backend process crashes immediately after this point.

This module has ZERO dependency on the main backend app -- the sidecar is
a fully standalone process, run and deployed independently.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

WAL_DB_PATH = Path(__file__).parent / "wal.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT,
    razorpay_order_id TEXT,
    razorpay_payment_id TEXT,
    amount REAL,
    customer_email TEXT,
    direction TEXT NOT NULL,          -- 'request' or 'response'
    razorpay_path TEXT NOT NULL,      -- e.g. '/v1/orders' or '/v1/payments/pay_xxx'
    raw_payload TEXT NOT NULL,        -- full JSON body, as seen on the wire
    captured_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_wal_order_id ON wal_entries(order_id);
CREATE INDEX IF NOT EXISTS idx_wal_rzp_order_id ON wal_entries(razorpay_order_id);
CREATE INDEX IF NOT EXISTS idx_wal_rzp_payment_id ON wal_entries(razorpay_payment_id);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(WAL_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_wal_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


def record_entry(
    *,
    direction: str,
    razorpay_path: str,
    raw_payload: dict[str, Any],
    order_id: Optional[str] = None,
    razorpay_order_id: Optional[str] = None,
    razorpay_payment_id: Optional[str] = None,
    amount: Optional[float] = None,
    customer_email: Optional[str] = None,
) -> int:
    """Durably write one intercepted request/response to the local WAL.

    This is called BEFORE the sidecar forwards the request onward to the
    real Razorpay API (for `direction="request"`) and again as soon as
    Razorpay's reply is received (for `direction="response"`), so the
    record exists independent of whether the caller (Resync's backend)
    is still alive to receive it.
    """
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO wal_entries (
                order_id, razorpay_order_id, razorpay_payment_id, amount,
                customer_email, direction, razorpay_path, raw_payload, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                razorpay_order_id,
                razorpay_payment_id,
                amount,
                customer_email,
                direction,
                razorpay_path,
                json.dumps(raw_payload),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        return cursor.lastrowid


def find_by_razorpay_order_id(razorpay_order_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM wal_entries WHERE razorpay_order_id = ? ORDER BY captured_at ASC",
            (razorpay_order_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def find_by_razorpay_payment_id(razorpay_payment_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM wal_entries WHERE razorpay_payment_id = ? ORDER BY captured_at ASC",
            (razorpay_payment_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def all_entries(limit: int = 200) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM wal_entries ORDER BY captured_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
