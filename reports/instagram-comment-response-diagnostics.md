# Instagram comment response diagnostics

**Updated:** 2026-10-01

## Scope and safety boundary

This comparison uses the already saved direct-probe HTML and one ordinary,
authorized Edge browser observation. The previously rate-limited GraphQL
operation was not retried. No cookies, headers, cursors, comment text,
usernames, profile URLs, or credential-like values are retained in the
artifacts below.

The existing Playwright capture utility was not attached to the user's Edge
extension tab, so the browser observation is recorded as
`genuine_authorized_browser_dom_response`, not as a `capture-manifest.json`
network event. The DOM still exposes the response document type and JSON
structure; it does not expose response headers or a redirect chain.

## Direct Python probe that returned HTML

Evidence is in `data/instagram-probe/root-comments-response.metadata.json` and
the sanitized copy at
`data/instagram-probe/root-comments-response.sanitized.html`.

| Diagnostic | Observation |
|---|---|
| Request | `GET /api/v1/media/{media_id}/comments/` with `can_support_threading=true` and `sort_order=popular`; no continuation token was supplied |
| HTTP result | `200`, `text/html`, 651,190 bytes on the saved run (the earlier run was 651,207 bytes) |
| Final URL | Same endpoint path; the probe used `follow_redirects=false` |
| Redirect history | Not captured; no redirect is indicated by the recorded final URL |
| HTML title | `Instagram` |
| Canonical URL | No canonical link in the retained markup |
| Document structure | HTML5 doctype, `html[lang=en]`, `head`, `body`, static Instagram assets, splash-screen, stylesheets, and script tags |
| Login/challenge markers | No `login`, `log in`, `sign up`, `checkpoint`, `challenge`, `captcha`, `suspended`, or error marker in retained visible text |
| Embedded JSON | Not observed in the retained sanitized markup |
| Bootstrap data | **UNKNOWN**: script contents were removed by the sanitizer, so the original bootstrap payload cannot be assessed |
| Credential markers | None in the retained sanitized artifact |

**Classification: `NORMAL_APPLICATION_SHELL` (moderate confidence).** The
title, doctype, language, splash screen, static assets, and absence of access or
error indicators match Instagram's normal application document shell. The
artifact is not sufficient to prove what the original scripts would have
bootstrapped, and it does not prove that the comments request was accepted as
an API request. It is not classified as an authentication/challenge page or an
error document from the evidence retained.

## Browser response observed during normal browsing

The browser was on a continuation URL for the same root-comment endpoint. It
included the query keys `can_support_threading`, `min_id`, and `sort_order`.
The browser DOM exposed:

| Diagnostic | Observation |
|---|---|
| Final URL | `/api/v1/media/{media_id}/comments/` with continuation state (query values redacted) |
| Redirect history | Not available from the DOM observation; no redirect was indicated |
| HTTP status | Not exposed by the browser connector; the body contains application field `status: "ok"` |
| Content type | `application/json` from `document.contentType` |
| HTML title/canonical | Empty title; no canonical link (the document is JSON, not HTML) |
| Body | Valid JSON document, 15 root comments in the observed page |
| Reported count | `comment_count: 1562` |
| Root fields | `pk`, `strong_id__`, `text`, `created_at`, `created_at_utc`, `comment_like_count`, `child_comment_count`, `user`, and child-preview flags |
| User fields | `pk`, `id`, `username`, verification/privacy flags, and profile metadata |
| Pagination fields | `has_more_comments: false`, `has_more_headload_comments: true`, and a present `next_min_id` |
| Ordering flags | `sort_order: "popular"`, `is_ranked: true` |

The retained projection is
`fixtures/instagram_root_comments_browser.schema.json`; it contains two
redacted samples and the observed field/type shape, not the full raw page.
The reviewed map is `fixtures/instagram_root_comments_mapping.json`.

## Pagination state evaluation

`instagram_collector.root_pagination.evaluate_root_comment_pagination` is an
offline evaluator only. It keeps `next_max_id` and `next_min_id` as opaque
strings, accepts caller-provided seen-cursor/page state, and reports one of
`CONTINUE`, `COMPLETE`, or `PARTIAL`.

The reviewed browser fixture evaluates to `CONTINUE`: the ordinary comments
mechanism is explicitly false, while the headload mechanism is true and has a
`next_min_id`. `COMPLETE` requires both mechanisms to be explicitly false with
no contradictory cursor. Missing flags/cursors, repeated cursors, repeated
pages, duplicate record IDs, invalid types, and multiple active mechanisms are
`PARTIAL`.

`compare_root_comment_pages` compares two sanitized fixtures for opaque cursor
transition, record overlap, and duplicate-page identity. It cannot prove that
the second request used the first cursor unless request metadata from both
responses is captured.

The existing SQLite checkpoints are not used by this evaluator. Root and reply
completion remain separate; no web traversal is wired until a genuine
continuation sequence establishes which mechanism is traversed and how it
terminates.

## Sorting and coverage

The observed page reports `sort_order=popular` and `is_ranked=true`. That is
evidence that this response is a ranked/popularity-oriented view, not a
chronological stream. There is no paired `sort_order=recent` or chronological
fixture, so ordering and stability are unverified. The page contains 15 records
while reporting 1,562 comments; it cannot establish that all comments are
covered or that ranked pagination eventually visits every record. Popularity
ranking may change membership between pages, so overlap and cursor advancement
must be measured from sequential browser fixtures before claiming coverage.

**Classification: `SUCCESSFUL_JSON_APPLICATION_RESPONSE` (body-level
evidence).** It is a root-comment page with normalized application status and
comment records. Its HTTP status and headers remain unverified because the
browser connector exposed only the document DOM.

## Structural comparison

The two results are different observations:

* The direct probe asked for an initial root page without `min_id` and received
  the normal HTML application shell.
* The browser observation loaded a continuation state with `min_id` and
  displayed the endpoint's JSON comment envelope.

This establishes that the HTML body is not proof that the endpoint always
returns HTML. It also does not identify a single cause. The changed request
state and browser navigation context are evidence-backed differences; the
available artifacts do not isolate authentication, headers, redirects,
cookies, or rate limiting as the cause. No request was replayed to test those
hypotheses.

The browser page is not an initial-page/continuation pair. Therefore cursor
advancement, repeated-cursor handling, natural exhaustion, and complete root
coverage remain unqualified. `has_more_comments=false` coexists with
`has_more_headload_comments=true` and a next cursor, so treating the first flag
as complete exhaustion would be incorrect.

## Qualification result

| Question | Result |
|---|---|
| Is the 651 KB HTML an auth/challenge page? | No such marker is present in the sanitized evidence |
| Is it an error/fallback document? | No error marker; the structure matches the normal Instagram shell |
| Is it JSON comment data? | No; the direct probe is HTML |
| Can the browser receive JSON comment data? | Yes, one continuation page was observed |
| Is the root REST schema validated? | Yes for the reviewed redacted projection; raw response retention is intentionally partial |
| Is root pagination validated? | No; only one continuation page is available; the evaluator is offline-only |
| Is live collection qualified? | No |

The next required experiment is a fresh, manually driven capture through the
existing utility: initial root response, one scroll continuation, one reply
branch, one reply continuation, and a terminal page. Preserve both root
cursor fields and safe request inputs (`max_id`/`min_id`) in the manifest. Stop
on 401/403/429, challenge, checkpoint, or login responses; do not replay a
captured request.
