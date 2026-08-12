# Customer Management Guide

The NexusPay Customer object is a persistent record that lets you attach payment methods, manage subscriptions, and track payment history across multiple transactions. This guide covers creating and managing customers, attaching payment methods, and avoiding common pitfalls.

## Why Use Customer Objects?

Without customer objects, each payment requires a fresh one-time token. Customer objects enable:

- **Saved payment methods**: charge a returning customer without asking for card details again.
- **Subscriptions**: subscriptions are always associated with a customer record.
- **Payment history**: retrieve all payments for a customer via the list API.
- **Dispute evidence**: customer email and IP address attached to the record strengthen chargeback responses.

## Creating a Customer

```json
POST /customers
Authorization: Bearer sk_live_your_secret_key

{
  "email": "jan@example.nl",
  "name": "Jan de Vries",
  "phone": "+31201234567",
  "metadata": {
    "internal_user_id": "usr_9918",
    "signup_date": "2025-06-01"
  }
}
```

**Response:**
```json
{
  "id": "cus_01HXYZ3333333333",
  "email": "jan@example.nl",
  "name": "Jan de Vries",
  "phone": "+31201234567",
  "default_payment_method": null,
  "metadata": {
    "internal_user_id": "usr_9918",
    "signup_date": "2025-06-01"
  },
  "created_at": "2025-06-01T12:00:00Z"
}
```

Store the `customer.id` in your own database alongside your internal user record. Use the `metadata` field to link back to your `internal_user_id` for bidirectional lookups.

## Attaching Payment Methods

After creating a customer, attach a payment method using a token obtained from NexusPay.js (see `docs/guides/payments_flow.md`):

```json
POST /customers/cus_01HXYZ3333333333/payment_methods

{
  "source": "tok_01HABC1234567890",
  "set_as_default": true
}
```

**Response:**
```json
{
  "id": "pm_01HXYZ8888888888",
  "customer_id": "cus_01HXYZ3333333333",
  "type": "card",
  "card": {
    "brand": "visa",
    "last4": "4242",
    "exp_month": 12,
    "exp_year": 2028
  },
  "is_default": true,
  "created_at": "2025-06-01T12:05:00Z"
}
```

A customer may have multiple payment methods. The `default_payment_method` is used for subscription renewals and any payment request that references the customer without specifying a payment method.

### Charging a Saved Payment Method

```json
POST /payments

{
  "amount": 4999,
  "currency": "EUR",
  "customer": "cus_01HXYZ3333333333",
  "payment_method": "pm_01HXYZ8888888888",
  "description": "Order #10043"
}
```

## Updating Customer Data

Update any customer field with a PATCH request. Omitted fields are preserved:

```json
PATCH /customers/cus_01HXYZ3333333333

{
  "email": "jan.devries@newdomain.nl",
  "metadata": {
    "account_tier": "premium"
  }
}
```

## Deduplicating Customers by Email

NexusPay does not automatically deduplicate customers by email. If a user signs up twice or uses two different emails, you may end up with two separate customer records. This fragments payment history and complicates subscription management.

**Recommended approach:**

Before creating a new customer, search for an existing one by email:

```
GET /customers?email=jan@example.nl
```

If a matching customer exists, use that record rather than creating a new one. Enforce the same deduplication check in your own user creation logic.

```python
def get_or_create_customer(email: str, name: str) -> dict:
    existing = nexuspay.customers.list(email=email)
    if existing.data:
        return existing.data[0]
    return nexuspay.customers.create(email=email, name=name)
```

## Listing Payment Methods for a Customer

```
GET /customers/cus_01HXYZ3333333333/payment_methods
```

**Response:**
```json
{
  "data": [
    {
      "id": "pm_01HXYZ8888888888",
      "type": "card",
      "card": { "brand": "visa", "last4": "4242", "exp_month": 12, "exp_year": 2028 },
      "is_default": true
    }
  ],
  "has_more": false
}
```

## Deleting a Customer

```json
DELETE /customers/cus_01HXYZ3333333333
```

**Critical warning:** Deleting a customer object does **not** automatically cancel their active subscriptions. If a customer with active subscriptions is deleted:

- The subscriptions remain in the `active` or `trialing` state.
- Renewal charges will fail because the customer record no longer exists.
- This results in failed subscription payments and `subscription.payment_failed` webhook events.

**Always cancel all active subscriptions before deleting a customer:**

```python
def delete_customer_safely(customer_id: str):
    subscriptions = nexuspay.subscriptions.list(customer_id=customer_id, status="active")
    for sub in subscriptions.data:
        nexuspay.subscriptions.cancel(sub["id"])

    # Also cancel trialing subscriptions
    trialing = nexuspay.subscriptions.list(customer_id=customer_id, status="trialing")
    for sub in trialing.data:
        nexuspay.subscriptions.cancel(sub["id"])

    nexuspay.customers.delete(customer_id)
```

Deleting a customer does not affect historical payment records — past payments remain accessible via their payment IDs.

## Customer-Level Metadata

For metadata best practices and constraints (50 key limit, 40-character key limit), see `docs/guides/metadata_guide.md`. Use customer metadata to store your internal identifiers, not sensitive data.
