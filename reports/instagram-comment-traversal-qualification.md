# Instagram comment traversal qualification

**Updated:** 2026-10-01

## Evidence inventory

| Required response | Available evidence | Provenance | Qualification |
|---|---|---|---|
| Initial root-comment response | None | Missing | Initial-page request/response pairing unverified |
| Subsequent root-comment response | One JSON continuation page shown in an authorized browser; a separate UI scroll added lazy comment nodes | Genuine browser DOM observations; redacted two-item schema projection and UI diagnostic record retained | Root field mapping validated; cursor advancement and response operation unverified |
| Initial child-reply response | One child-shaped JSON artifact | Imported `tree.txt`; request metadata absent | Reply fields validated; initial-page role unverified |
| Subsequent child-reply response | None | Missing | `after`/`before` behavior unverified |
| Terminal root response | None | Missing | Root termination unverified; the observed page has `has_more_comments=false` but also `has_more_headload_comments=true` and `next_min_id` |
| Terminal child response | One page reports `has_next_page=false`, `end_cursor=null` | Imported artifact; no preceding page | Terminal shape observed, natural exhaustion unqualified |

The machine-readable provenance record is
`fixtures/fixture-provenance.json`. There is no Playwright
`capture-manifest.json` for that earlier fixture, so no response was captured
by the new utility at that time. The imported child artifact is not
synthetic, but its capture source and request/response linkage cannot be
independently verified here.

### Subsequent bounded REST qualification

On 2026-10-01, a separate authorized Python REST run observed seven sequential
JSON root pages for media `3998405548181305448`. The sequence contained 93
unique IDs with no cross-page overlap, six advancing opaque `next_min_id`
cursors, and a page-7 terminal response with both continuation flags false.
This qualifies the observed headload protocol sequence and its natural
exhaustion, but not reported-count consistency or complete ranked-view
coverage. See [the extended REST pagination report](instagram-rest-pagination-qualification-12p-20261001.md).

A separate one-shot local request to the root REST path, using the local
session configuration and no continuation token, returned HTTP `200` with
`text/html` and about 651 KB. The raw body was not retained; a sanitized HTML
copy is at `data/instagram-probe/root-comments-response.sanitized.html` with
metadata beside it. The safe copy is classified as Instagram's normal
application shell, not a JSON comment response. A browser continuation page
then exposed a JSON envelope with 15 comments, `status=ok`, and explicit
pagination fields. See [the response diagnostics report](instagram-comment-response-diagnostics.md).

The root evaluator now treats `has_more_comments + next_max_id` and
`has_more_headload_comments + next_min_id` as separate mechanisms. The observed
page is `CONTINUE`, not complete: the first mechanism is false and the second
is true with an opaque cursor. Missing, repeated, contradictory, or duplicate
page state is reported `PARTIAL`; only two explicit false flags with no cursor
are `COMPLETE`. This is fixture-driven logic and is not a live traversal.

## What is validated

The reviewed root mapping normalizes two redacted sample records through the existing
model and confirms string IDs, null root parent IDs, author paths, text,
numeric epoch timestamps, like counts, and reported child counts. It is a
schema projection from a genuine browser response, not a complete raw page.

The reviewed child mapping normalizes three records through the existing
model. It confirms string comment IDs from `node.pk`, non-null parent IDs from
`node.parent_comment_id`, author IDs/usernames, text, numeric epoch timestamps,
`comment_like_count`, and explicit null `child_comment_count`. The response
contains `page_info.has_next_page` and `page_info.end_cursor`.

The existing `StateStore` already provides stable-ID upserts, observations,
independent reply checkpoints by parent, repeated-cursor detection, and resume
semantics for the documented API collector. Those state-machine tests are
synthetic documented-API tests; they do not qualify the internal web routes.
No web root/reply traversal was wired to the store because the initial root
page, a root continuation sequence, and child continuation contracts are not
observed as a complete sequence.

The new offline comparison helper measures opaque cursor transition, page
overlap, and duplicate-page fingerprints between two fixtures. There are no
two genuine root fixtures yet, so no cursor advancement or ranked-coverage
claim is made. The observed `sort_order=popular` and `is_ranked=true` flags are
evidence of a ranked view only; they do not establish chronological ordering
or full comment coverage.

## Targeted capture-coverage diagnostic

The capture utility now attaches all available Playwright contexts/pages when a
CDP browser is supplied. It counts requests and responses, captures failed
requests, records body-read failures and unexpected content types, preserves
alternative comment-like paths, and records target rejections without storing
credentials. Its target association uses the request referer/frame and the
response frame URL. These changes are covered by the offline capture tests.

The authorized Edge extension session used for the normal UI experiment had no
CDP endpoint, so no `capture-manifest.json` could be produced for that session.
The UI itself was exercised on the original post and one visible neighboring
post. Reply expansion worked on the original post. On the neighboring post,
scrolling the actual overflow comments panel changed `scrollTop` to 1515,
increased `scrollHeight` from 1,917 to 3,124, and exposed 16 stable comment
links after 15 initially visible links. This establishes lazy UI content, but
not a network response: the operation name, status, cursor transition, body,
overlap, and pagination flags were not exposed. The diagnostic outcome is
therefore **UNKNOWN at the network level** (consistent with a continuation
request missed by the unavailable capture hook); it is not classified as live
root pagination qualification. See
`data/instagram-probe/ui-continuation-observation.json` and
`reports/instagram-browser-capture.md`.

## Completeness status

| Field | Status |
|---|---|
| `root_protocol_complete` | **false / unverified** |
| `replies_protocol_complete` | **false / unverified** |
| `reported_count_consistent` | **unverified** |
| `collection_partial` | **true** |
| `termination_reason` | `missing_initial_root_and_cursor_transition` |

The imported child page must not be treated as a complete branch: there is no
parent request metadata or continuation sequence. The root browser page is a
single continuation observation, not a complete root traversal.

## Next required live experiment

Run the capture utility against an authorized test post and manually perform
one complete sequence: open comments, save the first root response, scroll to
obtain a second root response, expand one reply branch, save its first child
response, request a continuation, and capture the terminal page. Preserve the
capture manifest with each sanitized fixture. Stop immediately on 401/403/429,
checkpoint, challenge, or login responses; do not replay requests.

Until that sequence exists, no complete root/reply collection, cursor
advancement, or ranked-coverage claim is made. Latest offline suite: **62
passed**.
