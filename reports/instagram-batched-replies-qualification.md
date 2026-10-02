# Instagram batched reply qualification

**Evidence date:** 2026-10-02  
**Scope:** Sequential pending-parent traversal, global request budgets, resume behavior, lifecycle timing, and fixture-backed performance. No Instagram requests were made.

## Qualification result

| Status | Result | Evidence |
|---|---|---|
| `BATCHED_REPLY_EXECUTION` | **QUALIFIED for the existing collector path** | One real Crawlee/Playwright run handled four parents serially using one page and one transport. Four independent parent checkpoints completed. |
| `GLOBAL_REQUEST_BUDGET` | **QUALIFIED** | Offline tests cover a cap shared by roots and replies, a stop between parents, and a stop after committing a reply page. |
| `RESUME` | **QUALIFIED for saved state and deterministic interruption** | Resume restored the parent cursor, skipped completed parents, left root checkpoints unchanged, and added no duplicates. |
| `LIFECYCLE_TIMING` | **QUALIFIED for measurement hooks** | BrowserPool, browser/page creation, session-cookie setup, navigation, request admission, and shutdown hooks ran in the local fixture replay. |
| `INSTAGRAM_TRANSPORT` | **NOT REQUALIFIED HERE** | The browser fetches in the benchmark were intercepted by local fixtures. The prior linked full-form reply experiment remains separate evidence; this report does not qualify the integrated browser transport against Instagram. |
| `ROOT_TRAVERSAL` | **RETAINED FROM PRIOR QUALIFICATION; NOT REPEATED** | Fixture runs started with a completed root checkpoint and made zero root GraphQL requests. |
| `POST_TREE` | **NOT QUALIFIED HERE** | No live post tree was collected. |

The scheduler already iterated all eligible roots sequentially in one handler when no `--reply-parent-id` filter was supplied. This change keeps that path, adds a global per-run request cap, and makes its batching/resume behavior explicit in the report and tests. It does not add workers or alter the transport.

## Scheduler, budget, and recovery

`collect` now accepts `--max-http-requests`. The optional cap counts root and child GraphQL attempts together; existing per-root and per-parent page caps remain in force. A budget stop is recorded as `request_budget`. When a reply page has a next cursor, its records and cursor are committed together before the cap is reported. A later run resumes that parent from the saved cursor. The next eligible parent is left uncheckpointed if it was never requested.

Parents are processed one at a time in root order. Complete parent checkpoints are skipped. A restriction still stops the queue immediately. The root checkpoint is not reset by a reply-only resume, and root pages are not recrawled after natural exhaustion.

The regression suite covers multi-parent order and serialization, global root/reply limits, budget exhaustion between parents and within a branch, continuation cursor restoration, completed-branch skipping, empty terminal pages, interruption after an empty terminal page and after a committed parent, duplicate IDs, and root-checkpoint preservation. Atomic page/checkpoint persistence continues to use the existing SQLite transaction.

## Collection status and CLI exit contract

Each report now has a `collection_status` object:

- `TRANSPORT_SUCCESS` describes this invocation's attempted GraphQL requests: `true` means each returned HTTP 200 JSON; `false` means a request failed that check; `null` means no GraphQL request was attempted.
- `ROOT_PROTOCOL_COMPLETE` and `REPLIES_PROTOCOL_COMPLETE` describe saved cursor-chain termination.
- `COUNT_CONSISTENT` compares the saved unique root-plus-reply total with the post's reported count and is `null` if that count is unavailable.
- `SOURCE_COVERAGE_UNKNOWN` remains `true`; cursor exhaustion and count agreement do not prove that Instagram exposed the full corpus.
- `COLLECTION_PARTIAL` now means traversal is incomplete or an operational failure occurred. A count discrepancy alone does not make traversal partial.

CLI exit codes retain the previous contract: `0` requires non-partial traversal, total and per-parent count agreement, and validated count semantics. `2` still covers incomplete traversal and count uncertainty/inconsistency. Therefore a fully exhausted cursor tree with an unmatched count reports `COLLECTION_PARTIAL=false`, `COUNT_CONSISTENT=false`, and exit code `2`. Exit code `0` is not a source-coverage guarantee.

