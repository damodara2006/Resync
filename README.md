# Resync — Webhook Drop & State Reconciliation Agent

Built for the Razorpay AI Buildathon.

## The Problem

**Phantom Transactions**: a payment is successfully captured on Razorpay, but the
merchant's server crashes (or drops the webhook) before the local database is
updated. The customer is charged, but the order stays `PENDING`/`FAILED` locally.

## The Solution

Resync is an autonomous, state-driven reconciliation agent:

1. Scans Razorpay's captured payments against local DB orders to find phantom
   transactions (a captured payment with no matching `FULFILLED` order).
2. Feeds the raw server crash log for that transaction to Groq
   (`llama-3.3-70b-versatile`) via LangGraph, extracting the customer email,
   amount, and failure reason with a structured (Pydantic) output parser.
3. Runs the extraction through a **safety gate**: email match, amount ceiling
   (₹10,000), and a minimum LLM confidence score (0.85).
4. If the gates pass, the agent auto-heals the order (`FULFILLED`) or triggers
   a refund; if not, it escalates to a human. Every decision is written to an
   immutable audit log with full reasoning.

## Repo layout

```
backend/     FastAPI app, LangGraph reconciliation agent, MongoDB models
frontend/    React (Vite) storefront + admin dashboard
```

## Status

This repository is being built incrementally, chunk by chunk. See commit
history for progress. Each chunk is pushed manually after review.

## Running locally (once backend/frontend chunks land)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in Razorpay + Groq test keys
uvicorn main:app --reload --port 8000
```

Requires a MongoDB instance reachable at `MONGODB_URI` (local `mongod` or
MongoDB Atlas free tier both work).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Environment variables

See [`backend/.env.example`](backend/.env.example) for the full list
(Razorpay test keys, Groq API key, Mongo URI, safety-gate thresholds).
