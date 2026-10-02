# Instagram collector performance analysis

**Evidence date:** 2026-10-02. Timings combine saved whole-tree run totals, three authorized one-page root probes, the original bounded Dbq0I_HDIQ8 run, and its three-request completion run. GraphQL timing excludes browser navigation and page-resource requests.

## Historical whole-tree totals

| Post | Runs | Root requests | Reply requests | Total GraphQL requests | Runtime sum | Requests/s | Unique records/request | Unique records/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Dd7eoFRE5_t | 6 | 18 | 110 | 128 | 124.672 s | 1.027 | 11.55 | 11.85 |
| Dd9hgbek89B | 3 | 13 | 18 | 31 | 32.336 s | 0.959 | 21.94 | 21.03 |

These are sums of network-bearing collector runs. Time between resumes is excluded. A no-request report refresh is excluded. Historical artifacts have no request latency or phase timing, so latency percentiles and network share cannot be reconstructed for those trees.

Reply fanout was 110/128 requests on Dd7eoFRE5_t and 18/31 on Dd9hgbek89B. Applying the current sequential 500 ms pacing rule to those page/branch counts gives nominal waits of 127 x 500 ms = 63.5 s and 30 x 500 ms = 15.0 s. These are estimates, not saved telemetry from those historical runs.

## Three one-page root probes

Each probe returned first-party HTTP 200 application/json using the stock Playwright browser plugin. No alternate identities, proxies, fingerprint tooling, or retries were used.

| Post | Network latency | Headers | Body | JSON decode | Playwright evaluate | Normalization | SQLite transaction | Collector runtime |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DdFtyOcDwrZ | 1,187.5 ms | 1,187.0 ms | 0.5 ms | 0.1 ms | 1,208.7 ms | 0.641 ms | 3.010 ms | 6.467 s |
| Dbq0I_HDIQ8 page 1 | 756.0 ms | 755.7 ms | 0.3 ms | 0.2 ms | 769.2 ms | 0.398 ms | 2.037 ms | 2.855 s |
| DdvIOQ-Dy5s | 960.5 ms | 960.0 ms | 0.5 ms | 0.1 ms | 977.9 ms | 0.456 ms | 3.418 ms | 3.238 s |

At n=3, median network latency was 960.5 ms; median header wait 960.0 ms, body read 0.5 ms, JSON decode 0.1 ms, evaluate 977.9 ms, normalization 0.456 ms, and SQLite transaction 3.010 ms. Median commit time was 1.209 ms. p90/p95 are omitted because three samples are insufficient. Median time to first handler was 2.030 s. Lifecycle residuals were 5.223 s, 2.052 s, and 2.224 s; this residual combines startup/navigation/scheduling and shutdown, which the current hooks do not separate.

## Four-request resume inside the original Dbq0I_HDIQ8 budget

This resumed collector run sent two root pages and two child pages; those four requests were HTTP 200. Across the full bounded target sequence, ten GraphQL requests were made over seven runs: three root pages and seven child pages. The root cursor exhausted after three pages; six reply branches exhausted after seven child pages, while three remained unattempted. No access error or retry occurred.

| Measurement | Four-request resume |
|---|---:|
| Collector runtime | 5.376 s |
| Root/reply requests | 2 / 2 |
| Requests per second | 0.744 |
| Response records per request | 29.5 |
| New unique records per second | 21.391 |
| Root network time | 1,073.9 ms total; median 536.95 ms |
| Child network time | 625.2 ms total; median 312.60 ms |
| Network time across four requests | 1,699.1 ms |
| Request-start intervals | 3; median 907.98 ms |
| Configured/actual pacing | 500 ms; 3 sleeps totaling 1,516.409 ms |
| Root/reply normalization | 0.601 / 0.224 ms |
| SQLite records/dedup, checkpoint, commits | 2.775 / 0.099 / 23.338 ms |
| SQLite transaction time | 26.218 ms total |
| Crawlee handler/lifecycle | 3.321 / 5.362 s |
| Time to first/after last handler | 1.854 / 0.187 s |
| Lifecycle residual outside handler | 2.041 s |
| JSONL export/report build | 22.946 / 2.698 ms |

The measured wall-clock accounting puts about 38% outside the handler, 32% in GraphQL response wait/read, and 28% in explicit pacing. The handler includes network, sleeps, and local work; the lifecycle residual is outside it. Normalization and SQLite together took under 30 ms. The residual is not attributed to a particular Crawlee substage.

The single-page probes show a median 2.030 s time-to-first-handler, larger than the median 0.961 s response. This is direct evidence of fixed per-run overhead for small jobs. For multi-page runs, the recent bounded resume measures pacing and request waits directly. Historical whole-tree runs lack equivalent phase telemetry.

## Original 10-request Dbq0I_HDIQ8 phase

