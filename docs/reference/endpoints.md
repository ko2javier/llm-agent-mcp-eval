# API Endpoints Reference

**Base URL:** `https://api.nexuspay.io/v2`  
**Current API version:** v2 (released 2025-01-15)  
**Previous version:** v1 (deprecated 2025-07-01, sunset 2026-01-15)

---

## Payments

### POST /payments
Create a new payment.

| Parameter     | Type    | Required | Description                                      |
|---------------|---------|----------|--------------------------------------------------|
| amount        | integer | Yes      | Amount in cents (e.g. 1000 = €10.00)            |
| currency      | string  | Yes      | ISO 4217 code. Supported: EUR, USD, GBP, CHF, SEK, NOK, DKK |
| source        | string  | Yes      | Payment method token or card ID                  |
| description   | string  | No       | Max 255 characters                               |
| metadata      | object  | No       | Max 50 key-value pairs, keys max 40 chars        |
| capture       | boolean | No       | Default: true. Set false for auth-only           |
| idempotency_key | string | No     | Max 64 characters. Ensures deduplication         |

**Response:** Payment object. Status: `pending`, `succeeded`, `failed`, `cancelled`.

### GET /payments/:id
Retrieve a payment by ID.

### GET /payments
List payments. Supports pagination via `limit` (max 100, default 10) and `starting_after`.

### POST /payments/:id/capture
Capture an authorized payment. Only valid if `capture: false` was set on creation. Must be called within **7 days** of authorization.

### POST /payments/:id/cancel
Cancel a payment. Only valid for payments in `pending` status.

---

## Refunds

### POST /refunds
Create a refund for a succeeded payment.

| Parameter  | Type    | Required | Description                                      |
|------------|---------|----------|--------------------------------------------------|
| payment_id | string  | Yes      | ID of the payment to refund                      |
| amount     | integer | No       | Partial refund amount in cents. Default: full    |
| reason     | string  | No       | One of: `duplicate`, `fraudulent`, `requested_by_customer` |

**Constraints:**
- Refunds must be created within **180 days** of the original payment.
- Maximum **5 refunds** per payment.
- Partial refunds: minimum amount is **50 cents**.

### GET /refunds/:id
Retrieve a refund.

### GET /refunds
List refunds. Filter by `payment_id`.

---

## Subscriptions

### POST /subscriptions
Create a subscription.

| Parameter    | Type   | Required | Description                                         |
|--------------|--------|----------|-----------------------------------------------------|
| customer_id  | string | Yes      | Customer to bill                                    |
| plan_id      | string | Yes      | Subscription plan ID                                |
| trial_days   | integer| No       | Free trial period. Max: 90 days                     |
| billing_cycle| string | No       | `monthly` or `yearly`. Default: `monthly`           |

### POST /subscriptions/:id/cancel
Cancel a subscription. `cancel_at_period_end: true` cancels at next billing date.

### POST /subscriptions/:id/upgrade
Upgrade or downgrade a subscription plan. Proration is calculated automatically.

---

## Customers

### POST /customers
Create a customer.

| Parameter | Type   | Required | Description         |
|-----------|--------|----------|---------------------|
| email     | string | Yes      | Must be unique      |
| name      | string | No       | Max 200 characters  |
| metadata  | object | No       | Max 50 key-value pairs |

### GET /customers/:id
### PUT /customers/:id
### DELETE /customers/:id
Deleting a customer does not cancel active subscriptions — cancel subscriptions first.

---

## Webhooks

### POST /webhooks
Register a webhook endpoint.

| Parameter | Type     | Required | Description                        |
|-----------|----------|----------|------------------------------------|
| url       | string   | Yes      | HTTPS only. Max 2048 characters    |
| events    | string[] | Yes      | List of event types to subscribe   |
| secret    | string   | No       | Auto-generated if not provided     |

**Retry policy:** Failed webhook deliveries are retried up to **5 times** with exponential backoff: 1min, 5min, 30min, 2h, 8h.

### Available webhook events

| Event                        | Trigger                                 |
|-----------------------------|-----------------------------------------|
| payment.succeeded           | Payment completes successfully          |
| payment.failed              | Payment fails                           |
| payment.refunded            | Refund created                          |
| subscription.created        | New subscription starts                 |
| subscription.renewed        | Subscription renews                     |
| subscription.cancelled      | Subscription cancelled                  |
| subscription.payment_failed | Subscription billing fails              |
| customer.created            | New customer created                    |
| dispute.created             | Chargeback initiated                    |

---

## Reports

### GET /reports/summary
Returns aggregated payment metrics. Parameters: `from` (date), `to` (date), `currency`, `granularity` (`day`, `week`, `month`).

Maximum date range: **365 days**.

---

## Pagination

All list endpoints use cursor-based pagination:

```json
{
  "data": [...],
  "has_more": true,
  "next_cursor": "pay_abc123"
}
```

Pass `starting_after=pay_abc123` to get the next page. Default page size: 10. Maximum: 100.
