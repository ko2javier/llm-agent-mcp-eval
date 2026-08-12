# Security Guide

Security is a shared responsibility between NexusPay and the merchants integrating with the platform. This guide outlines the controls NexusPay provides and the obligations on your side to maintain a secure integration.

## PCI DSS Scope Reduction

The Payment Card Industry Data Security Standard (PCI DSS) applies to any system that stores, processes, or transmits raw cardholder data. Handling this data yourself requires significant compliance effort and audit overhead.

NexusPay's tokenization model is specifically designed to keep your servers out of PCI scope:

1. **Your frontend** uses the NexusPay.js library (or mobile SDK) and your **publishable key** to collect card data directly in the customer's browser.
2. Card data travels directly to NexusPay's PCI-compliant servers — it never touches your backend.
3. NexusPay returns a short-lived, single-use **payment token** that contains no sensitive data.
4. **Your backend** uses this token with your **secret key** to create a payment.

Under this model, your servers only ever see a token — not a card number, CVC, or expiry date. This substantially reduces your PCI DSS compliance scope.

**Never send raw card data to your own backend.** If you build a custom card collection form that POSTs card numbers to your server, you assume full PCI DSS cardholder data environment (CDE) scope.

## API Key Security

NexusPay issues two types of keys:

| Key Type | Prefix | Where to use | Who can see it |
|----------|--------|--------------|----------------|
| Publishable key | `pk_live_` / `pk_test_` | Frontend (browser/app) | Visible to end users — safe by design |
| Secret key | `sk_live_` / `sk_test_` | Backend only | **Must never be exposed** |

### Protecting the Secret Key

- Store the secret key in environment variables or a secrets manager (e.g., HashiCorp Vault, AWS Secrets Manager). Never hardcode it in source code.
- Never commit secret keys to version control, even in private repositories.
- Never log the secret key or include it in error messages.
- Do not include the secret key in frontend JavaScript bundles.

```bash
# Good: load from environment
export NEXUSPAY_SECRET_KEY="sk_live_your_key_here"
```

```python
# Good: read from environment at runtime
import os
secret_key = os.environ["NEXUSPAY_SECRET_KEY"]

# Bad: hardcoded in source
secret_key = "sk_live_your_key_here"  # NEVER DO THIS
```

### API Key Rotation

Rotate your secret key immediately if you suspect it has been compromised. In the Dashboard under **Developers → API Keys**, you can issue a new key. After issuing the new key:

1. Update your application's environment variable or secrets manager entry.
2. Deploy the updated configuration.
3. Revoke the old key only after confirming the new key is serving production traffic successfully.

Establish a regular key rotation schedule as part of your security hygiene, even without a known compromise event.

## Never Log Raw Card Data

Logging middleware, request/response loggers, and error tracking tools must be configured to **redact or mask card numbers before they are written to any log storage**.

Fields that must never appear in logs:

- `card.number` / PAN (primary account number)
- `card.cvc` / `card.cvv`
- Full `card.expiry`

```python
SENSITIVE_FIELDS = {"card_number", "cvc", "cvv", "expiry"}

def sanitize_log_payload(payload: dict) -> dict:
    return {
        k: "[REDACTED]" if k in SENSITIVE_FIELDS else v
        for k, v in payload.items()
    }
```

If you are using NexusPay.js for tokenization (recommended), these fields never reach your backend, eliminating this risk at the architectural level.

## Securing Webhook Endpoints

Your webhook endpoint receives signed HTTP POST requests from NexusPay. Without proper security:

- Attackers can forge fake webhook events to trigger unintended actions (e.g., marking an order as paid without a real payment).
- Replayed legitimate events can cause duplicate processing.

**Mandatory controls for webhook endpoints:**

1. **Verify the HMAC-SHA256 signature** on every incoming request using the `X-NexusPay-Signature` header. Reject any request whose signature does not match.
2. **Reject stale timestamps**: discard events where `X-NexusPay-Timestamp` is more than 5 minutes old to prevent replay attacks.
3. **Use HTTPS only**: webhook endpoints must be served over TLS (HTTPS). Plain HTTP endpoints will not receive events in production.

For the full signature verification implementation, see `docs/guides/webhooks_guide.md`.

## TLS Requirements

All API requests must be made over **HTTPS (TLS 1.2 or higher)**. NexusPay rejects plaintext HTTP connections at the infrastructure level. Ensure that:

- Your HTTP client does not disable certificate verification (`verify=True` in Python `requests`, not `rejectUnauthorized: false` in Node.js).
- Your server's TLS configuration for webhook endpoints uses a valid certificate from a trusted CA.

## Fraud Detection

NexusPay performs real-time fraud scoring on all payment requests. You can supplement this with:

- Populating the `customer.email` and `customer.ip_address` fields to provide additional context.
- Using metadata to associate payments with known internal customer identifiers, enabling cross-referencing with your own risk signals.

For further guidance, refer to `docs/guides/customers_guide.md`.

## Security Incident Response

If you suspect a security incident involving your NexusPay integration:

1. Immediately rotate your API keys via the Dashboard.
2. Review your webhook secret and rotate it if there is any risk of exposure.
3. Contact NexusPay security at security@nexuspay.eu with your account ID and a description of the incident.
4. Preserve logs and do not delete any potentially relevant data until the investigation is complete.
