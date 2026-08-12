# Webhooks Guide

Webhooks allow NexusPay to push real-time event notifications to your server when something happens in your account — a payment succeeds, a subscription renews, a dispute is opened, and so on. This guide explains how to receive, verify, and handle webhook events reliably.

## Overview

When an event occurs, NexusPay sends an HTTP POST request to the URL you have configured in the Dashboard or via the Webhooks API. Your endpoint must respond with an HTTP `200` status code within 10 seconds to acknowledge delivery. If it does not, NexusPay retries delivery up to **5 times** using an exponential backoff schedule: 1 minute, 5 minutes, 30 minutes, 2 hours, and 8 hours after the initial attempt.

## Configuring a Webhook Endpoint

Webhook endpoint URLs have a maximum length of **2048 characters**. Register your endpoint in the Dashboard under **Developers → Webhooks**, or via the API:

```json
POST /webhooks
{
  "url": "https://your-app.example.com/webhooks/nexuspay",
  "events": ["payment.succeeded", "payment.failed", "dispute.created"]
}
```

**Response:**
```json
{
  "id": "wh_01HXYZ1234567890",
  "url": "https://your-app.example.com/webhooks/nexuspay",
  "events": ["payment.succeeded", "payment.failed", "dispute.created"],
  "secret": "whsec_abcdef1234567890abcdef1234567890",
  "created_at": "2025-06-01T12:00:00Z"
}
```

Store the `secret` securely — you will use it to verify every incoming webhook request.

## Webhook Event Payload

Every webhook POST body is a JSON object with a consistent envelope structure:

```json
{
  "id": "evt_01HXYZ9876543210",
  "type": "payment.succeeded",
  "created_at": "2025-06-01T12:05:00Z",
  "data": {
    "id": "pay_01HABC1234567890",
    "amount": 4999,
    "currency": "EUR",
    "status": "succeeded"
  }
}
```

## Verifying Webhook Signatures

NexusPay signs every webhook request using **HMAC-SHA256** with your webhook secret. Always verify the signature before processing the payload. Failing to do so exposes your endpoint to spoofed events.

### Signature Header Format

Two headers are included with every webhook request:

| Header | Description |
|--------|-------------|
| `X-NexusPay-Signature` | HMAC-SHA256 hex digest of the raw request body |
| `X-NexusPay-Timestamp` | Unix timestamp (seconds) of when the event was sent |

### Verification Steps

1. Extract the `X-NexusPay-Timestamp` and `X-NexusPay-Signature` header values.
2. Construct the signed payload string: `{timestamp}.{raw_body}`.
3. Compute the HMAC-SHA256 of that string using your webhook secret.
4. Compare your computed digest to `X-NexusPay-Signature` using a constant-time comparison function.

**Python example:**

```python
import hmac
import hashlib
import time

def verify_webhook(raw_body: bytes, timestamp: str, signature: str, secret: str) -> bool:
    signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
    expected = hmac.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

**Node.js example:**

```javascript
const crypto = require("crypto");

function verifyWebhook(rawBody, timestamp, signature, secret) {
  const signedPayload = `${timestamp}.${rawBody}`;
  const expected = crypto
    .createHmac("sha256", secret)
    .update(signedPayload)
    .digest("hex");
  return crypto.timingSafeEqual(
    Buffer.from(expected),
    Buffer.from(signature)
  );
}
```

## Replay Attack Prevention

Even a valid signature can be replayed by a malicious actor. To prevent this, **reject any webhook whose `X-NexusPay-Timestamp` is more than 5 minutes old** relative to your server's current time.

```python
MAX_TIMESTAMP_AGE_SECONDS = 300  # 5 minutes

def is_timestamp_valid(timestamp: str) -> bool:
    event_time = int(timestamp)
    current_time = int(time.time())
    return abs(current_time - event_time) <= MAX_TIMESTAMP_AGE_SECONDS
```

Always check the timestamp **before** performing the HMAC comparison to fail fast on stale requests.

## Writing Idempotent Webhook Handlers

NexusPay may deliver the same event more than once — for example, if your server returned a non-200 response due to a transient error. Your handler must be **idempotent**: processing the same event twice should produce the same outcome as processing it once.

Recommended pattern:

1. Extract the event `id` from the payload.
2. Check your database for a record of that `id`.
3. If already processed, return HTTP `200` immediately without re-executing business logic.
4. Otherwise, process the event and persist the `id` before returning.

```python
def handle_webhook(event: dict):
    event_id = event["id"]

    if db.webhook_events.exists(event_id):
        return 200  # already handled — acknowledge and skip

    with db.transaction():
        process_event(event)
        db.webhook_events.insert(event_id, processed_at=now())

    return 200
```

## Responding to Webhooks

Your endpoint must return an HTTP `200` status code to acknowledge successful receipt. Any other status code (including `201`, `202`, `4xx`, or `5xx`) causes NexusPay to treat the delivery as failed and schedule a retry.

Do not perform slow operations (database writes, third-party API calls) synchronously in the webhook handler path. Instead, enqueue the event in an internal job queue and return `200` immediately.

## Supported Event Types

Refer to `docs/reference/endpoints.md` for the full list of available event types and their payload schemas.
