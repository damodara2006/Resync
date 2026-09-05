"""Short, prefixed, sortable-ish IDs for internal entities (not Razorpay IDs)."""
import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"
