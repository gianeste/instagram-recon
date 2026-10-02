# Instagram legacy scraper compatibility

**Date:** 2026-10-01  
**Target:** `https://www.instagram.com/p/Dd9MKlfTDho/`  
**Status:** Static review, offline harness, and bounded live comparison complete (one request per project).

## Result

The two projects still contain the same legacy GraphQL request shape. After the user explicitly authorized one retest despite the earlier `429`, both projects made one sequential request with the same configured session. Each returned `200 application/json` and the expected comment-edge shape. The earlier `429` remains historical evidence; this successful bounded run does not establish that broader crawling or the normal CLIs are reliable.

The pasted request ends mid-sentence after “Do not repeatedly change”; this report covers its complete visible phases 1–5.

## Bounded live results

Each project's original HTTP library sent one read-only first-page request to the legacy GraphQL endpoint for the target post. Both responses were `200 application/json`, 23,573 bytes, with top-level keys `data`, `extensions`, and `status`. Both contained `data.shortcode_media.edge_media_to_parent_comment`, 24 parent-comment edges, and `page_info`; `has_next_page` and an end cursor were present. The cursor value was withheld. No retries, login, or pagination requests were made.

Both parsers successfully produced the first 10 comment previews without parser errors. `instacomments` had non-empty IDs, text, authors, and timestamps for all 10; its 10 previews had no non-null like counts, and one inline reply preview was present. `InstaScrape` parsed text, username, and timestamp for all 10, while its output shape omits IDs, likes, and replies. The actual first-page response contained 24 edges, but the compatibility artifact intentionally retains only 10 parent previews per project.

The configured session values are absent from the result artifact. To minimize retained personal data, the earlier comment previews were removed and replaced with aggregate field counts. The artifact at `data/instagram-legacy-compatibility-live.json` now contains only safe response metadata and record counts.

**Conclusion:** The legacy query/hash and both one-page request helpers work with the configured session for this target at the time of the run. This does not qualify full pagination, the normal CLIs, future session access, or other posts.

## Reviewed upstream snapshots

