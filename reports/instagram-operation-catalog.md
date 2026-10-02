# Instagram operation catalog and fixture status

**Updated:** 2026-10-01  
**Boundary:** one bounded seven-page REST sequence reached natural exhaustion on 2026-10-01. The recorded GraphQL HTTP 429 remains restricted and was not retried.

This catalog records request observations, not stable API contracts. One imported child-comment response, one genuine browser-observed root shape, and one bounded two-page REST sequence are available; terminal and complete-coverage semantics remain fail-closed.

## Observed internal web operations

| Operation | Request evidence | Known inputs | REQUEST_OBSERVED | RESPONSE_OBSERVED | SCHEMA_VALIDATED | PAGINATION_VALIDATED | LIVE_COLLECTION_QUALIFIED |
|---|---|---|---:|---:|---:|---:|---:|
| `PolarisSearchBoxRefetchableQuery` | User supplied an authenticated browser request description for `POST /api/graphql`, search term `samsung`, `context=blended`, `search_surface=web_top_search`, and `include_reel=true`. No response was retained. | `query` is a search-term input. `context`, `search_surface`, and `include_reel` are candidate behavior inputs; their actual effects are untested. Request/session state and transport fields are not result filters. | YES | NO | NO | NO | NO |
| `GET /api/v1/media/{media_id}/comments/` | User supplied an authorized-browser cURL shape. A bounded Python run observed seven JSON pages, six advancing `min_id` continuations, and a terminal page. | `media_id` identifies the media; `can_support_threading`, `permalink_enabled`, and opaque `min_id`/`max_id` state are semantic inputs. The sequence returned 93 unique IDs with zero overlap; page 7 had both continuation flags false and no cursor. | YES | YES (seven JSON pages) | YES (reviewed mapping) | YES (headload transition and terminal response) | NO |
| `PolarisPostChildCommentsQuery` | User reports observing this reply operation. Observed `doc_id`: `28027289793632076`; a supplied `tree.txt` response artifact has the matching child-comment connection shape, but its request metadata was not retained. | `media_id`, `parent_comment_id`, `after`, `before`, `first`, `last`, and `is_chronological`. Pagination and chronological semantics have not been measured. | YES | YES (fixture; request linkage unverified) | YES (fixture mapping) | NO | NO |
| `PolarisPostCommentsPaginationQuery` | User supplied a comments GraphQL request; the client made one initial-page request. | `media_id`, `after`, `before`, `first`, `last`, and `sort_order` are request variables. The captured continuation included opaque state that is not copied here. | YES | YES (429, zero bytes) | NO | NO | NO |

For search, no category is confirmed: users, hashtags, places, posts, Reels, other types, and suggestions are all unobserved. There is no captured submit/navigation sequence to establish whether the search-box operation is followed by a different content-discovery operation. Pagination and ranking are likewise unknown.

### Reviewed child-response fixture

`fixtures/polaris_child_comments_tree.sanitized.json` is a sanitized copy of
the supplied `tree.txt` JSON artifact. Its structural fingerprint is
`367241e0b9b6ec0e9a1e338675fd06ba533e372351afd91f644581cdf7919f15` and it
contains three child-comment edges under
`$.data.xdt_api__v1__media__media_id__comments__parent_comment_id__child_comments__connection.edges`.
The reviewed mapping is
`fixtures/polaris_child_comments_mapping.json`.

The fixture supports these mappings: comment ID `node.pk`; parent ID
`node.parent_comment_id`; author ID and username `node.user.pk` and
`node.user.username`; text `node.text`; numeric epoch creation time
`node.created_at`; like count `node.comment_like_count`; and reported child
count `node.child_comment_count`. All three items have a parent ID and the
child-count field is explicitly null. The connection exposes
`page_info.has_next_page` and `page_info.end_cursor`; this one page reports
`false` and `null`. That is a terminal response observation, not proof that
the operation's cursor protocol or live completeness is qualified.

### Reviewed root-comment response shape

