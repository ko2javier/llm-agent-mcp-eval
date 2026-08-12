# Going Live Checklist

Before switching your NexusPay integration from sandbox to production, complete every item on this checklist. Skipping steps is a common source of production incidents.

## 1. API Keys

- [ ] **Switch to live API keys**: Replace all references to `sk_test_...` and `pk_test_...` with your live keys (`sk_live_...` / `pk_live_...`). Test and live keys must never be mixed within a single request.
- [ ] **Store keys securely**: Live secret keys must be stored in environment variables or a secrets manager — never in source code or configuration files committed to version control. See `docs/guides/security_guide.md`.
- [ ] **Remove test keys from production**: Verify that no test-prefixed key appears anywhere in your production configuration.

## 2. API Versioning

- [ ] **Target API v2**: Confirm all requests include the `NexusPay-Version: 2025-01-15` header or use the v2 base URL. The v1 API is deprecated as of 2025-07-01 and sunsets on 2026-01-15. Requests to v1 after sunset return HTTP `410 Gone`. See `docs/guides/api_versioning.md`.

## 3. Webhook Configuration

- [ ] **HTTPS endpoint only**: Your production webhook URL must use HTTPS. HTTP endpoints are rejected. The URL must not exceed **2048 characters**.
- [ ] **Signature verification implemented**: Every incoming webhook must have its HMAC-SHA256 signature verified before being processed. See `docs/guides/webhooks_guide.md`.
- [ ] **Timestamp validation active**: Reject webhook events with an `X-NexusPay-Timestamp` more than 5 minutes old to prevent replay attacks.
- [ ] **Live webhook secret configured**: The sandbox and production webhook secrets are different. Reconfigure your application to use the live webhook secret retrieved from the Dashboard.
- [ ] **Idempotent webhook handlers**: Your handlers correctly deduplicate events by persisting processed event IDs.

## 4. Idempotency

- [ ] **Idempotency keys on all mutations**: Every `POST /payments`, `POST /payments/:id/capture`, and `POST /payments/:id/refunds` request includes a unique `Idempotency-Key` header (UUID v4, max 64 characters). See `docs/guides/idempotency_guide.md`.
- [ ] **Keys generated before requests**: Idempotency keys are generated and persisted in your database *before* the API call is made, ensuring they survive process crashes.
- [ ] **Same key on retries**: When retrying a failed request, your code reuses the original idempotency key — it does not generate a new one.

## 5. Error Handling

- [ ] **All error codes handled**: Your application handles every error code in `docs/reference/error_codes.md` gracefully — no unhandled exceptions that surface raw API errors to end users.
- [ ] **Non-retryable errors not retried**: `card_declined`, `expired_card`, `do_not_honor`, and similar codes do not trigger automatic retries. The customer is prompted to resolve the issue instead.
- [ ] **Retryable errors use backoff**: `service_unavailable`, `gateway_timeout`, and `internal_server_error` responses trigger retries with exponential backoff. See `docs/guides/error_handling_guide.md`.
- [ ] **Rate limit errors handled**: HTTP 429 responses read the `retry_after` value and wait the specified duration before retrying.

## 6. Payment Flow

- [ ] **Card tokenization only on frontend**: Raw card data is never sent to your backend. All card collection uses NexusPay.js or the mobile SDK with your publishable key.
- [ ] **Payment IDs persisted before order fulfilment**: The `payment.id` is saved to your database as part of the same transaction that fulfils the order, preventing fulfilment without a confirmed payment reference.
- [ ] **Amount in smallest currency unit**: All `amount` values are expressed in cents (or equivalent), not decimal. €10.00 = `1000`.

## 7. Refund and Authorization Handling

- [ ] **Refund constraints communicated to operations team**: Customer-facing support staff understand the 180-day refund window and 5-refund-per-payment limit.
- [ ] **Authorization captures scheduled**: If using auth-only payments, a mechanism is in place to capture within the **7-day** window. Expired authorizations cannot be recovered.

## 8. Rate Limit Monitoring

- [ ] **Rate limit headers monitored**: Your application reads the `X-RateLimit-Remaining` and `X-RateLimit-Reset` response headers and alerts when approaching limits.
- [ ] **Bulk operations throttled**: Batch jobs and nightly reconciliation scripts are rate-limited to stay within the thresholds defined in `docs/reference/rate_limits.md`.

## 9. Security Review

- [ ] **TLS certificate valid**: Your webhook endpoint and any NexusPay-facing services use a valid certificate from a trusted CA.
- [ ] **No sensitive data in logs**: Log sanitisation is in place to prevent card numbers, CVC codes, and API keys from appearing in log storage.

## 10. Sandbox Smoke Test

- [ ] **Full payment flow tested in sandbox**: A complete test payment was successfully made using card `4242 4242 4242 4242` and refunded, with all webhooks received and verified.
- [ ] **Decline scenario tested**: A declined payment using card `4000 0000 0000 0002` returns the correct error message to the user without crashing the application.

## Final Step — Activate Live Mode

Once all items above are checked, activate your live integration by pointing your application to the production base URL (`https://api.nexuspay.eu/v2`) with your live API keys.

Process a low-value real transaction immediately after going live to confirm end-to-end operation before opening to general traffic.
