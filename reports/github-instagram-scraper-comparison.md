# Instagram legacy scraper comparison

**Date:** 2026-10-01  
**Targets tested:** `Dd9MKlfTDho` and `Dd6m2a6Exca`  
**Overall result:** `instacomments` completed one legacy GraphQL cursor chain. `InstaScrape` returned comment JSON for 13 pages, then stopped on HTTP 572 before natural exhaustion. The query hash is demonstrably functional for this session, but full corpus coverage is not established.

## Findings

Both GitHub projects use the same request protocol: `GET https://www.instagram.com/graphql/query/`, query hash `97b41c52301f77ce508f55e66d17620e`, and variables `shortcode`, `first=50`, then `after` for continuation. They are different client implementations of the same historical operation, not independent protocol evidence.

On `Dd9MKlfTDho`, each returned HTTP 200 JSON with 24 parent edges and an available next cursor. On `Dd6m2a6Exca`, `instacomments` followed 33 pages to `has_next_page=false` and counted 1,535 distinct parent comment IDs. `InstaScrape` advanced through 13 JSON pages (607 distinct IDs in the raw edges); its 14th request returned HTTP 572, `text/html`, and zero bytes. That run stopped without retrying. The cause of 572 is unknown.

The live runs prove that this legacy hash can return real comment records with the configured session. They do not prove that either project can retrieve every comment in Instagram's corpus: the reported total count was not recorded or reconciled, and the successful view's coverage semantics are unknown. `InstaScrape` did not reach a terminal cursor.

Our collector is a separate design. Its one-shot internal web GraphQL operation uses `POST /api/graphql` and `PolarisPostCommentsPaginationQuery`, not this legacy hash; its latest request returned HTTP 429 with no body or comments. A separate internal REST diagnostic did reach a seven-page terminal sequence on `Dd9MKlfTDho` with 93 unique IDs, but did not reconcile the reported count and is not an integrated collector path. The documented Graph API collector was not live-tested.

## Source and test environment

The isolated upstream snapshots still match the public `main` heads checked with `git ls-remote` on 2026-10-01.