After the four-request resume, five additional one-page parent probes used the remainder of the stated cap. The seven child requests consist of six initial-operation pages and one continuation page. All seven were HTTP 200 text/javascript JSON; the three root requests were HTTP 200 application/json. There were no retries or access errors.

| Measurement | Bounded post total |
|---|---:|
| GraphQL requests | 10: 3 root, 7 child |
| Collector runtime sum | 27.491 s across 7 separate runs |
| Requests per second | 0.364 |
| Response observation records/request | 18.1 (181 rows including duplicates) |
| Final unique IDs/request | 17.1 (171 IDs) |
| Final unique IDs/second | 6.22 |
| Total measured GraphQL response time | 3.794 s |
| Root response time | 1.830 s total; median 756 ms across 3 samples |
| Child response time | 1.964 s total; median 279.359 ms across 7 samples |
| Child response p90/p95 | Omitted; sample count is below 20 |
| Recorded application pacing | 4.059 s across the runs |
| Saved unique comments | 171: 137 roots and 34 replies |

The seven report runtimes are summed across separate browser sessions and exclude the pauses between runs. Five one-parent filters were intentionally run as separate collector processes; their repeated startup overhead is not representative of one continuous traversal. The original 27.491 seconds are not a single uninterrupted crawl and are not all network latency.

## Three-request completion run

At 08:03:31Z the collector resumed Dbq0I_HDIQ8 with a one-page cap per pending branch. It made exactly three sequential full-form child requests, no root requests, and no retries. All three responses were HTTP 200 `text/javascript` JSON. The completed root checkpoint was skipped.

| Measurement | Three-request run |
|---|---:|
| Collector runtime | 7.245 s |
| Root/reply requests | 0 / 3 |
| Handler / whole Crawlee lifecycle | 2.426 / 7.241 s |
| Lifecycle residual outside handler | 4.815 s |
| Time to first / after last handler | 4.629 / 0.186 s |
| HTTP response time, total | 840.226 ms; median 296.171 ms (n=3) |
| Headers / body / JSON decode | 839.938 / 0.287 / 0.077 ms total |
| Full-form transport call time | 841.269 ms total |
| Request-start intervals | 2; median 793.673 ms |
| Configured / actual pacing | 500 ms; 3 waits totaling 1,522.026 ms |
| Reply normalization | 0.132 ms |
| SQLite transaction | 31.020 ms (0.598 persistence/dedup, 0.034 checkpoint, 30.385 commit) |
| JSONL export / report generation | 21.364 / 2.622 ms |
| Response records / new unique records | 11 / 4 |

The 27.491-second original phase plus this 7.245-second run equals 34.736 seconds across eight separate runs, for 13 requests and 175 final unique records. This aggregate is not one continuous crawl. The follow-up's request rate was 0.414/s; the combined request rate was 0.374/s. The follow-up run itself was dominated by the 4.815-second lifecycle residual (66% of wall time), followed by pacing (21%) and response wait/read (12%). These measurements do not support calling network latency the dominant cost. The residual combines startup, navigation, scheduling, and shutdown because the current hooks do not split them.

## Bottleneck and next experiment

Across the small Dbq0I_HDIQ8 runs, fixed per-run lifecycle time is material. In the three-request completion run it was 4.815 s outside the handler, compared with 0.840 s of response wait/read, 1.522 s of explicit pacing, 31 ms in SQLite, and 0.132 ms in normalization. The largest measured segment is the lifecycle residual, but its exact Crawlee substage is unknown. Historical whole-tree runs lack phase timing, so this does not prove that lifecycle overhead dominates a long uninterrupted crawl.

The next performance experiment should measure one collector process handling several pending parents against separate one-parent invocations, using only naturally pending work and the existing sequential scheduler. The original five one-parent probes summed 19.260 s for five requests; the later three-parent run took 7.245 s for three. The workloads differ, so this suggests a fixed-startup opportunity but does not quantify a causal speedup. Keep the 500 ms pacing and concurrency policy unchanged until a separate bounded experiment supports a change.

## Instrumentation and reliability

The collector records request header/body/JSON timing, evaluate or full-form call duration, response timestamps, request-start intervals, actual pacing, root/reply normalization, SQLite record/dedup/checkpoint/commit/transaction durations, Crawlee handler/lifecycle bounds, and export/report time. Percentiles require at least 20 samples. Raw response bodies and cursor values are not emitted in timing fields.

The configured request-handler timeout is collection duration plus 15 seconds; navigation timeout is capped at 45 seconds. The 90-second bounded run completed in 5.376 seconds. A regression verifies that a 120-second collection duration sets a 135-second handler timeout. This keeps global collection time bounded while individual HTTP requests have separate timeouts.

The post-change full test result is recorded in the end-to-end qualification report. Historical totals, the initial bounded phase, and the three-request follow-up remain separate; missing historical phase times are not presented as measurements.
