# Instagram crawler reconnaissance — initial findings

**Reviewed:** 2026-10-01  
**Scope:** documented APIs, public library implementations, supplied request capture, local environment  
**Live Instagram data requests in the original reconnaissance:** 0

## Current update (2026-10-01)

The active collector now has one live entry point: `python -m instagram_collector collect`. It pages the previously qualified legacy root-comment GraphQL operation from a Crawlee `PlaywrightCrawler` running CloakBrowser. Direct HTTP clients, the documented Graph API collector, REST parsing, and manual browser capture are not active collector paths. Older reports below record those investigations.

The documented Meta API remains a separately investigated feasibility option for eligible owned media, but no Graph API live response was qualified and its collector code has been removed from this checkout. Documented access to owned media does not imply access to arbitrary posts. The internal search capture still contains no response evidence, so discovery of actual posts for arbitrary customer keywords remains unproven.

On `Dd6m2a6Exca`, that GraphQL path returned 1,535 unique roots across 33 HTTP 200 pages and reached `has_next_page=false`. The endpoint reported 1,570 comments; 13 roots advertised 32 replies that were not collected, so overall coverage remains partial. See the [Crawlee legacy GraphQL qualification](reports/instagram-legacy-graphql-crawlee-qualification-20261001.md).

## Executive finding

A useful, policy-supported collector is feasible for professional accounts that authorize our Meta app, selected hashtag feeds through the Facebook Login API, and the connected account's own media/comments/mentions. This does not replace a general Instagram discovery product: Meta's documented API does not provide arbitrary caption-keyword search, all consumer profiles, or comment trees for any public post.

The top requirement—finding posts from arbitrary customer-defined words—remains unproven for Instagram's web search and unavailable through the documented commercial Graph API. Meta Content Library/API is the closest first-party keyword-search surface found, but access is for qualified public-interest research and runs in a secure research environment.

The user reports an approved Graph API app. No Graph API token or Instagram user ID was available to the original reconnaissance, so no Graph API operation was live-qualified there. The later web GraphQL result is only a rate-limit response and does not qualify a schema or collection path. Other live operation results below remain **UNTESTED**.

## Environment and evidence

- Checkout contained one file, `curl.txt`; it was a Windows cURL export for `POST https://www.instagram.com/api/graphql`, operation `PolarisSearchBoxRefetchableQuery`, query `samsung`, surface `web_top_search`, context `blended`, and `include_reel=true`.
- The original export also contained authenticated cookies, session/CSRF material, and request signatures. It has been replaced with a credential-free summary. Those values were not replayed or copied into this report.
- The capture has no response body, HTTP status, response size, records, IDs, page info, or cursor. It establishes a request shape only; it does **not** establish that search returned posts, matched captions, included Reels in results, or paginated.
- At the time of the original reconnaissance, the computer-use inventory showed no open apps or browser tabs, and there was no configured Graph API token. This checkout now contains the Python collector, SQLite store, tests, local `.env`, and offline fixture importer; current credentials are not documented here.
- App approval is user-reported; token scopes, API login mode, account type, and linked Page have not been verified. Meta's published automated-collection guidance does not make a signed-in web session a documented API entitlement. This project does not retry the rate-limited internal endpoint or implement challenge/rate-limit workarounds.

## Capability matrix

`CONFIRMED` means an authorized live response was examined. No row is confirmed in this run. `PARTIAL` means the documented surface covers only a restricted account/content class; it is not a completeness claim.

