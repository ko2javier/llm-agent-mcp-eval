# Multi-Currency Guide

NexusPay supports accepting payments in multiple currencies across the European market and beyond. This guide explains which currencies are supported, how amounts are handled, and how settlement works.

## Supported Currencies

| Currency | Code | Smallest Unit | Notes |
|----------|------|---------------|-------|
| Euro | `EUR` | cent (1/100) | Primary settlement currency |
| US Dollar | `USD` | cent (1/100) | |
| Pound Sterling | `GBP` | penny (1/100) | |
| Swiss Franc | `CHF` | rappen (1/100) | |
| Swedish Krona | `SEK` | öre (1/100) | |
| Norwegian Krone | `NOK` | øre (1/100) | |
| Danish Krone | `DKK` | øre (1/100) | |

All `amount` values in the API must be expressed in the **smallest currency unit** (cents, pennies, etc.):

| Amount you want to charge | Correct API value |
|---------------------------|-------------------|
| €10.00 | `1000` |
| $49.99 | `4999` |
| CHF 25.50 | `2550` |
| SEK 150.00 | `15000` |

## NexusPay Does Not Convert Currencies

**NexusPay does not perform currency conversion.** The `currency` field you specify in the payment request is the currency in which the customer is charged. NexusPay passes this charge to the card network exactly as submitted.

This means:

- If you charge `{ "amount": 1000, "currency": "EUR" }`, the customer is billed €10.00 by their bank.
- If the customer's card is issued in GBP, their bank applies its own foreign exchange rate to convert the charge — NexusPay has no control over this rate.
- Your settlement (what NexusPay pays out to you) depends on your configured **settlement currency** — see below.

**Best practice: charge the customer in their local currency.** This improves conversion rates, reduces card decline rates caused by foreign transaction blocks, and provides a better customer experience by eliminating surprise FX fees on the customer's bank statement.

```python
def determine_charge_currency(customer_country: str) -> str:
    country_to_currency = {
        "DE": "EUR", "FR": "EUR", "NL": "EUR", "ES": "EUR",
        "GB": "GBP",
        "US": "USD",
        "CH": "CHF",
        "SE": "SEK",
        "NO": "NOK",
        "DK": "DKK",
    }
    return country_to_currency.get(customer_country, "EUR")
```

## Settlement Currency

Your settlement currency is the currency in which NexusPay pays out your earnings to your bank account. It is configured at the account level in the Dashboard under **Settings → Payouts**.

If you charge customers in multiple currencies but your settlement currency is `EUR`, NexusPay converts foreign currency receipts to EUR at the time of settlement using the applicable interbank exchange rate, minus any applicable FX conversion fee. Refer to your merchant agreement for the exact fee schedule.

To avoid conversion fees, configure a separate bank account and payout destination for each currency you accept.

## Multi-Currency Reporting

When generating reports across multiple currencies, amounts are not aggregated into a single total — each currency is reported separately. This prevents misleading summaries that mix different denominations.

```
GET /reports/summary?start_date=2025-06-01&end_date=2025-06-30&granularity=month
```

**Response:**
```json
{
  "data": [
    {
      "period": "2025-06",
      "currency": "EUR",
      "total_payments": 1420,
      "total_amount": 7832100,
      "total_refunds": 28,
      "net_amount": 7644300
    },
    {
      "period": "2025-06",
      "currency": "GBP",
      "total_payments": 312,
      "total_amount": 1654200,
      "total_refunds": 5,
      "net_amount": 1621800
    }
  ]
}
```

All amounts in report responses are in the smallest unit of each respective currency.

## Creating Multi-Currency Payments

Specify the currency explicitly on every payment request. There is no default — omitting `currency` returns a `400 invalid_request` error.

```json
POST /payments

{
  "amount": 2550,
  "currency": "CHF",
  "source": "tok_01HABC1234567890",
  "description": "Zurich Workshop — Ticket #887"
}
```

## Refunds in Multiple Currencies

A refund is always issued in the **same currency** as the original payment. You cannot refund in a different currency. See `docs/guides/refunds_guide.md` for refund constraints and error codes.

## Filtering Payments by Currency

Use the `currency` filter on list endpoints to retrieve payments in a specific currency:

```
GET /payments?currency=SEK&status=succeeded
```

For pagination and filter syntax, see `docs/guides/pagination_filtering.md`.

## Testing Multi-Currency Payments

All test card numbers work with all supported currencies in the sandbox. To test a CHF payment:

```json
POST /payments

{
  "amount": 2550,
  "currency": "CHF",
  "source": "tok_test_4242424242424242"
}
```

Sandbox payouts are simulated and do not involve real bank transfers or FX conversion.
