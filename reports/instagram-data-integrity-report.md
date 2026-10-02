# Instagram saved-data integrity audit

**Audit date:** 2026-10-02

**Method:** SQLite databases opened read-only; existing JSONL exports compared by stable comment ID. No Instagram requests were made for this audit.

## Results

| Dataset | Roots | Replies | Root/reply ID overlap | Orphan replies | Export IDs match SQLite | Root checkpoint | Reply branches |
|---|---:|---:|---:|---:|---|---|---|
| `Dd7eoFRE5_t` | 810 | 668 | 0 | 0 | Yes | 18 pages, natural exhaustion | 89 complete, 0 partial, 0 unattempted |
| `Dd9hgbek89B` | 633 | 47 | 0 | 0 | Yes | 13 pages, natural exhaustion | 18 complete, 0 partial, 0 unattempted |
| `Dd6m2a6Exca` current | 1,539 | 24 | 0 | 0 | Yes | 33 pages, natural exhaustion | 0 complete, 3 partial, 10 unattempted |
| `DdsVkZLEjsi` archive | 145 | 0 | 0 | 0 | No export pair at the audited path | 4 pages, natural exhaustion | 1 advertised parent unattempted |

For both fully collected posts, every distinct ID in `comment_observations` exists in `comments`. There are no root/reply identity collisions, parent mismatches, or orphan replies. This is direct evidence against records being dropped between normalization and SQLite persistence for the saved responses examined.

## Reply-source accounting

| Dataset | Embedded preview IDs | Child-operation IDs | Preview/child overlap | Preview-only | Child-only | Observation rows | Unique saved IDs |
|---|---:|---:|---:|---:|---:|---:|---:|
| `Dd7eoFRE5_t` | 178 | 668 | 178 | 0 | 490 | 1,656 | 1,478 |
| `Dd9hgbek89B` | 33 | 47 | 33 | 0 | 14 | 713 | 680 |
| `Dd6m2a6Exca` current | 24 | 0 | 0 | 24 | 0 | 1,563 | 1,563 |

The 178 and 33 repeated observations are preview/child cross-source duplicates. Stable-ID storage retained one normalized reply row for each. In `Dd7eoFRE5_t`, child IDs came from 477 initial-operation records and 191 continuation-operation records. In `Dd9hgbek89B`, all 47 child replies came from initial-operation pages.

## Parent reply-count checks

| Dataset | Parents advertising replies | Advertised total | Saved replies under those parents | Matching counts | Mismatching counts |
|---|---:|---:|---:|---:|---:|
| `Dd7eoFRE5_t` | 89 | 741 | 668 | 58 | 31 |
| `Dd9hgbek89B` | 18 | 58 | 47 | 12 | 6 |
| `Dd6m2a6Exca` current | 13 | 32 | 24 | 10 | 3 |
| `DdsVkZLEjsi` archive | 1 | 1 | 0 | 0 | 1, not attempted |

All `Dd7eoFRE5_t` and `Dd9hgbek89B` reply checkpoints terminated with `natural_exhaustion`. The `Dd6m2a6Exca` current state has three attempted child requests ending in `unexpected_schema` and ten parents not attempted; its complete root cursor does not make its reply tree complete.

## Repeated-record evidence

- The first and last complete `DdsVkZLEjsi` root scans contain the same 145 IDs (same SHA-256 ID-set hash). An intervening scan stopped at 41 roots and is not a complete-scan comparison.
- The archived `Dd6m2a6Exca` scan has 1,535 roots. The later scan has all 1,535 plus four additional roots; no archived root is absent from the later ID set. Its reported connection count changed from 1,570 to 1,574 between the saved observations.
- `Dd7eoFRE5_t` and `Dd9hgbek89B` have one completed root scan each; resumed runs after root completion add reply pages, not independent root-set replications.

## Count-history limitation and fix

Older `post_observations` rows were updated in place once per run. That retained at most the last count snapshot for a run and caused reply-only resumes to appear as repeated count observations even when no root response arrived. The prior in-memory report also assigned a report-generation timestamp to the run-level count. Those are not per-page count histories.

The collector now appends one observation when a root response supplies a comment count, uses that response's timestamp, and reports the timestamp basis. It no longer invents a new observation when a reply-only run inherits an old count. Existing databases remain unchanged; overwritten intermediate observations cannot be reconstructed retroactively.

