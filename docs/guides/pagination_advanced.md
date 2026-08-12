# Advanced Pagination Patterns

NexusPay uses cursor-based pagination across all list endpoints. This guide covers patterns for fetching all records in a loop, terminating iteration correctly, staying within rate limits during bulk fetches, and running parallel paginated queries.

For the fundamentals of cursor syntax and basic filtering, see `docs/guides/pagination_filtering.md`.

## Pagination Parameters Recap

| Parameter | Default | Maximum |
|-----------|---------|---------|
| `limit` | **10** | **100** |
| `cursor` | — (first page) | — |

All list responses include:

```json
{
  "data": [...],
  "has_more": true,
  "next_cursor": "cur_01HXYZ1234567890"
}
```

## Pattern 1 — Fetching All Records in a Loop

Use `has_more` as your termination condition. When `has_more` is `false`, you have retrieved the last page and must stop.

### Python

```python
import nexuspay

def fetch_all_payments(filters: dict) -> list:
    all_payments = []
    cursor = None

    while True:
        page = nexuspay.payments.list(
            limit=100,
            cursor=cursor,
            **filters
        )
        all_payments.extend(page.data)

        if not page.has_more:
            break

        cursor = page.next_cursor

    return all_payments

# Example: fetch all EUR payments in June
payments = fetch_all_payments({
    "currency": "EUR",
    "created_after": "2025-06-01T00:00:00Z",
    "created_before": "2025-06-30T23:59:59Z",
    "status": "succeeded"
})
```

### JavaScript / Node.js

```javascript
async function fetchAllPayments(filters) {
  const allPayments = [];
  let cursor = null;

  while (true) {
    const page = await nexuspay.payments.list({
      limit: 100,
      cursor,
      ...filters,
    });

    allPayments.push(...page.data);

    if (!page.has_more) break;
    cursor = page.next_cursor;
  }

  return allPayments;
}
```

**Termination condition:** Always check `has_more === false` — do not use an empty `data` array as your sentinel. On the last page, `data` may contain records but `has_more` will be `false`.

## Pattern 2 — Rate-Limit-Aware Pagination

On accounts with lower rate limit tiers, rapid sequential pagination can exhaust your request quota. Add a short delay between pages to stay within limits.

```python
import time

def fetch_all_payments_throttled(filters: dict, delay_ms: int = 200) -> list:
    all_payments = []
    cursor = None

    while True:
        page = nexuspay.payments.list(limit=100, cursor=cursor, **filters)
        all_payments.extend(page.data)

        if not page.has_more:
            break

        cursor = page.next_cursor
        time.sleep(delay_ms / 1000)  # convert ms to seconds

    return all_payments
```

Monitor the `X-RateLimit-Remaining` response header to adjust your delay dynamically:

```python
def adaptive_delay(response_headers: dict):
    remaining = int(response_headers.get("X-RateLimit-Remaining", 1000))
    if remaining < 100:
        time.sleep(0.5)   # slow down significantly when close to limit
    elif remaining < 500:
        time.sleep(0.1)   # mild throttling
    # else: no delay needed
```

For rate limit tiers and burst window details, refer to `docs/reference/rate_limits.md`.

## Pattern 3 — Parallel Pagination for Multiple Filters

When you need to fetch records across several independent dimensions simultaneously (e.g., multiple currencies or date ranges), you can paginate each dimension in parallel.

```python
import asyncio
import aiohttp

async def fetch_currency_payments(session, currency: str) -> list:
    payments = []
    cursor = None

    while True:
        params = {"currency": currency, "limit": 100}
        if cursor:
            params["cursor"] = cursor

        async with session.get("/payments", params=params) as resp:
            page = await resp.json()

        payments.extend(page["data"])
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]

    return payments

async def fetch_all_currencies():
    currencies = ["EUR", "GBP", "USD", "CHF", "SEK", "NOK", "DKK"]

    async with aiohttp.ClientSession(
        base_url="https://api.nexuspay.eu/v2",
        headers={"Authorization": "Bearer sk_live_your_key"}
    ) as session:
        tasks = [fetch_currency_payments(session, c) for c in currencies]
        results = await asyncio.gather(*tasks)

    return {c: payments for c, payments in zip(currencies, results)}
```

**Caution:** Parallel requests multiply your rate limit consumption proportionally. With 7 concurrent currency paginations, each page of results is 7 requests counted against your quota simultaneously. Monitor `X-RateLimit-Remaining` carefully or limit concurrency.

## Pattern 4 — Resumable Pagination

For large exports that may span multiple process runs (e.g., a nightly job that should resume on failure), persist the last-seen cursor to durable storage:

```python
def export_payments_resumable(job_id: str, filters: dict):
    cursor = db.get_export_cursor(job_id)  # None if not started

    while True:
        page = nexuspay.payments.list(limit=100, cursor=cursor, **filters)
        db.save_export_batch(job_id, page.data)

        if not page.has_more:
            db.mark_export_complete(job_id)
            break

        cursor = page.next_cursor
        db.save_export_cursor(job_id, cursor)  # persist before next iteration
```

Persist the cursor **after** processing each page, not before. This ensures that if the process crashes mid-page, you reprocess the current page rather than skipping it (idempotent batch inserts handle the duplication).

## Common Mistakes

| Mistake | Consequence | Fix |
|---------|-------------|-----|
| Using `data` being empty as loop termination | Stops prematurely on partial final pages | Use `has_more === false` |
| Not persisting cursor before next request | Skips or duplicates records on crash | Persist cursor to durable storage |
| Generating a new cursor from scratch on retry | Restarts from page 1, duplicating records | Reuse the persisted cursor |
| Ignoring rate limit headers | Rate limit errors mid-export | Monitor `X-RateLimit-Remaining` |
| Requesting `limit` > 100 | `400 invalid_request` error | Cap at 100 per page |
