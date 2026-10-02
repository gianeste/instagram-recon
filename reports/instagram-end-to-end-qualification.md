# Instagram end-to-end collector qualification

**Date:** 2026-10-02

## Latest integrated qualification update

**Bounded target:** Dbq0I_HDIQ8, authorized public @nytimes post. The first qualification used a 10-request cap and completed the root cursor plus six reply branches. A later three-request sequential resume attempted only the three remaining branches. Across eight collector runs, the post has 13 GraphQL requests; all returned HTTP 200 JSON. No root pages were recrawled and no requests were retried.

The stock Playwright browser plugin returned root JSON on the three one-page samples. On Dbq0I_HDIQ8, the root cursor resumed without replay: two additional root pages brought the checkpoint to three pages and natural exhaustion. The reported count was 203 on all three saved root responses. The last reply-only run made exactly three child requests and zero root requests.

The full-form child transport returned `text/javascript` JSON for the three pending parents. The page edge counts were 7, 1, and 3, each with `has_next_page=false`. Their final unique saved replies are 7, 2, and 3 because the second parent already had two embedded previews; its one fetched edge overlapped a preview. Together with the six previously completed branches, all nine reply-bearing parents now have independent natural-exhaustion checkpoints. The only saved-count mismatch is `17959207985984296`: advertised 1, saved 0, with an explicit empty terminal response. Across sources, one embedded ID under `18115526543319370` never appeared in a child response but remains saved from the root preview.

SQLite now contains 137 roots and 38 unique replies (175 combined). JSONL ID/parent pairs match SQLite exactly; there are no orphans or root/reply identity collisions. Seventeen repeated observations were deduplicated. The root checkpoint remains at three pages with its original completion timestamp. The final report has `root_protocol_complete=true`, `replies_protocol_complete=true`, `reported_count_consistent=false`, `collection_partial=true`, and `termination_reason=natural_exhaustion`. This qualifies the observed cursor tree, not agreement with the reported count or complete corpus access.

| Status | Current evidence |
|---|---|
| TRANSPORT_QUALIFIED | Full-form initial and continuation operations returned valid JSON in the linked 30-reply experiment and live child pages on Dbq0I_HDIQ8. Browser child-fetch remains unqualified. |
| ROOT_TRAVERSAL_QUALIFIED | Dbq0I_HDIQ8 natural root exhaustion over three pages; root browser fetch also returned JSON for the other two sampled posts. |
| REPLY_PAGINATION_QUALIFIED | All nine Dbq0I_HDIQ8 branches completed across ten pages; the prior linked experiment completed 15 + 15 + 0. |
| RESUME_QUALIFIED | The root cursor resumed without replay; completed reply branches were skipped during the three-parent follow-up. Deterministic interruption tests restore a child cursor and resume at the next pending parent. |
| POST_TREE_QUALIFIED | Qualified for the observed cursor tree on Dbq0I_HDIQ8 and the completed Dd7eoFRE5_t and Dd9hgbek89B traversals. Count differences remain unresolved. |

This update supersedes the older Phase 4 statement below that bounded post qualification had not started. Historical browser-fetch failure details remain valid for that earlier attempt.

**Target:** `Dd7eoFRE5_t`, media `3997923790051057645`, parent `18356734951220570`

## Current full-tree qualification

**Result:** Yes. The collector reached natural cursor exhaustion for the post's root comments and every root-advertised reply branch. This qualifies the observed pagination protocol for this post. The reported-count discrepancy remains unresolved, so `collection_partial` is still true and this is not a claim that Instagram's reported corpus count was reconciled.

