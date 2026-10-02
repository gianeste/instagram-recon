# Legacy GraphQL on Crawlee + CloakBrowser

**Date:** 2026-10-01  
**Target:** `https://www.instagram.com/p/Dd6m2a6Exca/`  
**Protocol:** legacy parent-comment GraphQL GET, hash `97b41c52301f77ce508f55e66d17620e`

## Method

At qualification time this ran as the opt-in `collect-browser --legacy-graphql`
mode. The same path is now the only live collector entry point, named `collect`.
Crawlee opens one Playwright page through its CloakBrowser plugin; the page issues
the historical same-origin `fetch` with a page size of 50 and follows each
opaque `end_cursor` sequentially. The run used concurrency 1, a 0.5-second
pause between pages, a 100-page cap, no retries, no proxy rotation, and an
ephemeral browser context.

Only `sessionid`, `ds_user_id`, `csrftoken`, and `mid` from the local cookie
configuration were placed in that context. The browser response listener was
not attached in this mode. Comment records were normalized and saved through
the existing `StateStore`; diagnostics contain only status, byte, schema-key,
edge-count, and cursor-presence metadata. Raw response bodies and cursor values
are not in the JSON report or pagination log. SQLite keeps cursor checkpoints
and cursor history for traversal state and potential resume.

## Live result

| Measurement | Result |
|---|---:|
| Crawlee page requests | 1 |
| Legacy GraphQL pages | 33 |
| GraphQL responses | 33 × HTTP 200 JSON |
| Response bytes | 1,470,573 |
| Parent edges | 1,535 |
| Distinct comment IDs | 1,535 |
| Duplicate IDs | 0 |
| Final page | `has_next_page=false` |
| Reported endpoint count | 1,570 |
| Root count matches reported count | No |
| Wall time | 45.175 seconds |

The root cursor protocol exhausted naturally and qualifies for this target,
session, and run. The previous `instacomments` baseline also returned 1,535
distinct parent IDs over 33 pages and reached a terminal cursor. This modern
run therefore reproduced the strongest prior result using the Crawlee +
CloakBrowser browser lifecycle and the collector's normal persistence path.

Overall collection remains **partial**. The endpoint count was 1,570 while
1,535 root comments were returned. Thirteen returned comments advertised 32
replies in total; this run did not make child-comment requests. Neither a
terminal root cursor nor the reported count establishes complete historical
coverage.

The response omitted the post ID and shortcode. Records are stored under the
explicit surrogate key `shortcode:Dd6m2a6Exca`; returned media identity is
therefore unverified. A cookie session was supplied, but account authentication
was not independently verified. `metadata_complete` remains false.

During implementation, three one-page diagnostic/validation attempts also
received HTTP 200 JSON before the final 33-page run. The final run had no 429s,
HTTP errors, or retries.

## Code and validation

- Implementation: `instagram_collector/crawlee_browser.py` and
  `instagram_collector/cli.py`.
- Command documentation: `README.md`.
- Saved normalized collection and report:
  `data/legacy-graphql-qualification/legacy-graphql/Dd6m2a6Exca/`.
- `python -m pytest -q`: **68 passed**.
- Python compile check and Node syntax check of the in-page fetch script passed.

This is an experimental compatibility path for an undocumented historical
Instagram query, not a supported API. The qualified claim is limited to root
cursor exhaustion on this one post and session; replies, identity cross-check,
and corpus completeness are unqualified.
