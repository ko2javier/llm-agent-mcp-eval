# Pagination and Filtering

All list endpoints in NexusPay use cursor-based pagination. This approach is more reliable than offset pagination for large datasets and real-time data.

## How Cursor Pagination Works

Instead of requesting "page 2", you request "everything after item X". The API returns a cursor pointing to the last item in the current page, which you pass in the next request.

```json
GET /payments?limit=10

{
  "data": [ ... ],
  "has_more": true,
  "next_cursor": "pay_9Kx2mN7pQr"
}
```

To fetch the next page:

```
GET /payments?limit=10&starting_after=pay_9Kx2mN7pQr
```

When `has_more` is `false`, you have reached the last page.

## Why Not Offset Pagination?

Offset pagination (`?page=2&per_page=10`) has a fundamental problem with real-time data: if a new payment is created between your first and second request, every item shifts by one position, causing duplicates or skipped items. Cursor pagination avoids this entirely.

## Page Size

The `limit` parameter controls how many items are returned per page.

- Default: **10**
- Maximum: **100**
- Minimum: **1**

For bulk data exports, use the maximum page size to minimize the number of requests and stay within rate limits.

## Filtering

List endpoints support filters via query parameters.

### Payments

| Filter         | Type    | Description                                      |
|----------------|---------|--------------------------------------------------|
| `status`       | string  | Filter by status: `pending`, `succeeded`, `failed`, `cancelled` |
| `customer_id`  | string  | Payments for a specific customer                 |
| `from`         | date    | Created on or after this date (ISO 8601)         |
| `to`           | date    | Created on or before this date (ISO 8601)        |
| `currency`     | string  | ISO 4217 currency code                           |
| `min_amount`   | integer | Minimum amount in cents                          |
| `max_amount`   | integer | Maximum amount in cents                          |

### Refunds

| Filter       | Type   | Description                    |
|--------------|--------|--------------------------------|
| `payment_id` | string | Refunds for a specific payment |
| `from`       | date   | Created on or after this date  |
| `to`         | date   | Created on or before this date |

### Subscriptions

| Filter        | Type   | Description                              |
|---------------|--------|------------------------------------------|
| `customer_id` | string | Subscriptions for a specific customer    |
| `status`      | string | `active`, `cancelled`, `past_due`, `trialing` |
| `plan_id`     | string | Subscriptions on a specific plan         |

## Sorting

By default, all lists are sorted by creation date, newest first (`created_at DESC`). To reverse the order, pass `order=asc`.

## Date Ranges

Date filters accept ISO 8601 format: `2025-03-15` or `2025-03-15T14:30:00Z`. If no timezone is specified, UTC is assumed.

The maximum date range for list queries is **365 days**. Requests spanning more than 365 days will return a validation error. For longer ranges, use the Reports API.

## Combining Filters

Filters are combined with AND logic. A payment must match all specified filters to be included.

```
GET /payments?status=succeeded&currency=EUR&from=2025-01-01&to=2025-03-31&limit=100
```

This returns up to 100 succeeded EUR payments created in Q1 2025.
