# Instagram child response and refresh qualification

**Evidence date:** 2026-10-02  
**Live requests during this work:** 0  
**Test suite:** 83 passed  
**Compile check:** passed

## Child response audit

The successful 30-reply reference and the failed Dd-3dhPjaJc request are different media/parent pairs. The sanitized linked manifest for the successful reference identifies media `3997923790051057645`, parent `18356734951220570`, and a run beginning at `2026-10-02T05:38:07.445348Z`. The saved Dd-3dhPjaJc observation identifies parent `17923839663425652` and a SQLite media key based on the shortcode; the exact numeric media ID sent in its request was not retained. Its saved observation time is `2026-10-02T08:50:11.598Z`.

| Field | Successful full-form reference | Failed browser child response |
|---|---|---|
| Operation | Initial `PolarisPostChildCommentsQuery`, doc ID `28027289793632076`; continuation `PolarisPostCommentsChildrenPaginationtQuery`, doc ID `27229753410037873` | Initial `PolarisPostChildCommentsQuery`, doc ID `28027289793632076` |
| Media / parent | `3997923790051057645` / `18356734951220570` | Shortcode-scoped SQLite media key / `17923839663425652`; exact request `media_id` unavailable |
| HTTP / content type | Three linked `200` responses, `text/javascript; charset=utf-8` | `200`, `text/html` |
| Response shape | Child connection with `edges` and `page_info`; 15 + 15 + 0 replies, 30 unique IDs, all declared the requested parent | No parsed JSON, reply IDs, parent IDs, or pagination metadata |
| Pagination | Each continuation `after` matched the preceding `end_cursor`; terminal page explicitly had `has_next_page=false` | No cursor data |
| Session / access evidence | Manifest stores no credential values. It does not establish that the browser and reference used the same authenticated session. | Collector recorded that a cookie session was supplied, not that the endpoint accepted it. The retained HTML signals included a doctype, HTML element, and app assets; login and challenge markers were absent. |
| Redirect evidence | Not material to the linked response schema; response redirect details are not in the manifest | Final response path and redirect state were not saved, so a transparent redirect cannot be ruled in or out |

The strongest controlled comparison is also saved in [the end-to-end qualification report](instagram-end-to-end-qualification.md): the collector browser fetch was tried against the linked reference's exact media/parent pair. It used the same initial operation and doc ID, but returned HTTP 200 HTML instead of child JSON. The reference request used a full form with 29 fields and 24 explicitly supplied headers. The browser code constructs a form with only `doc_id` and `variables`, and supplies six application headers while relying on browser defaults for the rest. The saved request observation does not include the complete serialized variables, so this is a verified code/request-shape difference, not proof of why Instagram returned HTML.

The HTML does **not** establish that the request was blocked. The saved signals do not show an authentication or challenge page, and the old response record lacks redirect details. An application-shell response, redirect behavior, request-context difference, or another endpoint behavior remains possible. The evidence cannot distinguish those explanations. The successful full-form transport remains the isolated reference; it was not discarded or changed to explain away the browser result. No request was repeated.

The Dd-3dhPjaJc observation's original safe classifier was `application_shell_like`. An older report used the broader `unexpected_schema` stop reason for a browser HTML response. The new classifier records the transport fact as `unexpected_html`; it does not interpret the shell as a block or an authentication failure.

The collector now records a sanitized final response path, redirect flag and redirect-location path when available, plus explicit login/challenge evidence. It does not retain query strings, response bodies, or credentials. The old observations cannot be backfilled with those fields.

## Response classification and resumability

Child outcomes now distinguish valid GraphQL JSON, valid empty terminal JSON, unexpected HTML, other non-JSON, unexpected schema, parent mismatch, authentication required, explicit access restriction, access denied, rate limiting, network failure, timeout, and an unavailable comment signal. Authentication and restrictions are assigned only from explicit status, URL-path, or response-marker evidence. HTTP 403 remains `access_denied`; it is not relabeled as a challenge. No outcome claims authentication expiration without evidence.

An HTTP 200 HTML response is recorded as `unexpected_html` and leaves the parent checkpoint incomplete. It stops that reply batch. A later explicit resume can try that incomplete parent again from its saved cursor (or the initial request when no cursor was saved); there are no automatic retries. The fixture test resumed an HTML-failed branch from its initial operation, kept the completed root checkpoint, and retained both response observations. An empty child page advances to `COMPLETE` only after the verified child schema parses and explicitly reports `has_next_page=false`.

## Incremental refresh semantics