The genuine browser observation is retained as the redacted schema projection
`fixtures/instagram_root_comments_browser.schema.json`, with mapping
`fixtures/instagram_root_comments_mapping.json` and metadata in
`data/instagram-probe/root-comments-browser-response.metadata.json`. The page
contained 15 root comments while reporting `comment_count=1562`, with root
fields `pk`, `strong_id__`, `text`, numeric creation timestamps,
`comment_like_count`, `child_comment_count`, and nested `user` metadata. Root
items had no observed parent field, so the reviewed normalizer supplies a null
parent ID. The response reported `status=ok`, `sort_order=popular`,
`threading_enabled=true`, `has_more_comments=false`,
`has_more_headload_comments=true`, and a present `next_min_id`.

The retained file is a two-item redacted projection rather than a complete raw
response. It validates field mapping and type handling, but does not validate
cursor advancement, ordering beyond the returned `popular` flags, or complete
coverage.

The offline evaluator in `instagram_collector.root_pagination` keeps the two
mechanisms independent and only reports `COMPLETE` when both are explicitly
terminal. It preserves opaque cursor strings, detects repeats, duplicate pages,
missing fields, and contradictory flags, and reports ambiguous state as
`PARTIAL`. No SQLite checkpoint is advanced by this evaluator.

The bounded REST sequence is documented in [the extended pagination qualification report](instagram-rest-pagination-qualification-12p-20261001.md). It qualifies six headload cursor transitions and one terminal response, but does not establish reported-count coverage or chronological ordering. Operation names and document IDs belong to Instagram's web application bundle and are treated as version-dependent. Only the child-query ID above is recorded because it was explicitly supplied for this recon. No observation establishes whether an identifier changes between sessions or releases. A request `doc_id` routes an internal query; it does not make that query a documented or authorized API contract.

### Inputs and incidental state

Inputs naming a media, parent comment, query text, sort choice, threading mode, or cursor are candidate semantic inputs because they describe the requested target or traversal. Their actual effects still require matched, authorized browser observations. Browser form fields, application/revision identifiers, CSRF/session material, and Relay provider state are transport or application state; their exact necessity and version behavior are not established here. No credential values, captured cursors, or request signatures are recorded in this catalog.

## Browser response capture

`python -m tools.capture_instagram_responses` attaches to a manually driven Playwright browser and observes matching responses. It recognizes the REST root-comment path, GraphQL child-comment operations, and other GraphQL operation names containing `comment` or `reply`. It never replays a request, writes request headers, or stores a raw form body. Only an allowlisted set of semantic pagination variables is retained. JSON fixtures are sanitized before writing; signed URL query strings and credential-like fields are removed. HTTP 401/403/429/451 and explicit challenge/login/rate-limit markers are recorded as metadata and stop the capture without retry.

The capture manifest runs the existing offline inspector on each JSON fixture and records its shape fingerprint, structural schema, and pagination candidate paths. `SCHEMA_VALIDATED` remains false until a reviewer confirms field mappings against an authentic fixture. The child fixture and the reviewed root schema projection are the two reviewed exceptions; neither is a live collection qualification.

See the dedicated [browser capture report](instagram-browser-capture.md) for setup and evidence boundaries.
See the [comment traversal qualification report](instagram-comment-traversal-qualification.md) for provenance and missing-page status.

## Sanitized fixture handling

`python -m instagram_collector inspect-response response.json` runs offline. It reports a JSON-shaped schema, nested field paths and types, object/array paths, candidate comment/parent/author/text/count/time/pagination fields, and a SHA-256 fingerprint of the response shape (field names and JSON types; values do not affect it). It rejects common credential-bearing field names and never loads `.env`, sends requests, or writes the raw response.

Example with explicit ID extraction:

```powershell
python -m instagram_collector inspect-response .\sanitized-response.json `
  --operation PolarisPostChildCommentsQuery `
  --comment-id-path 'data.comments.edges[*].node.id' `
  --output .\reports\response-shape.json
