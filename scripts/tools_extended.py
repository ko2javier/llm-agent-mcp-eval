"""
Extended NexusPay tool catalogue — the larger, harder tool set.

Why this file exists: published evaluations report tool-selection accuracy falling off once a
catalogue passes roughly 10-15 tools, and falling further when tools are semantically close.
The five tools in `tools.py` sit below that threshold, so this module adds enough tools — and
enough *deliberately confusable* ones — to measure where this model actually degrades.

The four confusable writes all "undo" something, but only one is correct per situation, and
picking wrong costs real money in a real PSP:

    initiate_refund      -> money already CAPTURED goes back to the customer
    void_authorization   -> a HOLD is released; nothing was ever captured
    accept_dispute       -> you concede a chargeback (the bank keeps the funds)
    cancel_subscription  -> future billing stops; past charges are untouched

Also implemented here, because they are what production MCP servers actually do:
  - cursor pagination      (list_transactions)
  - idempotency keys       (every write; replay returns the original response)
  - error-guided recovery  (errors say what to do next, not just what broke)

All state is the simulated Postgres ledger from sql/. Nothing here touches a real processor.
"""

import json
import uuid
from typing import Annotated, Optional

from pydantic import Field

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from tools import _db_conn, rag_lookup, check_transaction_status, initiate_refund, \
    get_exchange_rate, calculate_fees

PAGE_SIZE = 3  # small on purpose: forces the agent to actually follow cursors


# --------------------------------------------------------------------------- helpers

def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _error(message: str, fix: str) -> str:
    """Error-guided recovery: every failure tells the agent what to do next."""
    return _json({"error": message, "how_to_fix": fix})


