# Payments Flow

This guide walks through the complete end-to-end flow for accepting a card payment using NexusPay — from securely collecting card details on the frontend to confirming the payment result on the backend.

## Overview

NexusPay uses a two-key model to keep your server out of PCI scope as much as possible:

- **Publishable key** — safe to embed in frontend code; used only to tokenize card data.
- **Secret key** — must never leave your backend; used to create and manage payments.

For authentication details, refer to `docs/guides/authentication.md`.

## Step 1 — Tokenize the Card on the Frontend

Card details (number, expiry, CVC) must never be sent to your own server. Instead, use the NexusPay.js library or mobile SDK to collect card data and exchange it for a single-use **payment token** directly from your customer's browser.

```html
<script src="https://js.nexuspay.eu/v2/nexuspay.js"></script>
<script>
  const nexus = NexusPay("pk_live_your_publishable_key");

  async function submitCard(cardElement) {
    const { token, error } = await nexus.createToken(cardElement);

    if (error) {
      // Display error to the customer
      showError(error.message);
      return;
    }

    // Send the token to your backend
    await sendToBackend(token.id);
  }
</script>
```

The token is a short-lived, single-use reference to the card data stored on NexusPay's servers. It contains no sensitive information itself.

## Step 2 — Send the Token to Your Backend

Your frontend submits the token ID (e.g., `tok_01HABC1234567890`) to your own server via a standard form POST or AJAX call. Your backend then uses this token to create a payment.

```javascript
// Frontend: POST token to your backend
const response = await fetch("/checkout/pay", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ token_id: token.id, amount: 4999, currency: "EUR" }),
});
```

## Step 3 — Create the Payment on Your Backend

Using your **secret key**, your backend calls `POST /payments` with the token, amount, and currency. The `amount` field is always expressed in the **smallest currency unit** (cents for EUR/USD/GBP).

```json
POST /payments
Authorization: Bearer sk_live_your_secret_key
Content-Type: application/json
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000

{
  "amount": 4999,
  "currency": "EUR",
  "source": "tok_01HABC1234567890",
  "description": "Order #10042 — Premium Widget",
  "metadata": {
    "order_id": "10042",
    "customer_email": "jane@example.com"
  }
}
```

Always include an `Idempotency-Key` header when creating payments to prevent duplicate charges if your request is retried. See `docs/guides/idempotency_guide.md` for details.

## Step 4 — Handle the Response

NexusPay returns a payment object synchronously. Inspect the `status` field to determine the outcome.

### Successful Payment

```json
{
  "id": "pay_01HXYZ9876543210",
  "amount": 4999,
  "currency": "EUR",
  "status": "succeeded",
  "description": "Order #10042 — Premium Widget",
  "captured": true,
  "created_at": "2025-06-01T14:22:00Z",
  "metadata": {
    "order_id": "10042",
    "customer_email": "jane@example.com"
  }
}
```

### Failed Payment

```json
{
  "id": "pay_01HXYZ0000000001",
  "amount": 4999,
  "currency": "EUR",
  "status": "failed",
  "error": {
    "code": "card_declined",
    "message": "The card was declined by the issuer.",
    "decline_code": "insufficient_funds"
  }
}
```

## Step 5 — Store the Payment ID

Persist the `payment.id` (e.g., `pay_01HXYZ9876543210`) in your database immediately upon receiving a successful response, before fulfilling the order. This ID is the primary reference for all subsequent operations: refunds, disputes, and support lookups.

## Payment Status Reference

| Status | Meaning |
|--------|---------|
| `succeeded` | Payment captured and funds will be settled |
| `failed` | Payment was declined or encountered an error |
| `pending` | Awaiting asynchronous confirmation (rare) |
| `cancelled` | Payment was voided before capture |

## Asynchronous Confirmation

For most card payments, the `status` in the synchronous API response is definitive. However, for certain payment methods, the outcome may be delivered asynchronously via the `payment.succeeded` or `payment.failed` webhook event. Implement webhook handling as described in `docs/guides/webhooks_guide.md` to handle these cases.

## Error Handling

For a full list of error codes and which are safe to retry, refer to `docs/reference/error_codes.md` and `docs/guides/error_handling_guide.md`.
