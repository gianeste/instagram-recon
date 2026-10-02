# Instagram browser response capture

**Updated:** 2026-10-01

## Purpose

`tools/capture_instagram_responses.py` observes ordinary, manually performed
Instagram browsing actions. It is a capture aid, not a request replayer or a
private-endpoint collector. The operator must navigate to authorized test
content, open comments, expand replies, and scroll.

## Run

Install the optional dependency:

```powershell
python -m pip install -e ".[capture]"
```

Start a new headed browser and navigate manually:

```powershell
python -m tools.capture_instagram_responses --output .\data\instagram-captures
```

To observe an already running browser, launch it with a local DevTools
connection and pass the local endpoint without putting cookies in the command:

```powershell
python -m tools.capture_instagram_responses `
  --cdp-url http://127.0.0.1:9222 `
  --target-shortcode DdeY69zlNuQ
```

The utility waits for Enter by default. `--duration N` is available for a
bounded manual experiment. `--redact-usernames` and `--redact-text` preserve
the response shape while reducing public-content retention.

## What is written

`capture-manifest.json` contains operation identity, endpoint kind, status,
content type, response classification, media/parent identifiers when present,
an allowlisted set of pagination inputs, a shape fingerprint, candidate
pagination paths, the full structural result from `response_fixtures.py`, and
qualification flags. JSON responses are written as
sanitized `response-*.json` fixtures. Request headers, cookies, CSRF values,
full form bodies, and non-JSON response bodies are not written. URL query
strings are removed because signed media URLs are unnecessary for comment
schema analysis.

The existing `response_fixtures.inspect_response` function analyzes every JSON
fixture. A restriction response is metadata-only and ends the experiment; the
tool does not retry or attempt to work around it.

## Evidence status

The repository now contains one sanitized child-comment response derived from
the supplied `tree.txt` artifact at
`fixtures/polaris_child_comments_tree.sanitized.json`, plus its reviewed field
map. It validates three reply records, parent IDs, author fields, text,
numeric timestamps, like counts, and the presence of `page_info` fields. The
artifact does not retain request metadata, so its association with
`PolarisPostChildCommentsQuery` is recorded as unverified linkage. It is one
terminal page, not pagination qualification. The prior scripted GraphQL
attempt remains HTTP 429 with a zero-byte response and was not retried. Root
comment fields, cursor advancement, repeated-cursor behavior, branch fan-out,
result ordering, and live completeness are still **UNVERIFIED**. Synthetic
offline tests are not counted as live protocol qualification.

A later supplied root-comment cURL adds request evidence for a continuation
state (`cached_comments_cursor` and `bifilter_token`) and `sort_order=popular`.
It contains no response body or status, so it does not advance any response or
pagination qualification flag.

## Browser-observed root response

An authorized Edge tab was manually navigated to a continuation URL for the
root-comment REST endpoint. The browser exposed a JSON document with
`document.contentType=application/json`, application field `status=ok`, 15
root comments, a reported `comment_count` of 1562, and the fields
`has_more_comments=false`, `has_more_headload_comments=true`, and
`next_min_id` present. A redacted two-item schema projection is retained at
`fixtures/instagram_root_comments_browser.schema.json`; its reviewed mapping
is `fixtures/instagram_root_comments_mapping.json`.

This observation was made through the browser connector's page DOM rather than
the utility's network event hook. The connector did not expose HTTP headers,
response status, or redirect history, and the retained fixture is intentionally
not a complete raw response. It validates the root field paths and value types,
but not cursor advancement, repeated-cursor handling, natural exhaustion, or
live collection completeness. See
`reports/instagram-comment-response-diagnostics.md` for the HTML-versus-JSON
comparison.

The capture utility now also retains an allowlisted `max_id` request input, and
the response inspector recognizes `next_max_id`, `has_more_comments`, and
`has_more_headload_comments` as pagination candidates. This prepares a normal
manual scroll capture for the alternate root mechanism without replaying a
request. The root pagination evaluator reports `CONTINUE`, `COMPLETE`, or
`PARTIAL` offline and does not write SQLite checkpoints; root and reply
completion remain separate until sequential browser fixtures establish the
live transition. Captured `min_id`/`max_id` values remain opaque strings; the
capture utility does not parse or manufacture their internal state.

## Targeted UI continuation diagnostic (2026-10-01)

The capture utility was reviewed and hardened for diagnosis. When attached to
a Playwright/CDP browser it now attaches every available context and page,
counts requests and responses, records failed requests, counts body-read
failures and unexpected response kinds, records target rejections, and keeps
unmatched comment-like paths as path-only diagnostics. It recognizes the
known REST root route, named GraphQL comment/reply operations, alternative
`/comments` routes without a friendly operation name, and GraphQL requests
whose allowlisted variables identify comment pagination. No headers, cookies,
CSRF values, or raw request bodies are written.

The authorized Edge extension session used for this experiment did not expose
a local CDP endpoint, so the utility could not attach to that existing page.
The browser UI was still exercised normally. On `Dd6m2a6Exca`, expanding a
visible reply control changed the UI to `Hide all replies` and displayed one
reply. The post did not expose a root “view all comments” control. On the
visible neighboring post `Dd9MKlfTDho`, the actual comments panel was located
as a 320×402 overflow container. Scrolling it changed the measured scroll
position to 1515, increased its scroll height from 1,917 to 3,124, and added a
sixteenth stable `/c/` comment link after 15 were initially visible. No access
restriction appeared and no “view all comments” control appeared.

This is genuine UI-level evidence of lazy comment content, but it is not a
captured response. The operation, HTTP status, cursor supplied/returned,
response schema, overlap, and termination state therefore remain **UNKNOWN**.
The evidence is consistent with a continuation request that the capture tool
could not observe, but it cannot distinguish that from content already
prefetched by the page. The sanitized observation record is
`data/instagram-probe/ui-continuation-observation.json`. No undocumented
request was replayed and no restricted endpoint was retried.
