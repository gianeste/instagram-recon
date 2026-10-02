# Instagram Crawlee + CloakBrowser qualification

**Updated:** 2026-10-01

## Scope

This is one bounded browser qualification against the authorized target
`https://www.instagram.com/p/Dd9MKlfTDho/`. The implementation reuses the
existing capture writer, reviewed fixture mappings, root pagination evaluator,
and `StateStore`. It does not replay a captured request, import cookies, or
retry the previously rate-limited GraphQL operation.

The browser integration follows CloakBrowser's published Crawlee plugin
pattern ([example](https://raw.githubusercontent.com/CloakHQ/CloakBrowser/main/examples/integrations/crawlee_example.py)) and uses
`PlaywrightCrawler`/`BrowserPool` as documented by
[Crawlee](https://crawlee.dev/python/docs/guides/playwright-crawler).

## Implementation

`instagram_collector/crawlee_browser.py` provides `collect-browser` with:

- one `PlaywrightCrawler` request and one browser page;
- a persistent, isolated profile selected by `--user-data-dir`;
- headed mode by default, with manual login as an operator action;
- concurrency 1, no request retries, no session rotation, and no proxy use;
- response listeners attached in `pre_navigation_hook`, before navigation;
- normal comment-button, comments-container scroll, more-comments, and one
  reply-expansion action where the UI exposes them;
- sanitized response fixtures and allowlisted semantic request inputs only;
- existing normalization, SQLite upserts/checkpoints, and JSONL exports when
  genuine response records exist;
- independent root/reply completeness and qualification flags.

The capture diagnostics now retain only safe counts for unmatched responses,
operation names, status codes, and target document metadata. They do not write
cookies, request headers, raw form bodies, CSRF values, or response bodies for
unmatched non-JSON traffic.

Installed versions used for the run:

| Package | Version |
|---|---:|
| `crawlee` | 1.9.2 |
| `playwright` | 1.62.0 |
| `cloakbrowser` | 0.5.10 |

## Live run evidence

The final bounded run was written under
`data/live-qualification-20261001c/Dd9MKlfTDho/`:

- `collection_report.json`
- `responses/capture-manifest.json`
- `state.sqlite`

Observed report values:

| Observation | Result |
|---|---|
| Final URL | `https://www.instagram.com/p/Dd9MKlfTDho/` |
| Page title | `Instagram` |
| Crawlee target requests | 1 finished, 0 failed |
| Browser network responses | 80, all status 200 in unmatched diagnostics |
| Matched comment responses | 0 |
| Root pages/comments | 0 / 0 |
| Reply pages/replies | 0 / 0 |
| Media ID | unavailable |
| Termination | `experiment_timeout` |
| Collection | partial |

The only named GraphQL traffic retained by the diagnostics was three
`fetchPolarisLoggedOutExperimentQuery` requests and one
`QuickPromotionSupportIGSchemaBatchFetchQuery`. Four responses used
`/api/graphql`; none matched a comment or reply operation. No
`/api/v1/media/{id}/comments/`, `PolarisPostCommentsPaginationQuery`, or
`PolarisPostChildCommentsQuery` response was observed. No 401, 403, 429, 451,
challenge, or CAPTCHA response was observed.

The browser reached the Instagram shell, but the isolated profile had no
completed manual login. The report therefore leaves session authentication
`unverified` and does not treat the logged-out bootstrap traffic as post or
comment access. The existing Edge session was not reused because it did not
provide a CDP endpoint and no cookies were transferred.

The requested experiment duration was 15 seconds. The run ended after about
50 seconds because the browser navigation was still completing while Crawlee
performed its graceful stop; no additional target or retry was issued. This
is recorded as a lifecycle limitation, not as collection success.

## Qualification levels

| Level | Status | Evidence |
|---|---|---|
| Browser | **QUALIFIED for shell startup/navigation** | CloakBrowser launched, Crawlee completed one target request, final URL/title were observed. |
| JSON capture | **NOT QUALIFIED** | Zero matched comment JSON responses. |
| Root pagination | **NOT QUALIFIED** | No root page or cursor transition. |
| Reply collection | **NOT QUALIFIED** | No child response or parent attachment. |
| Reply pagination | **NOT QUALIFIED** | No reply sequence. |
| Tree/completeness | **NOT QUALIFIED** | No target media ID, records, or terminal protocol state. |

The reviewed root and child fixtures remain offline schema evidence only. They
were not silently counted as live observations for this run.

## Tests

The complete offline suite passes:

```text
66 passed in 2.47s
```

`py_compile` also passes for the browser and capture modules.

## Remaining qualification step

Run the same command with the isolated profile in headed mode, complete the
authorized manual Instagram login, verify the target post and comments are
visible, then repeat one normal scroll and one reply expansion. Preserve the
resulting sanitized `capture-manifest.json`. Stop immediately on a login wall,
challenge, rate limit, or other access restriction. Until a genuine comment
response and linked continuation are captured, root/reply collection and
completeness remain unverified.
