# Direct Python Instagram GraphQL probe

**Date:** 2026-10-01  
**Verdict:** **FAILURE — rate limited**

## Request

One read-only `httpx` request was sent to the endpoint from the supplied
browser capture:

- method: `POST`
- endpoint: `https://www.instagram.com/api/graphql`
- operation: `PolarisPostCommentsPaginationQuery`
- target media ID: `3998405548181305448`
- referer: the target post `Dd9MKlfTDho`
- credentials/session values: loaded from the local `.env`; none were printed
  or written to the report
- variables: preserved the captured `after` value as a JSON-encoded string,
  with `before=null`, `first=10`, `last=null`, `media_id`, `sort_order=popular`,
  and the captured Relay login flag
- request encoding: `application/x-www-form-urlencoded`

The request used the captured operation name, document ID from local
configuration, CSRF/session headers, and relevant browser request headers. No
pagination loop or retry was performed.

## Response

| Field | Observation |
|---|---|
| HTTP status | `429` |
| Content-Type | `text/plain` |
| Response length | `0` bytes |
| Valid JSON | No |
| Top-level fields | None |
| Comment records | None |
| GraphQL errors | None; the body was empty |
| Classification | `rate_limited` |
| Retries | None |

Because the server returned HTTP 429, the experiment stopped immediately. No
HTML classification was applicable and no follow-up request was made.

The machine-readable sanitized result is
`data/direct-graphql-probe-20261001.json`.

The one-request utility is `tools/probe_direct_graphql.py`. It reads the
existing local session configuration and requires the captured raw JSON cursor
through `IG_POST_COMMENTS_AFTER`; it never prints that value and never loops.

This establishes that the standalone Python client reached Instagram and was
stopped by a rate limit. It does not establish whether the session would have
returned comment JSON outside the restriction window, and it does not qualify
the internal operation for repeated or production use.
