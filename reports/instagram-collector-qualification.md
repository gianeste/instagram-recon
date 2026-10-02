# Instagram collector qualification

> Current status: `collect` is the only live collector entry point. It traverses root comments through the legacy GraphQL query inside Crawlee + CloakBrowser; the 33-page qualification returned 1,535 unique roots and reached the endpoint's terminal cursor. It does not fetch replies, and the reported-count mismatch leaves total coverage partial. See the [current qualification](instagram-legacy-graphql-crawlee-qualification-20261001.md). The remaining sections are a historical snapshot.

**Date:** 2026-10-01  
**Implementation:** 0.1.0  
**Historical documented Graph API requests at the time of this snapshot:** 0

## Result

The repository contains a read-only collector for the documented Instagram Platform Graph API. Offline tests exercise URL parsing, request encoding, API error handling, SQLite persistence, cursor progression, duplicate suppression, metadata observation history, refresh, and resume after both budget stop and an abrupt process stop. The previously recorded offline result is **16 passed**.

The current Edge session is authenticated and displays the requested post URL. A browser-visible smoke observation showed the verified `apple` account, caption “The one and only @roses_are_rosie”, date label “September 19”, about 1.8M likes, 48.6K reposts, and the “View all 4,471 comments” link. These are UI labels, not captured API fields; the count may change. The browser control did not expose the Network panel or request/response bodies. No post metadata or comment response schema was inspected, and no live API pagination or reply behavior is confirmed. The sample media ID in the project brief is not independently verified from the UI and is not hardcoded into the collector.

No Graph API token was configured at the time of this historical snapshot. The current internal-web settings remain local and are not reproduced in this report.

## Implemented request paths

These are the paths the code is written to call; none was live-qualified in this run:

| Purpose | Graph API path | Qualification |
|---|---|---|
| Resolve shortcode by enumerating the authorized account's media | /{ig_user_id}/media | Offline only |
| Read an explicitly supplied media ID | /{ig_media_id} | Offline only |
| Read root comments | /{ig_media_id}/comments | Offline only |
| Read replies for each root comment | /{ig_comment_id}/replies | Offline only |

The private browser request /api/v1/media/{media_id}/comments/ and its min_id token are not used. Its response and continuation semantics remain unobserved. The API client selects the documented Graph API host from the configured login mode and sends the app token only in the Authorization header.

## Evidence matrix

| Capability | Code | Offline evidence | Live evidence |
|---|---|---|---|
| Parse post/reel URL and shortcode | Implemented | Pytest cases | Not applicable |
| Resolve URL to media ID through connected-account media | Implemented | Synthetic Graph page | Not tested |
| Validate explicit media ID against permalink | Implemented | Synthetic response | Not tested |
| Normalize metadata, caption tags, author, and carousel children | Implemented | Synthetic response | Not tested |
| Page root comments | Implemented | Two-page synthetic response | Not tested |
| Page replies | Implemented | Synthetic replies edge | Not tested |
| Cursor encoding and continuation | Implemented | Mock HTTP request and synthetic pages | Not tested |
| Natural exhaustion | Implemented from absence of Graph paging.next | Synthetic terminal page | Not tested |
| Repeated/missing cursor stop | Implemented | Synthetic repeated-cursor case | Not tested |
| Request budget and resume | Implemented | Interrupted synthetic traversal then resume | Not tested |
| Refresh and stable-ID deduplication | Implemented | Repeated synthetic traversal | Not tested |
| Metadata observation history and null-preserving latest snapshot | Implemented | Synthetic refresh snapshots | Not tested |
| Resume after an abrupt process stop | Implemented | Synthetic interrupted refresh then resume | Not tested |
| Field provenance for returned/null/omitted/unrequested values | Implemented | Synthetic response | Not tested |
| Comment-count reconciliation | Implemented as a separate comparison | Synthetic matching count | Not tested |
| Manual Playwright response capture | Implemented as an observation utility | Sanitizer, operation-matching tests, and one supplied child-response fixture | No live continuation captured |
| Anonymous/authenticated comparison | Not implemented | None | Not tested |
| Ordering modes | Not implemented | Meta's official collection says ordering is unsupported | Not tested |
| Web GraphQL/REST private endpoints | Not implemented | Request-only evidence is documented separately | Not tested |

Synthetic responses exist only inside tests; they must not be read as captured Instagram results.

The requested media field set is deliberately limited to identity, caption, media type/product type, permalink, timestamp, account username/owner ID, engagement counts, media/thumbnail URLs, and child media identity/type/URLs. Other profile and media details are marked `not_requested`; a requested field can be `not_returned` or `returned_null`. `metadata_complete` covers only core media ID, permalink, media type, and timestamp. Per-run post/author snapshots are retained in SQLite and exported as `metadata_observations.jsonl`.

## Boundaries

The public Meta API collection is a distinct product interface from the Instagram web GraphQL and REST-style endpoints in the request captures. It describes professional-account media and comment management, hashtagged media, cursor pagination, and restrictions by login path. It does not establish that arbitrary public post shortcodes or arbitrary public comment trees are accessible to this app. [Meta Instagram API collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api)

For the existing documented-API implementation, returned media fields for this app, whether its professional account can resolve the sample shortcode, comment response field availability, reply edge behavior, natural pagination exhaustion, response schema changes, and count agreement remain unknown. A future live run should begin with one metadata request and one comment page, save sanitized response examples, then page/resume only after the continuation shape is confirmed. The internal web GraphQL/session-cookie path remains unqualified. A separate Playwright observation utility now captures responses generated by manual browsing, but it does not replay requests or turn an unverified fixture into a collector.

## Reproducible commands

    python -m pip install -e ".[test]"
    python -m pytest -q
    python -m instagram_collector collect "https://www.instagram.com/p/DdeY69zlNuQ" --include-replies --max-requests 10
    python -m instagram_collector status DdeY69zlNuQ
    python -m instagram_collector export DdeY69zlNuQ

The live collect command will fail closed until IG_RECON_ACCESS_TOKEN, IG_RECON_USER_ID, IG_RECON_LOGIN_MODE, and IG_RECON_API_VERSION are set in the process environment.
