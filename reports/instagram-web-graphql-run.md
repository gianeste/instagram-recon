# Instagram web GraphQL run record

**Date:** 2026-10-01  
**Target:** `https://www.instagram.com/p/DdeY69zlNuQ/`

## Last live result

The one initial-page request to `POST https://www.instagram.com/api/graphql` using `PolarisPostCommentsPaginationQuery` returned:

| Diagnostic | Observation |
|---|---|
| HTTP status | `429` |
| Content type | `text/plain` |
| Response bytes | `0` |
| Classification | `rate_limited` / empty body |
| Retry | None |
| Comments saved | None |

The client did not print or store the response body, cookie, token, or redirect URL. No further Instagram requests were made. This response cannot be used as a comment fixture.

## Operation catalog update

The latest user-provided observations add the root REST operation and child-reply GraphQL operation below. Their request schemas are recorded in [the operation catalog](instagram-operation-catalog.md). One supplied child-response artifact and one genuine browser-observed root schema projection are now field-mapped offline; request linkage and multi-page pagination remain unverified.

| Surface | Request evidence | Response schema | Status |
|---|---|---|---|
| `PolarisSearchBoxRefetchableQuery` | User-provided search request description. | **UNVERIFIED** | No response retained; suggestions vs content discovery, result categories, ranking, `include_reel` effect, and paging are unknown. |
| `GET /api/v1/media/{media_id}/comments/` | User supplied a continuation-shaped request with `sort_order=popular`, `can_support_threading=true`, and structured `min_id` (`cached_comments_cursor` plus `bifilter_token`). Values and credentials were not retained. A separate one-shot local probe returned `200 text/html` (651,207 bytes), while an authorized browser continuation displayed a JSON root-comment envelope. | **SCHEMA VALIDATED (redacted projection)** | One browser page exposes root fields and pagination flags. Cursor advancement, ordering coverage, and live completeness remain unverified. |
| `PolarisPostChildCommentsQuery` | User reports observing reply operation; observed `doc_id=28027289793632076`, with variables `media_id`, `parent_comment_id`, `after`, `before`, `first`, `last`, `is_chronological`. | **SHAPE VALIDATED** | `fixtures/polaris_child_comments_tree.sanitized.json` maps reply IDs, parents, authors, text, numeric timestamps, likes, null child counts, and page-info fields. The artifact does not retain request metadata, so operation linkage is unverified. |
| `PolarisPostCommentsPaginationQuery` | User-supplied cURL request; one client request was made. | **UNVERIFIED** | The HTTP 429 returned no schema. |

Operation names and document IDs are internal web application details and are treated as version-dependent. A reported `doc_id` does not establish stability or permission for automated use.

## Fixture importer and normalized model

The new offline command is:

```powershell
python -m instagram_collector inspect-response .\sanitized-response.json `
  --operation PolarisPostChildCommentsQuery `
  --comment-id-path 'data.comments.edges[*].node.id'
```

It identifies JSON object/array structure, nested field types and likely comment/parent/author/timestamp/text/count/pagination fields, and computes a response-shape fingerprint. It does not load `.env`, contact Instagram, or persist raw responses. Credential-like fields are rejected. ID values are emitted only when an explicit comment-ID path is requested.

Normalization requires a reviewed field map marked `verified: true` whose fingerprint matches the fixture. It reuses the existing normalized comment model (ID, media ID, parent ID, author ID/name, text, timestamp, like count, reported reply count, field status, provenance). The child mapping is at `fixtures/polaris_child_comments_mapping.json`; the root projection mapping is at `fixtures/instagram_root_comments_mapping.json`.

## Completeness semantics and offline tests

The one-page web report now remains partial even if a future response has no next cursor: `live_qualified`, `response_schema_verified`, and `pagination_semantics_verified` remain false; `root_comments_protocol_complete` remains false. A missing or unverified interface schema cannot be treated as natural exhaustion.

Existing deterministic offline tests exercise the documented Graph API collector's initial and continuation pages, cursor advancement/repetition, natural exhaustion, missing pagination data, reply branches, deduplication, and interrupted traversal/resume. The new root test uses the redacted browser schema projection for field handling; pagination tests remain synthetic or one-page observations and do not count as live qualification. Latest full offline run: **66 passed**.

## Documented API boundary

Meta's documented Instagram API and the internal web interfaces are separate products. Meta describes professional-account access to owned media and management/replies to comments on that media, with cursor pagination; this is not general access to arbitrary public posts. [Meta's Instagram API collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-db99ce99-bf76-475c-8b76-718576c11cae)

For an authorized professional test account, the documented path can validate accessible media metadata, root comments on the account's own media, and replies to those comments when app permissions permit. The existing `collect-graph-api` code has corresponding media, comments, and replies paths. No Graph API token or live response was used in this checkout, so those paths remain unqualified here.

Do not infer that documented API access extends to arbitrary posts, or that an authenticated web session authorizes automated use of the private web endpoints. Do not retry the rate-limited operation or use a workaround.
