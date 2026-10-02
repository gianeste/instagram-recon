# Instagram post tree qualification: Dd9hgbek89B

**Date:** 2026-10-02  
**Target:** `https://www.instagram.com/nytimes/p/Dd9hgbek89B/`

## Result

The integrated collector naturally exhausted the root cursor and every root-advertised reply branch. This qualifies the observed cursor tree for this post. The reported count remains 85 higher than the 680 unique stored IDs, so corpus completeness is unresolved and `collection_partial` remains true.

| Status | Result | Evidence |
|---|---|---|
| `TRANSPORT_QUALIFIED` | **QUALIFIED for the captured full-form collector path** | 18 child requests returned HTTP 200 `text/javascript` JSON with the expected child connection. All used `PolarisPostChildCommentsQuery`; no continuation request was needed on this post. |
| `ROOT_TRAVERSAL_QUALIFIED` | **QUALIFIED** | 13 root requests returned HTTP 200 JSON; the cursor chain ended with `has_next_page=false`. |
| `REPLY_PAGINATION_QUALIFIED` | **QUALIFIED for all observed parent branches** | All 18 parents advertising replies have independent, complete checkpoints; each branch terminated after one initial-operation page. |
| `RESUME_QUALIFIED` | **QUALIFIED for the exercised root-resume path; reply recovery backed by regressions** | Later reply runs reused the completed 13-page root checkpoint and skipped a completed branch. Existing fault-injection tests cover restoring an interrupted reply cursor. |
| `POST_TREE_QUALIFIED` | **QUALIFIED for the observed cursor tree** | Root and reply protocols naturally exhausted. The reported-count mismatch prevents a corpus-completeness claim. |

## Completeness metrics

| Metric | Value |
|---|---:|
| `root_protocol_complete` | true |
| `replies_protocol_complete` | true |
| `reported_count_consistent` | false |
| `collection_partial` | true |
| `termination_reason` | `natural_exhaustion` |
| Unique roots | 633 |
| Unique replies | 47 |
| Complete parent branches | 18 |
| Partial parent branches | 0 |
| Unattempted parent branches | 0 |
| Duplicate record encounters deduplicated | 33 |
| Collector-observed GraphQL requests | 31 (13 root + 18 child) |
| Collector-measured runtime | 32.336 seconds across three runs |
| Reported comment count | 765 |
| Unique stored IDs | 680 |
| Unresolved count discrepancy | 85 |

The request total covers root and child GraphQL attempts. Browser navigation and page-resource requests are not inventoried. Runtime is the sum of the three saved collector run measurements.

The root operation supplied the reported count. The saved metadata also includes the requested shortcode and canonical permalink; the response did not provide a complete post metadata record.

## SQLite checks

Read-only checks of `data/Dd9hgbek89B/state.sqlite` found 680 records and 680 distinct comment IDs, all on one media key. The records comprise 633 roots and 47 replies. Every reply's stored parent matched its normalized parent field and referenced a root in this post; there were no orphan replies or ID mismatches.

SQLite contains one complete root checkpoint at 13 pages and 18 independent complete reply checkpoints at one page each. Every checkpoint's termination reason is `natural_exhaustion`. The existing suite passed **66 tests**.

The request caps were 25 root pages, one child page for the first transport probe, then at most three pages per remaining parent (51 possible child requests in that sweep). Actual collector-observed API usage was 31 requests. No 401, 403, or 429 boundary occurred, and the collector has automatic request retries disabled.

This post did not exercise the continuation operation because every reply branch terminated on its initial page. Continuation linkage remains supported by the separately qualified three-page experiment for `Dd7eoFRE5_t`.
