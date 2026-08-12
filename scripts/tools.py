"""
Tool implementations for the NexusPay agent, plus their OpenAI-style function
schemas (used as the `tools` param in vLLM's /v1/chat/completions).

All five tools operate on simulated data:
  - rag_lookup            : semantic search over the NexusPay docs (real embed server + real chunks)
  - check_transaction_status : reads the mock_transactions table (fake ledger, see sql/)
  - initiate_refund       : WRITES to mock_transactions (status -> 'refunded') — no real money moves
  - get_exchange_rate      : REAL external API call (Frankfurter, ECB rates, no key needed)
  - calculate_fees         : pure local arithmetic, no I/O

initiate_refund is the only state-changing (POST-like) tool. It is entirely local/simulated —
there is no real payment processor behind it.
"""

import json
import os

import numpy as np
import psycopg2
import requests

DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "nexuspay_rag"
DB_USER = "postgres"
DB_PASSWORD = "postgres"

EMBEDDING_URL = "http://localhost:8083/embed"
CHUNKS_FILE = os.path.join(os.path.dirname(__file__), "..", "output", "chunks.json")
TOP_K = 3
HTTP_TIMEOUT = 30

FEE_SCHEDULE = {
    "payment": (0.029, 30),  # 2.9% + 30 cents, card-payment-style
    "payout": (0.0, 0),      # no fee on payouts in this fictional schedule
}

_chunks_cache = None
_chunk_vecs_cache = None


def _db_conn():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)


