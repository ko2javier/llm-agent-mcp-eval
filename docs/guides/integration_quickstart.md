# Integration Quickstart

Get your first test payment running in under 5 minutes. This guide walks through installing the SDK, authenticating, creating a €10.00 test payment, inspecting the response, and issuing a refund.

## Prerequisites

- A NexusPay account (sign up at nexuspay.eu)
- Your **test secret key** (`sk_test_...`) from the Dashboard under **Developers → API Keys**

## Step 1 — Install the SDK

### Python

```bash
pip install nexuspay
```

Requires Python 3.8 or later.

### Node.js / JavaScript

```bash
npm install @nexuspay/sdk
```

Requires Node.js 16 or later.

## Step 2 — Authenticate

Set your test secret key as an environment variable — never hardcode it in your source files.

```bash
export NEXUSPAY_SECRET_KEY="sk_test_your_key_here"
```

### Python

```python
import os
import nexuspay

nexuspay.api_key = os.environ["NEXUSPAY_SECRET_KEY"]
```

### JavaScript

```javascript
import NexusPay from "@nexuspay/sdk";

const nexuspay = new NexusPay({
  apiKey: process.env.NEXUSPAY_SECRET_KEY,
});
```

All API calls made with a `sk_test_` key operate in the sandbox environment and do not process real money.

## Step 3 — Create a Test Payment for €10.00

Amounts are always expressed in the **smallest currency unit**. For EUR, that is cents: €10.00 = `1000`.

Use the test card token `tok_test_4242424242424242` to simulate a card tokenized from the test card `4242 4242 4242 4242`.

### Python

```python
import uuid

payment = nexuspay.payments.create(
    amount=1000,
    currency="EUR",
    source="tok_test_4242424242424242",
    description="Quickstart test payment",
    idempotency_key=str(uuid.uuid4()),
)

print(f"Payment ID: {payment['id']}")
print(f"Status: {payment['status']}")
```

### JavaScript

```javascript
import { v4 as uuidv4 } from "uuid";

const payment = await nexuspay.payments.create({
  amount: 1000,
  currency: "EUR",
  source: "tok_test_4242424242424242",
  description: "Quickstart test payment",
  idempotencyKey: uuidv4(),
});

console.log(`Payment ID: ${payment.id}`);
console.log(`Status: ${payment.status}`);
```

## Step 4 — Inspect the Response

A successful payment returns a payment object with `status: "succeeded"`:

```json
{
  "id": "pay_01HXYZ9876543210",
  "amount": 1000,
  "currency": "EUR",
  "status": "succeeded",
  "captured": true,
  "description": "Quickstart test payment",
  "created_at": "2025-06-01T14:22:00Z",
  "metadata": {}
}
```

**Key fields to store:**

| Field | Why |
|-------|-----|
| `id` | Primary reference for refunds, disputes, and support |
| `status` | Must be `succeeded` before fulfilling an order |
| `amount` | Confirm the charged amount matches what you sent |

If the payment fails, the response includes an `error` object with a `code` field. See `docs/guides/error_handling_guide.md` for how to handle specific error codes.

## Step 5 — Issue a Refund

Refund the payment using its ID. Here we refund the full amount (1000 cents = €10.00):

### Python

```python
refund = nexuspay.refunds.create(
    payment_id=payment["id"],
    idempotency_key=str(uuid.uuid4()),
)

print(f"Refund ID: {refund['id']}")
print(f"Refund status: {refund['status']}")
```

### JavaScript

```javascript
const refund = await nexuspay.refunds.create({
  paymentId: payment.id,
  idempotencyKey: uuidv4(),
});

console.log(`Refund ID: ${refund.id}`);
console.log(`Refund status: ${refund.status}`);
```

**Refund response:**

```json
{
  "id": "ref_01HABC0000000001",
  "payment_id": "pay_01HXYZ9876543210",
  "amount": 1000,
  "currency": "EUR",
  "status": "pending",
  "created_at": "2025-06-01T14:25:00Z"
}
```

A `status` of `pending` is expected — the refund is queued for processing. It transitions to `succeeded` after settlement. Subscribe to the `refund.succeeded` webhook event to be notified when it completes (see `docs/guides/webhooks_guide.md`).

## Complete Example (Python)

```python
import os
import uuid
import nexuspay

nexuspay.api_key = os.environ["NEXUSPAY_SECRET_KEY"]

# Create a payment
payment = nexuspay.payments.create(
    amount=1000,
    currency="EUR",
    source="tok_test_4242424242424242",
    description="Quickstart test payment",
    idempotency_key=str(uuid.uuid4()),
)
assert payment["status"] == "succeeded", f"Unexpected status: {payment['status']}"
print(f"Payment {payment['id']} succeeded.")

# Refund it
refund = nexuspay.refunds.create(
    payment_id=payment["id"],
    idempotency_key=str(uuid.uuid4()),
)
print(f"Refund {refund['id']} is {refund['status']}.")
```

## Complete Example (JavaScript)

```javascript
import NexusPay from "@nexuspay/sdk";
import { v4 as uuidv4 } from "uuid";

const nexuspay = new NexusPay({ apiKey: process.env.NEXUSPAY_SECRET_KEY });

// Create a payment
const payment = await nexuspay.payments.create({
  amount: 1000,
  currency: "EUR",
  source: "tok_test_4242424242424242",
  description: "Quickstart test payment",
  idempotencyKey: uuidv4(),
});

if (payment.status !== "succeeded") {
  throw new Error(`Unexpected status: ${payment.status}`);
}
console.log(`Payment ${payment.id} succeeded.`);

// Refund it
const refund = await nexuspay.refunds.create({
  paymentId: payment.id,
  idempotencyKey: uuidv4(),
});
console.log(`Refund ${refund.id} is ${refund.status}.`);
```

## Next Steps

| Topic | Guide |
|-------|-------|
| Handling card declines and errors | `docs/guides/error_handling_guide.md` |
| Verifying webhook events | `docs/guides/webhooks_guide.md` |
| Preventing duplicate charges | `docs/guides/idempotency_guide.md` |
| Saving cards for repeat customers | `docs/guides/customers_guide.md` |
| Setting up recurring billing | `docs/guides/subscriptions_guide.md` |
| Going live in production | `docs/guides/going_live_checklist.md` |