| Status | Current result | Scope |
|---|---|---|
| `TRANSPORT_QUALIFIED` | **QUALIFIED** | Captured full-form transport returned JSON for 110 child-page requests across the post's 89 reply-bearing parents. Browser-fetch child transport remains unqualified. |
| `ROOT_TRAVERSAL_QUALIFIED` | **QUALIFIED** | 18 root pages returned HTTP 200 JSON and ended with `has_next_page=false`; 810 unique roots were saved. |
| `REPLY_PAGINATION_QUALIFIED` | **QUALIFIED** | All 89 reply branches reached explicit natural exhaustion across 110 pages. |
| `RESUME_QUALIFIED` | **QUALIFIED** | Saved root and child cursors resumed after the initial one-minute handler timeout; completed branches were skipped on later runs. Offline fault-injection tests also pass. |
| `POST_TREE_QUALIFIED` | **QUALIFIED for observed cursor protocol** | Roots and all 89 advertised branches are complete. Count consistency and count semantics remain unqualified. |

The share URL's `/nytimes/p/<shortcode>/` form was added to the URL parser and covered by a regression. Root collection used 18 sequential legacy GraphQL pages. The root response omitted a stable media ID, so SQLite consistently used the shortcode-scoped media key `shortcode:Dd7eoFRE5_t`; child requests used the decoded media ID from the scoped capture. All reply rows have stable string IDs, a valid root parent, and the same post media key.

Reply collection used the existing `FullFormReplyTransport` with explicit same-media parent retargeting. The exact captured parent and a second parent were qualified first; the resumed post run then traversed all 89 branches. All 110 child responses were HTTP 200 `text/javascript` JSON. Operation selection was `PolarisPostChildCommentsQuery` for 89 initial pages and `PolarisPostCommentsChildrenPaginationtQuery` for 21 continuation pages. Empty terminal pages completed their branches. No 401, 403, or 429 response occurred, and the transport performs no retries.

