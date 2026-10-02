# Dd6m2a6Exca session and GraphQL qualification

**Observed:** 2026-10-01  
**Target:** `https://www.instagram.com/p/Dd6m2a6Exca/`  
**Goal:** determine whether the authorized account session can retrieve post metadata, image URLs, and comment trees through Instagram's internal GraphQL interface.

## Evidence obtained

The connected Edge profile already had this post open. No navigation, reload, comment-pagination click, or reply-expansion click was performed. The authenticated page displayed `meovv`, a verified badge, the caption announcing MEOVV's `[GO HARD]` single album, an approximate `198K likes` label, and visible comments with reply controls.

| Data | Evidence | Limit |
|---|---|---|
| Caption and author | Rendered page/DOM | Browser observation; no GraphQL response provenance |
| Publication timestamp | DOM `time[datetime]`: `2026-09-30T15:00:33.000Z` | Rendered metadata, not a verified API field |
| Image URLs and bytes | Two assets from the current page inventory were exported as JPEGs: 190,261 and 141,208 bytes | Two currently loaded carousel images; total carousel coverage is unknown |
| Comment sample | 15 visible comment links yielded IDs and ISO timestamps; rendered comment-container text was retained | A sample only; no root pagination or replies were traversed |
| GraphQL operation/request/response | No target-specific network body is available through the current browser automation API | **UNVERIFIED** |
| Complete comment tree | No captured reply response or cursor sequence | **UNVERIFIED / incomplete** |

Artifacts under `data/Dd6m2a6Exca/`:

- `browser_observation.json`: caption, timestamp, UI labels, 15 comment IDs/timestamps/rendered texts, and explicit partial/provenance flags.
- `browser_assets/manifest.json`: the two observed image URLs, filenames, byte counts, SHA-256 hashes, and browser-asset provenance.
- `browser_assets/f927c1a51e6c33ce.jpg` and `browser_assets/43e111a8f97ed304.jpg`: downloaded JPEG bytes. The first image was visually inspected locally.

These artifacts contain no account cookie, CSRF token, session secret, or copied authentication header. Image URLs include the CDN's resource parameters and may expire; they are not account-session credentials.

## GraphQL qualification boundary

The browser tool supports reading the current DOM and exporting observed assets. Its advertised capabilities do not include Network request/response bodies. The inline JSON scripts in the current document did not contain the target shortcode; the target may have been opened through client-side navigation. This observation does not establish which operation loaded it. Unrelated notification/direct-message records were not exported.

A follow-up capability check confirmed that browser-level capabilities expose only viewport controls and the tab exposes only `pageAssets`. The GraphQL-filtered console-log query returned zero entries. No HAR was found in the workspace or supplied attachment directory, and no response/GraphQL JSON capture was found by filename in the workspace. These checks do not inspect the whole computer or prove the browser made no GraphQL requests; they establish that no usable capture is currently available through these surfaces.

The earlier `PolarisPostCommentsPaginationQuery` request returned HTTP 429 with zero bytes. It was not retried, and no alternative request was sent to work around that rate limit. The two JPEG acquisitions used the browser asset exporter for already observed CDN URLs.

## Fresh direct REST probe

Two read-only initial requests were made on 2026-10-01 to the observed
`GET /api/v1/media/{media_id}/comments/` route for this post. The first used
the local session configuration and the second added the two normal
browser-context headers present in the supplied capture. Neither request was
redirected or retried.

| Variant | HTTP | Content type | Bytes | JSON | Result |
|---|---:|---|---:|---|---|
| local session headers | 200 | `text/html` | 650,161 | no | no comment page |
| browser-context headers | 200 | `text/html` | 650,457 | no | no comment page |

Both responses ended at the comments path. Their title was `instagram`.
The sanitized second-pass inspection found login/challenge markers, but no
canonical or recognizable bootstrap marker. This is classified as
**INCONCLUSIVE HTML access/application fallback**; the retained diagnostics do
not prove whether the document is Instagram's normal shell or an access page.
No comment IDs, continuation cursor, or pagination response was obtained.

Machine-readable diagnostics:

- `data/rest-pagination-Dd6m2a6Exca-20261001.json`
- `data/rest-pagination-Dd6m2a6Exca-20261001-header-variant.json`

The direct REST result for this post is therefore not comparable to the
previous seven-page JSON sequence for `Dd9MKlfTDho`; this target remains
unqualified for comment pagination.

Therefore the account's browser session demonstrably exposes useful data for this target, but **cookie-backed Python GraphQL retrieval is not yet proven**. No metadata document ID, media-ID response field, GraphQL comment schema, cursor sequence, or complete reply tree was established for this target. The original GraphQL objective remains unachieved; qualification is blocked pending a usable target response capture while the no-retry instruction remains in effect.

## Next evidence required

An already captured, sanitized GraphQL response for this exact post, together with its operation name and non-secret request variables, can be inspected by the existing offline importer. A path to such a local JSON/HAR capture was requested. It must omit cookies, authorization/session/CSRF material, and request signatures. A successful response is needed before implementing a target-specific parser or attempting pagination.

No collector source was changed, and no commit or push was made. The existing offline test result is historical evidence only; it does not qualify this post's live GraphQL behavior.
