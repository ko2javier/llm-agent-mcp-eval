# Rate Limits

NexusPay API enforces rate limits per API key, per plan. Limits reset every 60 seconds (rolling window).

## Limits by Plan

| Plan       | Requests/min | Requests/day | Concurrent connections | Webhook endpoints |
|------------|-------------|--------------|----------------------|-------------------|
| Free       | 60          | 1,000        | 5                    | 2                 |
| Starter    | 300         | 10,000       | 20                   | 10                |
| Pro        | 1,000       | 100,000      | 50                   | 50                |
| Enterprise | 10,000      | Unlimited    | 500                  | Unlimited         |

## Limits by Endpoint Category

| Category         | Free | Starter | Pro    | Enterprise |
|------------------|------|---------|--------|------------|
| Payments         | 20/m | 100/m   | 500/m  | 5,000/m    |
| Refunds          | 5/m  | 20/m    | 100/m  | 1,000/m    |
| Subscriptions    | 10/m | 50/m    | 200/m  | 2,000/m    |
| Webhooks (calls) | 10/m | 60/m    | 300/m  | 3,000/m    |
| Reports          | 2/m  | 10/m    | 50/m   | 500/m      |

## Burst Allowance

Each plan has a burst allowance of 2× the per-minute limit for up to 10 seconds. After the burst window, the standard limit applies.

| Plan       | Burst limit | Burst window |
|------------|-------------|--------------|
| Free       | 120 req     | 10s          |
| Starter    | 600 req     | 10s          |
| Pro        | 2,000 req   | 10s          |
| Enterprise | 20,000 req  | 10s          |

## Rate Limit Headers

Every response includes:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1714500060
X-RateLimit-Window: 60
```

`X-RateLimit-Reset` is a Unix timestamp indicating when the current window resets.

## HTTP 429 Response

When the limit is exceeded, the API returns HTTP 429 with:

```json
{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Too many requests. Retry after 23 seconds.",
    "retry_after": 23
  }
}
```

## IP-Level Limits

Regardless of plan, a single IP address is limited to 5,000 requests/minute across all API keys. This limit cannot be increased.