The first broad child pass stopped after 79 successful page requests and left 10 parents unattempted. It ran for 62.173 seconds because the installed Crawlee 1.9.2 default request-handler timeout is 60 seconds; the collector processes branches sequentially in one handler. The collector now sets that timeout to 15 seconds beyond its configured duration. The next run resumed saved cursors, then two further bounded passes completed the remaining branches. The official [Crawlee source](https://github.com/apify/crawlee-python/blob/master/src/crawlee/crawlers/_basic/_basic_crawler.py) documents the one-minute default.

### Completeness fields

| Metric | Result |
|---|---:|
| `root_protocol_complete` | true |
| `replies_protocol_complete` | true |
| `reported_count_consistent` | false |
| `collection_partial` | true |
| `termination_reason` | `natural_exhaustion` |
| Unique roots | 810 |
| Unique replies | 668 |
| Complete parent branches | 89 |
| Partial parent branches | 0 |
| Unattempted parent branches | 0 |
| Duplicate record encounters deduplicated | 178 |
| Total collector-observed GraphQL requests | 128 (18 roots + 110 replies; browser resource requests are not inventoried) |
| Total runtime | 124.672 seconds across six network runs for the persisted post tree; excludes isolated scratch transport checks. 124.705 seconds including the local report refresh |
| Reported comment count | 1,700 |
| Unique saved roots plus replies | 1,478 |
| Unresolved count discrepancy | 222 |

The 89 roots advertised 741 replies; 668 unique replies were saved, a separate 73-count difference. The database contains 1,478 unique comment IDs after deduplication. `reported_count_semantics_validated` is false; numerical agreement is not used as a completeness test.

The earlier test snapshot completed with **66 passed**; the latest full suite completed with **69 passed**. `git diff --check` reported only LF-to-CRLF working-copy notices. No commit or push was made.

The earlier browser-fetch attempt remains an historical failure: it returned HTTP 200 `text/html` instead of reply JSON. The current transport qualification applies to the captured full-form path only.

## Initial browser-transport qualification snapshot

The following statuses and phases describe the initial browser-fetch attempt, before the full-form follow-up above.

## Initial qualification statuses

| Status | Result | Evidence and scope |
|---|---|---|
| `TRANSPORT_QUALIFIED` | **NOT QUALIFIED** | One collector child request returned HTTP 200 `text/html`, 650,970 bytes, no JSON payload. |
| `ROOT_TRAVERSAL_QUALIFIED` | **QUALIFIED on a separate archived post only** | The saved `Dd6m2a6Exca` run records 33 root pages and natural cursor exhaustion in [the post collection qualification](instagram-comment-tree-qualification.md). This run did not request root pages for `Dd7eoFRE5_t`. |
| `REPLY_PAGINATION_QUALIFIED` | **QUALIFIED for the standalone reference only** | The linked full-form sequence for this exact media/parent returned 15 + 15 + 0 replies over three response-linked requests, ending with `has_next_page=false`. The collector browser transport is not qualified. |
| `RESUME_QUALIFIED` | **QUALIFIED offline** | Deterministic interruption/resume tests restore the saved cursor, skip committed pages and completed branches, and preserve root state. |
| `POST_TREE_QUALIFIED` | **NOT QUALIFIED** | The bounded post-tree phase was gated on integrated transport success and was not started. |

## Phase 1: transport qualification

The collector used the exact media/parent pair from the linked experiment. Its scratch SQLite database contained one seeded parent row and a pre-completed root checkpoint, so the run issued no root GraphQL request and could spend its one-request budget on the initial child operation only. The root record/checkpoint were not obtained from this live run.

| Comparison | Linked full-form reference | Main collector browser fetch |
|---|---|---|
| Request | `POST /api/graphql`; `PolarisPostChildCommentsQuery`, doc ID `28027289793632076` | Same endpoint, operation, and doc ID |
| Status | 200 | 200 |
| Content type | `text/javascript; charset=utf-8` | `text/html; charset="utf-8"` |
| Body | JSON: `data` → child connection → `edges` and `page_info` | 650,970-byte HTML; no JSON/schema |
| Replies | 15 unique IDs on page 1 | No reply IDs available |
| Parent identity | All returned nodes declared the requested parent | No reply nodes to validate |
| Pagination | `has_next_page=true`; cursor hash `bfc931a67a7d56785b81c3736e5cba4be485e65a94cce2e6c336da3fa0313203` | No pagination metadata |

The reference JSON has the verified child connection, `edges[].node` fields including `pk`, `parent_comment_id`, `user`, `text`, `created_at`, and `comment_like_count`, plus four `page_info` fields: `end_cursor`, `has_next_page`, `has_previous_page`, and `start_cursor`. The browser response had no comparable schema, ID set, parent IDs, or pagination values. Its HTML signals were doctype, `<html>`, and app assets; login and challenge markers were absent. The collector stopped with `unexpected_schema` after that response.

The request contracts differ. The isolated reference requires 29 form fields; the collector sends only `doc_id` and `variables` in its form body. The reference also explicitly sets 24 headers, while the browser code explicitly sets six application headers and relies on browser defaults for the rest. The missing form parameters include `fb_dtsg`, `jazoest`, `lsd`, `fb_api_req_friendly_name`, and other request-context fields. This identifies a concrete request difference, but the single response does not prove which difference caused the HTML response. The reference implementation and its saved captures remain isolated and unchanged. No access restriction was bypassed.

The one new Instagram API attempt was not retried. The browser run took **6.263 seconds**. CloakBrowser also made two version-check GETs (PyPI and GitHub); the browser's document/resource subrequests were not inventoried, so a process-wide wire-request total is unavailable. The collector's measured request count is one child API attempt; no root API request was made.

## Phase 2: SQLite integration

With no network requests, the three already-saved linked HTTP response bodies were passed through the collector's `_child_page` parser and `StateStore.save_page` in a temporary database:

| Page | Operation | HTTP / content type | Replies | `has_next_page` | Saved checkpoint |
|---:|---|---|---:|---|---|
| 1 | `PolarisPostChildCommentsQuery` | 200 / `text/javascript` | 15 | true | Page 1, cursor saved |
| 2 | `PolarisPostCommentsChildrenPaginationtQuery` | 200 / `text/javascript` | 15 | true | Page 2, next cursor saved |
| 3 | `PolarisPostCommentsChildrenPaginationtQuery` | 200 / `text/javascript` | 0 | false | Page 3, `COMPLETE`, `natural_exhaustion` |

The replay persisted **30 unique string IDs**. Every reply had media ID `3997923790051057645` and parent ID `18356734951220570`; duplicate count was zero. The response-derived cursor hashes matched each next request's input hashes. The reply ID-set SHA-256 was `df7d6176573a635cf76f318c6c1f283382059fdbda6231781d1ddb5180448d1f`. The root checkpoint was identical before and after the three reply commits. The empty third page advanced the branch to `COMPLETE` because its response explicitly set `has_next_page=false`.

Offline regressions also verify stable-ID deduplication between an embedded preview and a fetched reply, separate checkpoints for two parents, atomic page/record/checkpoint rollback on invalid input, and preservation of a completed root checkpoint.

## Phase 3: resume qualification

Fault injection saved the first reply page and then raised before the next response. The next experiment restored that branch's saved cursor and selected the continuation operation; it did not request the initial page again. Both saved replies remained available, no duplicate record was introduced, and the root checkpoint remained unchanged. A separate resume test confirms a completed parent branch is skipped while another parent's checkpoint advances independently.

This qualifies deterministic offline recovery behavior. It does not qualify a live browser transport restart, because the browser response did not provide a usable cursor.

## Phase 4: bounded post qualification

A later bounded experiment used Dbq0I_HDIQ8 after the integrated full-form transport succeeded. Its original cap was 10 GraphQL calls including the saved first-page sample; all ten calls were used. That cap left three eligible branches unattempted without checkpoints. The checkpoint history shows no attempt or failure for them; this was a deliberate budget stop, not a scheduler loss. At 08:03:31Z, a second bounded run made one sequential request per pending parent, reached natural exhaustion on all three, and issued no root request. The root checkpoint and completed branches were preserved.

## Phase 5: completeness metrics

These metrics describe Dbq0I_HDIQ8 after the original 10-request run and its three-request completion run. Counts reflect the final SQLite/export state, not just the latest reply-only run.

| Metric | Value |
|---|---:|
| root_protocol_complete | true |
| replies_protocol_complete | true |
| reported_count_consistent | false |
| collection_partial | true |
| termination_reason | natural_exhaustion |
| Unique roots | 137 |
| Unique replies | 38 |
| Complete parent branches | 9 |
| Partial parent branches | 0 |
| Unattempted parent branches | 0 |
| Duplicate observations deduplicated | 17 |
| Total GraphQL requests | 13: 3 root and 10 child; all HTTP 200 |
| Total collector runtime | 34.736 seconds across eight runs |
| Reported comment count | 203 on three root responses; no new count observation on reply-only resume |
| Unique saved roots plus replies | 175 |
| Unresolved arithmetic difference | 28 |

The nine roots advertise 39 replies; 38 unique reply IDs are persisted. All nine branches exhausted their observed child cursors. One returned an empty terminal page despite advertising one reply. The branch total accounts for one of the 28 records in the global arithmetic difference; the other 27 cannot be assigned to the observed reply-bearing parents from saved evidence. No displayed-count semantics or corpus completeness claim is inferred.

## Phase 6: final validation

The final pytest run completed with **71 passed in 10.81 seconds**. New regression coverage verifies filtered/incomplete branch queues stay partial, page-budget exhaustion preserves the cursor, resume skips completed parents, interruption resumes at the next pending parent, empty terminal pages complete a branch, and root checkpoints remain untouched. `compileall` passed. `git diff --check` reported no whitespace errors; Git emitted only LF-to-CRLF working-copy notices. No commit or push was made.

No commit or push was made.
