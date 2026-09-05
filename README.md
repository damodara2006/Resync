# Resync

**Razorpay AI Builder Internship 2026 — AI Revenue Recovery**

## Problem

A payment can be successfully captured by Razorpay while the merchant's backend crashes before the transaction is saved to its own database.

Razorpay knows the payment happened, but the merchant may have lost the local execution state needed to reconstruct the missing order.

**Resync recovers that missing state using durable execution evidence captured before the crash.**

## How It Works

```text
Merchant Backend
      |
      v
  SQLite WAL
      |
      | Record request
      | before Razorpay call
      v
   Razorpay
      |
      | Payment captured
      v
Backend crashes
      |
      v
Healing Agent
      |
      +---- Razorpay payment data
      +---- WAL evidence
      +---- MongoDB state
      |
      v
Validation + AI Assessment
      |
   +--+--+
   |     |
 PASS   FAIL
   |     |
   v     v
Recover  Manual Review
MongoDB
```

Recovery Process

1. WAL — Records important Razorpay requests and internal order information before the external call.
2. Detection — Finds captured Razorpay payments without a corresponding MongoDB order.
3. Validation — Checks amounts and identifiers deterministically.
4. AI Assessment — Groq ("openai/gpt-oss-120b") evaluates whether the surviving evidence is sufficient for recovery.
5. Safety Gate — Recovery only happens when the validation and confidence checks pass.
6. Audit — Recovery decisions and reasoning are recorded.

Why Resync?

Razorpay's API can tell a merchant that a payment exists.

Resync addresses the harder case where the merchant's own database has lost the transaction state.

It combines:

Razorpay payment state
        +
Merchant-side WAL evidence
        =
Recoverable merchant state

Resync does not replace Razorpay reconciliation. It provides the missing execution evidence needed for crash recovery.

Demo

The "/wal-sidecar" dashboard demonstrates a crash scenario where:

- A Razorpay payment succeeds.
- The merchant database receives no order.
- The WAL still contains the execution evidence.
- The healing agent detects and evaluates the orphaned payment.
- The missing MongoDB order is reconstructed when the safety checks pass.

Tech Stack

- Backend: FastAPI, Python
- Database: MongoDB
- WAL: SQLite
- AI: Groq ("openai/gpt-oss-120b")
- Payments: Razorpay
- Frontend: React, Vite

Repository

backend/    FastAPI, Razorpay, WAL, healing agent
frontend/   React storefront and recovery dashboard

Run Locally

Backend

cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 9000

Configure Razorpay test keys, Groq API key, and "MONGODB_URI" in ".env".

Frontend

cd frontend
npm install
cp .env.example .env
npm run dev
