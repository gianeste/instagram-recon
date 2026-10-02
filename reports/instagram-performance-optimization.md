# Instagram performance optimization qualification

**Evidence date:** 2026-10-02  
**Live collection:** none in this qualification. The failed child request for `Dd-3dhPjaJc` was not retried.  
**Test suite:** 78 passed.

## Result

The root traversal for `Dd-3dhPjaJc` remains qualified. Its 56 root pages exhausted normally and saved 2,616 unique roots. The one live child request returned HTTP 200 `text/html`; reply transport for this post is still unqualified, and the saved report correctly marks the collection partial. No additional request was sent.

The collector already has a sequential, single-invocation path through root pages and eligible reply parents. A three-trial local fixture comparison measured a median 5.98 seconds for one invocation versus 10.90 seconds for three parent-filtered invocations: **45.1% lower wall time** for the same six child requests and pacing. This is an invocation choice using the existing scheduler, not a change to collection behavior.

No request pacing, concurrency, retry, identity, transport, or SQLite behavior was changed. Audit cleanup removed the obsolete 725-line compatibility harness and moved `requests` to the opt-in `full-form` extra. Its saved offline results and reports remain.

## Live baseline: `Dd-3dhPjaJc`

These are the three active collector runs; time between invocations is excluded.

| Run | Requests (root / child) | Wall | HTTP execution | Pacing | SQLite transactions | First handler | After handler |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 20 (20 / 0) | 28.498 s | 13.543 s | 9.638 s | 42.050 ms | 4.629 s | 197 ms |
| 2 | 20 (20 / 0) | 24.202 s | 11.935 s | 9.649 s | 47.236 ms | 1.949 s | 198 ms |
| 3 | 17 (16 / 1) | 18.183 s | 8.148 s | 7.609 s | 34.731 ms | 1.777 s | 190 ms |
| **Total** | **57 (56 / 1)** | **70.883 s** | **33.625 s** | **26.896 s** | **124.017 ms** | — | — |

The traversal returned 56 JSON responses and one HTML response. It saved 2,616 roots and 23 embedded replies (2,639 unique records total). Instagram reported 2,703 comments, leaving a numerical difference of 64. The root cursor tree completed; replies did not. The current report records `root_protocol_complete=true`, `replies_protocol_complete=false`, `reported_count_consistent=false`, `collection_partial=true`, `operational_failure=true`, and termination `unexpected_schema` for the HTML child response.

### Request latency and tail

For the 56 root requests, saved browser timings are:

| Measure | Network | Header wait | Body read | JSON decode |
|---|---:|---:|---:|---:|
| Total | 33.365 s | 33.321 s | 43.5 ms | 3.8 ms |
| Median | 226.55 ms | 226.35 ms | 0.3 ms | 0.1 ms |
| p90 | 902.3 ms | 901.65 ms | 1.7 ms | 0.1 ms |
| p95 | 3,871.9 ms | 3,871.4 ms | 2.8 ms | 0.2 ms |

The five requests over three seconds were root pages 3, 14, 25, 36, and 47 (3.77–4.11 s). They recur at 11-page intervals, but the saved evidence does not identify why. Their response sizes were about 45.8–46.5 KB, close to the 46.5 KB median. Across all 56 pages, sizes ranged from 8.9 KB to 57.3 KB and Pearson size/latency correlation was 0.117. Size does not explain the observed tail in this sample.

The slow time is almost entirely before response headers arrive; response-body reading and JSON decoding are negligible by comparison. The old run did not save connection timing, so it cannot establish whether those waits involved DNS, a new connection, server response time, or another network factor.

### Collector path and measured local work

- One Crawlee `PlaywrightCrawler` request opens the post page. Root and child GraphQL fetches run sequentially inside that page handler; they are not individually scheduled by Crawlee.
- The browser fetch path reuses that page and its browser-managed network stack. It does not construct a new HTTP client for each GraphQL page. The collector disables Crawlee `SessionPool`; configured cookies are applied to the page context. Saved connection reuse/protocol evidence is unavailable for the live baseline.
- The opt-in full-form transport owns one `requests.Session` per collector invocation and reuses it for requests. Its `requests` dependency is now optional.
- There are no separate metadata HTTP requests. Available post metadata comes from responses already collected.
- The response body is read once, JSON-decoded once in the page, then normalized from the returned object. SQLite saves records, cursor state, and page checkpoint in one transaction.
- Across the three live runs, normalization took 13.701 ms and JSON decoding 3.8 ms. Export files took 125.201 ms total. These costs are too small to explain the multi-second request tail.
- The measured time outside handler work was about 9.013 seconds over the three runs. It includes Crawlee/browser lifecycle and other run finalization; it is not all browser startup.

The latest run separated the lifecycle phases: browser runtime initialization 314 ms, page/context initialization 765 ms, cookie application 70 ms, navigation 579 ms, browser-pool shutdown 181 ms, and time after the last handler 190 ms. Its time to first handler was 1.777 seconds. The earlier cold run took 4.629 seconds to first handler and 3.419 seconds for navigation. These are per-invocation costs, and phases overlap with lifecycle bounds; do not sum them as disjoint wall-time buckets.

## Connection and response timing instrumentation

The collector now records browser `PerformanceResourceTiming` data for the exact response URL, alongside its existing request observations: DNS, connection, TLS, request wait, response transfer, byte sizes, and next-hop protocol. The report aggregates the timing fields and protocol when available. Matching by response URL avoids selecting an unrelated page fetch.

The local fixture benchmark exercised this capture path for intercepted browser fetches. Its zero connection timings only describe local route interception; they are not evidence about Instagram connection reuse. A future permitted root run is needed to characterize live connection establishment and transfer. No child retry is implied by this instrumentation.

