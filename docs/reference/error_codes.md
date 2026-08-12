# Error Codes

All NexusPay API errors follow a consistent structure:

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "param": "string or null",
    "doc_url": "https://docs.nexuspay.io/errors/<code>"
  }
}
```

---

## HTTP Status Codes

| HTTP Status | Meaning                                      |
|-------------|----------------------------------------------|
| 200         | Success                                      |
| 201         | Resource created                             |
| 400         | Bad request — invalid parameters             |
| 401         | Unauthorized — invalid or missing API key    |
| 403         | Forbidden — insufficient permissions         |
| 404         | Resource not found                           |
| 409         | Conflict — duplicate idempotency key         |
| 422         | Unprocessable — business logic error         |
| 429         | Rate limit exceeded                          |
| 500         | Internal server error                        |
| 503         | Service temporarily unavailable              |

---

## Error Code Reference

### Authentication Errors (401)

| Code                  | Description                                              |
|-----------------------|----------------------------------------------------------|
| `invalid_api_key`     | The API key provided is not valid                        |
| `expired_api_key`     | The API key has expired                                  |
| `missing_api_key`     | No API key was provided in the request                   |
| `revoked_api_key`     | The API key has been revoked                             |

### Authorization Errors (403)

| Code                       | Description                                           |
|----------------------------|-------------------------------------------------------|
| `insufficient_permissions` | API key lacks permission for this operation           |
| `plan_limit_exceeded`      | Operation not available on current plan               |
| `sandbox_only`             | Operation only available in sandbox environment       |

### Validation Errors (400)

| Code                    | Description                                             |
|-------------------------|---------------------------------------------------------|
| `missing_required_param`| A required parameter is missing (`param` field set)     |
| `invalid_param_value`   | Parameter value is invalid (`param` field set)          |
| `invalid_currency`      | Currency code not supported                             |
| `amount_too_small`      | Amount is below the minimum (50 cents)                  |
| `amount_too_large`      | Amount exceeds maximum (999,999,99 cents = ~€1M)        |
| `invalid_metadata`      | Metadata exceeds 50 keys or key length exceeds 40 chars |

### Payment Errors (422)

| Code                        | Description                                          |
|-----------------------------|------------------------------------------------------|
| `card_declined`             | Card was declined by the issuer                      |
| `insufficient_funds`        | Card has insufficient funds                          |
| `card_expired`              | Card expiration date has passed                      |
| `incorrect_cvc`             | CVC code is incorrect                                |
| `do_not_honor`              | Generic decline — contact card issuer                |
| `fraudulent`                | Payment blocked by fraud detection                   |
| `capture_window_expired`    | 7-day capture window has passed                      |
| `payment_not_capturable`    | Payment was not created with `capture: false`        |
| `already_captured`          | Payment has already been captured                    |
| `already_cancelled`         | Payment has already been cancelled                   |

### Refund Errors (422)

| Code                        | Description                                          |
|-----------------------------|------------------------------------------------------|
| `refund_window_expired`     | 180-day refund window has passed                     |
| `max_refunds_exceeded`      | Maximum 5 refunds per payment already reached        |
| `refund_amount_exceeds_payment` | Refund amount exceeds original payment          |
| `partial_refund_too_small`  | Partial refund below minimum of 50 cents             |
| `payment_not_refundable`    | Payment is not in a refundable state                 |

### Subscription Errors (422)

| Code                          | Description                                        |
|-------------------------------|----------------------------------------------------|
| `plan_not_found`              | Subscription plan does not exist                   |
| `trial_too_long`              | Trial period exceeds maximum of 90 days            |
| `subscription_already_cancelled` | Subscription is already cancelled              |
| `customer_has_no_payment_method` | Customer has no payment method on file         |

### Rate Limit Errors (429)

| Code                  | Description                                              |
|-----------------------|----------------------------------------------------------|
| `rate_limit_exceeded` | Too many requests. Check `retry_after` in response body  |
| `ip_limit_exceeded`   | IP-level limit of 5,000 req/min exceeded                 |

### Server Errors (500 / 503)

| Code                  | Description                                              |
|-----------------------|----------------------------------------------------------|
| `internal_error`      | Unexpected server error. Contact support if persistent   |
| `service_unavailable` | API temporarily unavailable. Retry with backoff          |
