# Extended Instagram REST comment pagination qualification

**Date:** 2026-10-01  
**Pagination protocol:** **COMPLETE for the observed sequence**  
**Collection coverage:** **PARTIAL / unverified**

## Experiment

One fresh initial request and six naturally linked continuation requests were
made with one second between requests. The run stopped when the response
reached an explicit terminal state. It did not retry any request or use the
GraphQL/browser paths.

| Page | HTTP | Bytes | Records | New IDs | Overlap with prior pages |
|---:|---:|---:|---:|---:|---:|
| 1 | 200 JSON | 29,751 | 15 | 15 | 0 |
| 2 | 200 JSON | 26,673 | 9 | 9 | 0 |
| 3 | 200 JSON | 32,041 | 15 | 15 | 0 |
| 4 | 200 JSON | 30,364 | 15 | 15 | 0 |
| 5 | 200 JSON | 30,321 | 15 | 15 | 0 |
| 6 | 200 JSON | 29,021 | 15 | 15 | 0 |
| 7 | 200 JSON | 18,044 | 9 | 9 | 0 |

The sequence produced **93 unique comment IDs** with no duplicate IDs or
duplicate page fingerprints. The opaque `next_min_id` cursor was carried in
memory only; the evidence file stores only length and short SHA-256 hashes.

## Terminal behavior

Pages 1 through 6 reported `has_more_comments=false` and
`has_more_headload_comments=true` with an opaque `next_min_id`. Each cursor
advanced and produced new IDs.

Page 7 reported:

- `has_more_comments=false`;
- `has_more_headload_comments=false`;
- no `next_max_id` or `next_min_id` continuation cursor.

The existing evaluator classified page 7 as `COMPLETE` with
`natural_exhaustion`. This is the first genuine multi-page terminal sequence
for the observed REST headload mechanism.

## What this proves

- The Python client can follow the REST headload cursor across six linked
  continuations.
- `has_more_comments=false` alone would have stopped at page 1 and missed 78
  observed comments.
- The cursors advanced without overlap or repetition in this sequence.
- The response is a ranked/variable view in at least the first pages
  (`is_ranked=true` was observed); chronological or complete historical
  ordering was not established.

## What remains unverified

The run did not retain the response body or reported `comment_count`, so
`reported_count_consistent` remains unknown. A terminal protocol flag does not
prove that the ranked view contains every comment represented by Instagram's
reported count. The correct collection state is therefore:

```text
root_protocol_complete = true
reported_count_consistent = unknown
collection_partial = true
termination_reason = natural_exhaustion
```

Machine-readable evidence:
`data/rest-pagination-qualification-12p-20261001.json`.
