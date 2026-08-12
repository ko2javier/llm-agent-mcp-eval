# Subscriptions Guide

This guide covers the full lifecycle of a subscription on NexusPay — from creating a billing plan to handling failed payments, upgrading plans, and managing cancellation.

## Concepts

| Term | Description |
|------|-------------|
| **Plan** | A reusable billing template (amount, currency, interval) |
| **Customer** | A stored customer record with an attached payment method |
| **Subscription** | The association between a customer and a plan, with billing state |

## Step 1 — Create a Plan

Plans define the recurring charge amount and interval. Create plans once and reuse them across many subscriptions.

```json
POST /plans
Authorization: Bearer sk_live_your_secret_key

{
  "name": "Pro Monthly",
  "amount": 2900,
  "currency": "EUR",
  "interval": "month",
  "interval_count": 1,
  "description": "NexusApp Pro plan — billed monthly"
}
```

**Response:**
```json
{
  "id": "plan_01HXYZ2222222222",
  "name": "Pro Monthly",
  "amount": 2900,
  "currency": "EUR",
  "interval": "month",
  "interval_count": 1,
  "created_at": "2025-06-01T00:00:00Z"
}
```

Supported `interval` values: `day`, `week`, `month`, `year`.

## Step 2 — Create a Customer

Before creating a subscription, ensure the customer exists and has a default payment method attached. See `docs/guides/customers_guide.md` for customer management.

```json
POST /customers

{
  "email": "jan@example.nl",
  "name": "Jan de Vries",
  "metadata": { "user_id": "usr_9918" }
}
```

## Step 3 — Create the Subscription

Attach the customer to a plan to start a subscription. Optionally include a trial period.

```json
POST /subscriptions

{
  "customer_id": "cus_01HXYZ3333333333",
  "plan_id": "plan_01HXYZ2222222222",
  "trial_period_days": 14,
  "metadata": {
    "signup_source": "web"
  }
}
```

**Response:**
```json
{
  "id": "sub_01HXYZ4444444444",
  "customer_id": "cus_01HXYZ3333333333",
  "plan_id": "plan_01HXYZ2222222222",
  "status": "trialing",
  "trial_end": "2025-06-15T00:00:00Z",
  "current_period_start": "2025-06-01T00:00:00Z",
  "current_period_end": "2025-06-15T00:00:00Z",
  "created_at": "2025-06-01T00:00:00Z"
}
```

The maximum trial period is **90 days**. After the trial ends, the subscription transitions to `active` and the first charge is attempted.

## Subscription Status Reference

| Status | Description |
|--------|-------------|
| `trialing` | Within the trial period — no charges yet |
| `active` | Billing normally; payment succeeded |
| `past_due` | Most recent payment failed; retries ongoing |
| `cancelled` | Subscription has ended |
| `unpaid` | All retry attempts exhausted; requires intervention |

## Billing Cycles

NexusPay automatically charges the customer's default payment method at the start of each billing period. The `current_period_start` and `current_period_end` fields always reflect the current billing window.

### Monthly Billing Example

| Period | Start | End |
|--------|-------|-----|
| Month 1 | 2025-07-01 | 2025-08-01 |
| Month 2 | 2025-08-01 | 2025-09-01 |
| Month 3 | 2025-09-01 | 2025-10-01 |

### Yearly Billing

Use `"interval": "year"` and `"interval_count": 1`. The customer is charged once per year.

## Handling Payment Failures

When a subscription renewal charge fails, NexusPay fires the `subscription.payment_failed` webhook:

```json
{
  "type": "subscription.payment_failed",
  "data": {
    "subscription_id": "sub_01HXYZ4444444444",
    "payment_id": "pay_01HXYZ5555555555",
    "error_code": "card_declined",
    "attempt_count": 1,
    "next_attempt_at": "2025-07-06T00:00:00Z"
  }
}
```

NexusPay retries failed subscription payments on the schedule defined in `docs/reference/endpoints.md`. During retries, the subscription status is `past_due`. After all retries are exhausted, the status transitions to `unpaid` and the `subscription.unpaid` event fires.

**Recommended action on `subscription.payment_failed`:**
- Notify the customer by email with a link to update their payment method.
- Check `attempt_count` to escalate urgency in follow-up messages.

## Upgrading or Downgrading Plans

To change a subscription's plan, update the `plan_id`. NexusPay calculates proration automatically.

```json
PATCH /subscriptions/sub_01HXYZ4444444444

{
  "plan_id": "plan_01HXYZ6666666666",
  "proration_behavior": "create_prorations"
}
```

| `proration_behavior` | Effect |
|----------------------|--------|
| `create_prorations` | Immediately charges or credits the prorated difference |
| `none` | Plan changes at next billing period with no immediate charge |

## Cancellation Options

### Cancel at Period End

The subscription remains `active` until the end of the current billing period, then transitions to `cancelled`:

```json
PATCH /subscriptions/sub_01HXYZ4444444444

{
  "cancel_at_period_end": true
}
```

### Cancel Immediately

```json
DELETE /subscriptions/sub_01HXYZ4444444444
```

Immediate cancellation does not issue a refund for unused time. If a refund is owed, issue it separately via the Refunds API (see `docs/guides/refunds_guide.md`).

## Webhook Events for Subscriptions

| Event | Triggered when |
|-------|---------------|
| `subscription.created` | New subscription created |
| `subscription.trial_ending` | 3 days before trial ends |
| `subscription.renewed` | Successful renewal charge |
| `subscription.payment_failed` | Renewal charge failed |
| `subscription.unpaid` | All retry attempts exhausted |
| `subscription.cancelled` | Subscription cancelled |