| Project | Branch snapshot | Commit | Source |
|---|---|---|---|
| `instacomments` | `main` | `828a380fa983806aa6d57ed7d565842ce44610f2` (2025-08-08) | [repository](https://github.com/AMINE1921/instacomments/tree/828a380fa983806aa6d57ed7d565842ce44610f2), [implementation](https://github.com/AMINE1921/instacomments/blob/828a380fa983806aa6d57ed7d565842ce44610f2/instacomments.py) |
| `InstaScrape` | `main` | `97b2f75036484f0f8781d92301ca42152aaf9c4a` (2026-04-30) | [repository](https://github.com/kaifcodec/InstaScrape/tree/97b2f75036484f0f8781d92301ca42152aaf9c4a), [main.py](https://github.com/kaifcodec/InstaScrape/blob/97b2f75036484f0f8781d92301ca42152aaf9c4a/main.py), [login.py](https://github.com/kaifcodec/InstaScrape/blob/97b2f75036484f0f8781d92301ca42152aaf9c4a/login.py) |

Both complete code trees were reviewed before importing or executing their code. The isolated snapshots are under `research/instagram-legacy-compatibility-20261001/upstream/`.

## Implementation comparison

| | `instacomments` | `InstaScrape` |
|---|---|---|
| HTTP library | `requests` | asynchronous `httpx` |
| Parent-comment request | `GET https://www.instagram.com/graphql/query/?query_hash=…&variables=…` | Same endpoint and `GET`, using `params` |
| Legacy hash | `97b41c52301f77ce508f55e66d17620e` | Same hash |
| First-page variables | `shortcode`, configurable `first` (default 50) | `shortcode`, `first=50` |
| Continuation | Adds `after` from `page_info.end_cursor` | Same |
| Session input | `.env`: `SESSIONID`, `DS_USER_ID`, `CSRFTOKEN`, `MID`; no login | Valid `cookie.json`, otherwise prompts for username/password and invokes custom login |
| Additional metadata or shortcode requests | None; shortcode is sent directly in GraphQL variables | None for the comment query; shortcode is sent directly |
| Reply handling | Optional inline `edge_threaded_comments.edges` preview; no reply pagination | Does not parse replies |
| Export | JSON, CSV, or TXT; usernames or detailed records | Timestamped JSON and TXT |

Both parsers expect `data.shortcode_media.edge_media_to_parent_comment`. `instacomments` keeps IDs, text, owner username, likes, timestamps, and available inline reply previews. `InstaScrape` keeps only text, username, and timestamp; it drops comment IDs and likes.

`instacomments.extract_media()` accepts `/p/` and `/reel/`, and builds the referer from the URL type. `InstaScrape.extract_shortcode()` already accepts both URL paths, but its original header builder always sent a `/reel/` referer. The local test copy now accepts a media type and uses `/p/` for the supplied target.

### Authentication and failure behavior

`instacomments` loads four separate cookie fields through `python-dotenv`, makes no login attempt, and exits if a required field is missing. Its original request had no timeout, followed redirects, and printed the first 300 response characters on HTTP errors.

The `InstaScrape` CLI accepts cookies only from a valid `cookie.json`; it does not read the existing `.env` names. If the file is missing or expired, it prompts for credentials. `login.py` performs prelogin and login POSTs to Instagram’s `i.instagram.com/api/v1/` endpoints and writes the resulting cookies to `cookie.json`. The normal scraper flow also retries/re-authenticates: any initial `ScrapeError` triggers an interactive login and another request; later pages retry up to three times and refresh authentication after unauthorized responses or redirects. A 429 could therefore lead to an unrequested login attempt in the normal CLI path. Login failures can print the response JSON or raw response text, so that path was not executed.

For this comparison, the harness calls only each implementation’s one-page `graphql_request` function. It does not call either CLI, pagination loop, login function, cookie-file writer, or auth-refresh handler. The two local edits also remove response-body snippets from HTTP error messages. Neither project contacted a telemetry or unrelated service in the reviewed code; the optional `InstaScrape` login code has the separate Instagram login destination described above.

Both projects hardcode the same mobile Chrome user agent and Instagram app ID in the web request. The local `IG_USER_AGENT` differs from that hardcoded value, while `IG_APP_ID` matches. To honor the no-fingerprint-manipulation constraint, the prepared live harness replaces only the user-agent header in memory with the existing configured value for both clients. No proxy rotation or challenge handling was added. `InstaScrape`'s unused login path also generates device identifiers and a randomized connection-speed header; that code was reviewed but not executed.

## Local session setup

The checkout's `.env` uses `IG_SESSION_COOKIE` and `IG_CSRF_TOKEN`, rather than the names expected by `instacomments`. The harness maps the cookie fields in memory for both clients and uses `IG_USER_AGENT` for the in-memory header described above. It verified the required `sessionid`, `ds_user_id`, `csrftoken`, and `mid` fields are present and that the explicit CSRF value matches the cookie. No cookie values were printed, copied into either upstream tree, or written to a report. InstaScrape's `cookie.json` was not created.

## Changes from upstream

- `instacomments.py`: adds a 20-second timeout, disables redirects, and reports only HTTP status, content type, and response byte count on errors.
- `InstaScrape/main.py`: adds a `media_type` header-builder argument (default remains `reel`) for the supplied `/p/` target, and removes response-body text from HTTP errors.
- `compat_harness.py` is outside both upstream trees. Offline mode is the default. Live mode requires `--acknowledge-prior-429`, records the explicit retest authorization without asserting that the old restriction cleared, runs both clients sequentially with one initial-page request each, uses the configured user agent in memory, and skips the second client if the first sees a rate limit or access restriction. Its `.env` root path was corrected to the repository root after the first live preflight stopped before network access.
- The upstream requirements files are unchanged. `InstaScrape` enables `http2=True` but does not declare `h2`; `h2` was installed only in the isolated test environment. `urllib3` in `instacomments` is redundant because `requests` already depends on it.

## Offline verification

The isolated Python 3.13.5 environment installed both projects’ declared requirements plus `h2` for InstaScrape’s HTTP/2 mode. Imports succeeded for `requests 2.34.2`, `python-dotenv 1.2.4`, `tqdm 4.70.1`, `httpx 0.28.1`, and `h2 4.4.1`; `pip check` found no broken requirements. `py_compile` passed for the harness and all three upstream Python files.

`compat_harness.py` ran both request builders against a synthetic response. It verified the supplied post URL, endpoint, method, hash, serialized variables, referer, and parsers. Each mocked client made one successful request; its separate mocked 429 and redirect checks each made one request and exposed no response body. The output schema is shared in `offline-results.json`; its comment records are synthetic and are not Instagram data.

The live-mode guard was checked: running `--live-pair` without `--acknowledge-prior-429` exits before loading a client or making a request. The first authorized live invocation also stopped locally because the harness resolved `.env` one directory too high; that root path was corrected, and the command was then rerun once per project.

The existing direct probe report records the earlier 429 and immediate stop: [instagram-direct-graphql-probe-20261001.md](instagram-direct-graphql-probe-20261001.md). The bounded retest results above are later evidence for this session and target. If the harness is run again, it requires `--acknowledge-prior-429`; it does not retry, invoke login, or store cursor values, and it skips Project B if Project A receives a rate limit or access restriction.
