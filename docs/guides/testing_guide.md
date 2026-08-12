# Testing Guide

NexusPay provides a fully isolated sandbox environment that mirrors production behaviour without processing real money. This guide explains how to use test card numbers, trigger specific error scenarios, and test your webhook handlers.

## Sandbox Environment

All sandbox requests are authenticated with your test API keys, which are prefixed with `sk_test_` (secret) and `pk_test_` (publishable). Test keys are available in the Dashboard under **Developers → API Keys**.

- **Base URL (sandbox):** `https://api.sandbox.nexuspay.eu/v2`
- **Base URL (production):** `https://api.nexuspay.eu/v2`

Test and live environments are completely isolated. No data crosses between them.

## Test Card Numbers

Use the following card numbers in the sandbox to simulate different payment outcomes. All test cards accept any future expiry date, any 3-digit CVC, and any billing postcode.

### Standard Test Cards

| Card Number | Outcome | Error Code |
|-------------|---------|------------|
| `4242 4242 4242 4242` | Payment succeeds | — |
| `4000 0000 0000 0002` | Card declined | `card_declined` |
| `4000 0000 0000 9995` | Insufficient funds | `card_declined` / `insufficient_funds` |
| `4000 0000 0000 0069` | Card expired | `expired_card` |
| `4000 0000 0000 0127` | Incorrect CVC | `incorrect_cvc` |
| `4000 0000 0000 0119` | Processing error | `processing_error` |
| `4000 0000 0000 0044` | Do not honour | `do_not_honor` |

### 3D Secure Test Cards

| Card Number | Outcome |
|-------------|---------|
| `4000 0025 0000 3155` | 3DS required; authentication succeeds |
| `4000 0000 0000 3220` | 3DS required; authentication fails |

### Refund and Authorization Testing

Any successful payment made with `4242 4242 4242 4242` can be refunded in the sandbox with the same constraints as production (180-day window, 5-refund limit, 50-cent minimum).

To test authorization and capture flows, create a payment with `capture: false` using any success card. See `docs/guides/auth_capture_flow.md`.

## Simulating Specific Error Codes

To trigger specific API errors (unrelated to card behaviour), use query parameters or special metadata keys in sandbox:

```json
POST /payments

{
  "amount": 1000,
  "currency": "EUR",
  "source": "tok_test_simulate_service_unavailable"
}
```

Special test tokens for simulating infrastructure errors:

| Test Token | Simulated Error |
|------------|----------------|
| `tok_test_simulate_service_unavailable` | HTTP 503 `service_unavailable` |
| `tok_test_simulate_timeout` | HTTP 504 `gateway_timeout` |
| `tok_test_simulate_rate_limit` | HTTP 429 `rate_limit_exceeded` |

## Testing Webhooks

### Sandbox Webhook Delivery

Webhook events are fired in the sandbox exactly as in production. Configure your webhook endpoint in the Dashboard under **Developers → Webhooks** and point it to your sandbox endpoint.

For local development, use a tunnelling tool such as `ngrok` or `cloudflared` to expose your localhost server to NexusPay's sandbox:

```bash
ngrok http 3000
# Forwarding: https://abc123.ngrok.io -> http://localhost:3000
```

Register `https://abc123.ngrok.io/webhooks/nexuspay` as your sandbox webhook URL.

### Manually Triggering Webhook Events

Use the Dashboard or the API to send a test webhook event to your endpoint without making a real payment:

```json
POST /webhooks/wh_01HXYZ1234567890/test

{
  "event_type": "payment.succeeded"
}
```

This sends a synthetic event with realistic data to your configured endpoint. Use it to verify your signature verification logic and idempotency handling without completing a full payment flow.

### Verifying Signature Verification

The sandbox uses the same HMAC-SHA256 signature scheme as production. Your test webhook secret (prefixed `whsec_test_`) is separate from your live webhook secret. Test your verification code using the sandbox secret before going live.

For the full signature verification implementation, see `docs/guides/webhooks_guide.md`.

## Testing Subscriptions

In the sandbox, you can advance billing periods manually to test renewal, failure, and retry logic without waiting for real time to pass:

```json
POST /test/subscriptions/sub_01HXYZ4444444444/advance

{
  "advance_to": "next_billing_cycle"
}
```

This triggers the renewal charge immediately, firing the appropriate webhook events (`subscription.renewed` or `subscription.payment_failed`).

To simulate a renewal failure, ensure the subscription's customer has the decline card `4000 0000 0000 0002` as their default payment method before advancing.

## Sandbox Rate Limits

The sandbox applies the same rate limit structure as production. Refer to `docs/reference/rate_limits.md` for details. If you encounter `rate_limit_exceeded` errors during automated testing, reduce the concurrency of your test runner or add delays between requests.

## Testing Checklist

Before moving to production, verify the following in the sandbox:

- [ ] Successful payment creates and stores a payment ID correctly
- [ ] Declined payment surfaces an appropriate error message to the user
- [ ] Retry with the same idempotency key returns the original result (not a new payment)
- [ ] Refund creates correctly and fires `refund.succeeded` webhook
- [ ] Webhook signature verification rejects tampered payloads
- [ ] Webhook timestamp check rejects events older than 5 minutes
- [ ] Duplicate webhook delivery is handled idempotently

For the full production readiness checklist, see `docs/guides/going_live_checklist.md`.
