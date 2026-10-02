# Instagram comment collector

The only live collection command is `collect`. Root comments use the previously
qualified legacy GraphQL query from a Crawlee `PlaywrightCrawler` page running in
Playwright. After root traversal completes, the collector attempts sequential
child-reply requests using the initial operation or cursor continuation
operation. The browser-fetch child transport is not live-qualified; see the
[end-to-end qualification report](reports/instagram-end-to-end-qualification.md).

These are undocumented Instagram endpoints and can stop working when Instagram
changes them. A terminal cursor establishes protocol exhaustion only; reported
count scope and full comment-tree coverage remain separate. Login, challenge,
permission, and rate-limit boundaries stop the run without retry or rotation.

## Install and collect

    python -m pip install -e ".[test]"
    python -m instagram_collector collect https://www.instagram.com/p/Dd6m2a6Exca/ `
      --resume --max-root-pages 100 --duration 240 `
      --output .\data

Set `IG_SESSION_COOKIE` and `IG_APP_ID` in `.env`; `IG_CSRF_TOKEN` can override
the `csrftoken` cookie. See [.env.example](.env.example). Do not commit or share
session values.

Normalized records, checkpoints, and a report are stored under
`<output>/<shortcode>/`. Existing legacy-layout state is copied forward once;
the source remains intact. `--resume` is the default and continues the active
saved cursor, including an interrupted refresh. `--refresh` walks the full
ranked root cursor chain on a separate checkpoint while preserving the completed
`comments` checkpoint and all normalized records. It reports new IDs, changed
fields, and records not observed during that scan; one absence is never treated
as deletion. Ranked order is not established as chronological, so a page-limited
refresh does not establish complete discovery. `--fresh` resets traversal
checkpoints while preserving records and run history. Raw response bodies and
cursor values are not written to exports.

## Local utilities

`status <shortcode>` reads the latest saved report. `inspect-response` analyzes a
local sanitized JSON fixture and makes no network requests.

    python -m instagram_collector status Dd6m2a6Exca --output .\data
    python -m instagram_collector inspect-response .\sanitized-response.json

The [qualification report](reports/instagram-comment-tree-qualification.md)
records metadata availability, root refresh behavior, and reply limitations.
Other reports document methods investigated during reconnaissance; their
network tools are not shipped as collector entry points.

Run the local suite with `python -m pytest -q` after the test extra is installed.

## Experimental captured full-form reply transport

The previously integrated browser `fetch()` path sent just `doc_id` and
`variables` and returned an HTML application document in the live qualification.
The standalone experiment instead used a **29-field captured form** and an
ordinary Python `requests` POST, which was qualified for one parent and a
three-page response chain. The collector now offers an **explicit opt-in**
transport that follows the latter request format. It does not infer or generate
Meta application tokens and does not conceal access restrictions.

To check this transport in isolation, using the **local, private, existing**
`instagram-graphql-test/.env` with the two linked request templates:

```powershell
python -m instagram_collector probe-reply `
  "https://www.instagram.com/p/Dd7eoFRE5_t/" `
  --media-id 3997923790051057645 `
  --parent-id 18356734951220570 `
  --reply-form-env "..\instagram-graphql-test\.env" `
  --max-pages 3
```

`probe-reply` makes at most three sequential requests. It performs no automatic
retries and stops on HTTP 429/403, non-JSON, GraphQL errors, cursor anomalies,
or the page budget. It only writes a sanitized summary to
`data/<shortcode>/reply_probe_report.json`, **not** raw response bodies,
cookies, or comments. A local optional `REPLY_REFERER` entry in the supplied
form `.env` can preserve the specific referer associated with your successful
captured request. Don't commit the local `.env` or distribute it in archives.

To run the same transport through the **existing SQLite-backed collector**
after that post's root collection is already present:

```powershell
python -m instagram_collector collect `
  "https://www.instagram.com/p/Dd7eoFRE5_t/" `
  --resume --reply-parent-id 18356734951220570 `
  --reply-transport full-form `
  --reply-form-env "..\instagram-graphql-test\.env" `
  --max-reply-pages 3 --duration 120
```

The collector keeps the working root-comment path unchanged and uses the new
transport only for replies. By default, captured request templates are
**restricted to their original media ID and parent ID**. Experimental use on
other parents requires the explicit `--reply-allow-retarget` flag, and such
retargeting is not qualified by the standalone test. A form capture can expire
or become invalid as Instagram changes internal operations and session state.

No live Instagram request was executed as part of this repair. The new tests
verify request construction, response classification, cursor linkage,
SQLite page commits, deduplication, and preservation of the root checkpoint
**offline**. The direct transport remains a prototype until separately
qualified against authorized live access.