| Capability | Result | Documented/observed access | Pagination and known boundary | Live evidence |
|---|---|---|---|---|
| Connected account profile and metadata | PARTIAL | Instagram Platform API for a connected Business/Creator account; fields depend on login path and permissions. | API edges are cursor-based. Exact returned fields and account values are untested. | UNTESTED |
| Connected account's posts and Reels | PARTIAL | The authorized professional account's media edge; Reels are media objects. | Cursor pagination exists. Full accessible history and mixed post/Reel traversal have not been exhausted. | UNTESTED |
| Another account's profile/posts | PARTIAL | Facebook Login Business Discovery can look up public Business/Creator accounts by username. | Not a general user directory; personal/private profiles are outside this surface. Full historical depth is unverified. | UNTESTED |
| Individual post details | PARTIAL | Read media reachable from the connected account or Business Discovery. Media IDs and permalinks/shortcodes are usable identifiers; field availability varies. | No broad official endpoint was found for arbitrary post URLs. Cross-edge ID equality has not been measured. | UNTESTED |
| Hashtag search | PARTIAL | Facebook Login path: resolve a hashtag, then request `top_media` or `recent_media`. Instagram Login does not expose hashtag search. | Cursor paging is documented. Meta's documented limit is 30 unique hashtags per account in a rolling 7-day period; this is a discovery feed, not a historical archive. | UNTESTED |
| Arbitrary caption keyword search | BLOCKED on the documented commercial API | No Graph API full-text post search was found. Hashtag search, account search, and search-box suggestions are different operations. | No official Graph API cursor exists for arbitrary caption terms. The supplied web request has no response, so its results are UNTESTED. | UNTESTED |
| Account search | PARTIAL | Business Discovery resolves a specified username for eligible public professional accounts. | General fuzzy display-name/user search and its result paging are not exposed by the documented API. | UNTESTED |
| Comments and nested replies on our media | PARTIAL | Comment-management API for media owned by the connected professional account. | Comment and reply edges can be paged; complete exhaustion, deleted/hidden comments, and count reconciliation were not tested. Keep `protocol_complete` separate from `reported_count_consistent`. | UNTESTED |
| Comments/replies on arbitrary public posts | BLOCKED on the documented commercial API | The standard comment-management surface is scoped to the app user's media. Meta Content Library/API has public Instagram comments for approved researchers. | Research-library access is separately gated and data is served in a secure environment. | UNTESTED |
| Mentions and tagged content | PARTIAL | Mention/tag edges for the connected account. | Does not provide a global search for all mentions of arbitrary users. | UNTESTED |
| Incremental refresh | PARTIAL | Poll known account-media and permitted hashtag edges, then deduplicate by IDs. | Hashtag quota limits term breadth; no measured refresh cadence, overlap, or webhook coverage for arbitrary discovery. | UNTESTED |
| Anonymous access | BLOCKED for the documented API | Instagram Platform calls require app/account authorization. Human-visible public pages are not a supported general collection API. | Meta's terms separately restrict automated web collection without express permission. | UNTESTED |
| Research keyword discovery | PARTIAL | Meta Content Library/API searches public Facebook/Instagram content; Meta describes near-real-time content from creator and business accounts on Instagram and public comments. | Qualified academic/nonprofit public-interest research access, application, and secure environment; not a general commercial customer API. | UNTESTED |

The 30-hashtag quota is documented by Meta-derived API references and current secondary references; confirm the exact limit in the approved app's live version before relying on it. Meta's public API collection confirms the Facebook Login/Instagram Login split, professional-account restriction, cursor pagination, hashtag discovery, comments, mentions, and lack of result ordering.

## Search and discovery findings

### Hashtags

The supported official discovery path is a Facebook Login professional account with the necessary reviewed permissions and linked Page. It has distinct top and recent media edges. The account can query at most 30 unique hashtags per rolling seven days; re-querying a previously used hashtag inside that window does not provide a general archival crawl. No live requests to `python`, `gaming`, `mechanicalkeyboards`, or `technology` were made, so result mix, ordering, pages, ceilings, and repeat overlap remain unmeasured.

### Keywords

The approved commercial Graph API has no documented arbitrary caption-search edge. The captured web query for `samsung` was a blended top-search GraphQL request with Reels requested, but its response was absent. It cannot establish full-text search, phrase matching, ranking, post/Reel coverage, or pagination. The proposed queries (`RTX 5090`, `NVIDIA`, `mechanical keyboard`, `gaming laptop`, and `artificial intelligence`) remain UNTESTED.

Meta Content Library/API is a first-party research alternative: Meta says it supports search/filtering over public content and describes Instagram creator/business content and public comments. Eligibility is limited to qualified academic or nonprofit institutions doing scientific/public-interest work. This is not a drop-in commercial search API for customer monitoring.

### Users

The official Business Discovery path is exact-username-oriented and limited to public professional accounts. It is suitable for following known account names, not as a replacement for general account search. The web search capture could have returned mixed result types; without its response, this remains unverified.

