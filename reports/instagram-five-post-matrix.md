# Instagram five-post qualification matrix

**Evidence date:** 2026-10-02. The three sampled posts were selected from public @nytimes posts with the user's authorization. Dbq0I_HDIQ8 was later resumed with a three-request cap to finish its pending reply branches. No roots were recrawled.

## Collection results

| Post | Reported count and observation time | Media key | Unique roots | Unique replies | Unique total | Root pages/state | Reply pages; branches | Requests/errors | Runtime | Numerical agreement |
|---|---|---|---:|---:|---:|---|---|---:|---:|---:|
| [DdFtyOcDwrZ](https://www.instagram.com/nytimes/p/DdFtyOcDwrZ/) | 971 at 07:26:16.943Z | `shortcode:DdFtyOcDwrZ` | 50 | 46 embedded previews | 96 | 1 / page budget | 0; 22 advertised, all unattempted | 1 / 0 | 6.467 s | 9.89% |
| [Dbq0I_HDIQ8](https://www.instagram.com/nytimes/p/Dbq0I_HDIQ8/) | 203 at 07:26:50.668Z, 07:31:43.476Z, 07:31:44.259Z | `shortcode:Dbq0I_HDIQ8` | 137 | 38 | 175 | 3 / natural exhaustion | 10; 9 complete, 0 partial, 0 unattempted | 13 / 0 | 34.736 s across 8 runs | 86.21% |
| [DdvIOQ-Dy5s](https://www.instagram.com/nytimes/p/DdvIOQ-Dy5s/) | 2,141 at 07:27:03.057Z | `shortcode:DdvIOQ-Dy5s` | 50 | 53 embedded previews | 103 | 1 / page budget | 0; 24 advertised, all unattempted | 1 / 0 | 3.238 s | 4.81% |
| [Dd7eoFRE5_t](https://www.instagram.com/nytimes/p/Dd7eoFRE5_t/) | 1,700 at 06:29:11Z and 06:32:17Z | `shortcode:Dd7eoFRE5_t` | 810 | 668 | 1,478 | 18 / natural exhaustion | 110; 89 complete, 0 partial, 0 unattempted | 128 / 0 | 124.672 s across 6 runs | 86.94% |
| [Dd9hgbek89B](https://www.instagram.com/nytimes/p/Dd9hgbek89B/) | 765 at 06:47:40Z | `shortcode:Dd9hgbek89B` | 633 | 47 | 680 | 13 / natural exhaustion | 18; 18 complete, 0 partial, 0 unattempted | 31 / 0 | 32.336 s across 3 runs | 88.89% |

Numerical agreement is `(unique roots + unique replies) / reported count`. It is an arithmetic ratio, not recall or proof of corpus completeness. All five posts have `reported_count_consistent=false` and `collection_partial=true`.

## Independent qualification statuses

| Post | `root_protocol_complete` | `replies_protocol_complete` | `reported_count_consistent` | `collection_partial` | `LIVE_TRANSPORT_QUALIFIED` and scope | `termination_reason` |
|---|---|---|---|---|---|---|
| DdFtyOcDwrZ | false | false | false | true | Qualified for the sampled root JSON response; child transport not exercised | `page_budget` |
| Dbq0I_HDIQ8 | true | true | false | true | Qualified for root JSON and full-form child JSON on this post | `natural_exhaustion` |
| DdvIOQ-Dy5s | false | false | false | true | Qualified for the sampled root JSON response; child transport not exercised | `page_budget` |
| Dd7eoFRE5_t | true | true | false | true | Qualified for saved root and full-form child response chains | `natural_exhaustion` |
| Dd9hgbek89B | true | true | false | true | Qualified for saved root and full-form child response chains | `natural_exhaustion` |

The DdFtyOcDwrZ and DdvIOQ-Dy5s rows are saved one-page samples from bounded live root responses; they do not qualify root exhaustion or replies. The Dd7eoFRE5_t and Dd9hgbek89B trees are completed saved traversals. Dbq0I_HDIQ8 is now a completed traversal of its saved root cursor and all nine roots advertising replies. `POST_TREE_QUALIFIED` applies only to those observed cursor trees; it does not assert that the returned corpus equals Instagram's count.

## Dbq0I_HDIQ8 branch audit and completion

Before the follow-up, three parents had no reply checkpoint. They were left unattempted when the explicit 10-request qualification cap was consumed. The saved run history shows 3 root requests plus 7 child requests. The child runs recorded explicit `reply_parent_filter` values for the selected branches, so the other parents were intentionally outside those bounded runs. There was no request attempt, error checkpoint, or interruption for the three parents; the scheduler's parent filter excluded them by design. This was an intentional budget stop, not a queue-completion bug.

| Parent comment ID | Advertised replies | Embedded previews saved before follow-up | Prior checkpoint | Follow-up result |
|---|---:|---:|---|---|
| `18056679296536860` | 7 | 3 | None (`not_attempted`) | 1 page / 7 edges, HTTP 200 JSON, natural exhaustion; 7 unique saved |
| `18115526543319370` | 2 | 2 | None (`not_attempted`) | 1 page / 1 edge, HTTP 200 JSON, natural exhaustion; final 2 saved from previews |
| `18168924550451617` | 3 | 3 | None (`not_attempted`) | 1 page / 3 edges, HTTP 200 JSON, natural exhaustion; 3 unique saved |

The follow-up started at 08:03:31Z and made exactly three sequential child requests, with no root request. The root checkpoint remains at three pages, complete with `natural_exhaustion`, and its saved timestamp predates the follow-up. Each child response was `200 text/javascript`, parsed as JSON, and associated with the requested parent. All three responses used the initial child operation and explicitly returned `has_next_page=false`. Across all nine parents, the advertised reply total is 39 and 38 unique replies are saved. The sole parent-level count mismatch is `17959207985984296` (advertised 1, saved 0) despite an explicit empty terminal response.

After completion, SQLite contains 137 roots and 38 replies. The two JSONL exports match all 175 SQLite IDs and parent IDs exactly; there are no orphan replies or root/reply ID collisions. `comment_observations` has 192 rows for 175 IDs, so 17 repeat observations were deduplicated. Across the full tree, 17 embedded-preview IDs overlap fetched child IDs, one embedded ID (`17993062685824912`, parent `18115526543319370`) appears only in the root preview, and 20 child IDs have no matching embedded preview. The new probes returned 11 edges, of which 7 overlapped saved previews and 4 added unique IDs.

Instagram's reported count remained 203 across the three existing root responses. No new count observation was created by the reply-only follow-up. The final arithmetic difference is 28. Only one of those records is localized to a specific reply-bearing parent by its advertised child count; the remaining 27 are not explained by the observed parent reply counts. No cause is established.

The first-page roots for the three additional posts returned HTTP 200 `application/json` using the stock Playwright browser plugin. The full-form child path returned legitimate child JSON in the bounded and completed Dbq0I_HDIQ8, Dd7eoFRE5_t, and Dd9hgbek89B traversals. The three latest responses matched the parsed `data → child connection → edges/page_info` schema; the requested parent identity was validated and each page reported `has_next_page=false`. They used the initial child operation; the continuation operation remains qualified by the linked 15 + 15 + 0 sequence and the completed 19-reply branch. The earlier browser child-fetch result remains an HTML response and does not qualify that transport. The alternate-sort probe remains unqualified after HTTP 429 and was not retried.

## Interpretation limits

Natural cursor exhaustion means the server response explicitly said there was no next page for the observed branch. It does not prove that every comment counted by Instagram was accessible through that response path. The two older complete trees and the newly completed Dbq tree still disagree with displayed counts by 222, 85, and 28. The one-page samples have much larger differences because they are intentionally partial. Count semantics, hidden or unavailable records, and server-side corpus selection remain unresolved.
