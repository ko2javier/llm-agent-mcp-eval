# Disputes Guide

A dispute (also called a chargeback) occurs when a cardholder contacts their bank to challenge a charge. The bank temporarily reverses the funds and requests evidence from you to determine whether the original payment was legitimate. This guide explains how NexusPay notifies you of disputes and how to respond effectively.

## How Disputes Work

When a cardholder files a dispute:

1. The card network notifies NexusPay.
2. NexusPay creates a `dispute` object and fires the `dispute.created` webhook event.
3. The disputed amount is held pending resolution.
4. You have a limited window (typically 7–10 business days, as determined by the card network and bank) to submit evidence. Refer to the `evidence_due_by` field on the dispute object for your exact deadline.
5. The bank reviews the evidence and renders a decision — either in your favour (dispute won, funds returned) or the cardholder's favour (dispute lost, funds permanently returned to the cardholder).

An additional dispute fee may apply per chargeback regardless of outcome. Refer to your NexusPay merchant agreement for fee details.

## The `dispute.created` Webhook

Subscribe to `dispute.created` to be notified immediately when a dispute is opened. Timely action is essential — delays reduce the quality of evidence you can provide.

```json
{
  "type": "dispute.created",
  "data": {
    "id": "dis_01HXYZ7777777777",
    "payment_id": "pay_01HXYZ9876543210",
    "amount": 4999,
    "currency": "EUR",
    "reason": "fraudulent",
    "status": "needs_response",
    "evidence_due_by": "2025-06-10T23:59:00Z",
    "created_at": "2025-06-01T08:00:00Z"
  }
}
```

## Dispute Types

| Reason Code | Description | Common Cause |
|-------------|-------------|--------------|
| `fraudulent` | Cardholder denies making the transaction | Stolen card or account takeover |
| `product_not_received` | Customer claims they never received the goods or service | Delivery failure, fulfilment error |
| `product_unacceptable` | Item received but significantly not as described | Quality issues, wrong item shipped |
| `duplicate` | Customer was charged more than once for the same order | Duplicate payment processing |
| `subscription_cancelled` | Customer claims they cancelled but were still charged | Cancellation not processed correctly |
| `credit_not_processed` | Customer was promised a refund that never arrived | Refund processing failure |
| `unrecognized` | Cardholder does not recognize the transaction | Unclear billing descriptor |

## Retrieving a Dispute

```json
GET /disputes/dis_01HXYZ7777777777
```

**Response:**
```json
{
  "id": "dis_01HXYZ7777777777",
  "payment_id": "pay_01HXYZ9876543210",
  "amount": 4999,
  "currency": "EUR",
  "reason": "fraudulent",
  "status": "needs_response",
  "evidence_due_by": "2025-06-10T23:59:00Z",
  "evidence": null,
  "created_at": "2025-06-01T08:00:00Z"
}
```

## Dispute Status Reference

| Status | Description |
|--------|-------------|
| `needs_response` | Evidence window is open; action required |
| `under_review` | Evidence submitted; awaiting bank decision |
| `won` | Dispute decided in your favour; funds returned |
| `lost` | Dispute decided in cardholder's favour |
| `charge_refunded` | You issued a full refund before contesting |

## Submitting Evidence

Submit evidence via the API before the `evidence_due_by` deadline. Evidence requirements vary by dispute reason — the more specific and verifiable your documentation, the stronger your case.

```json
POST /disputes/dis_01HXYZ7777777777/evidence

{
  "customer_name": "Jane Smith",
  "customer_email": "jane@example.com",
  "customer_ip_address": "203.0.113.42",
  "customer_signature": "base64-encoded-signature",
  "shipping_tracking_number": "DHL-123456789",
  "shipping_carrier": "DHL",
  "delivery_date": "2025-05-28",
  "receipt": "base64-encoded-pdf-or-image",
  "additional_notes": "Customer confirmed delivery via email on 2025-05-29. Transcript attached."
}
```

### Evidence by Dispute Type

| Dispute Reason | Key Evidence to Submit |
|----------------|----------------------|
| `fraudulent` | IP address, device fingerprint, customer authentication logs, billing address match |
| `product_not_received` | Shipping tracking number, delivery confirmation, carrier receipt |
| `product_unacceptable` | Product description at time of purchase, photos, return policy |
| `duplicate` | Proof that both charges correspond to distinct orders |
| `subscription_cancelled` | Terms of service, proof cancellation was not received before billing date |

After submitting evidence, the dispute status transitions to `under_review`.

## Accepting a Dispute

If the dispute is valid (e.g., a genuine fraud case or fulfilment error), you can accept it rather than contest it. Accepting immediately concedes the funds and avoids a dispute fee in some cases:

```json
POST /disputes/dis_01HXYZ7777777777/accept
```

This transitions the status to `lost` without requiring the bank to render a decision.

## Dispute Webhook Events

| Event | Triggered when |
|-------|---------------|
| `dispute.created` | A new dispute is opened |
| `dispute.evidence_submitted` | You have submitted evidence |
| `dispute.won` | Bank decided in your favour |
| `dispute.lost` | Bank decided against you |
| `dispute.closed` | Dispute closed for any reason |

Configure webhook handling as described in `docs/guides/webhooks_guide.md`.

## Reducing Dispute Risk

- Use a clear, recognisable billing descriptor so customers recognise the charge.
- Send order confirmation emails with full itemisation immediately after purchase.
- Process cancellation and refund requests promptly — a refund is always preferable to a dispute.
- Attach customer email, IP address, and order metadata to payments to strengthen evidence if a dispute is later filed.