Historical reply observations remain in the report, but transport success and timing totals are sliced to the current run. This prevents old observations from being compared with a new invocation's request budget.

## Fixture-backed benchmark

The benchmark used four saved roots with two reply pages each, eight unique replies, the same root checkpoint, an eight-request cap, and the existing 500 ms pacing. A local Playwright route fulfilled every page and GraphQL request. The browser made no requests outside those fixture routes. The repeated arm ran first; this is one measured trial, not a median.

| Measurement | Four one-parent invocations | One four-parent invocation |
|---|---:|---:|
| Total wall time | 10,040.866 ms | 5,822.948 ms |
| Crawlee runs / page navigations | 4 / 4 | 1 / 1 |
| Root / reply GraphQL requests | 0 / 8 | 0 / 8 |
| Unique roots / replies | 4 / 8 | 4 / 8 |
| Completed parent branches | 4 | 4 |
| Duplicate records | 0 | 0 |
| Root checkpoint preserved | yes | yes |
| Reply checkpoints complete | yes | yes |
| Requested / actual pacing | 4,000 / 4,048 ms | 4,000 / 4,072 ms |
| Local fixture HTTP execution | 21.300 ms | 19.300 ms |
| JSON decode | 0.100 ms | 0 ms rounded |
| SQLite page transactions | 47.768 ms | 168.983 ms |

The batch arm used **4,217.918 ms less wall time (42.01%)** in this fixture trial while keeping requests and pacing equal. No SQLite speedup was measured; the transaction timings varied in the opposite direction in this single trial.

### Measured lifecycle phases

These totals are summed across four crawls in the repeated arm and one crawl in the batch arm. They are local headless-browser fixture timings, not Instagram transport timings.

| Phase | Four invocations | One invocation |
|---|---:|---:|
| Collector/SQLite initialization | 10.036 ms | 2.297 ms |
| Session configuration load | 0.005 ms | 0.001 ms |
| Crawlee, BrowserPool, and crawler construction | 4.092 ms | 0.876 ms |
| Browser runtime initialization | 1,322.335 ms | 350.803 ms |
| Browser controller creation (BrowserPool launch hook) | 0.094 ms | 0.022 ms |
| Browser page/context initialization | 2,998.253 ms | 767.889 ms |
| Request scheduling/admission | 184.299 ms | 52.625 ms |
| Navigation | 355.251 ms | 119.130 ms |
| After-handler crawler shutdown | 699.581 ms | 172.944 ms |
| BrowserPool shutdown | 656.518 ms | 162.375 ms |

The browser runtime, page/context, navigation, scheduling, and cleanup phases account for most of the measured difference. The page/context phase includes the actual persistent browser process launch, context creation, and page creation; the small BrowserPool launch-hook interval measures controller creation and is not presented as process startup. `BrowserPool` shutdown is included in the after-handler shutdown interval, so those two values overlap and must not be added together. HTTP execution and pacing are separately measured; the lifecycle residual is not labeled browser startup. Crawlee's request statistics cover the top-level page navigation; the child GraphQL fetches execute inside the handler and have their own request timings.

## Validation and limits

- Full suite: **78 passed** (`py -3 -m pytest -q`).
- The real Crawlee/Playwright benchmark used only local route fixtures and isolated temporary Crawlee storage. It did not qualify an Instagram response, reported count, or full post corpus.
- The measured comparison is one trial with the repeated arm first, so browser/OS cache order can affect its wall-time delta. Treat 42.01% as an observed fixture result, not a production throughput promise.
- The full-form transport implementation and its linked live experiment were retained. No live transport request was attempted because the prior alternate-sort experiment had received HTTP 429; this run did not establish that restrictions had cleared.
- Count semantics and Instagram source coverage remain unresolved. Count agreement, where observed, is not proof of corpus completeness.
- No concurrency, proxy, transport behavior, sort, or architecture changes were made.
