# Instagram comment coverage analysis

**Evidence date:** 2026-10-02. This report combines the read-only audit of saved SQLite/JSONL datasets with fifteen bounded, authorized GraphQL requests across three public @nytimes posts. It does not infer corpus completeness from numerical agreement or terminal cursors.

## Five-post matrix

| Post | Reported count and response time | Roots | Replies | Unique total | Difference | Root protocol | Reply branches | Requests / HTTP errors | Runtime | Numerical agreement |
|---|---:|---:|---:|---:|---:|---|---|---:|---:|---:|
| [DdFtyOcDwrZ](https://www.instagram.com/nytimes/p/DdFtyOcDwrZ/) | 971 at 07:26:16.943Z | 50 | 46 embedded previews | 96 | 875 | Partial, one page | 22 advertised, all unattempted | 1 / 0 | 6.467 s | 9.89% |
| [Dbq0I_HDIQ8](https://www.instagram.com/nytimes/p/Dbq0I_HDIQ8/) | 203 at 07:26:50.668Z, 07:31:43.476Z, 07:31:44.259Z | 137 | 38, embedded and fetched | 175 | 28 | Complete, 3 pages | 9 advertised; 9 complete, 0 partial, 0 unattempted | 13 / 0 | 34.736 s across eight runs | 86.21% |
| [DdvIOQ-Dy5s](https://www.instagram.com/nytimes/p/DdvIOQ-Dy5s/) | 2,141 at 07:27:03.057Z | 50 | 53 embedded previews | 103 | 2,038 | Partial, one page | 24 advertised, all unattempted | 1 / 0 | 3.238 s | 4.81% |
| [Dd7eoFRE5_t](https://www.instagram.com/nytimes/p/Dd7eoFRE5_t/) | 1,700 at 06:29:11Z and 06:32:17Z | 810 | 668 | 1,478 | 222 | Complete, 18 pages | 89 complete, 0 partial, 0 unattempted | 128 / 0 | 124.672 s across six network runs | 86.94% |
| [Dd9hgbek89B](https://www.instagram.com/nytimes/p/Dd9hgbek89B/) | 765 at 06:47:40Z | 633 | 47 | 680 | 85 | Complete, 13 pages | 18 complete, 0 partial, 0 unattempted | 31 / 0 | 32.336 s across three network runs | 88.89% |

Numerical agreement is unique roots plus unique replies divided by the reported count. It is an arithmetic ratio, not verified recall. The first and third new posts are one-page samples, so those ratios are not useful recall estimates. Dbq0I_HDIQ8 exhausted its root cursor and all nine observed reply-bearing branches. All five posts still have an unresolved numerical difference; the collector marks `reported_count_consistent=false` and `collection_partial=true`.

The three new targets were chosen using third-party index previews, but first-party counts were 971, 203, and 2,141; those index hints were not reliable for classification. The original Dbq0I_HDIQ8 phase used its complete 10-request cap. After the three remaining branches were audited, a separate three-request run completed them. Across all three sampled posts, 15 GraphQL requests were made. No retries were made. Browser navigation and page resources are outside the GraphQL request count.

## Data integrity and reply accounting

For Dd7eoFRE5_t and Dd9hgbek89B, saved response-observation IDs, SQLite rows, stable IDs, parent relationships, and JSONL exports agree. No orphan replies or root/reply ID collisions were found. Embedded preview IDs overlap fetched child IDs by 178 on Dd7eoFRE5_t and 33 on Dd9hgbek89B; stable-ID storage retained one row per comment.

The final Dbq0I_HDIQ8 state contains 137 root rows and 38 reply rows. The comments.jsonl and replies.jsonl ID/parent sets exactly match its 175 SQLite rows. All distinct observed IDs exist in SQLite; no orphan replies were found. `comment_observations` has 192 rows for 175 IDs: 137 root observations, 18 embedded previews, 33 initial child-operation records, and 4 continuation-operation records. Seventeen preview/child repeats were deduplicated; one preview (`17993062685824912`, parent `18115526543319370`) was not present in any child response, while 20 child IDs had no matching preview. All nine reply-bearing branches completed over ten child pages. The root checkpoint stayed at three pages while the three remaining branches completed; the last run made zero root requests and three child requests. One branch advertised one reply but returned an empty terminal child connection. The 19-reply selected parent completed over two pages.

For the two older full-tree datasets, advertised parent reply totals exceed saved unique replies by 73 on Dd7eoFRE5_t (741 advertised, 668 observed) and 11 on Dd9hgbek89B (58 advertised, 47 observed). Both trees exhausted all observed child cursors, and all returned IDs persisted. This does not establish that the API exposed every reply represented by each parent count. On Dbq0I_HDIQ8, nine parents advertise 39 replies and 38 unique replies are saved. Seventeen embedded previews overlap fetched child IDs. For parent `18115526543319370`, the child page returned one edge although two embedded previews were already saved; one preview ID was not observed in the child connection. All nine branches are complete, with one saved-count mismatch at parent `17959207985984296` (advertised 1, saved 0). See the [data-integrity report](instagram-data-integrity-report.md) for checkpoint and per-dataset checks.

This is direct cross-source evidence that the terminal child connection for `18115526543319370` did not contain every ID in that root response's embedded preview: `17993062685824912` remained preview-only even though the child page explicitly terminated. It was not lost in storage; the root preview record remains in SQLite and the JSONL export. This single branch difference does not explain the post's reported-count gap.

## Why reported counts differ

The cause is unresolved. The saved evidence shows no records dropped between normalization, SQLite, and JSONL for the two fully traversed posts or the bounded Dbq0I_HDIQ8 sample. This rules against observed local persistence loss for returned IDs, not content omitted before a response reached the collector.

- Dd7eoFRE5_t reports 1,700 and has 1,478 unique saved IDs. The first and terminal root observations both reported 1,700.
- Dd9hgbek89B reports 765 and has 680 unique saved IDs. Later resumes were reply-only and fetched no new count.
- Dbq0I_HDIQ8 returned count 203 on three root responses from 07:26:50.668Z through 07:31:44.259Z. It remained 203 across those observations; the 08:03 reply-only run supplied no new count observation. The final cursor traversal yielded 137 roots and 38 unique replies, leaving an arithmetic difference of 28.
- Of that 28-record arithmetic difference, one aligns with the single parent whose advertised reply count exceeds the saved unique replies. The other 27 cannot be assigned to the observed parent reply counts. They are an arithmetic residue, not evidence that exactly 27 replies are missing; the displayed count's scope is unverified.
- Dd6m2a6Exca changed from 1,570 to 1,574 between saved collections. The later root set retained all earlier 1,535 IDs and added four.

Meta documents controls that can hide or limit comment visibility, including Limits, Hidden Words, and restricted-account behavior. These sources establish that visibility can vary; they do not identify the cause of any listed post's gap: [Meta on Limits and hidden comments](https://about.fb.com/news/2021/08/protecting-our-community-from-abuse-on-instagram/), [Meta safety controls](https://www.meta.com/en-gb/safety/topics/safety-basics/tools/stay-safe/). No evidence here establishes whether the reported count includes replies, hidden, deleted, moderated, or viewer-unavailable comments, or whether its scope matches the GraphQL count field.

## Sorting-mode reconnaissance

The main legacy root request sends shortcode, page size, and optional cursor; it does not send a sort-mode field. A separate saved REST headload sequence was marked is_ranked=true and returned 93 unique IDs to its terminal response, but it does not establish chronological ordering or complete discovery and is not a comparable second mode for the two full-tree datasets.

An alternate PolarisPostCommentsPaginationQuery probe with sort_order=popular returned HTTP 429 and an empty text/plain response. It was not retried. No alternate sort value has been verified through first-party documentation, an authentic successful response, or a permitted browser observation. There are no comparable P and C sets, so intersection, union, exclusive IDs, and Jaccard similarity are not calculable. We cannot conclude that alternate sorting exposes additional records or that IDs are exclusive to one supported ordering. The established root path remains unchanged.

## Explicit answers

1. **Why do the two existing full collections disagree with Instagram's counts?** The cause is unresolved. Parent reply-count gaps explain part of the arithmetic difference but do not establish count scope, visibility, timing, or server selection as the cause.
2. **Were records lost in normalization or persistence?** No evidence of loss was found for returned IDs in the completed trees or bounded Dbq0I_HDIQ8 traversal. Response observations, SQLite records, parent links, and exports agree.
3. **Does alternate supported sorting expose additional unique records?** No supported alternate mode returned a valid comparable dataset; one alternate query stopped at HTTP 429.
4. **Are IDs exclusive to one ordering?** Unknown; there are no two comparable ordering result sets.
5. **Does the discrepancy persist across five posts?** Yes, all five have numerical differences. Two new samples are one-page root-only samples; Dbq0I_HDIQ8 and the two older posts exhausted their observed root and reply cursors.
6. **Are discrepancies correlated with reply volume?** Not established. The sample is small, traversal completeness varies, and reply volume is confounded with post selection and response scope.
7. **Did the count change during collection?** It remained 203 across the three Dbq0I_HDIQ8 root responses. Dd7eoFRE5_t remained 1,700 at its first and terminal observations. Dd6m2a6Exca changed between saved collections. Older overwritten per-page values cannot be recovered.
8. **Which limitations appear to come from Instagram?** HTTP 429 on the alternate-sort probe and a prior child-browser HTML response are observed access/transport boundaries. On Dbq0I_HDIQ8, one embedded reply ID was absent from its parent's terminal child connection but retained from the root preview. These observations do not explain the global count gaps. Documented visibility controls are possible mechanisms, not post-specific findings.
9. **What is the measured bottleneck?** In the three-request completion run, the lifecycle residual outside the handler was 4.815 s, versus 0.840 s response wait/read and 1.522 s pacing. SQLite took 31 ms and reply normalization 0.132 ms. The residual is not split into startup, navigation, scheduling, and shutdown.
10. **What should be investigated next?** Keep eligible branches in one sequential collector run instead of launching a separate process per parent. The three-request batch completed in 7.245 s; the prior five one-parent runs summed to 19.260 s for five different requests. This suggests fixed-startup overhead but is not a matched comparison, so measure before claiming a speedup.

## Qualification states

| Scope | Transport | Root traversal | Reply pagination | Resume | Whole post tree |
|---|---|---|---|---|---|
| Dd7eoFRE5_t | Full-form qualified over 110 child requests | Qualified, 18 pages | Qualified, 89 branches/110 pages | Prior live resumes and deterministic fault-injection tests | Qualified for observed cursors only; count gap remains |
| Dd9hgbek89B | Full-form qualified over 18 initial-operation pages | Qualified, 13 pages | Qualified for 18 one-page branches; no continuation on this post | Deterministic recovery tests | Qualified for observed cursors only; count gap remains |
| Dbq0I_HDIQ8 | Full-form initial and continuation requests returned parsed JSON, HTTP 200 | Qualified, 3 pages | All 9 parents complete across 10 pages | Root checkpoint reused; completed branches skipped; three pending parents completed in one run | Qualified for observed cursor tree; 28-count gap remains |
| DdFtyOcDwrZ and DdvIOQ-Dy5s | Browser root fetch returned HTTP 200 JSON | Not qualified beyond one-page budgets | Not attempted | Not applicable | Not qualified |

These statuses qualify observed protocol behavior and saved data. None claims retrieval of every comment represented by Instagram's displayed count.
