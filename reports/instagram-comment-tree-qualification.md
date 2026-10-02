# Instagram post collection and refresh qualification

**Date:** 2026-10-02  
**Target:** `Dd6m2a6Exca`  
**Status:** Root traversal qualified; refresh qualified offline; post metadata partial; reply traversal incomplete.  
**Evidence:** Existing archived collection, saved browser observation, SQLite state, deterministic tests. No live requests were made for this update, and the archived collection was not modified.

## Post metadata availability

The saved root GraphQL response shape has `shortcode_media.edge_media_to_parent_comment` and its comment connection. It does not return the wider post object. The collector now stores the returned comment count with its source and observation time. It keeps the requested shortcode and canonical URL, but the archived response does not contain Instagram's stable media ID; the database key remains `shortcode:Dd6m2a6Exca`.

| Field | Evidence and status |
|---|---|
| Stable media ID | Not returned by the root operation. Stored ID is the explicit shortcode surrogate. |
| Shortcode | Available from the requested post URL. |
| Canonical permalink | Normalized from the requested URL and stored; not returned in the root response. |
| Post owner ID | Unavailable. Comment owner IDs do not establish post ownership. |
| Post owner username | `meovv` in the existing authenticated browser DOM observation; absent from the root media object. |
| Caption | Present in the existing browser DOM observation; absent from the root media object. |
| Publication timestamp | `2026-09-30T15:00:33Z` in that DOM observation; absent from the root media object. |
| Media type | Not established by the root response or saved metadata. |
| Like count | DOM observation showed the approximate label `198K likes`; no exact count is available. |
| Comment count | `1,574`, returned as `edge_media_to_parent_comment.count`. |
| Carousel children | The separate page inventory captured two image assets, but no stable child IDs or complete child list; total carousel coverage is unknown. |
| Media dimensions | Not returned by the root operation and not preserved in the browser observation. |
| Reel metadata | Not returned or captured. |

The DOM fields are separate observations and are not represented as fields from the root GraphQL operation. `metadata_complete` remains false. No extra metadata request was added.

## Root collection and refresh

The existing root query and sequential cursor traversal remain unchanged. The archived target has **1,539 unique roots** across **33 pages**, with natural cursor exhaustion. The full saved traversal took **43.378 seconds**. The later saved runs reused the completed root checkpoint; their shorter runtimes are not refresh measurements.

`--refresh` now traverses using the independent `comments_refresh` checkpoint. It preserves the completed `comments` checkpoint and existing normalized records. Each page still writes records, observations, and its cursor checkpoint in one SQLite transaction. `--resume` detects an interrupted refresh and continues the same scan ID from its saved refresh cursor. Stable comment IDs deduplicate records, and populated values survive later null observations.

A refresh compares current scan observations with earlier observations and reports new IDs, changed fields, and IDs not observed once. Not observed once does not mean deleted. The endpoint's ranked order has not been established as chronological. A bounded refresh must report partial; complete discovery through the currently exposed root result requires walking the full cursor chain rather than assuming a fixed number of initial pages is enough.

No live refresh was run, so this qualification has **no live refresh additions or updates**, and no refresh runtime measurement. The deterministic fixture discovered one new root, detected one text update, and retained one previously seen but unobserved record. If the current target still exposes the archived 33-page chain, a complete refresh requires up to 33 sequential root-page requests; none were made during this update.

## Reply reconciliation

All **24 stored replies** are linked to root comments and have source `instagram_legacy_graphql_embedded_reply`. The 13 roots below advertise **32 replies** in total. Ten roots have preview counts matching their advertised counts; three have an observed preview deficit totaling eight. A matching preview count still does not qualify a reply branch as independently traversed.

| Parent comment ID | Advertised | Embedded replies | Difference | Historical child attempt |
|---|---:|---:|---:|---|
| `17922294696431093` | 2 | 2 | 0 | HTTP 200, non-JSON |
| `17952948762036948` | 5 | 3 | 2 | HTTP 200, non-JSON |
| `17957667768217768` | 1 | 1 | 0 | Not attempted |
| `17991458538100516` | 6 | 3 | 3 | HTTP 200, non-JSON |
| `18012381932953446` | 1 | 1 | 0 | Not attempted |
| `18024417638704314` | 2 | 2 | 0 | Not attempted |
| `18077655707395633` | 2 | 2 | 0 | Not attempted |
| `18102906863133185` | 2 | 2 | 0 | Not attempted |
| `18107727470190690` | 1 | 1 | 0 | Not attempted |
| `18118624037515599` | 6 | 3 | 3 | Not attempted |
| `18133974553645453` | 1 | 1 | 0 | Not attempted |
| `18137828113622515` | 2 | 2 | 0 | Not attempted |
| `18629091568056431` | 1 | 1 | 0 | Not attempted |
| **Total** | **32** | **24** | **8** | **3 attempted, 10 not attempted** |

The latest saved database contains three attempted child branches, despite earlier notes recording two attempts. Its report shows three HTTP 200 non-JSON responses, with response sizes 650,736, 650,824, and 650,814 bytes; the latest capture identifies `text/html`. No child response produced a reply record or a valid pagination page. No child request was made for this update, and ordinary collection now extracts embedded replies only.

The overall count comparison is **1,539 roots + 24 replies = 1,563 unique records**, against **1,574 reported comments**, leaving an arithmetic difference of **11**. The eight advertised replies absent from embedded previews do not account for all 11. The reported count's visibility and reply scope remain unverified; numerical agreement would not prove complete coverage.

## Checkpoint and test qualification

Offline recovery coverage verifies legacy SQLite migration, preservation of the completed root checkpoint, separate refresh cursor restoration, interrupted refresh continuation, stable-ID deduplication, mutable-field detection, non-deletion of unobserved records, and atomic page/checkpoint persistence. A regression test confirms the normal page handler does not invoke the unqualified child operation.

`python -m pytest --collect-only -q` discovered **54 tests**. `python -m pytest -q` executed **54 tests: 54 passed, 0 skipped**. The prior reported 50 tests are the existing suite; this update adds four refresh and request-policy regression tests. No commits or pushes were made.

## Qualification verdict

- **Root traversal:** qualified for natural exhaustion of the saved 33-page ranked cursor chain.
- **Refresh and recovery:** qualified offline; live additions, updates, and runtime remain unmeasured.
- **Post metadata:** partial. Shortcode, permalink, and reported comment count are available; additional fields are limited to separately captured DOM observations or unavailable.
- **Reply previews:** 24 stable, linked records preserved; 8 of the 32 advertised replies are absent from previews.
- **Independent reply traversal:** unqualified for all 13 branches. Three prior attempts returned non-JSON; ten were not attempted. The child operation remains disabled in normal collection.
- **Count reconciliation:** unresolved by 11 numerically; count semantics do not establish completeness.
