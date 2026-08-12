# Reporting Guide

The NexusPay Reports API provides aggregated financial summaries suitable for accounting, reconciliation, and business analytics. This guide covers the summary endpoint parameters, granularity options, date range limits, and how to combine reporting data with detailed transaction lists.

## Overview

NexusPay offers two complementary approaches to financial data:

| Approach | Use case | Endpoint |
|----------|---------|----------|
| **Reports API** | Aggregated totals, periodic summaries, accounting exports | `GET /reports/summary` |
| **List endpoints** | Individual transaction details, filtering, reconciliation | `GET /payments`, `GET /refunds` |

For most accounting workflows, start with the Reports API to get period totals, then use list endpoints to retrieve the underlying transactions if line-item detail is required.

## Summary Report Parameters

```
GET /reports/summary
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string (ISO 8601 date) | Yes | Start of the reporting period, inclusive |
| `end_date` | string (ISO 8601 date) | Yes | End of the reporting period, inclusive |
| `granularity` | string | No | `day`, `week`, or `month`. Default: `day` |
| `currency` | string | No | Filter to a specific currency. Omit for all currencies |
| `timezone` | string | No | IANA timezone for period boundaries. Default: `UTC` |

### Date Range Limit

The maximum date range for a single report request is **365 days**. Requests spanning more than 365 days return a `400 invalid_request` error. For multi-year data, make multiple requests with non-overlapping date ranges and aggregate the results in your application.

```
GET /reports/summary?start_date=2025-01-01&end_date=2025-12-31&granularity=month
```

## Granularity Options

### Daily (`granularity=day`)

Returns one data point per calendar day. Suitable for operational monitoring and daily reconciliation.

```
GET /reports/summary?start_date=2025-06-01&end_date=2025-06-07&granularity=day&currency=EUR
```

**Response:**
```json
{
  "data": [
    {
      "period": "2025-06-01",
      "currency": "EUR",
      "total_payments": 47,
      "total_amount": 231500,
      "total_refunds": 2,
      "refund_amount": 8998,
      "net_amount": 222502,
      "dispute_count": 0
    },
    {
      "period": "2025-06-02",
      "currency": "EUR",
      "total_payments": 53,
      "total_amount": 268900,
      "total_refunds": 1,
      "refund_amount": 4999,
      "net_amount": 263901,
      "dispute_count": 1
    }
  ]
}
```

### Weekly (`granularity=week`)

Returns one data point per ISO week (Monday–Sunday). Useful for weekly business reviews.

```
GET /reports/summary?start_date=2025-06-01&end_date=2025-06-30&granularity=week
```

The `period` field uses the ISO week start date (Monday) as the label.

### Monthly (`granularity=month`)

Returns one data point per calendar month. Suitable for monthly financial closes and VAT reporting.

```
GET /reports/summary?start_date=2025-01-01&end_date=2025-12-31&granularity=month
```

The `period` field uses `YYYY-MM` format.

## Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `period` | string | Period identifier (date, week start, or month) |
| `currency` | string | Currency code for this row |
| `total_payments` | integer | Count of successful payments |
| `total_amount` | integer | Sum of captured amounts (smallest unit) |
| `total_refunds` | integer | Count of processed refunds |
| `refund_amount` | integer | Sum of refund amounts (smallest unit) |
| `net_amount` | integer | `total_amount` minus `refund_amount` |
| `dispute_count` | integer | Count of disputes opened in this period |

## Exporting Data for Accounting

### Generating a Monthly Export

For accounting system imports, request monthly granularity for the relevant fiscal period:

```
GET /reports/summary?start_date=2025-01-01&end_date=2025-12-31&granularity=month&currency=EUR
```

Accept the response as JSON and transform it in your export pipeline, or use the Dashboard's CSV export feature under **Reports → Export** for one-off downloads.

### VAT Reporting

NexusPay does not calculate or report VAT — this is your responsibility as the merchant. Use the reporting data to derive gross revenue, then apply the applicable VAT rates for each jurisdiction based on the customer's billing country, which you should capture in payment metadata.

## Combining Reports with List Endpoints

The Reports API provides totals; the list endpoints provide line items. Use them together for complete reconciliation:

**Step 1 — Get period total:**
```
GET /reports/summary?start_date=2025-06-01&end_date=2025-06-30&granularity=month&currency=EUR
```

**Step 2 — Retrieve individual payments for the same period:**
```
GET /payments?created_after=2025-06-01T00:00:00Z&created_before=2025-06-30T23:59:59Z&currency=EUR&status=succeeded
```

Paginate through all results using `has_more` and `cursor` — see `docs/guides/pagination_filtering.md` and `docs/guides/pagination_advanced.md`.

**Step 3 — Verify totals match.** If the sum of individual payment amounts equals the `total_amount` from the report, reconciliation is complete.

## Rate Limits for Reporting Requests

Report generation is resource-intensive. Long date ranges at daily granularity may take several seconds to process. If you are generating reports programmatically, space out requests and respect the rate limits defined in `docs/reference/rate_limits.md`. Consider scheduling report generation during off-peak hours.
