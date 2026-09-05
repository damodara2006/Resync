# Resync

Razorpay AI Builder Internship 2026 — AI Revenue Recovery.

## Problem

A payment can be captured on Razorpay while the merchant's backend
crashes before writing anything to its own database — not even a
`PENDING` row. The money moves, but the local database has no record the
checkout ever happened. A reconciliation job that only queries Razorpay's
API after the fact can recover the payment details, but has no way to
match a payment back to an internal order if the backend crashed before
it could tell Razorpay which order this was.

## Approach

A single backend process puts a local Write-Ahead Log in front of every
Razorpay call:

1. Before each outbound call to Razorpay (create an order, verify a
   payment), the request is written to a local SQLite WAL. The write
   lands on disk before the network call happens, so it survives even if
   the process crashes immediately afterward.
2. A healing agent independently asks Razorpay which payments it has
   captured, then checks MongoDB for a matching order. If MongoDB has no
   record at all, the WAL is the only place the order's identity survives.
3. Groq (`openai/gpt-oss-120b`) assesses whether the WAL record is
   complete enough to reconstruct an order from. Amount and identifier
   consistency are checked deterministically in code, not left to the
   model.
4. A safety gate (amount ceiling, WAL consistency, model confidence) must
   pass before the order is reconstructed in MongoDB. If it fails, the
   payment is left for manual review instead of being guessed at. Every
   decision is written to an audit log with its full reasoning.

## Scope

This targets the case where the backend crashes before Razorpay has any
way to know which internal order a payment belongs to. For a crash that
happens after an order is normally created and recorded, a periodic
reconciliation job against Razorpay's payments API is simpler and
sufficient on its own — this project is specifically about the harder
case where that lookup has nothing to match against.

## Repo layout

```
backend/    FastAPI app: storefront checkout, the WAL, the healing agent
frontend/   React (Vite) storefront and dashboard
```

## Running locally

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Razorpay test keys, Groq key, Mongo URI
uvicorn main:app --reload --port 9000
```

Requires a MongoDB instance reachable at `MONGODB_URI` (local `mongod` or
MongoDB Atlas).

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

`/` is the storefront. `/wal-sidecar` is the dashboard: a button to
simulate a mid-flight crash with zero database footprint, and a button to
run the healing agent against the resulting orphaned payment.

## Environment variables

See [`backend/.env.example`](backend/.env.example).