- Every new `--refresh` scan has an independent root checkpoint edge and a reply checkpoint edge scoped to its scan ID. Regular collection checkpoints and earlier refresh histories remain intact.
- Refresh starts each reply-bearing parent with the initial operation. It never reuses a cursor from another snapshot. Resume of an interrupted refresh restores the same scan ID and its saved reply cursor.
- Root traversal is repeated for the current refresh snapshot. Reply traversal visits all stored roots with a positive reported reply count, including historical roots still in SQLite, and reads each branch through explicit termination. Pages are not skipped because their IDs were seen before.
- Stable comment IDs deduplicate records. Root and reply associations remain tied to their media and parent IDs. `comment_observations` retains scan/run provenance; saved comments are not deleted when absent from a refresh.
- The report exposes current-scan reply counts, newly discovered IDs by parent, and each parent's checkpoint history. `not_observed_once_ids` is withheld until both root traversal and every eligible reply branch complete; absence does not mean deletion.
- A refresh is a successful refresh only when both root and reply protocols complete. A partial refresh does not advance `last_refresh_at` or qualify as the latest successful refresh.

This is deliberately exhaustive over the observed cursor chains. It is bounded by the existing page, request, and runtime limits, and uses the existing 500 ms pacing. It does not claim that ranked cursor exhaustion covers every comment Instagram may report.

## Offline integrity and recovery results

Fixture-backed integrated collector runs covered an unchanged post, changed reported count, new root, new replies, embedded-preview deduplication, an empty terminal branch, HTML, interruption, and resume.

- Refresh produced 3 roots and 6 unique saved replies in the changed-post fixture. It found 5 new IDs, deduplicated the embedded/fetched overlap, and preserved the two historical replies absent from the new traversal.
- The advertised reply branch with an empty terminal page completed at one page with `natural_exhaustion`; it did not create a reply record.
- The unchanged-post fixture reported no new IDs or changed fields, kept stable IDs, and deduplicated the repeated root/reply observations.
- A fault after one committed reply page left its cursor and prior records available. Resume selected the continuation operation, skipped a completed parent, completed the remaining branches, and did not call the root request path.
- An HTML failure left `pages=0`, `complete=false`; the next run restored the same refresh scan and retried only that parent. No root checkpoint or earlier reply checkpoint was reset.
- Count observations remained in history. Incomplete scans did not report not-observed records as missing or deleted.

The tests use temporary SQLite databases and deterministic responses. They validate collector and storage behavior, not Instagram's live endpoint response.

## Offline performance comparison

Five trials per arm used identical fixture responses, a one-page root chain, three child pages across two parents, a four-request budget, and the production 500 ms pacing. Refresh began with previously stored root/reply records; the fresh arm began empty. Both ended with the same seven unique IDs and two complete reply branches.

| Measure | Fresh traversal median (min–max) | Refresh median (min–max) |
|---|---:|---:|
| Wall time | 1,670.960 ms (1,658.874–1,690.454) | 1,619.306 ms (1,605.825–1,628.160) |
| Collector initialization | 53.768 ms (52.148–58.412) | 2.338 ms (2.150–2.623) |
| HTTP/network time | 0 ms (fixture transport) | 0 ms (fixture transport) |
| Pacing | 1,527.359 ms (1,524.967–1,533.971) | 1,523.474 ms (1,518.056–1,529.749) |
| SQLite transactions | 23.528 ms (22.945–35.695) | 23.630 ms (23.017–26.478) |
| Normalization | 0.138 ms (0.123–0.185) | 0.141 ms (0.124–0.146) |
| Requests | 4 | 4 |
| New IDs | 7 records inserted into empty state | 3 newly discovered against saved state |
| Final unique records / complete branches | 7 / 2 | 7 / 2 |

The request saving was **zero**. Refresh needs the same root and reply cursor traversal to establish current-snapshot completeness. Refresh wall time was 51.654 ms lower in this offline sample, but that difference is dominated by fresh-database initialization and run-to-run fixture timing; the measurement has no network and does not run Crawlee or a browser. It is not evidence of a live speedup. SQLite and normalization work were both small relative to the unchanged pacing. Crawlee/browser lifecycle overhead was not exercised.

## Qualification and limitations

| Area | Result |
|---|---|
| Full-form child reference | Prior 30-reply linked sequence remains qualified for its exact media/parent and three responses |
| Browser child transport | **Not qualified live**; prior HTTP 200 HTML response remains unresolved |
| Error classification | Offline-qualified for HTML, schema, network, auth, restriction, and rate-limit distinctions |
| Incremental refresh storage and resume | Offline-qualified for the fixtures above |
| Live incremental refresh | Not run; requires an allowed session and permitted endpoint access |
| Request savings | None demonstrated; current exhaustive refresh performs the full observed traversal |
| Corpus completeness | Unknown. Cursor termination and numerical count agreement do not establish complete source coverage |

Validation completed with `83 passed`, `py -3 -m compileall -q instagram_collector tests`, and `git diff --check`. The only diff-check output was Git's LF-to-CRLF working-copy notice. No live collection, commit, or push was performed.
