# Instagram legacy scraper pagination

**Date:** 2026-10-01  
**Target:** `https://www.instagram.com/p/Dd6m2a6Exca/`  
**Query:** `97b41c52301f77ce508f55e66d17620e`  
**Outcome:** `instacomments` completed pagination; `InstaScrape` stopped on HTTP 572.

## Results

| Project | Requests | Result | Parent comment edges | Pagination |
|---|---:|---|---:|---|
| `instacomments` | 33 | Completed; HTTP 200 JSON on every page | 1,535 across 33 pages; 1,535 distinct IDs; no duplicate IDs | Final page reported `has_next_page=false` |
| `InstaScrape` | 14 | Pages 1–13 returned HTTP 200 JSON; page 14 returned HTTP 572, `text/html`, 0 bytes | 607 across the 13 successful pages; 607 distinct raw IDs; no duplicate IDs | Stopped on the error; no retry |

Both clients used the same configured session, query hash, page size (50), and target. Requests were sequential. `instacomments` ran first through completion, followed by `InstaScrape`. Since they shared a session, the request order may have affected the later error; the run does not establish why HTTP 572 occurred.

`instacomments` parsed all 1,535 returned parent edges. Text was nonempty in 1,441 records; author and timestamp were present in all. No parsed record had a non-null like count. The pages contained 24 inline reply previews in total; reply pagination was not attempted.

`InstaScrape` parsed all 607 edges from its successful pages. Text was nonempty in 578 records; author and timestamp were present in all. Its parser output omits comment IDs, likes, and replies, although the raw GraphQL edges had 607 distinct IDs.

The 100 page ceiling was not reached. A local offline cursor check passed for both parsers before the live run. No login, retry, challenge handling, or cursor value storage was used. The saved JSON contains only per page status, size, edge counts, parser counts, and cursor presence flags; it contains no comment text, cursor values, or credential values: `data/instagram-pagination-Dd6m2a6Exca-20261001.json`.

## Conclusion

The legacy cursor parameter paginated `instacomments` to completion for this target and session. `InstaScrape` advanced correctly through 13 pages, then could not complete because page 14 returned an empty HTTP 572 HTML response. The test stopped there rather than retrying. Its pagination compatibility is therefore **partially demonstrated, not qualified to completion**.
