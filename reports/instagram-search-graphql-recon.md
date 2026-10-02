# Instagram web GraphQL search reconnaissance

**Date:** 2026-10-01  
**Operation observed:** PolarisSearchBoxRefetchableQuery  
**Evidence status:** One manually captured authenticated request; no response body or UI event sequence

The separate comments GraphQL request later returned HTTP 429 with no body; that response does not inform search behavior. The expanded operation inventory and fixture status are in the [operation catalog](instagram-operation-catalog.md).

## Finding

This capture is consistent with Instagram’s top-search box fetching or refetching results for the text “samsung”. That is an inference from the operation name, search_surface=web_top_search, and hasQuery=true. It does not establish that the operation returns only suggestions, or that it returns posts. No result objects were supplied, so the primary question—whether an ordinary keyword discovers actual posts—remains **unanswered**.

The operation is an internal Instagram web GraphQL call. It is not the documented Instagram Graph API. Meta’s official API collection describes professional-account media and hashtagged-media access, and documents cursor pagination and no result ordering; it does not document this operation or an arbitrary caption-keyword search. [Meta’s Instagram API collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-56730cef-8d38-4f1a-8cc3-54444b625e7c)

## Evidence and limits

The user supplied a sanitized description of one authenticated request from Instagram’s Explore/search interface. The search request was not replayed, and no search response or UI event sequence is available. A later comments request is documented separately. The previous cURL export has been replaced with a non-executable summary; session, CSRF, signature, and browser-state values are not retained here.

The supplied material contains request metadata and variables only. It contains no HTTP status, response payload, result objects, result identifiers, pagination metadata, or second request from the same UI flow. “Unknown” below means unknown from this evidence, not evidence that a result type or feature is absent.

## Observed request

Endpoint: POST https://www.instagram.com/api/graphql

Operation name: PolarisSearchBoxRefetchableQuery

Sanitized variable shape:

    {
      "data": {
        "context": "blended",
        "include_reel": "true",
        "query": "samsung",
        "rank_token": "<redacted>",
        "search_session_id": "<redacted>",
        "search_surface": "web_top_search"
      },
      "hasQuery": true
    }

The request reportedly also contained doc_id, fb_api_req_friendly_name, x-fb-friendly-name, x-ig-app-id, x-csrftoken, and standard web-application parameters. Their values are omitted. The supplied value of include_reel is the string "true".

## Result types and response schema

No response was captured, so no response schema or sanitized response example can be reported. The following categories are **unobserved**, not confirmed empty:

| Candidate result category | Evidence in supplied request/response | Finding |
|---|---|---|
| Users/accounts | No response objects | Unknown |
| Hashtags | No response objects | Unknown |
| Places | No response objects | Unknown |
| Posts | No response objects | Unknown |
| Reels | include_reel is requested, but no response objects | Unknown |
| Other result types | No response objects | Unknown |

There is no evidence yet that samsung matched caption text, that posts were returned, or that Reels were included. The operation name makes a search-box suggestion/refetch role plausible, but it is not a schema and does not settle whether results include content.

## UI sequence and operations

Only one operation name has been observed: PolarisSearchBoxRefetchableQuery. The capture does not show whether it fired while typing, after a debounce, on Enter, after navigation to a results page, or during another step. It also does not show whether submitting the query triggers a different GraphQL operation.

| UI action/interface | Operation name | Response schema | Evidence |
|---|---|---|---|
| Explore/search top-search request, exact action unknown | PolarisSearchBoxRefetchableQuery | Not captured | One request description |
| Typing suggestions as a sequence | Unknown | Not captured | No interaction timeline |
| Submit with Enter / results page | Unknown | Not captured | No post-submit request |
| Category tabs, filters, or result-type views | Unknown | Not captured | No such interactions supplied |
| Scroll/load-more | Unknown | Not captured | No follow-up request or cursor |

To map Instagram’s sequence, a normal user can capture the browser Network log while opening search, typing a term, pausing, pressing Enter, and scrolling if the page offers more results. Record operation names, sanitized variable shapes, response object type names/field names, and whether a follow-up request occurs. Do not export cookies, CSRF values, access tokens, signatures, rank_token, or search_session_id.

## Search semantics, ranking, and pagination

| Question | Result |
|---|---|
| Suggestions or content discovery? | The name and web_top_search context suggest a search-box refetch. Payload semantics are unverified. |
| Does Enter invoke another operation? | Unknown; no Enter/results-page trace was supplied. |
| Is pagination exposed? | Unknown. No response or follow-up request was captured. The supplied variable shape has no obvious cursor field, but that does not rule out response cursors or pagination in another operation. |
| Ranked or chronological? | Unknown. rank_token suggests ranking-related request state by name, but there is no result ordering or sort metadata to inspect. |
| Do ordinary keywords find posts? | Unknown. A request with query=samsung is not evidence of returned posts or caption matching. |
| Does include_reel change coverage? | Unknown. One request with "true" is not a comparison. Do not infer coverage from the flag name. |
| Do results differ for ordinary queries? | No comparison is available. Only samsung was supplied. |
| Does anonymous access differ? | Unknown. Only an authenticated request was supplied; no anonymous browser interaction was captured. |

