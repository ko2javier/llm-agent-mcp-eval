# Metadata Guide

The `metadata` field is available on most NexusPay objects — payments, customers, refunds, subscriptions, and disputes. It allows you to attach your own structured key-value data to any API object, making it easy to cross-reference NexusPay records with entities in your own systems.

## Metadata Constraints

| Property | Limit |
|----------|-------|
| Maximum number of keys per object | **50** |
| Maximum key length | **40 characters** |
| Maximum value length | refer to the reference documentation |
| Allowed key characters | alphanumeric, underscores, hyphens |

Values must be strings. Numbers, booleans, and nested objects are not supported — serialize them to strings before storing.

## Common Use Cases

### Linking to Internal Order IDs

Attach your internal order or invoice ID to every payment. This lets your support team look up the NexusPay payment from your own back-office system, and vice versa.

```json
{
  "metadata": {
    "order_id": "ORD-2025-098231",
    "invoice_id": "INV-00421"
  }
}
```

### Customer Reference Tracking

Store your internal user or customer ID on NexusPay customer and payment objects. This is especially useful when a customer uses multiple email addresses or payment methods across their lifetime.

```json
{
  "metadata": {
    "internal_user_id": "usr_9918",
    "signup_cohort": "2024-Q3"
  }
}
```

### Subscription and Product Context

On subscription objects, record the plan tier, feature flags, or sales channel to support analytics queries without joining across systems.

```json
{
  "metadata": {
    "plan_tier": "pro",
    "billing_country": "NL",
    "sales_channel": "web"
  }
}
```

### Operational Tracking

Track which part of your infrastructure created a payment — useful for debugging and tracing in microservices architectures.

```json
{
  "metadata": {
    "created_by_service": "checkout-api",
    "deployment_version": "v3.14.1",
    "region": "eu-west-1"
  }
}
```

## Metadata vs the `description` Field

Both fields add human-readable context to API objects, but they serve different purposes:

| Field | Purpose | Constraints | Visibility |
|-------|---------|-------------|------------|
| `metadata` | Machine-readable key-value pairs for internal use | 50 keys, 40-char keys | Not shown to customers |
| `description` | Human-readable summary of the payment | Max **255 characters**, single string | May appear on bank statements |

Use `description` for customer-facing context (e.g., `"Order #10042 — Premium Widget"`). Use `metadata` for internal cross-references and operational data that customers should never see.

## Querying by Metadata

You can filter list endpoints by metadata key-value pairs to retrieve objects matching specific internal identifiers:

```
GET /payments?metadata[order_id]=ORD-2025-098231
```

**Response:**
```json
{
  "data": [
    {
      "id": "pay_01HXYZ9876543210",
      "amount": 4999,
      "currency": "EUR",
      "status": "succeeded",
      "metadata": {
        "order_id": "ORD-2025-098231",
        "invoice_id": "INV-00421"
      }
    }
  ],
  "has_more": false
}
```

This is particularly useful for support tooling and reconciliation scripts that need to look up a payment by your own internal reference rather than the NexusPay payment ID.

For full filter syntax and pagination parameters, see `docs/guides/pagination_filtering.md`.

## Updating Metadata

Metadata can be updated on existing objects by sending a PATCH request. Only the keys you include are updated — omitted keys are preserved. To delete a key, set its value to `null`:

```json
PATCH /payments/pay_01HXYZ9876543210

{
  "metadata": {
    "order_id": "ORD-2025-098231",
    "shipping_status": "delivered",
    "invoice_id": null
  }
}
```

After this update, `invoice_id` is removed and `shipping_status` is added, while `order_id` retains its existing value.

## Security Considerations

- Do not store sensitive data in metadata: no card numbers, passwords, SSNs, or authentication tokens.
- Metadata is visible to anyone with access to your NexusPay Dashboard and to any system that calls the API with your secret key. Apply the same access controls you would to any business data.
- Metadata is not end-to-end encrypted beyond NexusPay's standard data-at-rest encryption. Do not rely on it for data classification purposes.

## Best Practices

1. **Establish a naming convention** for metadata keys across your team. Inconsistent key names (e.g., `order_id`, `orderId`, `orderID`) make querying unreliable.
2. **Store NexusPay IDs in your own database too**: metadata bridges your system to NexusPay, but always persist the NexusPay `payment.id` in your own records as the primary reference.
3. **Keep metadata minimal**: store only what you will actually query or display. Avoid dumping entire JSON blobs as stringified values — use structured keys instead.
