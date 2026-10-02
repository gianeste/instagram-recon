# Instagram REST comment pagination qualification

**Date:** 2026-10-01  
**Verdict:** **PARTIAL — continuation qualified, completeness unverified**

## Bounded experiment

Two read-only Python `httpx` GET requests were made against the same
authorized test media. The second request was issued only because the first
response advertised the headload continuation mechanism. No request was
retried, and no GraphQL or browser request was made.

| Page | HTTP | Bytes | Records | Unique IDs | Fingerprint |
|---:|---:|---:|---:|---:|---|
| 1 | 200 JSON | 29,751 | 15 | 15 | `3785d43b...5e841f` |
| 2 | 200 JSON | 26,673 | 9 | 9 | `93677ed0...1f5dc` |

The raw response bodies, comment text, usernames, and cursor values were not
saved. Cursor values are represented only by length and short SHA-256
diagnostic hashes in `data/rest-pagination-qualification-20261001.json`.

## Cursor relationship

The first response reported:

- `has_more_comments=false`, with no usable `next_max_id`;
- `has_more_headload_comments=true`, with an opaque `next_min_id`;
- `is_ranked=true`.

The second request supplied that opaque value as `min_id`, preserving it
without decoding or manufacturing it. The second response returned a different
opaque `next_min_id` hash, so cursor advancement was observed. The two pages
had zero ID overlap and nine new IDs on page two. The page fingerprints also
differed.

The second response still reported `has_more_comments=false` and
`has_more_headload_comments=true` with another `next_min_id`. Therefore the
experiment stopped at the two-request budget and did not observe terminal
behavior.

## Qualification

| Capability | Status |
|---|---|
| REST JSON response | **Qualified** |
| Root comment normalization shape | **Supported by existing reviewed mapping** |
| Headload cursor request linkage | **Qualified for this two-page sequence** |
| Cursor advancement | **Qualified** |
| New IDs across pages | **Qualified: 9** |
| Natural exhaustion | **Unverified** |
| Full reported-count coverage | **Unverified** |
| Ranked/chronological coverage | **Unverified**; `is_ranked=true` indicates a ranked view only |
| Complete collection | **Not qualified** |

The machine-readable evidence is
`data/rest-pagination-qualification-20261001.json`. This is a bounded live
protocol observation, not a production crawler qualification. A later test
would require explicit authorization for another limited continuation request;
it must stop on 429, 401, 403, 451, challenge, or non-JSON responses.
