# Instagram comment collector

The only live collection command is `collect`. It uses the previously qualified
legacy root-comment GraphQL query from a Crawlee `PlaywrightCrawler` page running
in CloakBrowser. The session cookies are added to an ephemeral browser context;
cursor requests run sequentially. REST comment requests, the newer Polaris
GraphQL operation, Meta's documented Graph API, and manual response capture are
not collector entry points.

This uses an undocumented Instagram endpoint and can stop working when
Instagram changes it. Collection is root-comments only: replies are not fetched,
and a post with advertised replies is reported as partial. Login, challenge,
permission, and rate-limit boundaries stop the run without retry or rotation.

## Install and collect

    python -m pip install -e .
    python -m instagram_collector collect https://www.instagram.com/p/Dd6m2a6Exca/ `
      --max-root-pages 100 --duration 240 `
      --output .\data

Set `IG_SESSION_COOKIE` and `IG_APP_ID` in `.env`; `IG_CSRF_TOKEN` can override
the `csrftoken` cookie. See [.env.example](.env.example). Do not commit or share
session values.

Normalized records, checkpoints, and a report are stored under
`<output>/legacy-graphql/<shortcode>/`. Raw GraphQL response bodies and cursor
values are not written to the report.

## Local utilities

`status <shortcode>` reads the latest saved report. `inspect-response` analyzes a
local sanitized JSON fixture and makes no network requests.

    python -m instagram_collector status Dd6m2a6Exca --output .\data
    python -m instagram_collector inspect-response .\sanitized-response.json

The [qualification report](reports/instagram-legacy-graphql-crawlee-qualification-20261001.md)
records the 33-page run on the example post. Other reports document methods
investigated during reconnaissance; their network tools are not shipped as
collector entry points.

Run the local suite with `python -m pytest -q`.