## Conclusion

For the two fully traversed saved trees, normalization and persistence are internally consistent with the responses recorded in SQLite and JSONL. This rules out observed pipeline loss for those records. It does not prove the server returned every item represented by the displayed count, and it does not explain the reported-count discrepancies.

## Historical addendum: initial Dbq0I_HDIQ8 10-request cap

The selected public post was sampled under a total cap of 10 GraphQL requests. The reported count was 203 on all three root responses, timestamped 07:26:50.668Z, 07:31:43.476Z, and 07:31:44.259Z. No separate count request followed reply traversal. Reply-only runs do not create count observations.

The completed root checkpoint has three pages and natural_exhaustion. Six of nine independent reply branches have natural_exhaustion checkpoints across seven child pages; three remain unattempted. One completed branch advertised one reply but returned zero child records with explicit terminal metadata. Its cursor is complete while its advertised count differs by one. The selected 19-reply branch completed over two pages.

The final SQLite database contains 137 roots and 34 unique replies. comments.jsonl and replies.jsonl together have the same 171 ID/parent pairs as SQLite. All distinct observed IDs are persisted and there are no orphans. comment_observations has 181 rows for 171 IDs: 137 root observations, 18 embedded previews, 22 initial child-operation records, and 4 continuation records. Ten child records overlap embedded previews and were deduplicated. The six completed branches contain 26 unique replies; the three unattempted branches have only root previews. The root checkpoint remained complete while reply checkpoints advanced independently.

This evidence supports integrated full-form transport, stable IDs, parent association, deduplication, exports, and independent checkpoint persistence for the bounded sample. It does not qualify the three unattempted branches or reconcile the displayed count.

## Count-history correction

The five reply-only runs correctly made no post_observations rows, but their saved reports carried forward the old count. The report-history fallback was including those as run_report_proxy entries. The history code now excludes report-only counts when instrumentation says the run made zero root requests. A regression covers this case. The refreshed collection report contains only the three response_payload count observations above; no synthetic reply-only entries are presented as observations.

## Dbq0I_HDIQ8 three-branch follow-up (2026-10-02 08:03Z)

Before this run, these three branches had no `replies` checkpoint, so their status was `NOT_ATTEMPTED`, not failed or partially saved. The original request budget had been consumed by three root requests and seven child requests. They were intentionally outside that 10-request bounded run. The root checkpoint was already complete at three pages, with `updated_at=2026-10-02T07:31:44Z`.

The follow-up used one sequential child request per pending parent and made zero root requests. Each returned HTTP 200 `text/javascript` JSON, explicitly named the requested parent, and had terminal pagination metadata:

| Parent ID | Advertised replies | Embedded previews before run | Reply rows after run | Checkpoint |
|---|---:|---:|---:|---|
| `18056679296536860` | 7 | 3 | 7 | 1 page / 7 edges, `COMPLETE`, `natural_exhaustion` |
| `18115526543319370` | 2 | 2 | 2 | 1 page / 1 edge, `COMPLETE`, `natural_exhaustion` |
| `18168924550451617` | 3 | 3 | 3 | 1 page / 3 edges, `COMPLETE`, `natural_exhaustion` |

All three branches now match their advertised reply counts. Across all nine branches, 39 replies are advertised and 38 unique replies are saved. The only mismatch is parent `17959207985984296` (advertised 1, saved 0) after an explicit empty terminal page. This is a parent-level discrepancy; it does not explain the full reported count difference.

The final SQLite state has 137 roots and 38 replies. The two exported JSONL files contain the same 175 ID/parent pairs as SQLite. There are zero orphan replies, zero root/reply ID collisions, and 17 duplicate observations across 192 observations; one normalized comment row remains per stable ID. Seventeen embedded-preview IDs overlap child responses, one preview ID (`17993062685824912`) under `18115526543319370` appears in no child response, and 20 child IDs have no matching preview. The root checkpoint is unchanged, and all nine reply checkpoints are complete. No persisted records were lost in this follow-up.

The three saved count observations remain 203 at 07:26:50.668Z, 07:31:43.476Z, and 07:31:44.259Z. The reply-only follow-up at 08:03Z did not create a fourth count observation. The final global arithmetic difference is 203 - 175 = 28; only one is attributable to a saved reply-count mismatch, leaving 27 unexplained by the observed parent reply counts. No corpus-level explanation is established.