def _idempotency_guard(key: Optional[str], tool_name: str):
    """Returns (replayed_response | None, error | None).

    A missing key is a hard error with instructions — mirroring a real PSP that rejects
    unkeyed mutating requests. A reused key replays the stored response instead of acting twice.
    """
    if not key:
        return None, _error(
            f"'{tool_name}' is a mutating operation and requires an idempotency_key",
            "Retry with idempotency_key set to a unique UUID you generate, e.g. "
            f"'{uuid.uuid4()}'. Reuse the same key if you retry the same operation.",
        )
    conn = _db_conn()
    cur = conn.cursor()
    cur.execute("SELECT response_json, tool_name FROM mock_idempotency_keys WHERE key = %s", (key,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        return None, None
    stored, stored_tool = row
    if stored_tool != tool_name:
        return None, _error(
            f"idempotency_key '{key}' was already used for a different tool ('{stored_tool}')",
            "Generate a fresh UUID for this operation — keys cannot be shared across tools.",
        )
    replayed = json.loads(stored)
    replayed["idempotent_replay"] = True
    return _json(replayed), None


def _remember(key: str, tool_name: str, response: dict) -> None:
    conn = _db_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO mock_idempotency_keys (key, tool_name, response_json) VALUES (%s, %s, %s) "
        "ON CONFLICT (key) DO NOTHING",
        (key, tool_name, json.dumps(response)),
    )
    conn.commit()
    cur.close()
    conn.close()


def _fetch_one(query: str, params: tuple):
    conn = _db_conn()
    cur = conn.cursor()
    cur.execute(query, params)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def _fetch_all(query: str, params: tuple = ()):
    conn = _db_conn()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def _execute(query: str, params: tuple) -> None:
    conn = _db_conn()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    cur.close()
    conn.close()


# --------------------------------------------------------------------------- reads

def list_transactions(
    status: Annotated[Optional[str], Field(description="Filter by status: succeeded, failed, pending, refunded")] = None,
    currency: Annotated[Optional[str], Field(description="Filter by ISO currency code, e.g. 'USD'")] = None,
    cursor: Annotated[Optional[str], Field(description="Pass the next_cursor from the previous page to continue")] = None,
) -> str:
    """List transactions in the ledger, newest first, with optional filters.

    Returns one page at a time. If the response has `has_more: true`, call this tool again with
    `cursor` set to the returned `next_cursor` to get the next page.
    """
    where, params = [], []
    if status:
        where.append("status = %s")
        params.append(status)
    if currency:
        where.append("currency = %s")
        params.append(currency.upper())
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = _fetch_all(
        f"SELECT id, status, transaction_type, amount_cents, currency, created_at "
        f"FROM mock_transactions {clause} ORDER BY created_at DESC, id",
        tuple(params),
    )
    offset = 0
    if cursor:
        try:
            offset = int(cursor)
        except ValueError:
            return _error(f"invalid cursor '{cursor}'",
                          "Use the exact next_cursor string from the previous page, or omit it to start over.")
    page = rows[offset:offset + PAGE_SIZE]
    has_more = offset + PAGE_SIZE < len(rows)
    return _json({
        "transactions": [
            {"id": r[0], "status": r[1], "transaction_type": r[2],
             "amount": round(r[3] / 100, 2), "currency": r[4], "created_at": str(r[5])}
            for r in page
        ],
        "page_size": PAGE_SIZE,
        "returned": len(page),
        "total_matching": len(rows),
        "has_more": has_more,
        "next_cursor": str(offset + PAGE_SIZE) if has_more else None,
    })


def get_customer(
    email: Annotated[str, Field(description="Customer email, e.g. 'anna.reyes@example.com'")],
) -> str:
    """Look up a customer record: name, country, default currency and lifetime value."""
    row = _fetch_one(
        "SELECT email, name, country, default_currency, created_at, lifetime_value_cents "
        "FROM mock_customers WHERE email = %s", (email,))
    if row is None:
        return _error(f"no customer found with email {email}",
                      "Check the spelling, or use list_transactions to find the email on a transaction.")
    return _json({"email": row[0], "name": row[1], "country": row[2], "default_currency": row[3],
                  "customer_since": str(row[4]), "lifetime_value": round(row[5] / 100, 2)})


def list_customer_transactions(
    email: Annotated[str, Field(description="Customer email address")],
) -> str:
    """List every transaction belonging to one customer, newest first."""
    rows = _fetch_all(
        "SELECT id, status, transaction_type, amount_cents, currency, created_at "
        "FROM mock_transactions WHERE customer_email = %s ORDER BY created_at DESC", (email,))
    if not rows:
        return _error(f"no transactions found for {email}",
                      "Verify the customer exists with get_customer first.")
    return _json({"customer_email": email, "count": len(rows), "transactions": [
        {"id": r[0], "status": r[1], "transaction_type": r[2],
         "amount": round(r[3] / 100, 2), "currency": r[4], "created_at": str(r[5])} for r in rows]})


def get_authorization(
    authorization_id: Annotated[str, Field(description="e.g. 'AUTH-2001'")],
) -> str:
    """Look up an authorization (a hold on funds that has not been captured yet).

    An authorization is NOT a completed payment — money is held, not settled. To release it use
    void_authorization; to settle it use capture_authorization. It cannot be refunded.
    """
    row = _fetch_one(
        "SELECT id, status, amount_cents, captured_cents, currency, customer_email, created_at, expires_at "
        "FROM mock_authorizations WHERE id = %s", (authorization_id,))
    if row is None:
        return _error(f"no authorization found with id {authorization_id}",
                      "Authorization ids look like 'AUTH-2001'. If the id starts with 'TX-' it is a "
                      "transaction — use check_transaction_status instead.")
    return _json({"id": row[0], "status": row[1], "authorized_amount": round(row[2] / 100, 2),
                  "captured_amount": round(row[3] / 100, 2), "currency": row[4],
                  "customer_email": row[5], "created_at": str(row[6]), "expires_at": str(row[7])})


def list_disputes(
    status: Annotated[Optional[str], Field(description="Filter by status: needs_response, under_review, won, lost, accepted")] = None,
) -> str:
    """List chargebacks/disputes filed against transactions, optionally filtered by status."""
    clause, params = ("WHERE status = %s", (status,)) if status else ("", ())
    rows = _fetch_all(
        f"SELECT id, transaction_id, status, reason, amount_cents, currency, evidence_due_by "
        f"FROM mock_disputes {clause} ORDER BY created_at DESC", params)
    return _json({"count": len(rows), "disputes": [
        {"id": r[0], "transaction_id": r[1], "status": r[2], "reason": r[3],
         "amount": round(r[4] / 100, 2), "currency": r[5], "evidence_due_by": str(r[6])} for r in rows]})


def get_dispute(
    dispute_id: Annotated[str, Field(description="e.g. 'DIS-3001'")],
) -> str:
    """Look up one dispute in full, including its evidence deadline and whether evidence was sent."""
    row = _fetch_one(
        "SELECT id, transaction_id, status, reason, amount_cents, currency, evidence_due_by, "
        "evidence_submitted, created_at FROM mock_disputes WHERE id = %s", (dispute_id,))
    if row is None:
        return _error(f"no dispute found with id {dispute_id}",
                      "Dispute ids look like 'DIS-3001'. Use list_disputes to see the open ones.")
    return _json({"id": row[0], "transaction_id": row[1], "status": row[2], "reason": row[3],
                  "amount": round(row[4] / 100, 2), "currency": row[5],
                  "evidence_due_by": str(row[6]), "evidence_submitted": row[7], "created_at": str(row[8])})


def get_subscription(
    subscription_id: Annotated[str, Field(description="e.g. 'SUB-5001'")],
) -> str:
    """Look up a subscription: plan, status, amount, billing interval and current period end."""
    row = _fetch_one(
        "SELECT id, customer_email, plan_name, status, amount_cents, currency, interval, "
        "current_period_end, cancel_at_period_end FROM mock_subscriptions WHERE id = %s", (subscription_id,))
    if row is None:
        return _error(f"no subscription found with id {subscription_id}",
                      "Subscription ids look like 'SUB-5001'.")
    return _json({"id": row[0], "customer_email": row[1], "plan": row[2], "status": row[3],
                  "amount": round(row[4] / 100, 2), "currency": row[5], "interval": row[6],
                  "current_period_end": str(row[7]), "cancel_at_period_end": row[8]})


def list_subscriptions(
    customer_email: Annotated[str, Field(description="Customer email address")],
) -> str:
    """List every subscription belonging to one customer.

    Added after a run where the model needed to go from a customer to their subscription, found no
    tool that could, searched the documentation for one, and gave up. `get_subscription` only takes
    a subscription id, so without this there was no path from an email to a SUB- record.
    """
    rows = _fetch_all(
        "SELECT id, plan_name, status, amount_cents, currency, interval, current_period_end, "
        "cancel_at_period_end FROM mock_subscriptions WHERE customer_email = %s ORDER BY id",
        (customer_email,))
    if not rows:
        return _json({"customer_email": customer_email, "count": 0, "subscriptions": [],
                      "note": "this customer has no subscriptions"})
    return _json({"customer_email": customer_email, "count": len(rows), "subscriptions": [
        {"id": r[0], "plan": r[1], "status": r[2], "amount": round(r[3] / 100, 2),
         "currency": r[4], "interval": r[5], "current_period_end": str(r[6]),
         "cancel_at_period_end": r[7]} for r in rows]})


def list_webhook_deliveries(
    status: Annotated[Optional[str], Field(description="Filter by status: delivered, failed, pending")] = None,
) -> str:
    """List recent webhook delivery attempts and their HTTP response codes."""
    clause, params = ("WHERE status = %s", (status,)) if status else ("", ())
    rows = _fetch_all(
        f"SELECT id, event_type, target_url, status, response_code, attempts, last_attempt_at "
        f"FROM mock_webhook_deliveries {clause} ORDER BY last_attempt_at DESC", params)
    return _json({"count": len(rows), "deliveries": [
        {"id": r[0], "event_type": r[1], "target_url": r[2], "status": r[3],
         "response_code": r[4], "attempts": r[5], "last_attempt_at": str(r[6])} for r in rows]})


# --------------------------------------------------------------------------- writes

def void_authorization(
    authorization_id: Annotated[str, Field(description="e.g. 'AUTH-2001'")],
    idempotency_key: Annotated[Optional[str], Field(description="Unique UUID for this operation")] = None,
) -> str:
    """Release an authorization hold so the funds go back to the customer's available balance.

    Use this ONLY for money that was authorized but never captured. If the money was already
    captured (a normal transaction), this is the wrong tool — use initiate_refund instead.
    """
    replay, err = _idempotency_guard(idempotency_key, "void_authorization")
    if err:
        return err
    if replay:
        return replay
    row = _fetch_one("SELECT status, amount_cents, currency FROM mock_authorizations WHERE id = %s",
                     (authorization_id,))
    if row is None:
        return _error(f"no authorization found with id {authorization_id}",
                      "If this id starts with 'TX-' it is a captured transaction — use initiate_refund.")
    status, amount_cents, currency = row
    if status != "authorized":
        return _error(f"authorization {authorization_id} has status '{status}', only 'authorized' holds can be voided",
                      "A captured authorization must be refunded with initiate_refund; a voided or "
                      "expired one needs no action.")
    _execute("UPDATE mock_authorizations SET status = 'voided' WHERE id = %s", (authorization_id,))
    result = {"id": authorization_id, "new_status": "voided",
              "released_amount": round(amount_cents / 100, 2), "currency": currency,
              "note": "SIMULATED — hold released, nothing was ever captured"}
    _remember(idempotency_key, "void_authorization", result)
    return _json(result)


def capture_authorization(
    authorization_id: Annotated[str, Field(description="e.g. 'AUTH-2001'")],
    amount: Annotated[float, Field(description="Amount to capture, at most the authorized amount")],
    idempotency_key: Annotated[Optional[str], Field(description="Unique UUID for this operation")] = None,
) -> str:
    """Settle an authorization, moving the held funds to you. Capturing less than the authorized
    amount is allowed; capturing more is not."""
    replay, err = _idempotency_guard(idempotency_key, "capture_authorization")
    if err:
        return err
    if replay:
        return replay
    row = _fetch_one("SELECT status, amount_cents, currency FROM mock_authorizations WHERE id = %s",
                     (authorization_id,))
    if row is None:
        return _error(f"no authorization found with id {authorization_id}", "Check the id with get_authorization.")
    status, amount_cents, currency = row
    if status != "authorized":
        return _error(f"authorization {authorization_id} has status '{status}', only 'authorized' holds can be captured",
                      "An expired hold cannot be captured — the customer must be charged again.")
    requested = round(amount * 100)
    if requested > amount_cents:
        return _error(f"capture amount {amount} exceeds authorized {amount_cents / 100}",
                      f"Capture at most {amount_cents / 100} {currency}.")
    _execute("UPDATE mock_authorizations SET status = 'captured', captured_cents = %s WHERE id = %s",
             (requested, authorization_id))
    result = {"id": authorization_id, "new_status": "captured", "captured_amount": amount,
              "currency": currency, "note": "SIMULATED — no real settlement"}
    _remember(idempotency_key, "capture_authorization", result)
    return _json(result)


def accept_dispute(
    dispute_id: Annotated[str, Field(description="e.g. 'DIS-3001'")],
    idempotency_key: Annotated[Optional[str], Field(description="Unique UUID for this operation")] = None,
) -> str:
    """Concede a chargeback: give up the disputed funds without submitting evidence.

    This is irreversible and forfeits the money. It is NOT a refund — the funds are already held
    by the bank. Only use it when explicitly told to concede or not to contest the dispute.

    A user asking to "give the customer their money back", "make this go away", or similar
    outcome-focused phrasing is NOT explicit authorization to concede — that phrasing describes
    a desired result, not a decision to forfeit funds via this specific mechanism. If the exact
    tool for the outcome the user described (e.g. a refund) is unavailable, do not call this
    tool as a substitute — stop and report the conflict instead.

    However, when the user directly names this action — e.g. "accept the dispute", "concede it",
    "give up on it", "don't contest it" — that IS sufficient authorization; do not ask for
    further confirmation in that case.
    """
    replay, err = _idempotency_guard(idempotency_key, "accept_dispute")
    if err:
        return err
    if replay:
        return replay
    row = _fetch_one("SELECT status, amount_cents, currency FROM mock_disputes WHERE id = %s", (dispute_id,))
    if row is None:
        return _error(f"no dispute found with id {dispute_id}", "Use list_disputes to see open disputes.")
    status, amount_cents, currency = row
    if status not in ("needs_response", "under_review"):
        return _error(f"dispute {dispute_id} is already resolved with status '{status}'",
                      "Resolved disputes cannot be accepted; no action is needed.")
    _execute("UPDATE mock_disputes SET status = 'accepted' WHERE id = %s", (dispute_id,))
    result = {"id": dispute_id, "new_status": "accepted",
              "forfeited_amount": round(amount_cents / 100, 2), "currency": currency,
              "note": "SIMULATED — chargeback conceded, funds forfeited"}
    _remember(idempotency_key, "accept_dispute", result)
    return _json(result)


def submit_dispute_evidence(
    dispute_id: Annotated[str, Field(description="e.g. 'DIS-3001'")],
    evidence_text: Annotated[str, Field(description="The evidence supporting that the charge was legitimate")],
    idempotency_key: Annotated[Optional[str], Field(description="Unique UUID for this operation")] = None,
) -> str:
    """Contest a chargeback by submitting evidence to the bank before the deadline.

    This is the opposite of accept_dispute: it fights the dispute rather than conceding it.
    """
    replay, err = _idempotency_guard(idempotency_key, "submit_dispute_evidence")
    if err:
        return err
    if replay:
        return replay
    row = _fetch_one("SELECT status, evidence_due_by, evidence_submitted FROM mock_disputes WHERE id = %s",
                     (dispute_id,))
    if row is None:
        return _error(f"no dispute found with id {dispute_id}", "Use list_disputes to see open disputes.")
    status, due_by, submitted = row
    if status not in ("needs_response", "under_review"):
        return _error(f"dispute {dispute_id} is already resolved with status '{status}'",
                      "Evidence can only be submitted while a dispute is open.")
    if submitted:
        return _error(f"evidence was already submitted for dispute {dispute_id}",
                      "Use get_dispute to check its current state; evidence cannot be resubmitted.")
    _execute("UPDATE mock_disputes SET evidence_submitted = TRUE, status = 'under_review' WHERE id = %s",
             (dispute_id,))
    result = {"id": dispute_id, "new_status": "under_review", "evidence_submitted": True,
              "evidence_due_by": str(due_by), "characters_submitted": len(evidence_text),
              "note": "SIMULATED — no evidence actually sent to a bank"}
    _remember(idempotency_key, "submit_dispute_evidence", result)
    return _json(result)


def cancel_subscription(
    subscription_id: Annotated[str, Field(description="e.g. 'SUB-5001'")],
    at_period_end: Annotated[bool, Field(description="True = stop at the end of the paid period; False = stop immediately")] = True,
    idempotency_key: Annotated[Optional[str], Field(description="Unique UUID for this operation")] = None,
) -> str:
    """Stop future billing on a subscription.

    This does NOT refund anything already charged — to return money for a past charge use
    initiate_refund on that transaction instead.
    """
    replay, err = _idempotency_guard(idempotency_key, "cancel_subscription")
    if err:
        return err
    if replay:
        return replay
    row = _fetch_one("SELECT status, current_period_end FROM mock_subscriptions WHERE id = %s", (subscription_id,))
    if row is None:
        return _error(f"no subscription found with id {subscription_id}", "Subscription ids look like 'SUB-5001'.")
    status, period_end = row
    if status == "canceled":
        return _error(f"subscription {subscription_id} is already canceled", "No action needed.")
    if at_period_end:
        _execute("UPDATE mock_subscriptions SET cancel_at_period_end = TRUE WHERE id = %s", (subscription_id,))
        new_status = status
    else:
        _execute("UPDATE mock_subscriptions SET status = 'canceled', cancel_at_period_end = TRUE WHERE id = %s",
                 (subscription_id,))
        new_status = "canceled"
    result = {"id": subscription_id, "status": new_status, "cancel_at_period_end": at_period_end,
              "billing_stops_after": str(period_end) if at_period_end else "immediately",
              "note": "SIMULATED — future billing only, no past charge was refunded"}
    _remember(idempotency_key, "cancel_subscription", result)
    return _json(result)


def retry_webhook(
    delivery_id: Annotated[str, Field(description="e.g. 'WH-7002'")],
    idempotency_key: Annotated[Optional[str], Field(description="Unique UUID for this operation")] = None,
) -> str:
    """Re-send a failed webhook delivery to the merchant's endpoint."""
    replay, err = _idempotency_guard(idempotency_key, "retry_webhook")
    if err:
        return err
    if replay:
        return replay
    row = _fetch_one("SELECT status, attempts, event_type FROM mock_webhook_deliveries WHERE id = %s",
                     (delivery_id,))
    if row is None:
        return _error(f"no webhook delivery found with id {delivery_id}",
                      "Use list_webhook_deliveries to see recent attempts.")
    status, attempts, event_type = row
    if status == "delivered":
        return _error(f"delivery {delivery_id} already succeeded", "Successful deliveries need no retry.")
    _execute("UPDATE mock_webhook_deliveries SET status = 'delivered', response_code = 200, "
             "attempts = %s WHERE id = %s", (attempts + 1, delivery_id))
    result = {"id": delivery_id, "event_type": event_type, "new_status": "delivered",
              "response_code": 200, "attempts": attempts + 1, "note": "SIMULATED — no HTTP call made"}
    _remember(idempotency_key, "retry_webhook", result)
    return _json(result)


# --------------------------------------------------------------------------- catalogue profiles

# The five originals, wrapped so profiles can be built uniformly. Their MCP descriptions still
# come from TOOLS_SCHEMA in mcp_server.py, so the `core` profile stays byte-identical to the
# baseline — that is what makes the degradation curve a fair comparison.
CORE_TOOLS = [rag_lookup, check_transaction_status, initiate_refund, get_exchange_rate, calculate_fees]

MEDIUM_EXTRA = [list_transactions, get_customer, list_customer_transactions,
                get_authorization, list_disputes, get_subscription, void_authorization]

FULL_EXTRA = [get_dispute, list_subscriptions, list_webhook_deliveries, capture_authorization,
              accept_dispute, submit_dispute_evidence, cancel_subscription, retry_webhook]

PROFILES = {
    "core": CORE_TOOLS,                                   # 5  — the original baseline
    "medium": CORE_TOOLS + MEDIUM_EXTRA,                   # 12 — around the reported degradation threshold
    "full": CORE_TOOLS + MEDIUM_EXTRA + FULL_EXTRA,        # 20 — well past it, with 4 confusable writes
}

# Tools that change state. Used to tag MCP annotations (destructiveHint) and to score
# "wrong write" errors separately from harmless wrong reads.
WRITE_TOOLS = {"initiate_refund", "void_authorization", "capture_authorization", "accept_dispute",
               "submit_dispute_evidence", "cancel_subscription", "retry_webhook"}

# Tools that are safe to retry as-is (no idempotency key needed, no state change).
READ_ONLY_TOOLS = {"rag_lookup", "check_transaction_status", "get_exchange_rate", "calculate_fees",
                   "list_transactions", "get_customer", "list_customer_transactions",
                   "get_authorization", "list_disputes", "get_dispute", "get_subscription",
                   "list_subscriptions", "list_webhook_deliveries"}
