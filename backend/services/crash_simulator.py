"""
Generates realistic simulated crash-dump log text for the "Simulate Server
Crash / Webhook Drop" demo path.

The text intentionally looks like a real stack trace with an unhandled
webhook payload embedded in it, so the Groq forensics step in the
reconciliation agent has something authentic to parse.
"""
from __future__ import annotations

from datetime import datetime, timezone


def build_crash_dump(
    order_id: str,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    amount: float,
    customer_email: str,
) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    return f"""[{ts}] CRITICAL webhook-worker-3: Unhandled exception while processing payment.capture webhook
Traceback (most recent call last):
  File "/app/webhooks/razorpay_handler.py", line 142, in handle_payment_captured
    order = await db.orders.find_one_and_update(
  File "/app/db/pool.py", line 58, in find_one_and_update
    conn = await self._acquire(timeout=2.0)
  File "/app/db/pool.py", line 71, in _acquire
    raise ConnectionPoolTimeout("no available connection in pool after 2.0s")
db.pool.ConnectionPoolTimeout: no available connection in pool after 2.0s

--- Process webhook-worker-3 killed (OOM) before retry could be scheduled ---

Unprocessed webhook payload (recovered from dead-letter buffer):
{{
  "event": "payment.captured",
  "payload": {{
    "payment": {{
      "entity": {{
        "id": "{razorpay_payment_id}",
        "order_id": "{razorpay_order_id}",
        "status": "captured",
        "amount": {int(round(amount * 100))},
        "currency": "INR",
        "email": "{customer_email}",
        "notes": {{
          "internal_order_id": "{order_id}"
        }}
      }}
    }}
  }}
}}

[{ts}] ERROR order-service: order_id={order_id} still marked PENDING after webhook drop.
Customer was charged (payment_id={razorpay_payment_id}, amount=INR {amount:.2f}) but local
fulfillment pipeline never ran. Manual/automated reconciliation required.
""".strip()
