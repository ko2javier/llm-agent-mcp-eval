# Error Handling Guide

Robust error handling is essential for building reliable payment integrations. This guide covers how to classify errors, implement safe retry logic, handle rate limits, and structure your logging to aid incident response.

## Error Response Structure

All NexusPay API errors return a consistent JSON body alongside the appropriate HTTP status code:

```json
{
  "error": {
    "code": "card_declined",
    "message": "The card was declined by the issuer.",
    "decline_code": "insufficient_funds",
    "request_id": "req_01HXYZ9999999999"
  }
}
```

Always capture `error.code` in your application logic — it is the stable, machine-readable identifier for the error type. The `message` field is human-readable and may change. The `request_id` uniquely identifies the request and should be included in any support tickets.

## Retryable vs Non-Retryable Errors

The most important distinction is whether an error is safe to retry automatically.

### Non-Retryable Errors

These errors indicate a deterministic failure — retrying the same request will produce the same result and may cause harm (e.g., charging the customer twice or confusing them with repeated declines).

| HTTP Status | Error Code | Reason |
|-------------|------------|--------|
| 400 | `invalid_request` | Malformed request — fix the payload |
| 400 | `amount_too_small` | Below minimum — adjust the amount |
| 402 | `card_declined` | Issuer declined — prompt customer to use a different card |
| 402 | `expired_card` | Card expired — customer must update card details |
| 402 | `insufficient_funds` | Not enough funds — customer must resolve with their bank |
| 402 | `do_not_honor` | Issuer blocked the transaction — do not retry |
| 404 | `not_found` | Resource does not exist — check the ID |
| 409 | `idempotency_key_mismatch` | Key reused with different parameters — use a new key |

**Do not retry `card_declined` errors.** Repeated decline attempts may trigger fraud flags at the issuer and worsen the customer's experience. Instead, prompt the customer to try a different card or contact their bank.

### Retryable Errors

These errors are transient — the same request may succeed if retried after a short wait.

| HTTP Status | Error Code | Notes |
|-------------|------------|-------|
| 429 | `rate_limit_exceeded` | Respect the `retry_after` header |
| 500 | `internal_server_error` | NexusPay server error — safe to retry |
| 502 | `bad_gateway` | Upstream infrastructure error |
| 503 | `service_unavailable` | Temporary unavailability — retry with backoff |
| 504 | `gateway_timeout` | Request timed out upstream |

## Exponential Backoff Strategy

When retrying transient errors, use exponential backoff with jitter to avoid thundering-herd effects:

```python
import time
import random

def retry_with_backoff(fn, max_retries=4):
    for attempt in range(max_retries):
        try:
            return fn()
        except RetryableError as e:
            if attempt == max_retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(wait)
```

**Suggested backoff schedule:**

| Attempt | Base wait | With jitter |
|---------|-----------|-------------|
| 1 | 1 second | 1–2 seconds |
| 2 | 2 seconds | 2–3 seconds |
| 3 | 4 seconds | 4–5 seconds |
| 4 | 8 seconds | 8–9 seconds |

Always use an **idempotency key** on requests you intend to retry. This ensures that even if the original request succeeded and the response was lost in transit, retrying returns the original result rather than creating a duplicate. See `docs/guides/idempotency_guide.md`.

## Handling Rate Limit Errors (HTTP 429)

When you exceed the API rate limit, NexusPay returns HTTP `429` with a `retry_after` field indicating how many seconds to wait before retrying:

```json
HTTP/1.1 429 Too Many Requests
Retry-After: 4

{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Rate limit exceeded. Retry after 4 seconds.",
    "retry_after": 4
  }
}
```

**Always honour the `retry_after` value.** Do not retry before this interval. For sustained high-throughput workloads, refer to `docs/reference/rate_limits.md` for rate limit tiers and burst allowances.

```python
def call_with_rate_limit_handling(fn):
    response = fn()
    if response.status_code == 429:
        retry_after = response.json()["error"]["retry_after"]
        time.sleep(retry_after)
        return fn()
    return response
```

## Distinguishing Decline Scenarios

Not all `card_declined` errors are equivalent. Use `decline_code` to provide a specific message to the customer:

| `decline_code` | Customer-facing message |
|----------------|------------------------|
| `insufficient_funds` | "Your card has insufficient funds. Please try a different card." |
| `expired_card` | "Your card has expired. Please update your payment details." |
| `do_not_honor` | "Your bank declined this transaction. Please contact your bank or use a different card." |
| `lost_card` | "This transaction cannot be processed. Please contact your bank." |
| `stolen_card` | "This transaction cannot be processed. Please contact your bank." |

Never expose raw `decline_code` values directly to customers in error messages.

## Logging Strategy

Effective logging accelerates debugging without creating compliance risk.

**Always log:**
- `error.code`
- `error.request_id`
- HTTP status code
- Timestamp
- Endpoint and method
- Idempotency key (if used)

**Never log:**
- Full card numbers (PAN)
- CVC / CVV codes
- Full API secret keys
- Webhook secrets

```python
import logging

logger = logging.getLogger("nexuspay")

def log_api_error(response):
    error = response.json().get("error", {})
    logger.error(
        "NexusPay API error",
        extra={
            "status_code": response.status_code,
            "error_code": error.get("code"),
            "request_id": error.get("request_id"),
            "endpoint": response.request.path_url,
        }
    )
```

For the complete list of error codes, see `docs/reference/error_codes.md`.
