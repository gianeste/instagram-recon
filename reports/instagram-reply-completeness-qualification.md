# Instagram reply completeness qualification

> Historical reply-investigation snapshot as of 2026-10-02 04:14:54 UTC. The
> current metadata, refresh, and test status is in
> [instagram-comment-tree-qualification.md](instagram-comment-tree-qualification.md).

**Post:** `Dd6m2a6Exca`  
**Latest bounded observation:** 2026-10-02 04:14:54 UTC  
**Verdict:** roots complete for the saved cursor chain; reply coverage remains partial

## Per-parent reconciliation

The 24 reply records are unique embedded previews from root responses. Every reply ID is distinct from every root ID, every reply links to a root in this post, and no reply timestamp precedes its parent timestamp. `Gap` is advertised count minus embedded preview count; a zero gap is not protocol completeness.

| Parent comment ID | Advertised | Embedded replies | Gap | Child operation evidence | Branch status |
|---|---:|---:|---:|---|---|
| `17922294696431093` | 2 | 2 | 0 | Attempt 1: HTTP 200, non-JSON; content type/body not retained | Partial |
| `17952948762036948` | 5 | 3 | 2 | Attempt 2: HTTP 200, non-JSON; content type/body not retained | Partial |
| `17957667768217768` | 1 | 1 | 0 | Not attempted | Partial |
| `17991458538100516` | 6 | 3 | 3 | Attempt 3: HTTP 200 `text/html`, shell-like HTML | Partial |
| `18012381932953446` | 1 | 1 | 0 | Not attempted | Partial |
| `18024417638704314` | 2 | 2 | 0 | Not attempted | Partial |
| `18077655707395633` | 2 | 2 | 0 | Not attempted | Partial |
| `18102906863133185` | 2 | 2 | 0 | Not attempted | Partial |
| `18107727470190690` | 1 | 1 | 0 | Not attempted | Partial |
| `18118624037515599` | 6 | 3 | 3 | Not attempted | Partial |
| `18133974553645453` | 1 | 1 | 0 | Not attempted | Partial |
| `18137828113622515` | 2 | 2 | 0 | Not attempted | Partial |
| `18629091568056431` | 1 | 1 | 0 | Not attempted | Partial |
| **Total** | **32** | **24** | **8** | **3 attempted; 10 unattempted** | **13 incomplete** |

The three numeric preview gaps are at `17952948762036948` (2), `17991458538100516` (3), and `18118624037515599` (3). All 13 branches remain incomplete because none has a successful child page and defensible terminal cursor. The ten unattempted branches are preserved as unattempted in SQLite.

## Stored evidence and retrieval approaches

**Embedded root replies.** The working legacy GraphQL GET remains the root collector. It reads `edge_threaded_comments.count` and nested `edges`, normalizing the 24 returned reply nodes with their containing root as parent. It does not retain raw response bodies or inspect nested reply `page_info`; `root_pagination.jsonl` describes root pagination only. Therefore no extra embedded replies or child cursors can be recovered from the saved root payloads.

The archived `responses/capture-manifest.json` records zero attached contexts, requests, and responses. There are no retained raw root pages. It cannot establish whether the root responses contained additional nested pagination metadata that the parser did not inspect.

No captured normal-UI interaction on this post links a reply expansion to this operation. The operation name/document ID are catalogued from prior supplied evidence, while the fixture's request metadata is absent. The bounded follow-up below invoked that known POST through the authorized browser page context; it did not click a UI reply control and does not prove the UI uses this operation.

**Imported child fixture.** `fixtures/polaris_child_comments_tree.sanitized.json` contains three distinct child IDs with one consistent explicit parent ID. That parent is not present in this post's root IDs or its 13 reply branches. The fixture reports `has_next_page=false` and no end cursor, but its provenance says `imported_external` from `tree.txt`, request metadata absent, response role uncertain, and pagination/live qualification false. It verifies a parser shape, not this post's operation linkage or a continuation sequence.

**Polaris child operation.** The operation label is `PolarisPostChildCommentsQuery`, document ID `28027289793632076`, POST `/api/graphql`. The two earlier attempts retained only HTTP status, byte count, and `json=false`; their content types and response bodies are unavailable. Their exact document type cannot be classified retrospectively.

The single bounded follow-up targeted the gap branch `17991458538100516` with `first=10`, one parent filter, and a one-page limit. It returned HTTP 200, `text/html`, 650,814 bytes, and no JSON payload. A metadata-only sample found a doctype, an HTML element, and Instagram/static asset references; no Instagram title, login marker, or challenge marker was detected in the sampled text. Classification: **application-shell-like HTML**, not a child-comment response. The body was not retained. The request used the configured cookie session, `credentials=include`, and the existing form content type, `Accept`, `X-Requested-With`, app ID, and CSRF header. Cookie supply is established; acceptance of this child operation is not. The successful root route establishes access to roots only.

No HTTP 401, 403, or 429 was observed in these three child attempts. The HTML response is consistent with an application document/fallback, but the evidence cannot distinguish an unsupported document ID, endpoint fallback, or child-specific authorization behavior. No header changes, alternate identities, routes, retries, or further live requests were used. Thus current support for this child operation is **not established**; the exact server-side reason for the HTML response is unknown.

