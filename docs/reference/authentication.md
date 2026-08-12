# Authentication

NexusPay authenticates requests using API keys passed in the HTTP `Authorization` header.

## API Key Format

```
Authorization: Bearer sk_live_4xKj9mN2pQrT8vWz
```

All API keys follow this format:

| Prefix        | Type        | Environment |
|---------------|-------------|-------------|
| `sk_live_`    | Secret key  | Live        |
| `sk_test_`    | Secret key  | Sandbox     |
| `pk_live_`    | Publishable | Live        |
| `pk_test_`    | Publishable | Sandbox     |

## Secret vs Publishable Keys

**Secret keys** have full API access: create payments, issue refunds, manage subscriptions, access reports. They must be stored securely on your server and never exposed to clients.

**Publishable keys** are limited to read operations and payment method tokenization. They are safe to embed in frontend JavaScript or mobile apps. A publishable key cannot create a payment directly — it can only create a payment method token, which your server then uses with the secret key.

## Key Rotation

You can create multiple API keys per account and assign them different permission scopes. This allows you to rotate keys without downtime:

1. Create a new key
2. Deploy your application with the new key
3. Revoke the old key

Revoking a key is immediate and irreversible. In-flight requests using a revoked key will fail with `revoked_api_key`.

## Scoped Keys

On Pro and Enterprise plans, API keys can be scoped to specific operations:

| Scope              | Operations allowed                        |
|--------------------|-------------------------------------------|
| `payments:read`    | GET /payments, GET /payments/:id          |
| `payments:write`   | POST /payments, capture, cancel           |
| `refunds:write`    | POST /refunds                             |
| `subscriptions`    | All subscription endpoints                |
| `reports:read`     | GET /reports/*                            |
| `webhooks`         | All webhook endpoints                     |

Scoped keys are not available on Free or Starter plans — those plans only support full-access keys.

## Two-Factor Authentication for Dashboard

API key management in the dashboard requires two-factor authentication (2FA). 2FA can be configured via TOTP (Google Authenticator, Authy) or hardware security keys (FIDO2/WebAuthn).

## Security Best Practices

- Never commit API keys to version control. Use environment variables or a secrets manager.
- Use the principle of least privilege — scope keys to the minimum required operations.
- Rotate keys every 90 days in high-security environments.
- Monitor API key usage in the dashboard — unexpected spikes may indicate a compromised key.
- Use different keys for different environments (development, staging, production).
