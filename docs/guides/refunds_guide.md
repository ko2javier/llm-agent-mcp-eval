# Refunds Guide

This guide covers how to issue full and partial refunds, understand refund constraints, handle errors, and ensure idempotent refund processing.

## Overview

A refund returns some or all of a captured payment's funds to the customer. Refunds are processed asynchronously — after the API call returns a `refund` object with `status: pending`, the funds typically settle within 5–10 business days depending on the customer's bank and card network.

## Refund Constraints

| Constraint | Value |
|------------|-------|
| Maximum refund window | **180 days** from the original payment |
| Maximum refunds per payment | **5** |
| Minimum partial refund amount | **50 cents** (in the payment's currency) |

## Creating a Full Refund

To refund the full captured amount, omit the `amount` field:

```json
POST /payments/pay_01HXYZ9876543210/refunds
Authorization: Bearer sk_live_your_secret_key
Idempotency-Key: a3bb189e-8bf9-3888-9912-ace4e6543002

{}
```

**Response:**
```json
{
  "id": "ref_01HABC0000000001",
  "payment_id": "pay_01HXYZ9876543210",
  "amount": 4999,
  "currency": "EUR",
  "status": "pending",
  "reason": null,
  "created_at": "2025-06-15T10:00:00Z"
}
```

## Creating a Partial Refund

To refund a specific amount, provide the `amount` in the smallest currency unit (cents):

```json
POST /payments/pay_01HXYZ9876543210/refunds
Idempotency-Key: a3bb189e-8bf9-3888-9912-ace4e6543003

{
  "amount": 1000,
  "reason": "partial_return",
  "metadata": {
    "returned_item_sku": "WIDGET-PRO-001"
  }
}
```

Multiple partial refunds may be issued against the same payment, provided the total does not exceed the original captured amount and neither constraint (180-day window, 5-refund limit) is violated.

## Valid Refund Reasons

| Reason code | Description |
|-------------|-------------|
| `duplicate` | Payment was made more than once |
| `fraudulent` | Payment was identified as fraudulent |
| `customer_request` | Customer requested a refund |
| `partial_return` | Customer returned part of the order |

The `reason` field is optional but recommended for accurate reporting.

## Idempotent Refunds

Always supply an `Idempotency-Key` header when creating refunds. If a network error causes your request to time out, retrying with the same idempotency key will return the original refund object rather than creating a duplicate refund.

See `docs/guides/idempotency_guide.md` for key generation best practices and a full explanation of idempotency semantics.

## Refund Status Lifecycle

```
pending → succeeded
        → failed
```

| Status | Meaning |
|--------|---------|
| `pending` | Refund accepted; awaiting settlement |
| `succeeded` | Funds returned to the customer |
| `failed` | Refund could not be processed |

Subscribe to the `refund.succeeded` and `refund.failed` webhook events to track settlement asynchronously. Refer to `docs/guides/webhooks_guide.md`.

## Error Handling

### `refund_window_expired`

Returned when the refund is attempted more than **180 days** after the original payment:

```json
{
  "error": {
    "code": "refund_window_expired",
    "message": "Refunds must be issued within 180 days of the original payment."
  }
}
```

If you need to return funds after this window, you must issue a manual bank transfer outside of the NexusPay system.

### `max_refunds_exceeded`

Returned when a sixth refund is attempted against the same payment:

```json
{
  "error": {
    "code": "max_refunds_exceeded",
    "message": "A maximum of 5 refunds may be issued per payment."
  }
}
```

To work around this limit, consolidate refund amounts and issue fewer, larger refunds where possible.

### `amount_exceeds_captured`

Returned when the sum of all refund amounts exceeds the original captured amount:

```json
{
  "error": {
    "code": "amount_exceeds_captured",
    "message": "Total refund amount cannot exceed the captured payment amount."
  }
}
```

### `amount_too_small`

Returned when a partial refund amount is below **50 cents**:

```json
{
  "error": {
    "code": "amount_too_small",
    "message": "Partial refund amount must be at least 50 cents."
  }
}
```

## Listing Refunds

Retrieve all refunds for a payment using the list endpoint:

```json
GET /payments/pay_01HXYZ9876543210/refunds
```

**Response:**
```json
{
  "data": [
    {
      "id": "ref_01HABC0000000001",
      "amount": 1000,
      "status": "succeeded",
      "created_at": "2025-06-15T10:00:00Z"
    },
    {
      "id": "ref_01HABC0000000002",
      "amount": 2000,
      "status": "pending",
      "created_at": "2025-06-20T09:30:00Z"
    }
  ],
  "has_more": false
}
```

For pagination details, see `docs/guides/pagination_filtering.md`.