## Profile, post, comments, Reels, and refresh

- The Instagram Platform API is for Business/Creator accounts. Facebook Login requires a linked Page and is the path that adds hashtag discovery and Business Discovery. Instagram Login supports many account-management surfaces without a Page but does not add hashtag search.
- The retired Basic Display API no longer provides an official personal-account path. Consumer/personal profiles are not a supported Graph API target.
- The official API supports a connected account's media, comments/replies, and mentions. It does not make a media's reported count proof of completeness. No live pagination branch was exhausted here; both `protocol_complete` and `reported_count_consistent` are UNTESTED.
- Reels can be represented as media, and current libraries expose profile Reel operations. Whether each official hashtag/business-discovery edge returns the expected Reel mix and fields needs a live fixture comparison.
- Incremental collection is practical for a bounded set of known accounts or hashtags if IDs and cursors are persisted. It does not solve open-world keyword discovery; repeat overlap, late-arriving posts, edit/deletion behavior, and resume semantics are not measured.

## Library review

| Project | Current documented coverage | Assessment |
|---|---|---|
| [instagrapi](https://github.com/subzeroid/instagrapi) | Unofficial Python client spanning public web and private mobile API flows; users, posts, comments, hashtags, Reels, and several search result types. PyPI lists version 3.0.16 released 2026-09-29. | Actively maintained, but a wrapper for undocumented surfaces. Its own docs call anonymous web paths opportunistic. Account/session handling and protocol churn make it a poor production foundation without express authorization. Not installed or live-tested here. Do not use challenge handling to bypass a challenge. |
| [Instaloader](https://github.com/instaloader/instaloader) | Profiles, posts, hashtag targets (login required), tagged posts, Reels, single-post shortcodes, and optional comments; recent 4.15.x releases. | Useful reference for traversal/resume and metadata, but primarily a downloader over unofficial site interfaces; no general caption keyword search. Not installed or live-tested here. |
| [gallery-dl](https://github.com/mikf/gallery-dl) | Current supported-sites list includes Instagram profiles, posts, Reels, tag searches, and tagged posts; cookies are listed for Instagram. | Actively maintained downloader, useful as a parser/operation reference; not a documented Instagram API or a completeness guarantee. Not installed or live-tested here. |

Feature lists and active releases demonstrate maintenance, not stable access, permission, or exhaustive collection. None was run against Instagram.

## Apify comparison

Apify's current [Hashtag Scraper](https://apify.com/apify/instagram-hashtag-scraper) claims hashtag/keyword extraction of posts and Reels and exposes structured captions, media IDs, timestamps, engagement, and some latest comments. Its page directs users to a separate Comments Scraper for all comments. Its [Search Scraper](https://apify.com/apify/instagram-search-scraper) advertises profile, hashtag, place, and popular-Reel search with bounded results; that is not evidence of an exhaustive arbitrary-caption index.

An Apify [actor issue](https://apify.com/apify/instagram-hashtag-scraper/issues/not-sure-how-to-retu-AMLtPISXxiibJ3be1) says runs may repeat the same results and do not deduplicate across prior datasets. No Apify run was performed in this reconnaissance, so no price/performance/completeness benchmark is claimed. An Apify listing is also not evidence of Meta authorization.

**Direct replacement candidates:** approved Graph API for connected professional-account media/comments/mentions and bounded hashtag discovery; Meta Content Library/API only for eligible research.  
**Not directly replaceable with the current first-party commercial API:** open-ended keyword discovery, arbitrary user/comment crawling, and general consumer-profile history. Those need an authorized/licensed discovery source or a customer-supplied list of known accounts/URLs.

## Authentication and account recovery

API credentials are currently absent from this shell; token lifetime, refresh, restart persistence, and granted scopes are UNTESTED. Keep the token in a secret manager/environment variable, never in a fixture or report. For hashtag work, confirm the app uses the Facebook Login API path and that required public-content permissions are approved.

The test account's temporary SMS number creates a recovery dependency. While signed in, replace it with a durable email/phone the team controls and enable authenticator-app two-factor authentication with saved recovery codes. Instagram's help guidance says that if the registered email/phone is inaccessible, users should regain it or update account details while signed in; without an accessible email and without a linked Facebook account, recovery may not be possible.

## Answers to the requested questions

1. **Useful without Apify?** Yes for connected professional accounts and a small, authorized set of hashtag feeds. No as a general public Instagram listening crawler under the documented commercial API.
2. **Arbitrary keyword posts?** No through the documented commercial Graph API. The in-app search request is not evidence that captions are searched. Meta Content Library is the first-party keyword-search candidate only for eligible research.
3. **Recent hashtag posts?** The official Facebook Login path documents recent/top media. It is quota-limited and not a historical archive; live behavior is UNTESTED.
4. **Accessible profile history?** Own professional-account media is cursor-paginated; Business Discovery offers public professional profiles. Full history exhaustion and personal-account access are not demonstrated/supported, respectively.
5. **Complete comment trees?** Not established. Official comment/reply access covers the connected account's own media; arbitrary public-post comment trees are outside that standard API. Exhaustion and count agreement must be separate measured flags.
6. **Reels and comments?** Reels are media; the connected account's eligible Reels and their comments are plausible through the official media/comment surfaces. Exact Reel-edge behavior and complete comments remain UNTESTED.
7. **Without authentication?** No documented general collection API. Public web visibility does not authorize automated collection.
8. **Authentication/account requirements?** A Meta app/token and Business or Creator account. Facebook Login plus linked Page and reviewed public-content permissions are needed for hashtag/business discovery. Instagram Login lacks hashtag search.
9. **Main limits?** Permission/app-review gate, professional-only official access, no arbitrary commercial full-text search, 30 unique hashtag queries per week, constrained comment ownership, unknown historical ceilings, unstable unofficial protocols, and test-account recovery risk.
10. **Sustainable production shape?** Start with one Meta-approved API adapter. Store tokens outside the DB/repo; persist normalized media/comment IDs and per-edge cursors in SQLite; record each request/page/status/duration; stop on auth/permission errors; make separate `protocol_complete` and `reported_count_consistent` fields; deduplicate on source IDs; keep any licensed discovery provider behind a separate adapter. Add scheduling only after coverage and refresh behavior are measured.
11. **What replaces Apify directly?** Direct Graph API operations for authorized professional accounts and bounded hashtags. Open-ended keyword discovery still needs a licensed/authorized source; Meta Content Library is research-only, subject to eligibility.
12. **Next uncertainty to reduce?** First, use the approved API token to verify login mode/scopes and page through one controlled professional profile plus one hashtag, including a Reel and a post with replies. For the highest-priority keyword question, obtain one fresh, manually initiated, authorized browser search capture with its response body sanitized; do not replay the private request. If eligible, separately test exact-phrase search in Meta Content Library.

## Offline check

`python -m pytest -q test_offline_fixture.py` validates only that the supplied request-only fixture has no credential material and is not labeled complete. It does not test Instagram behavior. The live experiment remains UNTESTED until the approved app's token and user ID are made available to the process.

## Sources

- [Meta Instagram API Postman collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api)
- [Meta Instagram Platform overview](https://developers.facebook.com/docs/instagram-platform/overview)
- [Meta hashtag search reference](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-hashtag-search)
- [Meta Business Discovery reference](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/business-discovery)
- [Meta Automated Data Collection Terms](https://www.facebook.com/legal/automated_data_collection_terms) and [archived copy](https://archive.vn/2026.09.16-133320/https%3A/www.facebook.com/legal/automated_data_collection_terms)
- [Meta Content Library announcement and eligibility](https://about.fb.com/news/2023/11/new-tools-to-support-independent-research/) and [ICPSR access page](https://www.icpsr.umich.edu/sites/somar/meta-content-library)
- [Instagram account recovery guidance](https://www.facebook.com/help/instagram/358911864194456)
- [instagrapi PyPI](https://pypi.org/project/instagrapi/3.0.16/), [Instaloader usage](https://instaloader.github.io/basic-usage.html), and [gallery-dl supported sites](https://github.com/mikf/gallery-dl/blob/master/docs/supportedsites.md)
- [Apify Hashtag Scraper](https://apify.com/apify/instagram-hashtag-scraper) and [Search Scraper](https://apify.com/apify/instagram-search-scraper)