## Lifecycle benchmark

The comparison used the existing collector in two invocation patterns:

- **A — repeated:** three separate Python collector processes, each restricted to one reply parent and given a two-request budget.
- **B — continuous:** one Python collector process, no parent filter, with a six-request global budget.

Each trial started with the same SQLite state: three roots, one embedded reply preview per root, and a completed root checkpoint. The actual sanitized child fixture `fixtures/polaris_child_comments_tree.sanitized.json` supplied the reply node fields and response structure. For the offline workload only, node IDs, parent IDs, cursor values, and two-page boundaries were generated deterministically. Each parent had two pages: an initial page containing two replies and a continuation page containing one reply. The embedded preview duplicated one fetched ID per parent.

Both arms used six sequential intercepted HTTP 200 JSON requests, three initial operations, three continuation operations, and the collector's unchanged 500 ms pacing. Total requested pacing was 3.0 seconds per arm. All six requests were routed locally; there was no Instagram access.

| Trial | A: 3 invocations | B: 1 invocation | A first-handler total | B first-handler | A pacing | B pacing |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 10.903 s | 5.984 s | 3.462 s | 1.211 s | 3.057 s | 3.028 s |
| 2 | 11.055 s | 6.155 s | 3.763 s | 1.173 s | 3.042 s | 3.044 s |
| 3 | 10.831 s | 5.670 s | 3.486 s | 1.153 s | 3.048 s | 3.040 s |
| **Median** | **10.903 s** | **5.984 s** | **3.486 s** | **1.173 s** | **3.048 s** | **3.040 s** |

Wall-time ranges were 10.831–11.055 s for A and 5.670–6.155 s for B. The median saving was 4.919 seconds (45.1%). Request count, response content, cursor transitions, and pacing were identical. The result demonstrates saved fixed invocation work for this short, local workload; it is not a live-post speed guarantee.

| Other median measurements | A: repeated | B: continuous |
|---|---:|---:|
| Handler total | 3.248 s | 3.412 s |
| Browser request latency (median of trial medians) | 2.45 ms | 2.40 ms |
| Request latency median range across trials | 2.40–2.75 ms | 2.35–2.70 ms |
| SQLite transaction total | 39.8 ms | 317.7 ms |
| Normalization | 0.179 ms | 0.171 ms |
| Export files | 84.0 ms | 27.6 ms |

SQLite transaction totals varied substantially by trial: A was 39.1, 39.8, and 48.0 ms; B was 317.7, 454.2, and 56.9 ms. The fixture workload and transaction semantics were the same, so this variance is not evidence of a collector-side SQLite regression or a reason to rewrite storage. The live baseline's measured total was 124 ms across 57 requests. Export time fell with one report/export pass instead of three, but the absolute saving was under 60 ms.

### Correctness checks in the benchmark

Both arms produced the same 12 unique comment IDs: 3 roots and 9 replies. Each of the 3 parents reached `natural_exhaustion` after two pages; all 3 embedded preview duplicates deduplicated by stable ID. The initial and continuation operations matched their respective cursors. The completed root checkpoint remained unchanged, and no root request was made. No duplicate comment rows appeared.

## Timeout, checkpoint, and resume review

- Browser GraphQL fetches have a separate 20-second abort timeout. Page navigation is bounded by `min(45 seconds, collection duration)`.
- The handler timeout is `duration + 15 seconds`. The overall run separately waits for the configured duration, requests a graceful Crawlee stop, allows up to 10 seconds for shutdown, then cancels if needed.
- The global HTTP budget counts root and reply attempts. Request pacing remains 500 ms. Successful pages commit records and their branch cursor/checkpoint atomically before the next await; interruption between pages therefore resumes from the last saved cursor. A response interrupted before commit may be requested again on resume.
- Completed reply branches are skipped, parent cursors are independent, and the completed root checkpoint is not reset during normal resume.

The full test suite covers atomic page/checkpoint writes, interruption and cursor restoration, independent parent checkpoints, completed-branch skipping, no unnecessary root recrawl, empty terminal pages, duplicate IDs, parent mismatch, global request budgets, and handler-timeout configuration.

## Changes and decision

1. Moved `requests` from mandatory dependencies to the `full-form` optional extra and documented its installation. Default browser collection no longer requires a dependency used only by the explicitly selected transport.
2. Deleted the unused 725-line archived compatibility harness; retained its results and qualification report.
3. Added exact-URL Resource Timing capture and aggregation for future live measurements.
4. Left root/reply scheduling, pacing, request budgets, connection ownership, normalization, SQLite transactions, and export schemas unchanged. The measured lifecycle saving comes from using the collector's existing single-invocation parent queue rather than restarting it for each parent.

The complete suite finished with **78 passed**. `git diff --check` reported no whitespace errors. No commits, pushes, live requests, or access-restriction retries were made.

## Remaining limitations

- Browser child transport on `Dd-3dhPjaJc` remains unqualified because the sole child response was HTML. Do not infer reply completeness from the root success.
- The live p95 tail's connection/server/network cause remains unknown. The saved run predates Resource Timing fields; the intercepted benchmark cannot answer that question.
- The lifecycle benchmark is small, synthetic, and local, with three trials. It qualifies identical collector behavior and measures repeated invocation cost, not Instagram latency or the duration of a full large-post crawl.
- The 64-count discrepancy is unresolved. Numerical agreement would not by itself establish corpus completeness.
- Python/browser startup phase values vary between cold and warm runs. Keep lifecycle residuals unattributed unless a phase was directly measured.
