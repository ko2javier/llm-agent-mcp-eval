# API Versioning

NexusPay follows a defined versioning policy to ensure that breaking changes are communicated well in advance, giving integrations time to migrate. This guide explains the current version, deprecation timeline, and how to migrate from v1 to v2.

## Current Version

| Version | Status | Release Date | Notes |
|---------|--------|--------------|-------|
| **v2** | Current | **2025-01-15** | Active, fully supported |
| v1 | Deprecated | — | Deprecated **2025-07-01** |

## Versioning Lifecycle

NexusPay versions go through four stages:

1. **Active** — fully supported; new features are added here.
2. **Deprecated** — still functional, but no new features; migration is strongly encouraged.
3. **Sunset** — the version is disabled; all requests return HTTP `410 Gone`.
4. **Removed** — version documentation is archived.

## V1 Deprecation and Sunset Timeline

| Event | Date |
|-------|------|
| v1 deprecated | **2025-07-01** |
| v1 sunset | **2026-01-15** |

As of **2025-07-01**, v1 is deprecated. It continues to function but will receive no updates or new endpoints. All new development must target v2.

As of **2026-01-15**, v1 is sunset. Any request to a v1 endpoint returns:

```
HTTP/1.1 410 Gone

{
  "error": {
    "code": "api_version_sunset",
    "message": "API v1 has been sunset as of 2026-01-15. Please migrate to v2. See https://docs.nexuspay.eu/guides/api_versioning"
  }
}
```

After the sunset date, there is no way to make v1 requests succeed — migration to v2 is mandatory.

## Specifying the API Version

Target a specific version using the base URL path:

| Version | Base URL |
|---------|----------|
| v2 | `https://api.nexuspay.eu/v2` |
| v1 | `https://api.nexuspay.eu/v1` *(deprecated)* |

Alternatively, if your SDK or base URL defaults to `/v2`, include the version header for explicit pinning:

```http
NexusPay-Version: 2025-01-15
```

## Breaking Changes in v2

The following changes from v1 to v2 are breaking — they require code changes in any integration that uses the affected features.

### 1. Pagination: Cursor-Based Replaces Offset-Based

**v1 (offset pagination):**
```
GET /payments?limit=10&offset=40
```

**v2 (cursor pagination):**
```
GET /payments?limit=10&cursor=cur_01HXYZ1234567890
```

v2 responses no longer include `total_count` or `offset`. The `has_more` boolean and `next_cursor` string are the authoritative pagination signals. See `docs/guides/pagination_filtering.md` and `docs/guides/pagination_advanced.md`.

**Migration steps:**
1. Remove any `offset` parameter from list requests.
2. Replace loop conditions that used `offset + limit < total_count` with `has_more === false`.
3. Store `next_cursor` from each response and pass it as `cursor` in the next request.

### 2. Amounts Always in Cents

**v1** accepted amounts in either decimal (`49.99`) or integer (`4999`) format, depending on the endpoint.

**v2** requires amounts to always be expressed as **integers in the smallest currency unit** (cents, pennies, etc.). Decimal values return a `400 invalid_request` error.

| Intended amount | v1 | v2 |
|-----------------|-----|-----|
| €49.99 | `49.99` or `4999` | `4999` (only) |
| £10.00 | `10.00` or `1000` | `1000` (only) |

**Migration steps:**
1. Audit all payment creation, refund, and plan creation calls.
2. Convert any decimal amounts to integers (multiply by 100 for two-decimal currencies).
3. Update your display layer to divide API amounts by 100 before showing to users.

## Non-Breaking Changes

The following changes in v2 are additive and do not require migration work from v1 integrations:

- New response fields on existing objects (e.g., `capture_before` on payment objects).
- New endpoints (e.g., `POST /disputes/:id/evidence`).
- New webhook event types.
- New optional request parameters.

NexusPay commits to not removing existing response fields or changing field types within a major version.

## Migration Checklist

- [ ] Update base URL from `https://api.nexuspay.eu/v1` to `https://api.nexuspay.eu/v2`
- [ ] Replace offset-based pagination with cursor-based pagination across all list calls
- [ ] Ensure all `amount` fields are integers in the smallest currency unit
- [ ] Test all flows in the sandbox with v2 endpoints before switching production traffic
- [ ] Remove any code that reads `total_count` or `offset` from list responses (no longer present in v2)
- [ ] Update SDK to a version that targets v2 (refer to your SDK's changelog)
- [ ] Set a calendar reminder to complete migration before **2026-01-15**

## SDK Version Compatibility

| SDK | v1 support | v2 support |
|-----|-----------|-----------|
| Python SDK ≥ 3.0 | No | Yes |
| Python SDK < 3.0 | Yes | No |
| Node.js SDK ≥ 4.0 | No | Yes |
| Node.js SDK < 4.0 | Yes | No |

Upgrade your SDK alongside the API migration. Running an older SDK against v2 endpoints may produce unexpected errors due to client-side request formatting differences.
