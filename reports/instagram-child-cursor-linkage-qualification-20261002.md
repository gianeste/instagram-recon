# Instagram child-reply cursor linkage qualification

**Date:** 2026-10-02  
**Post:** Dd7eoFRE5_t (nytimes)  
**Parent:** media_id 3997923790051057645, parent_comment_id 18356734951220570  
**Verdict:** **QUALIFIED for one bounded, three-page reply traversal.** The original saved cURL captures remain unlinked. The live sequence below uses response-derived continuation state. It does not qualify complete post-wide comment collection or the main browser request transport.

## Request audit and cursor contract

The initial request uses PolarisPostChildCommentsQuery, doc_id 28027289793632076. Its variables have after=null, before=null, media_id and parent_comment_id set, is_chronological/first/last null, and the logged-in Relay provider flag true.

Continuation requests use PolarisPostCommentsChildrenPaginationtQuery, doc_id 27229753410037873. They retain the same media and parent IDs, use first=5, and set after to the previous response's page_info.end_cursor.

The saved response connection exposes edges and page_info. The page_info fields are end_cursor, has_next_page, has_previous_page, and start_cursor; each edge also has a cursor. No separate pagination field or cursor transformation was found. The linked run used page_info.end_cursor verbatim; it did not use an edge cursor.

The original three saved requests had continuation cursors that did not match their preceding responses. Their shared session does not prove traversal linkage. Those captures remain PARTIAL and were not used as continuation input.

The Python runner starts from the first supplied form, retains all supplied form parameters and headers, replaces only the continuation variables.after value with the immediately preceding response cursor, serializes variables as JSON, then lets requests form-encode the body once. The offline encoding test verifies the decoded after value equals the original opaque cursor.

## Bounded live sequence

The runner sent one initial request, saved its response, then continued from that saved response in the same experiment. It sent no separately captured continuation cursor. The manifest notes that the continuation invocation resumed from the saved page-1 response.

| Sequence | Operation / doc ID | Input cursor linkage | Replies | has_next_page | Output cursor SHA-256 | HTTP / content type |
|---|---|---|---:|---|---|---|
| 1 | PolarisPostChildCommentsQuery / 28027289793632076 | Initial null | 15 | true | bfc931a67a7d56785b81c3736e5cba4be485e65a94cce2e6c336da3fa0313203 | 200 / text/javascript; charset=utf-8 |
| 2 | PolarisPostCommentsChildrenPaginationtQuery / 27229753410037873 | Matches page 1 output hash | 15 | true | 267a2502aeaf8e71928ac0c2510d5d9839130a4c7d1c79e7491ffff0a3b9f43b | 200 / text/javascript; charset=utf-8 |
| 3 | PolarisPostCommentsChildrenPaginationtQuery / 27229753410037873 | Matches page 2 output hash | 0 | false | null | 200 / text/javascript; charset=utf-8 |

All 30 reply IDs were unique. Each returned reply node declared the requested parent ID. The empty third response explicitly reported has_next_page=false, so terminal status comes from response data. No intermediate response is missing from this new sequence.

The sanitized pairing manifest is at D:/socialgist/crawlee/instagram-graphql-test/capture_manifest.json. It records sequence, operation, document/media/parent IDs, input/output cursor hashes and equality checks, reply IDs, status, content type, and raw response hashes. It stores no cookies, CSRF tokens, or raw cursor values. Complete response bodies remain in local response_linked_page_N_raw.txt files; pretty JSON companions are also saved.

## Collector integration

The existing browser collector now sends the initial operation for a fresh parent and the continuation operation/document ID for subsequent or resumed pages. It passes the checkpointed page_info.end_cursor unchanged, reuses the existing reply normalizer and per-parent SQLite checkpoints, and continues to use the existing deduplication and recovery behavior. Reply collection starts only after root collection completes. Root collection and root checkpoints remain in place; reply requests remain sequential.

Offline coverage verifies operation/document selection, exact initial variables, cursor advancement, interrupted traversal and resume, two populated pages followed by an empty terminal page, and stable reply normalization.

**Integration limit:** the bounded live trial used the standalone requests runner, which preserved all supplied form fields. The main browser fetch path was not separately live-tested and does not replay captured fb_dtsg, lsd, jazoest, or the other captured form fields. Its endpoint acceptance remains unqualified. The collector adapter is therefore integrated and offline-tested; only the standalone full-form request path is live-qualified.

## Scope and verification

This qualifies one parent and three pages only. It does not establish that all 1,687 reported post comments are retrievable, that every parent has replies, or that all reply branches can be exhausted.

- Main collector offline suite: 55 passed.
- Standalone verifier/encoding suite: 12 passed.
- Offline verifier for the linked live manifest: QUALIFIED; 3 paired requests/responses, 30 unique reply IDs, cursor links valid, terminal response observed.
- No commit or push was made.

