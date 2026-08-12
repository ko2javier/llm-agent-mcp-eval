# Architecture Overview

NexusPay is a payment processing API designed for European businesses. It handles the full payment lifecycle: authorization, capture, settlement, refunds, and recurring billing through subscriptions.

## Core Design Principles

**Idempotency first.** Every write operation accepts an `idempotency_key` parameter. If the same key is submitted twice, the second request returns the result of the first without creating a duplicate. This is critical for payment systems where network failures can cause retries.

**Eventual consistency for webhooks.** Webhook delivery is asynchronous. After a payment succeeds, the `payment.succeeded` event may arrive at your endpoint within milliseconds or up to 30 seconds later, depending on load. Never rely on webhooks as the primary source of truth — always confirm payment status via the API.

**Separation of authorization and capture.** By default, `POST /payments` both authorizes and captures in a single step. For marketplaces and delayed fulfillment, set `capture: false` to authorize only. The authorization holds funds on the customer's card for up to 7 days. After that, the authorization expires automatically.

## Authentication Model

NexusPay uses API keys for authentication. There are two types:

- **Secret keys** (`sk_live_...` or `sk_test_...`): Full access. Never expose in client-side code or public repositories.
- **Publishable keys** (`pk_live_...` or `pk_test_...`): Read-only, safe for frontend use. Can tokenize payment methods.

Each account has separate keys for live and sandbox environments. Sandbox transactions never move real money and are not subject to rate limits.

## Request Flow

```
Client → TLS 1.2+ → API Gateway → Auth middleware → Rate limiter → Business logic → Database
                                                                              ↓
                                                                     Webhook dispatcher
```

All API requests must use HTTPS. Plain HTTP connections are rejected with a connection error, not an HTTP response.

## Idempotency

Idempotency keys are strings up to 64 characters. They are scoped to your API key — the same idempotency key used with different API keys creates different operations.

Keys expire after **24 hours**. After expiration, the same key can be reused for a new operation.

If you submit an idempotency key that matches a previous request but with different parameters, the API returns HTTP 409 with error code `idempotency_key_mismatch`.

## Environments

| Environment | Base URL                        | Real money | Rate limits |
|-------------|---------------------------------|------------|-------------|
| Sandbox     | `https://api.nexuspay.io/v2`    | No         | None        |
| Live        | `https://api.nexuspay.io/v2`    | Yes        | Yes         |

Environment is determined by the API key, not the URL. Sandbox keys (`sk_test_...`) always route to the sandbox environment regardless of the endpoint used.

## Versioning

The API uses URL versioning. The current version is **v2**. Version v1 was deprecated on **2025-07-01** and will be sunset on **2026-01-15**. After the sunset date, v1 requests will return HTTP 410.

Breaking changes are only introduced in new major versions. Minor versions and patches are backward compatible and do not require URL changes.

## Data Residency

By default, all data is stored in the EU (Frankfurt, Germany). US data residency is available on Enterprise plans. Data residency cannot be changed after account creation.