def _embed(text: str):
    resp = requests.post(EMBEDDING_URL, json={"inputs": text}, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    vec = data[0] if isinstance(data[0], list) else data
    arr = np.array(vec, dtype=np.float32)
    norm = np.linalg.norm(arr)
    return arr / norm if norm > 0 else arr


def _load_chunks():
    global _chunks_cache, _chunk_vecs_cache
    if _chunks_cache is None:
        with open(CHUNKS_FILE, encoding="utf-8") as f:
            _chunks_cache = json.load(f)
        _chunk_vecs_cache = [_embed(c["chunk_text"]) for c in _chunks_cache]
    return _chunks_cache, _chunk_vecs_cache


def rag_lookup(question: str) -> str:
    chunks, vecs = _load_chunks()
    qvec = _embed(question)
    scored = sorted(
        ((float(np.dot(qvec, v)), i) for i, v in enumerate(vecs)),
        reverse=True,
    )[:TOP_K]
    passages = [f"(source: {chunks[i]['source_file']}) {chunks[i]['chunk_text']}" for _, i in scored]
    return json.dumps({"passages": passages}, ensure_ascii=False)


def check_transaction_status(transaction_id: str) -> str:
    conn = _db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT status, transaction_type, amount_cents, currency, customer_email, created_at, fee_cents "
        "FROM mock_transactions WHERE id = %s",
        (transaction_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        return json.dumps({"error": f"no transaction found with id {transaction_id}"})
    status, ttype, amount_cents, currency, email, created_at, fee_cents = row
    return json.dumps({
        "id": transaction_id,
        "status": status,
        "transaction_type": ttype,
        "amount": round(amount_cents / 100, 2),
        "currency": currency,
        "customer_email": email,
        "created_at": str(created_at),
        "fee": round(fee_cents / 100, 2),
    })


def initiate_refund(transaction_id: str, amount: float) -> str:
    conn = _db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT status, amount_cents, currency, transaction_type FROM mock_transactions WHERE id = %s",
        (transaction_id,),
    )
    row = cur.fetchone()
    if row is None:
        cur.close(); conn.close()
        return json.dumps({"error": f"no transaction found with id {transaction_id}"})
    status, amount_cents, currency, ttype = row
    if ttype != "payment":
        cur.close(); conn.close()
        return json.dumps({"error": f"transaction {transaction_id} is a '{ttype}', not a payment — cannot refund"})
    if status != "succeeded":
        cur.close(); conn.close()
        return json.dumps({"error": f"transaction {transaction_id} has status '{status}', cannot refund"})
    # mock_disputes only exists when the extended tool catalogue's schema is loaded — the base
    # 5-tool world has no concept of disputes, so skip the check there instead of erroring.
    cur.execute("SELECT to_regclass('public.mock_disputes')")
    if cur.fetchone()[0] is not None:
        cur.execute(
            "SELECT id FROM mock_disputes WHERE transaction_id = %s AND status IN ('needs_response', 'under_review')",
            (transaction_id,),
        )
        dispute_row = cur.fetchone()
        if dispute_row is not None:
            cur.close(); conn.close()
            return json.dumps({
                "error": f"transaction {transaction_id} has an open dispute ({dispute_row[0]}) — refunding on top "
                         "of an active chargeback would pay the customer twice. Use get_dispute to review it first."
            })
    requested_cents = round(amount * 100)
    if requested_cents > amount_cents:
        cur.close(); conn.close()
        return json.dumps({"error": f"refund amount {amount} exceeds original amount {amount_cents / 100}"})
    cur.execute("UPDATE mock_transactions SET status = 'refunded' WHERE id = %s", (transaction_id,))
    conn.commit()
    cur.close()
    conn.close()
    return json.dumps({
        "id": transaction_id,
        "refunded_amount": amount,
        "currency": currency,
        "new_status": "refunded",
        "note": "SIMULATED — no real payment processor involved",
    })


def get_exchange_rate(base_currency: str, target_currency: str) -> str:
    try:
        resp = requests.get(
            "https://api.frankfurter.app/latest",
            params={"from": base_currency.upper(), "to": target_currency.upper()},
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        rate = data["rates"].get(target_currency.upper())
        if rate is None:
            return json.dumps({"error": f"no rate available for {base_currency}->{target_currency}"})
        return json.dumps({
            "base": base_currency.upper(),
            "target": target_currency.upper(),
            "rate": rate,
            "date": data.get("date"),
            "source": "Frankfurter (ECB reference rates)",
        })
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def calculate_fees(amount: float, transaction_type: str) -> str:
    if transaction_type not in FEE_SCHEDULE:
        return json.dumps({"error": f"unknown transaction_type '{transaction_type}', expected one of {list(FEE_SCHEDULE)}"})
    pct, fixed_cents = FEE_SCHEDULE[transaction_type]
    fee = round(amount * pct + fixed_cents / 100, 2)
    return json.dumps({
        "amount": amount,
        "transaction_type": transaction_type,
        "fee": fee,
        "net_amount": round(amount - fee, 2),
        "formula": f"{pct*100:.1f}% + ${fixed_cents/100:.2f}" if transaction_type == "payment" else "no fee",
    })


TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "rag_lookup",
            "description": "Search the NexusPay API documentation (reference docs + guides) for policy, "
                            "how-to, and conceptual information. Use for questions not about a specific transaction.",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string", "description": "The question to search for"}},
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_transaction_status",
            "description": "Look up a specific transaction's status, amount, currency, and fee by its ID.",
            "parameters": {
                "type": "object",
                "properties": {"transaction_id": {"type": "string", "description": "e.g. 'TX-4521'"}},
                "required": ["transaction_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "initiate_refund",
            "description": "Refund a succeeded transaction, fully or partially. This changes the transaction's "
                            "status — only call it when the user has actually asked for a refund to happen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "string"},
                    "amount": {"type": "number", "description": "Amount to refund, in the transaction's currency major units (e.g. 50.00)"},
                },
                "required": ["transaction_id", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rate",
            "description": "Get the current exchange rate between two ISO currency codes (e.g. USD, EUR, GBP).",
            "parameters": {
                "type": "object",
                "properties": {
                    "base_currency": {"type": "string"},
                    "target_currency": {"type": "string"},
                },
                "required": ["base_currency", "target_currency"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_fees",
            "description": "Calculate the processing fee and net amount for a given amount and transaction_type "
                            "('payment' or 'payout').",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number"},
                    "transaction_type": {"type": "string", "enum": ["payment", "payout"]},
                },
                "required": ["amount", "transaction_type"],
            },
        },
    },
]

DISPATCH = {
    "rag_lookup": lambda args: rag_lookup(args["question"]),
    "check_transaction_status": lambda args: check_transaction_status(args["transaction_id"]),
    "initiate_refund": lambda args: initiate_refund(args["transaction_id"], args["amount"]),
    "get_exchange_rate": lambda args: get_exchange_rate(args["base_currency"], args["target_currency"]),
    "calculate_fees": lambda args: calculate_fees(args["amount"], args["transaction_type"]),
}


def execute_tool(name: str, arguments: dict) -> str:
    if name not in DISPATCH:
        return json.dumps({"error": f"unknown tool '{name}'"})
    try:
        return DISPATCH[name](arguments)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