```

Candidate paths are inspection hints, not confirmed field semantics. Comment IDs are extracted only for paths explicitly supplied by the operator. Normalized rows use the repository's existing `normalize_comment` shape; normalization is refused unless a human-reviewed mapping is marked `verified: true` and its shape fingerprint exactly matches the response. The child-response and root-response mappings above are the only verified internal-web mappings. Fixture values are not part of the default analysis output.

The existing normalized comment record contains `id`, `media_id`, `parent_id`, `author_id`, `username`, `text`, UTC `created_at`, original `timestamp_raw`, `like_count`, `reported_reply_count`, `visibility`, `field_status`, `source`, and `collected_at`. A response mapping must explicitly identify paths for fields that are present; the parser does not infer root/reply meaning from names alone. The reviewed child fixture established numeric epoch seconds, so the shared timestamp normalizer now accepts numeric seconds (and millisecond values) while preserving the raw value. These records match the model persisted by the existing SQLite `StateStore`; no second comment table or raw-response store was added.

To normalize a reviewed fixture, pass a JSON mapping file with `operation`, `verified: true`, `response_shape_fingerprint`, `items_path`, and a `fields` object. `id` is required; supported explicit fields are `parent_id`, `author_id`, `author_username`, `username`, `text`, `timestamp`, `like_count`, and `reply_count`. Then pass `--mapping mapping.json --media-id <id>` to `inspect-response`. A reply branch without a mapped parent field may use the explicitly supplied `--parent-id` context.

The `verified` marker is a review gate, not proof that Instagram guarantees the schema. A mapping must be reviewed against sanitized real responses from the relevant operation before use. The importer does not store a session, credentials, or a raw response, and is not a network collector.

The earlier hard-coded web `edges/node` parser was removed because no real response established those fields. The live `collect` command now inspects only the JSON shape, writes no comment records, and reports `schema_unverified`.

## Existing offline pagination coverage

The existing documented Graph API collector reuses `StateStore` and the normalized comment model. Its offline tests cover an initial and continuation page, cursor advancement, repeated cursors, natural exhaustion, missing paging data/cursor, partial reply branches, duplicate IDs, and interrupted traversal/resume. Those tests use synthetic Graph API-shaped responses. They establish local state-machine behavior only; they do **not** qualify any internal Instagram web response schema or prove live completeness. Latest full offline run: **66 passed**.

The child fixture test, root schema-projection test, and root pagination
evaluator tests are fixture-backed/offline for field normalization. The
extended REST sequence now qualifies six genuine headload cursor transitions
and natural exhaustion for that sequence; repeated-cursor handling under the
live route, reply-branch fan-out, and reported-count consistency remain
unverified.
The root browser page's `has_more_comments=false` is not sufficient because
`has_more_headload_comments=true` and `next_min_id` were also present. The
observed `sort_order=popular`/`is_ranked=true` values show a ranked view only;
they do not establish chronological ordering or full coverage of the reported
comment count.

## Access and feasibility boundary

Meta's documented Instagram API is separate from the internal web REST and GraphQL operations above. Meta's official collection describes access for professional accounts to their own media and management/replies to comments on that media; it also documents cursor paging and says consumer accounts are not accessible through the Facebook Login API. The current app's token, granted scopes, and live API response have not been validated here. [Meta's Instagram API collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-db99ce99-bf76-475c-8b76-718576c11cae)

With an eligible professional test account, the documented API can be used to validate the account's accessible media metadata, root comments on that owned media, and replies for those comments when the app's permissions allow. The existing code paths are `GET /{ig-user-id}/media`, `GET /{ig-media-id}/comments`, and `GET /{ig-comment-id}/replies`. None has been live-qualified in this checkout, and the configured web-session cookie is not a Graph API credential.

Those documented permissions do not imply access to comments on arbitrary posts. The internal web endpoints are undocumented application interfaces; a browser session and an observed operation name do not establish authorization for automated collection. The latest web GraphQL attempt was rate limited and was not retried; the separate seven-page REST observation does not establish production or arbitrary-post coverage.

**Feasibility:** own-account media and comment collection is a plausible bounded use of the approved professional-account API, pending an authorized live test with its own token and scopes. Arbitrary customer-keyword discovery of actual posts remains unproven by web search evidence and is not offered by the documented commercial Graph API. No comprehensive search or collection coverage is claimed.
