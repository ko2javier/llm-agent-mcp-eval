# Authorization and Capture Flow

This guide explains how to separate the authorization of a payment from its capture — a common pattern in industries where the final charge amount is not known at the time of booking.

## When to Use Auth-Only Payments

An authorization places a hold on the customer's funds without immediately settling the charge. Use this flow when:

- **Marketplaces** — funds should only be captured once a seller confirms the order.
- **Hotels** — the final amount depends on room service, minibar charges, or late checkout fees determined at checkout.
- **Car rentals** — the final charge may include fuel, damage fees, or toll charges not known at pickup.
- **Restaurants and bars** — a pre-authorization for a running tab before the final bill is calculated.

In all these cases, you authorize a maximum amount upfront, then capture the actual amount once it is known — within the allowed window.

## Step 1 — Create an Authorization

To authorize without capturing, set `capture` to `false` in the payment creation request:

```json
POST /payments
Authorization: Bearer sk_live_your_secret_key
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000

{
  "amount": 20000,
  "currency": "EUR",
  "source": "tok_01HABC1234567890",
  "capture": false,
  "description": "Hotel stay — room hold",
  "metadata": {
    "reservation_id": "RES-88421"
  }
}
```

**Response:**
```json
{
  "id": "pay_01HXYZ1111111111",
  "amount": 20000,
  "currency": "EUR",
  "status": "authorized",
  "captured": false,
  "capture_before": "2025-06-08T14:30:00Z",
  "created_at": "2025-06-01T14:30:00Z"
}
```

The `capture_before` timestamp indicates the deadline by which you must capture. Authorizations expire after **7 days**. After expiry, the hold is automatically released and the funds return to the customer — you cannot capture an expired authorization.

## Step 2 — Check Authorization Status

To verify that an authorization is still valid before capturing, retrieve the payment:

```json
GET /payments/pay_01HXYZ1111111111
```

**Response fields to check:**

| Field | Expected value for a capturable auth |
|-------|--------------------------------------|
| `status` | `authorized` |
| `captured` | `false` |
| `capture_before` | Future timestamp |

If `status` is `expired`, the authorization has lapsed and cannot be captured.

## Step 3 — Capture the Payment

When you know the final amount, capture the authorization. You may capture the full authorized amount or a lesser amount — you cannot capture more than the original authorization.

```json
POST /payments/pay_01HXYZ1111111111/capture

{
  "amount": 18500
}
```

**Response:**
```json
{
  "id": "pay_01HXYZ1111111111",
  "amount": 18500,
  "currency": "EUR",
  "status": "succeeded",
  "captured": true,
  "captured_at": "2025-06-03T11:00:00Z"
}
```

If you omit the `amount` field, NexusPay captures the full original authorized amount.

## Step 4 — Cancel an Unused Authorization

If the customer cancels the reservation or you no longer need the hold, cancel the authorization to release the funds immediately rather than waiting for the 7-day expiry:

```json
POST /payments/pay_01HXYZ1111111111/cancel
```

**Response:**
```json
{
  "id": "pay_01HXYZ1111111111",
  "status": "cancelled",
  "captured": false,
  "cancelled_at": "2025-06-02T09:15:00Z"
}
```

Cancelling an authorization does not trigger a refund (no funds were settled). It simply releases the hold on the customer's account.

## Auth-Capture Timeline

```
Day 0     Day 1     Day 3     Day 7 (deadline)
  |---------|---------|---------|
  ^                   ^         ^
  Authorize        Capture    Expires
  (status:        (status:   (auto-released)
  authorized)    succeeded)
```

## Common Error Cases

| Error code | Cause | Resolution |
|------------|-------|------------|
| `authorization_expired` | Attempted capture after the 7-day window | Create a new authorization |
| `authorization_already_captured` | Payment already captured | No action needed; check payment status |
| `invalid_capture_amount` | Capture amount exceeds authorized amount | Capture equal to or less than the original amount |

For a complete error code reference, see `docs/reference/error_codes.md`.

## Webhook Events

Subscribe to these events for authorization lifecycle notifications:

| Event | Triggered when |
|-------|---------------|
| `payment.authorized` | Authorization successfully created |
| `payment.captured` | Payment successfully captured |
| `payment.cancelled` | Authorization cancelled |
| `payment.expired` | Authorization expired without capture |

See `docs/guides/webhooks_guide.md` for webhook configuration and signature verification.
