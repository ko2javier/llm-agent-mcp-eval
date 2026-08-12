# Idempotency Guide

Idempotency is a property of an operation whereby performing it multiple times produces the same result as performing it once. In payments, this is critical: without idempotency, a network timeout could cause your server to retry a request and accidentally charge the customer twice.

## Why Idempotency Matters in Payments

Consider this scenario:

1. Your server sends `POST /payments` with a €49.99 charge.
2. NexusPay processes the payment successfully.
3. The network connection drops before NexusPay's response reaches your server.
4. Your server, receiving no response, retries the request.
5. Without idempotency, NexusPay creates a second payment — the customer is charged twice.

With an idempotency key, step 4 returns the original payment object and no second charge occurs.

## How to Use Idempotency Keys

Include the `Idempotency-Key` header in any mutating request (POST, PATCH, DELETE):

```http
POST /payments
Authorization: Bearer sk_live_your_secret_key
Content-Type: application/json
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000

{
  "amount": 4999,
  "currency": "EUR",
  "source": "tok_01HABC1234567890"
}
```

If NexusPay has already seen this key for the same API key, it returns the cached response from the original request — including the same HTTP status code — without executing the operation again.

## Generating Good Idempotency Keys

**Use UUID v4** for idempotency keys. UUID v4 is randomly generated and provides sufficient entropy to be globally unique without coordination:

```python
import uuid

idempotency_key = str(uuid.uuid4())
# e.g., "550e8400-e29b-41d4-a716-446655440000"
```

```javascript
import { v4 as uuidv4 } from "uuid";

const idempotencyKey = uuidv4();
// e.g., "550e8400-e29b-41d4-a716-446655440000"
```

**Key constraints:**

| Property | Value |
|----------|-------|
| Maximum length | **64 characters** |
| Expiration | **24 hours** after first use |
| Scope | Per API key (same key on a different API key is independent) |

Idempotency keys expire **24 hours** after they are first used. After expiry, the same key can be submitted again and will be treated as a new request. This means you should generate a fresh key for each distinct operation intent — do not reuse keys across sessions or days.

## Key Generation Strategies

### Per-Operation Intent

Generate a key each time you *intend* to perform an operation. Store the key alongside the pending operation record in your database so you can retrieve it during retries.

```python
# When creating a payment intent
pending_payment = db.create_pending_payment(
    order_id=order_id,
    idempotency_key=str(uuid.uuid4())
)

# When retrying (use the same key)
response = nexuspay.payments.create(
    amount=4999,
    currency="EUR",
    source=token_id,
    idempotency_key=pending_payment.idempotency_key
)
```

### Derived Keys

For deterministic operations where the same business event should always map to the same API call, you may derive the key from a stable business identifier:

```python
import hashlib

def make_idempotency_key(prefix: str, entity_id: str) -> str:
    raw = f"{prefix}:{entity_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]

key = make_idempotency_key("subscription-renewal", "sub_01HXYZ4444444444:2025-07")
```

Use this pattern carefully — only when the same business event should *always* result in the same API call and never be retried with different parameters.

## Key Scoping

Idempotency keys are scoped to your **API key**. The same key used with your test (`sk_test_...`) and live (`sk_live_...`) secret keys are completely independent — switching to live keys does not risk replaying test-mode idempotency records.

## The `idempotency_key_mismatch` Error

If you submit a request with an idempotency key that was previously used for a **different set of request parameters**, NexusPay returns a `409 Conflict` error:

```json
HTTP/1.1 409 Conflict

{
  "error": {
    "code": "idempotency_key_mismatch",
    "message": "This idempotency key was previously used with different request parameters. Generate a new key."
  }
}
```

This error is **non-retryable**. Generate a fresh UUID and resubmit. Do not attempt to "fix" the parameters to match — the cached result is already immutable for this key.

## When to Include an Idempotency Key

| Endpoint | Use idempotency key? |
|----------|---------------------|
| `POST /payments` | **Yes — always** |
| `POST /payments/:id/capture` | **Yes** |
| `POST /payments/:id/refunds` | **Yes — always** |
| `POST /customers` | Recommended |
| `POST /subscriptions` | Recommended |
| `GET /payments` | No (reads are always idempotent) |
| `GET /payments/:id` | No |

Read-only requests (GET) are inherently idempotent and do not require a key.

## Relationship to Retry Logic

Idempotency keys and retry logic work together. Always:

1. Generate the idempotency key **before** making the request.
2. Store the key **before** sending the request (in case your process crashes mid-flight).
3. Reuse the same key on every retry attempt for the same operation.
4. Only generate a new key when you are intentionally starting a new operation.

For guidance on retry strategies and backoff, see `docs/guides/error_handling_guide.md`.