| Project | Current `main` commit | Python | HTTP library in test environment |
|---|---|---:|---|
| `AMINE1921/instacomments` | [`828a380fa983806aa6d57ed7d565842ce44610f2`](https://github.com/AMINE1921/instacomments/tree/828a380fa983806aa6d57ed7d565842ce44610f2) | 3.13.5 | `requests 2.34.2` |
| `kaifcodec/InstaScrape` | [`97b2f75036484f0f8781d92301ca42152aaf9c4a`](https://github.com/kaifcodec/InstaScrape/tree/97b2f75036484f0f8781d92301ca42152aaf9c4a) | 3.13.5 | `httpx 0.28.1`, `h2 4.4.1` |
| `instagram-recon` | Source commit unavailable; this checkout has no `.git` metadata. Project version `0.1.0`. | 3.13.5 | `httpx 0.28.1` |

The configured web session was mapped in memory to the cookie fields required by each request helper. No cookie values were copied into either upstream tree, printed, or retained. Both legacy tests used the same user agent from the local configuration. No login, proxy rotation, challenge handling, or retries were used.

The harness called each project's original one-page GraphQL request function using its native HTTP library, then supplied the returned cursor sequentially. It did not invoke the normal CLIs. This avoids `InstaScrape`'s interactive login/authentication refresh and retry flow. A 100-page safety limit was set and not reached by the completed `instacomments` run.

Local test-copy changes were limited to safety and the supplied post URL: `instacomments.py` gained a 20-second timeout, disabled redirects, and stopped printing response bodies; `InstaScrape/main.py` gained a post/reel referer selector and stopped printing response bodies. The query hash and HTTP libraries were unchanged. The harness and isolated environment live under `research/instagram-legacy-compatibility-20261001/`.

`python -m pytest -q` passed: **66 passed in 4.54s**. The harness's offline cursor smoke check passed for both parsers. That smoke check used a synthetic fixture; no genuine raw legacy GraphQL page/cursor fixture was retained, so offline revalidation of the observed legacy cursor chain remains untested.

## Implementation differences

| Area | `instacomments` | `InstaScrape` | `instagram-recon` |
|---|---|---|---|
| Request interface | Sync `requests` GET to `/graphql/query/` with `query_hash` and serialized `variables` | Async `httpx` GET to the same endpoint and query parameters | Documented Graph API GET client; separate one-shot internal web GraphQL POST to `/api/graphql`; browser response capture |
| Query identity | Legacy parent hash above | Same legacy parent hash | Internal web operation `PolarisPostCommentsPaginationQuery` has a separate configured `doc_id`; documented API uses fields/edges, not this hash |
| Session path | Four separate `.env` fields (`SESSIONID`, `DS_USER_ID`, `CSRFTOKEN`, `MID`); no login | Normal CLI reads `cookie.json`; missing/invalid file can prompt for username/password and run custom login | Web experiment uses local web-session fields; documented API requires a bearer token and user ID; browser login is manual |
| Parsed comment fields | ID, text, username, timestamp, `like_count`, optional inline reply previews | Text, username, timestamp; drops IDs, likes, and replies | Normalized model supports comment ID, media/parent IDs, author, text, timestamp, likes, field status, and provenance |
| Pagination and storage | Cursor loop over `after`; returns a list; no durable checkpoint/dedup layer | Cursor loop exists; normal CLI wraps requests in retry/auth-refresh behavior; JSON/TXT output | Documented API path has request budgets, `paging` cursors, SQLite checkpoints, deduplication, resume, and explicit partial status. Internal web GraphQL remains one page and saves no comments while schema is unverified. |
| Failure behavior | No retry in request helper; original source had no timeout, followed redirects, and printed error-body text | Request helper reports errors; normal CLI may login after initial errors and retry later pages, so that flow was bypassed | Typed rate-limit/auth/access errors, explicit request budget, no retry on 429; partial termination is persisted for the documented API collector |

Static review found no unrelated telemetry. `InstaScrape`'s optional login code contacts Instagram's `i.instagram.com/api/v1/` login endpoints and writes `cookie.json`; it was reviewed but never executed. Its requirements enable HTTP/2 use without declaring `h2`; `h2` was installed only in the isolated test environment. The redundant `urllib3` requirement in Project A was not changed.

## Live diagnostics

### Legacy GraphQL requests

| Project / target | Requests | HTTP and response bytes | JSON and comments | Cursor and termination | Error / duration |
|---|---:|---|---|---|---|
| `instacomments` / `Dd9MKlfTDho` | 1 | `200 application/json`, 23,573 bytes | Valid JSON; 24 parent edges | `page_info` and end cursor present; `has_next_page=true`; first page only | No top-level `errors` key recorded; per-client duration not captured |
| `InstaScrape` / `Dd9MKlfTDho` | 1 | `200 application/json`, 23,573 bytes | Valid JSON; 24 parent edges | `page_info` and end cursor present; `has_next_page=true`; first page only | No top-level `errors` key recorded; per-client duration not captured |
| `instacomments` / `Dd6m2a6Exca` | 33 | 33 × `200 application/json`; 1,470,254 bytes total, 59,471 on page 1 | Valid JSON on every page; 1,535 parent edges and 1,535 distinct raw IDs; zero overlap duplicates | Cursors advanced; terminal page reported `has_next_page=false`; natural exhaustion | No top-level `errors` key recorded; no error. Per-client duration not captured |
| `InstaScrape` / `Dd6m2a6Exca` | 14 | Pages 1–13: `200 application/json`; page 14: `572 text/html`, 0 bytes; 601,285 bytes total | 607 parent edges across successful pages; 607 distinct raw IDs; zero overlap duplicates | Cursors advanced on pages 1–13; page 14 had no JSON pagination state; traversal incomplete | `http_error` on page 14; no retry. Per-client duration not captured |

Successful responses had top-level keys `data`, `extensions`, and `status`; no top-level `errors` key was recorded. The value of `status`, reported total comment count, and a separate media-ID cross-check were not retained. The requested shortcode was sent in each query; target identity was not independently rechecked against a returned media identifier.

Across the `Dd6m2a6Exca` pair, process wall time was about 50.3 seconds; project-specific duration was not measured. The `Dd9MKlfTDho` one-page pair took about 2.7 seconds total, also without per-project timing. The `Dd9MKlfTDho` live JSON artifact was sanitized after inspection: record values were removed and replaced by aggregate field counts. The `Dd6m2a6Exca` pagination artifact contains page metadata only. Neither artifact stores session values or raw cursors.

### Comment parser observations

On `Dd6m2a6Exca`, `instacomments` parsed all 1,535 parent edges: IDs, authors, and timestamps were present for all; text was nonempty for 1,441; no record had a non-null like count; 24 inline replies were present. Reply pagination was not attempted.

`InstaScrape` parsed all 607 edges received before the error: author and timestamp were present for all; text was nonempty for 578. Its parser output omits IDs, likes, and replies. The harness counted IDs directly from raw edge nodes for overlap diagnostics, but did not retain the IDs themselves.

The live response was reached using the supplied shortcode and produced the expected `shortcode_media.edge_media_to_parent_comment` path. Because raw payloads and media IDs were not retained, record-to-post identity and any reported count consistency remain unverified.

## Comparison with our collector

`instagram-recon` has three materially different pieces:

1. **Documented Graph API client:** `instagram_collector/api.py` uses `httpx`, bearer authentication, versioned Graph API hosts, bounded requests, and `paging` cursors. `PostCollector` normalizes posts/comments/replies and `StateStore` persists checkpoints and deduplicates by IDs. No Graph API token request or live Graph API response was tested here, so this route is **UNTESTED** for these targets.
2. **Internal web GraphQL experiment:** `instagram_collector/web_graphql.py` posts `PolarisPostCommentsPaginationQuery` to `https://www.instagram.com/api/graphql`. The saved one-shot probe returned HTTP 429, `text/plain`, zero bytes; it returned no JSON, comments, or cursor and was not retried. This is a different operation from the legacy GET hash. Its response schema is deliberately unverified and the CLI does not save comments.
3. **Browser and REST diagnostics:** the bounded Crawlee + CloakBrowser run loaded the page shell but was logged out and captured no comment JSON. Separately, a one-off Python REST headload sequence on `Dd9MKlfTDho` returned seven JSON pages, 93 unique IDs, six advancing cursors, and a terminal response. Its protocol reached natural exhaustion, but reported-count consistency and ranked-view coverage remain unknown; this REST probe is not an integrated collector path. Direct REST probes for `Dd6m2a6Exca` returned 200 HTML application/access fallback pages rather than comments.

The strongest design elements are already in our collector: typed stop reasons, bounded retries/budgets, a persistent cursor checkpoint, ID deduplication, normalized parent/reply records, and a distinction between protocol exhaustion and collection completeness. Project A's small inline reply preview is the only modest parser feature not already represented, but it does not paginate replies. Project B's parser loses IDs and reply/like fields, and its normal CLI's auth-refresh behavior is unsuitable for a fail-closed collector. **No code was copied or adopted.**

## Capability table

Statuses follow the requested definitions. `WORKING` means the live behavior was demonstrated; `PARTIAL` means some behavior worked but important requirements remain unqualified; `FAILED` means the attempted operation failed; `BLOCKED` means an access restriction prevented the attempt; `UNTESTED` means no valid experiment was performed.

| Capability | `instacomments` | `InstaScrape` | Our Collector |
|---|---|---|---|
| Request accepted? | **WORKING** — HTTP 200 on both targets; all 33 pages on `Dd6m2a6Exca` | **PARTIAL** — HTTP 200 through page 13; page 14 returned HTTP 572 | **PARTIAL** — separate REST request sequence succeeded on `Dd9MKlfTDho`; internal web GraphQL returned 429; documented API untested |
| JSON returned? | **WORKING** — expected comment JSON throughout both tests | **PARTIAL** — JSON through page 13, then empty HTML response | **PARTIAL** — REST diagnostic returned JSON; GraphQL probe returned no JSON; browser run captured none |
| Comments returned? | **WORKING** — 1,535 on the paginated target, plus 24 on the other target's first page | **PARTIAL** — 607 on the paginated target, plus 24 on the other target's first page | **PARTIAL** — 93 via a separate REST diagnostic; no comments via the web GraphQL or Crawlee run |
| Pagination available? | **WORKING** — observed advancing cursors and natural terminal page | **PARTIAL** — observed cursor advancement for 13 pages; no terminal page | **PARTIAL** — REST diagnostic reached protocol exhaustion; the application's internal GraphQL schema/paging is unverified |
| Replies available? | **PARTIAL** — inline previews parsed; no child-page traversal | **UNTESTED** — parser has no reply output; no live reply request was tested | **PARTIAL** — normalized reply model and API path exist; no live end-to-end reply sequence qualified |
| Existing session works? | **WORKING** — existing session accepted by the request helper after in-memory field mapping | **PARTIAL** — helper worked with that session; stock CLI expects `cookie.json` or may invoke login | **PARTIAL** — web session was used in diagnostics; internal GraphQL was rate-limited; documented API bearer path untested |
| Access restriction observed? | **WORKING** — none on the tested legacy requests | **PARTIAL** — no 429; HTTP 572 cause is unknown | **BLOCKED** — the separate internal web GraphQL operation returned HTTP 429; other routes had different results |
| Complete collection demonstrated? | **PARTIAL** — cursor protocol exhausted, but corpus count/coverage not checked | **PARTIAL** — successful partial traversal only; stopped before terminal cursor | **PARTIAL** — REST protocol ended, but ranked coverage/count were unverified; Graph API and web GraphQL collection remain unqualified |

## Phase 9 diagnostic record

| Field | `instacomments` | `InstaScrape` | Our collector |
|---|---|---|---|
| Source commit | `828a380fa983806aa6d57ed7d565842ce44610f2` | `97b2f75036484f0f8781d92301ca42152aaf9c4a` | Not available; workspace has no Git metadata; package version `0.1.0` |
| Python / library | Python 3.13.5 / `requests 2.34.2` | Python 3.13.5 / `httpx 0.28.1`, `h2 4.4.1` | Python 3.13.5 / `httpx 0.28.1` |
| Endpoint / method / identifier | `/graphql/query/` / GET / legacy hash `97b41c52301f77ce508f55e66d17620e` | Same | Documented Graph API GET path untested; internal web GraphQL POST `/api/graphql`, `PolarisPostCommentsPaginationQuery` doc ID; separate one-off REST GET is a different route |
| Authentication | Existing cookie session mapped to `SESSIONID`, `DS_USER_ID`, `CSRFTOKEN`, `MID` in memory | Same session in harness; normal CLI uses `cookie.json` or custom login | Web-session values for internal diagnostics; bearer token for documented API code; no API token request made |
| HTTP status / type / bytes | `Dd9`: 200 JSON, 23,573 bytes; `Dd6`: 33 × 200 JSON, 1,470,254 bytes total | `Dd9`: 200 JSON, 23,573 bytes; `Dd6`: 13 × 200 JSON then 572 HTML/0 bytes, 601,285 bytes total | Internal web GraphQL: 429 `text/plain`/0 bytes. Dd9 REST diagnostic: seven 200 JSON pages, 196,215 bytes total. Dd6 REST probes: 200 HTML, no comment JSON |
| JSON / comments / cursor | Dd9: valid, 24 edges, cursor present. Dd6: valid, 1,535 edges, terminal cursor state | Dd9: valid, 24 edges, cursor present. Dd6: valid for 607 edges; cursor present until failed page 14 | Web GraphQL: no JSON/comments/cursor. Dd9 REST: 93 unique IDs, cursors advanced and terminated; reported count unknown |
| Application error / termination | No top-level `errors` key recorded. Dd9 first page only; Dd6 natural exhaustion | No top-level `errors` key on JSON pages; page 14 stopped as `http_error` | 429 classified `rate_limited`, no retry. REST sequence `natural_exhaustion`, but collection partial |
| Duration | Per-project duration not captured | Per-project duration not captured | Per-request duration exists in the client design; these summarized artifacts do not include one comparable end-to-end figure |

## Answers to the requested questions

1. **Does `instacomments` still retrieve comment JSON?** Yes. It returned JSON on both targets and completed a 33-page cursor chain on `Dd6m2a6Exca`.
2. **Does `InstaScrape` still retrieve comment JSON?** Yes, for initial and continuation pages: 13 pages on `Dd6m2a6Exca`. It then received HTTP 572 and did not complete.
3. **Does the legacy GraphQL hash appear functional?** Yes, for the tested session and targets. This only demonstrates that the private historical query worked during these runs; it does not establish a supported or stable public API.
4. **Can either use our existing session?** Both request helpers did. Project A needed in-memory mapping from local names. Project B's stock CLI does not read this `.env` format and would otherwise use `cookie.json` or login.
5. **Are they meaningfully different at the protocol level?** No. They use the same endpoint, hash, method, and cursor variables. Their HTTP clients, session wrappers, parser output, CLI failure handling, and exports differ.
6. **Did either return actual comment records?** Yes. A returned 1,535 parent records on `Dd6m2a6Exca`; B returned 607 before stopping. Both returned 24 edges on the first-page `Dd9MKlfTDho` test.
7. **Did either demonstrate pagination?** A demonstrated cursor advancement and a terminal page. B demonstrated cursor advancement for 13 pages but not natural termination.
8. **Did either encounter HTTP 429?** Neither legacy scraper did. B received HTTP 572 on page 14. Our separate internal web GraphQL operation did receive HTTP 429.
9. **Does either contain useful code to incorporate?** No material change is warranted. The collector already has richer normalization, deduplication, checkpoints, resume, and explicit completeness states. A's inline reply preview is small but does not add full reply collection; B discards useful fields.
10. **What conclusions are established without guessing?** The shared legacy query/hash returned comment JSON and A exhausted the observed cursor sequence for one target. B's partial failure is observed but unexplained. Neither result verifies reported-count consistency or corpus-wide completeness. Our separate internal GraphQL operation remains blocked by its 429, while the documented Graph API was not live-tested.

## Evidence files

- First-page comparison: `reports/instagram-legacy-scraper-compatibility-20261001.md`
- Legacy cursor run: `reports/instagram-legacy-scraper-pagination-20261001.md`
- Sanitized first-page metadata: `data/instagram-legacy-compatibility-live.json`
- Sanitized per-page metadata: `data/instagram-pagination-Dd6m2a6Exca-20261001.json`
- Our internal GraphQL result: `reports/instagram-web-graphql-run.md`
- Our REST pagination result: `reports/instagram-rest-pagination-qualification-12p-20261001.md`
- Our browser qualification: `reports/instagram-crawlee-cloakbrowser-qualification.md`