The captured request supports no claim of comprehensive search coverage, ranking quality, chronological ordering, pagination depth, or matching completeness.

## Parameter roles

This classification is based on names and placement in a single request, not on controlled experiments. “Likely UI/search input” does not mean its behavior has been proven.

| Parameter | Tentative role | Confidence and caveat |
|---|---|---|
| data.query | Search text | High that it is the submitted text; whether it searches captions/posts is unknown. |
| data.context | Search context (blended) | Likely semantic/UI context; effect untested. |
| data.search_surface | Search surface (web_top_search) | Likely selects the UI surface; effect untested. |
| data.include_reel | Possible result-coverage option | Candidate semantic input. Only "true" observed; effect untested. |
| hasQuery | Query-state flag | Likely UI state; effect untested. |
| data.rank_token | Ranking/session-related state | Inferred from name; value intentionally redacted and not varied. |
| data.search_session_id | Search-session correlation/state | Inferred from name; value intentionally redacted and not varied. |
| doc_id | Internal operation identifier | Present, value omitted. Stability across versions/sessions is unknown. |
| fb_api_req_friendly_name, x-fb-friendly-name | Operation/diagnostic labels | Reported present; likely identify the operation rather than define search content. |
| x-ig-app-id | Web application/client identifier | Reported present; not a keyword predicate. Exact role/version behavior untested. |
| x-csrftoken, cookies, standard application parameters | Request security, authentication, or web-session state | Values omitted. Required web-request state is distinct from search semantics. |

No parameter was varied, so these are not causal findings. In particular, testing whether include_reel changes coverage requires naturally observed, authorized UI requests with different values and comparable responses. Do not alter hidden request variables or replay the request to manufacture an A/B test.

## Operation identifiers and application versions

The operation name is known, but the doc_id value is redacted. There is one supplied session and no before/after application-version capture. Whether the name or identifier changes between sessions or releases is **unknown**. No identifier-stability claim is made.

## Anonymous versus authenticated behavior

One authenticated request was supplied; there is no anonymous comparison. No attempt was made to access private GraphQL endpoints anonymously or to use an authenticated browser session. A future comparison should use only ordinary permitted browser interactions, and should stop if Instagram presents a login wall, challenge, or rate-limit response.

Meta’s documented Instagram API is a separate product surface: its official collection is for professional accounts, includes access to owned media and hashtagged media, excludes consumer accounts, uses cursor-based pagination, and does not support result ordering. Those facts do not describe or validate Instagram’s internal web GraphQL behavior. [Official API documentation](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-56730cef-8d38-4f1a-8cc3-54444b625e7c)

Meta describes its Content Library/API as a research tool for publicly accessible content, including Instagram creator/business content; access is through qualified academic or nonprofit institutions pursuing scientific or public-interest research. It is not the same API or a general commercial keyword-search entitlement. [Meta Content Library announcement](https://about.fb.com/news/2023/11/new-tools-to-support-independent-research/)

## Evidence needed to answer the primary question

A small, manually captured browser sequence is sufficient to advance this recon:

1. Search for samsung in the normal signed-in UI; capture the request sequence from typing through Enter and the corresponding response bodies.
2. Repeat with two ordinary terms, such as nvidia and mechanical keyboard, using the same UI steps.
3. If the UI offers normal category/filter controls or additional results on scroll, capture those requests and responses as separate interactions.
4. Use anonymous mode only through ordinary UI access that Instagram allows without signing in. Do not bypass a login wall.
5. Sanitize cookies, CSRF/authentication values, user IDs, signatures, rank/session tokens, and personal result fields. Preserve response type names, field names, counts, pagination metadata, and anonymized examples needed to distinguish users, hashtags, places, posts, and Reels.

Do not claim full or exhaustive search coverage from a few results. The useful conclusion is narrower: whether actual post/Reel objects appear for these ordinary terms, what UI action requested them, and whether a normal continuation path is exposed.

Meta’s public guidance says automated collection from Meta products requires prior permission. This investigation therefore did not automate Instagram web search or call the internal GraphQL endpoint. [Meta guidance on automated collection](https://about.fb.com/news/2021/04/how-we-combat-scraping/)

## Evidence ledger

| Item | Status |
|---|---|
| Supplied operation name and top-search request variables | Observed in user-provided description |
| Authenticated state of supplied interaction | Reported by user |
| Response schema/result categories | Not observed |
| Typeahead vs submit request sequence | Not observed |
| Pagination and ordering | Not observed |
| include_reel effect | Not tested |
| Query-to-query comparison | Not performed |
| Anonymous/authenticated comparison | Not performed |
| Operation-ID stability | Not tested |
| Private GraphQL request replay or automated browser collection by this investigation | None |
