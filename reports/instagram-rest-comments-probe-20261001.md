# Instagram REST comments probe

**Date:** 2026-10-01  
**Verdict:** **SUCCESS — JSON comments returned**

## Request

One read-only Python `httpx` GET was sent to:

`https://www.instagram.com/api/v1/media/3998405548181305448/comments/`

Query parameters were preserved from the supplied cURL:

- `can_support_threading=true`
- `permalink_enabled=false`

The referer, user agent, CSRF/app headers, and session cookie were loaded from
local environment configuration or the supplied browser request context. No
credentials were printed or written. No retry or pagination request was made.

## Response

| Field | Observation |
|---|---|
| HTTP status | `200` |
| Content-Type | `application/json` |
| Response length | `29,751` bytes |
| Valid JSON | Yes |
| Top-level fields | 29 |
| Comment records | 15 |
| GraphQL errors | Not applicable / none |
| `status` | Present |
| Pagination fields | `has_more_comments`, `has_more_headload_comments`, `next_min_id` present |
| Retry | None |

The sanitized machine-readable result is
`data/rest-comments-probe-20261001.json`. The response body itself was not
retained, so comment text, usernames, and opaque cursor values were not saved.

## Boundary

This is evidence that the standalone Python client can retrieve JSON comments
through the observed REST comments route for this media ID. It is separate from
the earlier `PolarisPostCommentsPaginationQuery` request, which returned HTTP
429. This single page does not qualify pagination completeness or access to
arbitrary posts.