The bounded run also made the normal target-page navigation and CloakBrowser's logged PyPI/GitHub version-check requests. It issued one child POST, sequentially, and no root GraphQL requests.

## Separate REST child-comments finding (2026-10-02)

The newly reported `GET /api/v1/media/{media_id}/comments/{comment_id}/child_comments/`
request belongs to a different post/account from this qualification target.
Its reported initial query has an empty `min_id`,
`is_chronological=true`, and `paging_direction=view_more`. No response JSON or
capture metadata for that request was attached or found in the local response
inventory. The currently open browser page exposes only rendered post content;
I did not trigger a request from it or use its IDs/session for this
qualification.

The historical [instagram_private_api `comment_replies` implementation](https://github.com/ping/instagram_private_api/blob/master/instagram_private_api/endpoints/media.py)
documents `child_comments`, `parent_comment`,
`has_more_tail_child_comments`, and `next_max_child_cursor`, with a fixed page
size of 20 and a `max_id` pagination argument. This corroborates the endpoint's
historical shape, but the `min_id`/`paging_direction` request report and absent
response body leave current field and cursor behavior unvalidated. It does not
establish whether any `child_comments` are missing from `Dd6m2a6Exca`.

No REST reply adapter was added. There is no verified JSON schema to map into
the existing comment model or to justify writing the existing per-parent
SQLite checkpoints. The qualified `Dd6m2a6Exca` figures above are unchanged;
the reported 11-record difference remains unresolved.

## Counts and timestamps

| Observation | Reported count | Unique roots | Embedded replies | Combined unique records | Arithmetic difference |
|---|---:|---:|---:|---:|---:|
| Archived report, 2026-10-02 00:58:23 UTC | 1,570 | 1,535 | 0 | 1,535 | 35 |
| Latest report, 2026-10-02 04:14:54 UTC | 1,574 | 1,539 | 24 | 1,563 | 11 |

The root count and reported count each rose by four between observations, so the root-only difference remained 35. The 24 embedded replies reduce the current arithmetic difference to 11. The reply previews' creation timestamps span 2026-09-30 15:05:32 UTC through 2026-10-01 04:41:34 UTC; each is later than its parent. These observations are not a same-time count contract. Instagram's reported-count scope and whether it includes replies remain unverified. Numerical agreement would not prove complete coverage.

## Recovery audit

- The archived SQLite database retains 1,535 roots and a completed 33-page root checkpoint with `natural_exhaustion`; the archived source remains present.
- Before the bounded run, the canonical state had 1,539 roots, a completed 33-page root checkpoint, and no checkpoint for the selected parent. The run resumed that checkpoint without replaying root GraphQL pages; root record update times predate the run.
- The selected branch now has an `unexpected_schema` checkpoint at page 0. The other ten unattempted branches have no fabricated progress.
- Regression tests cover nested legacy SQLite migration without source removal, completed-root resume, cursor restoration for interrupted roots and replies, stable-ID replay, repeated records, and atomic record/checkpoint transactions.
- Reply pagination is implemented as a separate per-parent cursor, but there is no genuine linked sequential child-response fixture to qualify continuation or natural exhaustion.

## Test-suite audit

`python -m pytest --collect-only -q` discovered **50 tests in seven files**. `python -m pytest -q` executed **50: 50 passed, 0 skipped**. Runtime dependencies Crawlee and CloakBrowser are declared in the project's base dependencies; the test extra adds pytest. The optional `importorskip("crawlee")` case ran here, so no dependency exclusion accounts for this run.

The earlier **66 passed** value appears in historical reports describing a documented Graph API/root-pagination test path that is absent from this checkout. Current Git history shows no deleted test files, and the current worktree has no test-file deletions. The exact 18-case inventory behind that historical number is not recoverable from the available Git history; it is a different/stale test snapshot, not a current skip. The prior 48-test result predates the two bounded-diagnostic regression tests added for this audit.

## Qualification

| Area | Status | Evidence |
|---|---|---|
| Root traversal | Complete for saved run | 1,539 roots; 33 pages; natural cursor exhaustion; resume did not replay roots. |
| Embedded reply collection | Verified | 24 unique, parent-linked preview replies; no root ID overlap. |
| Reply branch completeness | Partial | 13 advertised parents; 3 child requests returned non-JSON; 10 unattempted; no child terminal cursor. |
| Reply pagination | Not qualified | Imported fixture is one unrelated terminal-shaped sample; no genuine sequential response pair. |
| Count reconciliation | Unresolved | 1,574 reported versus 1,563 combined unique records; difference 11; count semantics unknown. |
| Checkpoint recovery | Qualified offline and root-resume observed | Regression tests pass; bounded live run reused the completed root checkpoint. |

No additional replies were recovered. The available authorized child interface currently returns application-shell-like HTML in the one bounded probe, while existing artifacts lack the two earlier bodies and any linked child continuation. This establishes the observed failure mode and its evidence limits; it does not prove the operation is permanently unsupported or that no other permitted UI path can expose replies.
