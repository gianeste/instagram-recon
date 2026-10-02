from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest

from instagram_collector import crawlee_browser as browser
from instagram_collector.collector import decode_shortcode, normalize_comment
from instagram_collector.crawlee_browser import (
    BrowserCommentExperiment,
    BrowserExperimentConfig,
    _CHILD_CONNECTION,
    _child_page,
)
from instagram_collector.response_fixtures import FixtureError, load_response
from instagram_collector.storage import StateStore


SHORTCODE = "post-1"
MEDIA_ID = f"shortcode:{SHORTCODE}"
PARENT_ID = "parent-1"


class FakePage:
    def __init__(self, callback):
        self.callback = callback

    async def evaluate(self, _script, arguments):
        return await self.callback(arguments)


def experiment(tmp_path, *, mode="resume", root_pages=10, reply_pages=10):
    result = BrowserCommentExperiment(BrowserExperimentConfig(
        target_url=f"https://www.instagram.com/p/{SHORTCODE}/",
        output_root=tmp_path,
        max_root_pages=root_pages,
        max_reply_pages=reply_pages,
        run_mode=mode,
    ))
    result._begin_store(MEDIA_ID)
    result.legacy_app_id = "fixture-app"
    result.legacy_cookies = [{"name": "csrftoken", "value": "fixture-csrf"}]
    return result


def root_record(comment_id=PARENT_ID, reply_count=1):
    return normalize_comment({
        "id": comment_id,
        "from": {"id": 10, "username": "author"},
        "text": "root",
        "timestamp": 1730000000,
        "reply_count": reply_count,
    }, MEDIA_ID, None, source="fixture-root")


def reply_record(comment_id, parent_id=PARENT_ID):
    return normalize_comment({
        "id": comment_id,
        "parent_id": parent_id,
        "from": {"id": 20, "username": "replier"},
        "text": "reply",
        "timestamp": 1730000001,
        "like_count": 2,
    }, MEDIA_ID, None, source="fixture-reply")


def observed_root_record(comment_id, reply_count):
    return normalize_comment({
        "id": comment_id,
        "from": {"id": "author-1", "username": "rooter"},
        "text": f"root {comment_id}",
        "timestamp": 1730000000,
        "reply_count": reply_count,
    }, MEDIA_ID, None, source="fixture-root")


def fetched_reply_record(comment_id, parent_id):
    return normalize_comment({
        "id": comment_id,
        "parent_id": parent_id,
        "from": {"id": "author-2", "username": "replier"},
        "text": "reply text",
        "timestamp": 1730000001,
        "like_count": 2,
    }, MEDIA_ID, None, source="fixture-reply")


def child_payload(parent_id=PARENT_ID, ids=("reply-1",), *, has_next=False, cursor=None):
    return {"data": {_CHILD_CONNECTION: {
        "edges": [{"node": {
            "pk": comment_id,
            "parent_comment_id": parent_id,
            "user": {"pk": "author-2", "username": "replier"},
            "text": "reply text",
            "created_at": 1730000001,
            "comment_like_count": 2,
            "child_comment_count": None,
        }} for comment_id in ids],
        "page_info": {"has_next_page": has_next, "end_cursor": cursor},
    }}}


def legacy_payload(comment_id, *, has_next, cursor, reply_count=0):
    return {"data": {"shortcode_media": {
        "shortcode": SHORTCODE,
        "edge_media_to_parent_comment": {
            "count": 3,
            "edges": [{"node": {
                "id": comment_id,
                "owner": {"id": "author-1", "username": "rooter"},
                "text": "root text",
                "created_at": 1730000000,
                "edge_threaded_comments": {"count": reply_count, "edges": []},
            }}],
            "page_info": {"has_next_page": has_next, "end_cursor": cursor},
        },
    }}}


def legacy_roots_payload(roots, *, reported_count, has_next=False, cursor=None):
    edges = []
    for comment_id, reply_count, embedded_ids in roots:
        edges.append({"node": {
            "id": comment_id,
            "owner": {"id": "author-1", "username": "rooter"},
            "text": f"root {comment_id}",
            "created_at": 1730000000,
            "edge_threaded_comments": {
                "count": reply_count,
                "edges": [{"node": {
                    "id": reply_id,
                    "owner": {"id": "author-2", "username": "replier"},
                    "text": f"reply {reply_id}",
                    "created_at": 1730000001,
                }} for reply_id in embedded_ids],
            },
        }})
    return {"data": {"shortcode_media": {
        "shortcode": SHORTCODE,
        "edge_media_to_parent_comment": {
            "count": reported_count,
            "edges": edges,
            "page_info": {"has_next_page": has_next, "end_cursor": cursor},
        },
    }}}


def seed_refresh_baseline(tmp_path, parent_ids=(PARENT_ID, "parent-2")):
    baseline = experiment(tmp_path, mode="fresh")
    try:
        roots = [observed_root_record(parent_id, 1) for parent_id in parent_ids]
        baseline.store.save_page(
            media_id=MEDIA_ID, edge="comments", parent_id=None, records=roots,
            run_id=baseline.run_id, scan_id=baseline.scan_id, next_cursor=None,
            has_next=False, current_cursor=None,
        )
        for parent_id in parent_ids:
            baseline.store.save_page(
                media_id=MEDIA_ID, edge="replies", parent_id=parent_id,
                records=[fetched_reply_record(f"old-{parent_id}", parent_id)],
                run_id=baseline.run_id, scan_id=baseline.scan_id, next_cursor=None,
                has_next=False, current_cursor=None,
            )
        baseline.reported_comment_count = len(parent_ids) * 2
        baseline._save_response_metadata()
        baseline.store.finish_run(baseline.run_id, {
            "root_protocol_complete": True,
            "replies_protocol_complete": True,
            "reported_comment_count": baseline.reported_comment_count,
        })
    finally:
        baseline.store.close()


def save_root(experiment, record=None):
    experiment.store.save_page(
        media_id=MEDIA_ID,
        edge=experiment.root_edge,
        parent_id=None,
        records=[record or root_record()],
        run_id=experiment.run_id,
        scan_id=experiment.scan_id,
        next_cursor=None,
        has_next=False,
        current_cursor=None,
    )


def save_reply_page(experiment, records, *, has_next=False, cursor=None, current=None):
    return experiment.store.save_page(
        media_id=MEDIA_ID,
        edge=experiment.reply_checkpoint_edge,
        parent_id=PARENT_ID,
        records=records,
        run_id=experiment.run_id,
        scan_id=experiment.scan_id,
        next_cursor=cursor,
        has_next=has_next,
        current_cursor=current,
    )


def test_child_fixture_normalizes_reply_ids_fields_and_parent_relationship():
    payload = load_response(Path(__file__).parents[1] / "fixtures" / "polaris_child_comments_tree.sanitized.json")
    records, has_next, cursor = _child_page(payload, "fixture-media", "18630157939026726")
    assert len(records) == 3
    assert all(isinstance(record["id"], str) for record in records)
    assert all(record["parent_id"] == "18630157939026726" for record in records)
    assert all(record["media_id"] == "fixture-media" for record in records)
    assert all(record["source_operation"] == "PolarisPostChildCommentsQuery" for record in records)
    assert all(record["collected_at"] and record["created_at"].endswith("Z") for record in records)
    assert (has_next, cursor) == (False, None)


def test_fixture_provenance_is_imported_and_does_not_qualify_live_pagination():
    path = Path(__file__).parents[1] / "fixtures" / "fixture-provenance.json"
    provenance = json.loads(path.read_text(encoding="utf-8"))
    child = provenance["fixtures/polaris_child_comments_tree.sanitized.json"]
    assert child["provenance"] == "imported_external"
    assert child["pagination_validated"] is False
    assert child["live_collection_qualified"] is False


def test_child_parser_rejects_missing_pagination_and_wrong_parent():
    with pytest.raises(FixtureError):
        _child_page({"data": {_CHILD_CONNECTION: {"edges": []}}}, MEDIA_ID, PARENT_ID)
    with pytest.raises(FixtureError, match="parent relationship"):
        _child_page(child_payload("different-parent"), MEDIA_ID, PARENT_ID)


def test_reply_cursor_advances_and_exhaustion_is_independent_of_root_cursor(tmp_path):
    run = experiment(tmp_path)
    try:
        save_root(run)
        first = save_reply_page(run, [reply_record("reply-1")], has_next=True, cursor="reply-cursor-1")
        assert first["after_cursor"] == "reply-cursor-1"
        assert run.store.checkpoint(MEDIA_ID, "comments")["complete"] is True
        second = save_reply_page(run, [reply_record("reply-2")], current="reply-cursor-1")
        assert second["complete"] is True
        assert second["termination_reason"] == "natural_exhaustion"
        assert run.store.checkpoint(MEDIA_ID, "comments")["pages"] == 1
        assert run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)["pages"] == 2
    finally:
        run.store.close()


def test_duplicate_reply_ids_are_idempotent(tmp_path):
    run = experiment(tmp_path)
    try:
        save_root(run)
        save_reply_page(run, [reply_record("reply-1")], has_next=True, cursor="c1")
        result = save_reply_page(run, [reply_record("reply-1")], current="c1")
        assert result["duplicates"] == 1
        assert len(run.store.comments(MEDIA_ID, parent_id=PARENT_ID)) == 1
    finally:
        run.store.close()


def test_fetched_reply_deduplicates_embedded_preview_by_stable_id(tmp_path):
    run = experiment(tmp_path)
    try:
        embedded = reply_record("reply-1")
        embedded["source_operation"] = "instagram_legacy_graphql_embedded_reply"
        run.store.save_page(
            media_id=MEDIA_ID, edge="comments", parent_id=None,
            records=[root_record(), embedded], run_id=run.run_id, scan_id=run.scan_id,
            next_cursor=None, has_next=False, current_cursor=None,
        )
        result = save_reply_page(run, [reply_record("reply-1")])
        assert result["duplicates"] == 1
        assert len(run.store.comments(MEDIA_ID, parent_id=PARENT_ID)) == 1
        assert len(run.store.all_comments(MEDIA_ID)) == 2
    finally:
        run.store.close()


def test_repeated_reply_cursor_stays_partial_and_keeps_saved_records(tmp_path):
    run = experiment(tmp_path)
    try:
        save_root(run)
        save_reply_page(run, [reply_record("reply-1")], has_next=True, cursor="c1")
        result = save_reply_page(run, [reply_record("reply-2")], has_next=True, cursor="c1", current="c1")
        checkpoint = run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)
        assert result["complete"] is False
        assert checkpoint["termination_reason"] == "repeated_cursor"
        assert checkpoint["after_cursor"] == "c1"
        assert len(run.store.comments(MEDIA_ID, parent_id=PARENT_ID)) == 2
    finally:
        run.store.close()


def test_empty_reply_page_with_explicit_terminal_flag_completes(tmp_path):
    records, has_next, cursor = _child_page(child_payload(ids=(), has_next=False), MEDIA_ID, PARENT_ID)
    assert records == []
    assert has_next is False
    assert cursor is None


def test_two_populated_reply_pages_then_empty_terminal_complete_branch(tmp_path, monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(browser.asyncio, "sleep", no_sleep)
    run = experiment(tmp_path)
    try:
        save_root(run, root_record(reply_count=2))
        requested_cursors = []
        request_specs = []

        async def reply_page(args):
            after = args["variables"]["after"]
            requested_cursors.append(after)
            request_specs.append((args["operation"], args["docId"], args["variables"]))
            if after is None:
                return {"status": 200, "json": True, "payload": child_payload(
                    ids=("reply-1",), has_next=True, cursor="cursor-1",
                )}
            if after == "cursor-1":
                return {"status": 200, "json": True, "payload": child_payload(
                    ids=("reply-2",), has_next=True, cursor="cursor-2",
                )}
            if after == "cursor-2":
                return {"status": 200, "json": True, "payload": child_payload(
                    ids=(), has_next=False,
                )}
            pytest.fail("continuation did not use the preceding response cursor")

        asyncio.run(run._collect_replies(FakePage(reply_page)))
        checkpoint = run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)
        assert requested_cursors == [None, "cursor-1", "cursor-2"]
        assert [(operation, doc_id) for operation, doc_id, _ in request_specs] == [
            ("PolarisPostChildCommentsQuery", "28027289793632076"),
            ("PolarisPostCommentsChildrenPaginationtQuery", "27229753410037873"),
            ("PolarisPostCommentsChildrenPaginationtQuery", "27229753410037873"),
        ]
        request_media_id = request_specs[0][2]["media_id"]
        assert request_specs[0][2] == {
            "after": None,
            "before": None,
            "media_id": request_media_id,
            "parent_comment_id": PARENT_ID,
            "is_chronological": None,
            "first": None,
            "last": None,
            "__relay_internal__pv__PolarisIsLoggedInrelayprovider": True,
        }
        assert request_specs[1][2]["after"] == "cursor-1"
        assert request_specs[1][2]["first"] == 5
        assert request_specs[2][2]["after"] == "cursor-2"
        assert checkpoint["pages"] == 3
        assert checkpoint["complete"] is True
        assert checkpoint["termination_reason"] == "natural_exhaustion"
        assert [row["id"] for row in run.store.comments(MEDIA_ID, parent_id=PARENT_ID)] == [
            "reply-1", "reply-2",
        ]
        assert run.report("empty_terminal_page")["replies_protocol_complete"] is True
        assert run.reply_observations[-1]["retrieval_outcome"] == "valid_empty_terminal_response"
        assert run.http_request_attempts == 3
        source_by_id = {
            row["id"]: row["source_operation"]
            for row in run.store.comments(MEDIA_ID, parent_id=PARENT_ID)
        }
        assert source_by_id == {
            "reply-1": "PolarisPostChildCommentsQuery",
            "reply-2": "PolarisPostCommentsChildrenPaginationtQuery",
        }
    finally:
        run.store.close()


def test_store_page_and_checkpoint_commit_atomically(tmp_path):
    run = experiment(tmp_path)
    try:
        with pytest.raises(ValueError, match="missing id"):
            run.store.save_page(
                media_id=MEDIA_ID, edge="comments", parent_id=None,
                records=[root_record(), {"id": ""}], run_id=run.run_id, scan_id=run.scan_id,
                next_cursor="must-not-advance", has_next=True, current_cursor=None,
            )
        assert run.store.comments(MEDIA_ID, parent_id=None) == []
        assert run.store.checkpoint(MEDIA_ID, "comments") is None

        saved = run.store.save_page(
            media_id=MEDIA_ID, edge="comments", parent_id=None,
            records=[root_record()], run_id=run.run_id, scan_id=run.scan_id,
            next_cursor=None, has_next=False, current_cursor=None,
        )
        assert set(saved["timings_ms"]) == {
            "record_persistence_and_deduplication", "checkpoint", "commit", "transaction"
        }
        assert all(value >= 0 for value in saved["timings_ms"].values())
    finally:
        run.store.close()


def test_parent_conflict_rejects_idempotency_collision(tmp_path):
    run = experiment(tmp_path)
    try:
        save_root(run)
        save_reply_page(run, [reply_record("same-id")])
        with pytest.raises(ValueError, match="conflicting parent"):
            run.store.save_page(
                media_id=MEDIA_ID, edge="comments", parent_id=None,
                records=[normalize_comment({"id": "same-id", "text": "root"}, MEDIA_ID, None)],
                run_id=run.run_id, scan_id=run.scan_id, next_cursor=None, has_next=False, current_cursor=None,
            )
    finally:
        run.store.close()


def test_parent_mismatch_marks_attempted_branch_partial_without_changing_roots(tmp_path):
    run = experiment(tmp_path)
    try:
        save_root(run, root_record(reply_count=1))
        root_checkpoint = run.store.checkpoint(MEDIA_ID, "comments")

        async def mismatch(_args):
            return {"status": 200, "json": True, "payload": child_payload(parent_id="wrong-parent")}

        asyncio.run(run._collect_replies(FakePage(mismatch)))
        checkpoint = run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)
        branch = run.report("parent_mismatch")["reply_branches"][0]
        assert checkpoint["termination_reason"] == "parent_mismatch"
        assert checkpoint["complete"] is False
        assert run.store.comments(MEDIA_ID, parent_id=PARENT_ID) == []
        assert run.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
        assert run.http_request_attempts == 1
        assert branch["request_attempted"] is True
        assert branch["status"] == "PARTIAL"
    finally:
        run.store.close()


def test_resume_skips_completed_branch_and_keeps_parent_checkpoints_independent(tmp_path):
    run = experiment(tmp_path)
    second_parent = "parent-2"
    try:
        run.store.save_page(
            media_id=MEDIA_ID, edge="comments", parent_id=None,
            records=[root_record(PARENT_ID), root_record(second_parent)],
            run_id=run.run_id, scan_id=run.scan_id, next_cursor=None,
            has_next=False, current_cursor=None,
        )
        run.store.save_page(
            media_id=MEDIA_ID, edge="replies", parent_id=PARENT_ID,
            records=[reply_record("reply-1", PARENT_ID)], run_id=run.run_id,
            scan_id=run.scan_id, next_cursor=None, has_next=False, current_cursor=None,
        )
        root_checkpoint = run.store.checkpoint(MEDIA_ID, "comments")
        calls = []

        async def second_branch(args):
            parent_id = args["variables"]["parent_comment_id"]
            calls.append(parent_id)
            return {
                "status": 200, "json": True,
                "payload": child_payload(parent_id=second_parent, ids=("reply-2",)),
            }

        asyncio.run(run._collect_replies(FakePage(second_branch)))
        report = run.report("resume_finished")
        assert calls == [second_parent]
        assert run.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
        assert run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)["pages"] == 1
        assert run.store.checkpoint(MEDIA_ID, "replies", second_parent)["pages"] == 1
        assert len(run.store.comments(MEDIA_ID, parent_id=PARENT_ID)) == 1
        assert len(run.store.comments(MEDIA_ID, parent_id=second_parent)) == 1
        assert run.http_request_attempts == 1
        assert report["complete_parent_branches"] == 2
        assert report["partial_parent_branches"] == 0
        assert report["unattempted_parent_branches"] == 0
        assert report["total_http_requests"] == 1
    finally:
        run.store.close()


def test_reply_page_budget_preserves_cursor_and_resumes_only_partial_branch(tmp_path):
    run = experiment(tmp_path, reply_pages=1)
    parent_2, parent_3 = "parent-2", "parent-3"
    try:
        run.store.save_page(
            media_id=MEDIA_ID, edge="comments", parent_id=None,
            records=[root_record(PARENT_ID, 2), root_record(parent_2, 1), root_record(parent_3, 1)],
            run_id=run.run_id, scan_id=run.scan_id, next_cursor=None,
            has_next=False, current_cursor=None,
        )
        root_checkpoint = run.store.checkpoint(MEDIA_ID, "comments")
        requests = []

        async def first_budgeted_run(args):
            parent = args["variables"]["parent_comment_id"]
            after = args["variables"]["after"]
            requests.append((parent, after))
            if parent == PARENT_ID:
                return {"status": 200, "json": True, "payload": child_payload(
                    ids=("reply-1",), has_next=True, cursor="cursor-1",
                )}
            return {"status": 200, "json": True, "payload": child_payload(
                parent_id=parent, ids=(), has_next=False,
            )}

        asyncio.run(run._collect_replies(FakePage(first_budgeted_run)))
        report = run.report("page_budget")
        assert requests == [(PARENT_ID, None), (parent_2, None), (parent_3, None)]
        assert report["replies_protocol_complete"] is False
        assert report["partial_parent_branches"] == 1
        assert report["complete_parent_branches"] == 2
        assert report["unattempted_parent_branches"] == 0
        assert run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)["termination_reason"] == "page_budget"
        assert run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)["after_cursor"] == "cursor-1"

        run.config = replace(run.config, max_reply_pages=2)
        requests.clear()

        async def resumed_run(args):
            parent = args["variables"]["parent_comment_id"]
            after = args["variables"]["after"]
            requests.append((parent, after))
            assert parent == PARENT_ID
            assert after == "cursor-1"
            return {"status": 200, "json": True, "payload": child_payload(
                ids=(), has_next=False,
            )}

        asyncio.run(run._collect_replies(FakePage(resumed_run)))
        report = run.report("resumed_after_page_budget")
        assert requests == [(PARENT_ID, "cursor-1")]
        assert report["replies_protocol_complete"] is True
        assert report["partial_parent_branches"] == 0
        assert report["unattempted_parent_branches"] == 0
        assert run.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
        assert {row["id"] for row in run.store.all_comments(MEDIA_ID)} == {
            PARENT_ID, parent_2, parent_3, "reply-1",
        }
    finally:
        run.store.close()


def test_interruption_resumes_at_next_pending_parent_without_replaying_completed_branches(tmp_path):
    run = experiment(tmp_path)
    parent_2, completed_parent = "parent-2", "parent-completed"
    try:
        run.store.save_page(
            media_id=MEDIA_ID, edge="comments", parent_id=None,
            records=[root_record(PARENT_ID), root_record(parent_2), root_record(completed_parent)],
            run_id=run.run_id, scan_id=run.scan_id, next_cursor=None,
            has_next=False, current_cursor=None,
        )
        run.store.save_page(
            media_id=MEDIA_ID, edge="replies", parent_id=completed_parent,
            records=[reply_record("reply-completed", completed_parent)],
            run_id=run.run_id, scan_id=run.scan_id, next_cursor=None,
            has_next=False, current_cursor=None,
        )
        root_checkpoint = run.store.checkpoint(MEDIA_ID, "comments")

        async def interrupted_after_first_parent(args):
            parent = args["variables"]["parent_comment_id"]
            if parent == parent_2:
                raise asyncio.CancelledError
            assert parent == PARENT_ID
            return {"status": 200, "json": True, "payload": child_payload(ids=("reply-1",))}

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(run._collect_replies(FakePage(interrupted_after_first_parent)))
        assert run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)["complete"] is True
        assert run.store.checkpoint(MEDIA_ID, "replies", parent_2) is None
        assert run.store.checkpoint(MEDIA_ID, "replies", completed_parent)["complete"] is True

        requests = []

        async def resume_pending_parent(args):
            parent = args["variables"]["parent_comment_id"]
            requests.append(parent)
            assert parent == parent_2
            return {"status": 200, "json": True, "payload": child_payload(parent_id=parent, ids=("reply-2",))}

        asyncio.run(run._collect_replies(FakePage(resume_pending_parent)))
        report = run.report("resume_next_pending_parent")
        assert requests == [parent_2]
        assert report["replies_protocol_complete"] is True
        assert report["complete_parent_branches"] == 3
        assert report["unattempted_parent_branches"] == 0
        assert run.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
        assert len(run.store.all_comments(MEDIA_ID)) == 6
    finally:
        run.store.close()


def test_later_null_observation_does_not_erase_populated_fields(tmp_path):
    run = experiment(tmp_path)
    try:
        populated = root_record()
        save_root(run, populated)
        sparse = normalize_comment({
            "id": PARENT_ID,
            "text": None,
            "timestamp": None,
            "like_count": None,
            "reply_count": None,
        }, MEDIA_ID, None, source="partial-observation")
        result = run.store.save_page(
            media_id=MEDIA_ID, edge="comments", parent_id=None, records=[sparse],
            run_id=run.run_id, scan_id=run.scan_id, next_cursor=None, has_next=False, current_cursor=None,
        )
        saved = run.store.comments(MEDIA_ID, parent_id=None)[0]
        assert result["duplicates"] == 1
        assert saved["text"] == "root"
        assert saved["author_id"] == "10"
        assert saved["created_at"] is not None
        assert saved["reported_reply_count"] == 1
    finally:
        run.store.close()


def test_new_artifact_path_copies_legacy_sqlite_without_removing_source(tmp_path):
    legacy = tmp_path / "legacy-graphql" / SHORTCODE / "state.sqlite"
    with StateStore(legacy) as store:
        store.save_post(media_id=MEDIA_ID, shortcode=SHORTCODE, post={"shortcode": SHORTCODE}, author={})
        store.begin_run("old-run", "old-scan", MEDIA_ID, "legacy")
        store.save_page(
            media_id=MEDIA_ID, edge="comments", parent_id=None, records=[root_record()],
            run_id="old-run", scan_id="old-scan", next_cursor=None, has_next=False, current_cursor=None,
        )
    run = BrowserCommentExperiment(BrowserExperimentConfig(
        target_url=f"https://www.instagram.com/p/{SHORTCODE}/", output_root=tmp_path,
    ))
    try:
        assert run.output_dir == tmp_path / SHORTCODE
        assert run.store.checkpoint(MEDIA_ID, "comments")["complete"] is True
        assert len(run.store.comments(MEDIA_ID, parent_id=None)) == 1
        assert legacy.exists()
    finally:
        run.store.close()


def test_rate_limit_stops_before_trying_another_reply_parent(tmp_path):
    run = experiment(tmp_path)
    second_root = root_record("parent-2", reply_count=1)
    try:
        run.store.save_page(
            media_id=MEDIA_ID, edge="comments", parent_id=None,
            records=[root_record(reply_count=1), second_root], run_id=run.run_id, scan_id=run.scan_id,
            next_cursor=None, has_next=False, current_cursor=None,
        )
        calls = []

        async def limited(_args):
            calls.append(True)
            return {"status": 429, "json": False, "boundary": "rate_limited"}

        asyncio.run(run._collect_replies(FakePage(limited)))
        assert len(calls) == 1
        assert run.reply_stop_reason == "rate_limited"
        assert run.reply_observations[-1]["retrieval_outcome"] == "rate_limited"
        assert run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)["termination_reason"] == "rate_limited"
        assert run.store.checkpoint(MEDIA_ID, "replies", "parent-2") is None
        assert run.store.checkpoint(MEDIA_ID, "comments")["complete"] is True
    finally:
        run.store.close()


def test_expired_reply_cursor_preserves_prior_page_and_marks_branch_partial(tmp_path):
    run = experiment(tmp_path)
    try:
        save_root(run, root_record(reply_count=2))
        save_reply_page(run, [reply_record("reply-1")], has_next=True, cursor="expired-cursor")

        async def expired(_args):
            return {
                "status": 200, "json": True, "payload": {}, "cursorExpired": True,
                "unavailable": False, "graphqlError": False,
            }

        asyncio.run(run._collect_replies(FakePage(expired)))
        checkpoint = run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)
        assert checkpoint["pages"] == 1
        assert checkpoint["after_cursor"] == "expired-cursor"
        assert checkpoint["complete"] is False
        assert checkpoint["termination_reason"] == "cursor_expired"
        assert len(run.store.comments(MEDIA_ID, parent_id=PARENT_ID)) == 1
    finally:
        run.store.close()


def test_interrupted_root_run_resumes_from_last_committed_cursor(tmp_path, monkeypatch):
    async def no_sleep(_seconds):
        return None
    monkeypatch.setattr(browser.asyncio, "sleep", no_sleep)
    first_run = experiment(tmp_path, root_pages=10)
    requests = []

    async def interrupted(_args):
        requests.append(_args["after"])
        if len(requests) == 1:
            return {"status": 200, "json": True, "payload": legacy_payload("root-1", has_next=True, cursor="c1")}
        if len(requests) == 2:
            return {"status": 200, "json": True, "payload": legacy_payload("root-2", has_next=True, cursor="c2")}
        raise RuntimeError("simulated interruption")

    try:
        asyncio.run(first_run._collect_legacy_graphql(FakePage(interrupted)))
        checkpoint = first_run.store.checkpoint(MEDIA_ID, "comments")
        assert checkpoint["pages"] == 2
        assert checkpoint["after_cursor"] == "c2"
        assert len(first_run.store.comments(MEDIA_ID, parent_id=None)) == 2
    finally:
        first_run.store.close()

    resumed = experiment(tmp_path, root_pages=10)
    seen = []

    async def finish_root(args):
        seen.append(args["after"])
        return {"status": 200, "json": True, "payload": legacy_payload("root-3", has_next=False, cursor=None)}

    try:
        asyncio.run(resumed._collect_legacy_graphql(FakePage(finish_root)))
        assert seen == ["c2"]
        checkpoint = resumed.store.checkpoint(MEDIA_ID, "comments")
        assert checkpoint["pages"] == 3
        assert checkpoint["complete"] is True
        assert len(resumed.store.comments(MEDIA_ID, parent_id=None)) == 3
    finally:
        resumed.store.close()


def test_interrupted_reply_run_resumes_its_parent_cursor(tmp_path, monkeypatch):
    async def no_sleep(_seconds):
        return None
    monkeypatch.setattr(browser.asyncio, "sleep", no_sleep)
    first_run = experiment(tmp_path, reply_pages=10)
    try:
        save_root(first_run, root_record(reply_count=2))
        root_checkpoint = first_run.store.checkpoint(MEDIA_ID, "comments")
        calls = []

        async def interrupted(args):
            variables = args["variables"]
            calls.append((args["operation"], args["docId"], variables["after"]))
            if len(calls) == 1:
                return {"status": 200, "json": True, "payload": child_payload(ids=("reply-1",), has_next=True, cursor="rc1")}
            raise RuntimeError("simulated interruption")

        asyncio.run(first_run._collect_replies(FakePage(interrupted)))
        checkpoint = first_run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)
        assert calls == [
            ("PolarisPostChildCommentsQuery", "28027289793632076", None),
            ("PolarisPostCommentsChildrenPaginationtQuery", "27229753410037873", "rc1"),
        ]
        assert checkpoint["pages"] == 1
        assert checkpoint["after_cursor"] == "rc1"
        assert len(first_run.store.comments(MEDIA_ID, parent_id=PARENT_ID)) == 1
        assert first_run.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
    finally:
        first_run.store.close()

    resumed = experiment(tmp_path, reply_pages=10)
    seen = []

    async def finish_reply(args):
        variables = args["variables"]
        seen.append((
            variables["parent_comment_id"],
            variables["after"],
            args["operation"],
            args["docId"],
        ))
        return {"status": 200, "json": True, "payload": child_payload(ids=("reply-2",), has_next=False)}

    try:
        asyncio.run(resumed._collect_replies(FakePage(finish_reply)))
        assert seen == [(
            PARENT_ID, "rc1",
            "PolarisPostCommentsChildrenPaginationtQuery", "27229753410037873",
        )]
        checkpoint = resumed.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)
        assert checkpoint["pages"] == 2
        assert checkpoint["complete"] is True
        assert len(resumed.store.comments(MEDIA_ID, parent_id=PARENT_ID)) == 2
        assert resumed.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
    finally:
        resumed.store.close()


def test_expired_reply_cursor_restarts_only_its_parent_branch(tmp_path, monkeypatch):
    async def no_sleep(_seconds):
        return None
    monkeypatch.setattr(browser.asyncio, "sleep", no_sleep)
    first = experiment(tmp_path)
    try:
        save_root(first, root_record(reply_count=2))
        save_reply_page(first, [reply_record("reply-1")], has_next=True, cursor="expired-cursor")
        first.store.set_termination(MEDIA_ID, "replies", "cursor_expired", PARENT_ID)
    finally:
        first.store.close()

    resumed = experiment(tmp_path)
    seen = []

    async def replay(args):
        seen.append(args["variables"]["after"])
        return {"status": 200, "json": True, "payload": child_payload(ids=("reply-1",), has_next=False)}

    try:
        asyncio.run(resumed._collect_replies(FakePage(replay)))
        assert seen == [None]
        assert resumed.reply_expiration_restarts == [PARENT_ID]
        assert resumed.store.checkpoint(MEDIA_ID, "comments")["complete"] is True
        checkpoint = resumed.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)
        assert checkpoint["complete"] is True
        assert checkpoint["pages"] == 1
        assert len(resumed.store.comments(MEDIA_ID, parent_id=PARENT_ID)) == 1
    finally:
        resumed.store.close()


def test_expired_root_cursor_restarts_root_branch_and_keeps_saved_records(tmp_path, monkeypatch):
    async def no_sleep(_seconds):
        return None
    monkeypatch.setattr(browser.asyncio, "sleep", no_sleep)
    first = experiment(tmp_path)
    try:
        first.store.save_page(
            media_id=MEDIA_ID, edge="comments", parent_id=None, records=[root_record(reply_count=0)],
            run_id=first.run_id, scan_id=first.scan_id, next_cursor="expired-cursor",
            has_next=True, current_cursor=None,
        )
        first.store.set_termination(MEDIA_ID, "comments", "cursor_expired")
    finally:
        first.store.close()

    resumed = experiment(tmp_path)
    seen = []

    async def replay(args):
        seen.append(args["after"])
        return {"status": 200, "json": True, "payload": legacy_payload("root-2", has_next=False, cursor=None)}

    try:
        asyncio.run(resumed._collect_legacy_graphql(FakePage(replay)))
        assert seen == [None]
        assert resumed.root_cursor_expiration_restarted is True
        assert resumed.store.checkpoint(MEDIA_ID, "comments")["termination_reason"] == "natural_exhaustion"
        assert len(resumed.store.comments(MEDIA_ID, parent_id=None)) == 2
    finally:
        resumed.store.close()


def test_refresh_preserves_root_checkpoint_and_deduplicates_records(tmp_path):
    original = experiment(tmp_path)
    save_root(original)
    original.store.close()
    refreshed = experiment(tmp_path, mode="refresh")
    try:
        assert refreshed.store.checkpoint(MEDIA_ID, "comments")["complete"] is True
        assert refreshed.store.checkpoint(MEDIA_ID, "comments_refresh") is None
        assert len(refreshed.store.comments(MEDIA_ID, parent_id=None)) == 1
        result = refreshed.store.save_page(
            media_id=MEDIA_ID, edge=refreshed.root_edge, parent_id=None, records=[root_record()],
            run_id=refreshed.run_id, scan_id=refreshed.scan_id, next_cursor=None,
            has_next=False, current_cursor=None,
        )
        assert result["duplicates"] == 1
        assert len(refreshed.store.comments(MEDIA_ID, parent_id=None)) == 1
        assert refreshed.store.checkpoint(MEDIA_ID, "comments")["complete"] is True
    finally:
        refreshed.store.close()


def test_refresh_delta_tracks_new_updated_and_not_observed_without_deleting(tmp_path):
    baseline = experiment(tmp_path)
    try:
        baseline_records = (
            root_record("old-root", 0),
            root_record("missing-root", 0),
            root_record("stable-root", 0),
        )
        for record in baseline_records:
            baseline.store.save_page(
                media_id=MEDIA_ID, edge=baseline.root_edge, parent_id=None, records=[record],
                run_id=baseline.run_id, scan_id=baseline.scan_id, next_cursor=None,
                has_next=False, current_cursor=None,
            )
        sparse_duplicate = root_record("stable-root", 0)
        sparse_duplicate["text"] = None
        baseline.store.save_page(
            media_id=MEDIA_ID, edge=baseline.root_edge, parent_id=None, records=[sparse_duplicate],
            run_id=baseline.run_id, scan_id=baseline.scan_id, next_cursor=None,
            has_next=False, current_cursor=None,
        )
        baseline.store.finish_run(baseline.run_id, {"root_protocol_complete": True})
    finally:
        baseline.store.close()

    refreshed = experiment(tmp_path, mode="refresh")
    try:
        changed = root_record("old-root", 0)
        changed["text"] = "updated root text"
        for records in ([changed], [root_record("stable-root", 0)], [root_record("new-root", 0)]):
            refreshed.store.save_page(
                media_id=MEDIA_ID, edge=refreshed.root_edge, parent_id=None, records=records,
                run_id=refreshed.run_id, scan_id=refreshed.scan_id, next_cursor=None,
                has_next=False, current_cursor=None,
            )
        delta = refreshed.store.scan_changes(MEDIA_ID, refreshed.scan_id, complete=True)
        assert delta["new_ids"] == ["new-root"]
        assert delta["updated_fields"] == {"old-root": ["text"]}
        assert delta["not_observed_ids"] == ["missing-root"]
        assert refreshed.store.scan_changes(MEDIA_ID, refreshed.scan_id, complete=False)["not_observed_ids"] is None
        assert len(refreshed.store.comments(MEDIA_ID, parent_id=None)) == 4
    finally:
        refreshed.store.close()


def test_interrupted_refresh_resumes_its_cursor_and_preserves_root_checkpoint(tmp_path, monkeypatch):
    async def no_sleep(_seconds):
        return None
    monkeypatch.setattr(browser.asyncio, "sleep", no_sleep)
    original = experiment(tmp_path)
    save_root(original)
    original.store.close()

    interrupted = experiment(tmp_path, mode="refresh")
    refresh_scan_id = interrupted.scan_id
    interrupted.store.save_page(
        media_id=MEDIA_ID, edge=interrupted.root_edge, parent_id=None,
        records=[root_record("refresh-root-1", 0)], run_id=interrupted.run_id,
        scan_id=interrupted.scan_id, next_cursor="refresh-cursor-1",
        has_next=True, current_cursor=None,
    )
    interrupted.store.close()

    resumed = experiment(tmp_path, mode="resume")
    seen = []

    async def finish(args):
        seen.append(args["after"])
        return {"status": 200, "json": True, "payload": legacy_payload("refresh-root-2", has_next=False, cursor=None)}

    try:
        assert resumed.root_edge == "comments_refresh"
        assert resumed.scan_id == refresh_scan_id
        asyncio.run(resumed._collect_legacy_graphql(FakePage(finish)))
        assert seen == ["refresh-cursor-1"]
        assert resumed.store.checkpoint(MEDIA_ID, "comments_refresh")["complete"] is True
        assert resumed.store.checkpoint(MEDIA_ID, "comments")["complete"] is True
        assert len(resumed.store.comments(MEDIA_ID, parent_id=None)) == 3
    finally:
        resumed.store.close()


def test_refresh_rewalks_all_parents_and_deduplicates_embedded_reply_previews(tmp_path, monkeypatch):
    async def no_sleep(_seconds):
        return None
    monkeypatch.setattr(browser.asyncio, "sleep", no_sleep)
    seed_refresh_baseline(tmp_path)
    refreshed = experiment(tmp_path, mode="refresh")
    root_checkpoint = refreshed.store.checkpoint(MEDIA_ID, "comments")
    try:
        async def root_page(args):
            assert args["after"] is None
            return {"status": 200, "json": True, "payload": legacy_roots_payload(
                [
                    (PARENT_ID, 3, ("new-r1",)),
                    ("parent-2", 1, ()),
                    ("parent-3", 1, ()),
                ],
                reported_count=9,
            )}

        asyncio.run(refreshed._collect_legacy_graphql(FakePage(root_page)))
        requested = []

        async def child_page(args):
            variables = args["variables"]
            parent, after = variables["parent_comment_id"], variables["after"]
            requested.append((parent, after, args["operation"], args["docId"]))
            if parent == PARENT_ID and after is None:
                payload = child_payload(parent, ("new-r1", "new-r2"), has_next=True, cursor="p1-next")
            elif parent == PARENT_ID and after == "p1-next":
                payload = child_payload(parent, ("new-r3",))
            elif parent == "parent-2":
                payload = child_payload(parent, (), has_next=False)
            elif parent == "parent-3":
                payload = child_payload(parent, ("new-r4",))
            else:
                pytest.fail(f"unexpected refresh request {parent=} {after=}")
            return {"status": 200, "json": True, "payload": payload}

        asyncio.run(refreshed._collect_replies(FakePage(child_page)))
        report = refreshed.report("natural_exhaustion")
        refreshed.store.finish_run(refreshed.run_id, report)
        assert refreshed.store.latest_successful_run(MEDIA_ID, mode="refresh") is not None

        assert [request[:2] for request in requested] == [
            (PARENT_ID, None), (PARENT_ID, "p1-next"), ("parent-2", None), ("parent-3", None),
        ]
        assert requested[0][2:] == ("PolarisPostChildCommentsQuery", "28027289793632076")
        assert requested[1][2:] == ("PolarisPostCommentsChildrenPaginationtQuery", "27229753410037873")
        assert refreshed.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
        assert refreshed.store.checkpoint(MEDIA_ID, "comments_refresh")["complete"] is True
        assert refreshed.reply_checkpoint_edge == f"replies_refresh:{refreshed.scan_id}"
        assert refreshed.store.checkpoint(MEDIA_ID, refreshed.reply_checkpoint_edge, "parent-2") == {
            "after_cursor": None, "complete": True, "pages": 1,
            "last_successful_page": 1, "termination_reason": "natural_exhaustion",
        }
        records = refreshed.store.all_comments(MEDIA_ID)
        by_id = {record["id"]: record for record in records}
        assert len(records) == 9
        assert by_id["new-r1"]["parent_id"] == PARENT_ID
        assert by_id["new-r4"]["parent_id"] == "parent-3"
        assert all(record["media_id"] == MEDIA_ID for record in records)
        assert report["duplicate_records"] == 3
        assert report["unique_roots"] == 3
        assert report["unique_replies"] == 6
        assert report["replies_protocol_complete"] is True
        assert report["reported_count_consistent"] is True
        assert report["last_refresh_at"] is not None
        assert report["reported_count_history"][-2]["reported_comment_count"] == 4
        assert report["reported_count_history"][-1]["reported_comment_count"] == 9
        assert report["refresh_delta"]["status"] == "COMPLETE"
        assert set(report["refresh_delta"]["new_comment_ids"]) == {
            "parent-3", "new-r1", "new-r2", "new-r3", "new-r4",
        }
        assert report["refresh_delta"]["not_observed_once_ids"] == ["old-parent-1", "old-parent-2"]
        assert set(next(row for row in report["reply_branches"] if row["parent_comment_id"] == PARENT_ID)["new_reply_ids"]) == {
            "new-r1", "new-r2", "new-r3",
        }
        assert [row["checkpoint_edge"] for row in next(
            row for row in report["reply_branches"] if row["parent_comment_id"] == PARENT_ID
        )["completeness_history"]] == ["replies", refreshed.reply_checkpoint_edge]
    finally:
        refreshed.store.close()


def test_unchanged_refresh_reports_no_new_or_updated_ids(tmp_path, monkeypatch):
    async def no_sleep(_seconds):
        return None
    monkeypatch.setattr(browser.asyncio, "sleep", no_sleep)
    seed_refresh_baseline(tmp_path, parent_ids=(PARENT_ID,))
    refreshed = experiment(tmp_path, mode="refresh")
    try:
        async def root_page(_args):
            return {"status": 200, "json": True, "payload": legacy_roots_payload(
                [(PARENT_ID, 1, ())], reported_count=2,
            )}

        asyncio.run(refreshed._collect_legacy_graphql(FakePage(root_page)))

        async def child_page(args):
            assert args["variables"]["after"] is None
            return {"status": 200, "json": True, "payload": child_payload(
                PARENT_ID, (f"old-{PARENT_ID}",),
            )}

        asyncio.run(refreshed._collect_replies(FakePage(child_page)))
        report = refreshed.report("natural_exhaustion")
        assert report["refresh_delta"]["status"] == "COMPLETE"
        assert report["refresh_delta"]["new_comment_ids"] == []
        assert report["refresh_delta"]["updated_records"] == {}
        assert report["unique_comment_ids"] == 2
        assert report["duplicate_records"] == 2
        assert report["collection_status"]["REPLIES_PROTOCOL_COMPLETE"] is True
    finally:
        refreshed.store.close()


def test_interrupted_refresh_resumes_child_cursor_skips_completed_parent_and_root(tmp_path, monkeypatch):
    async def no_sleep(_seconds):
        return None
    monkeypatch.setattr(browser.asyncio, "sleep", no_sleep)
    seed_refresh_baseline(tmp_path, parent_ids=("parent-1", "parent-2", "parent-3"))
    interrupted = experiment(tmp_path, mode="refresh")
    try:
        async def root_page(_args):
            return {"status": 200, "json": True, "payload": legacy_roots_payload(
                [("parent-1", 1, ()), ("parent-2", 2, ()), ("parent-3", 1, ())],
                reported_count=7,
            )}

        asyncio.run(interrupted._collect_legacy_graphql(FakePage(root_page)))
        active_edge = interrupted.reply_checkpoint_edge
        root_checkpoint = interrupted.store.checkpoint(MEDIA_ID, "comments")
        completed_parent_checkpoint = None

        async def fail_after_committed_page(args):
            parent = args["variables"]["parent_comment_id"]
            after = args["variables"]["after"]
            if parent == "parent-1":
                return {"status": 200, "json": True, "payload": child_payload(parent, ("new-p1",))}
            if after is None:
                return {"status": 200, "json": True, "payload": child_payload(
                    parent, ("new-p2-first",), has_next=True, cursor="p2-cursor",
                )}
            raise RuntimeError("injected interruption after committed page")

        asyncio.run(interrupted._collect_replies(FakePage(fail_after_committed_page)))
        completed_parent_checkpoint = interrupted.store.checkpoint(MEDIA_ID, active_edge, "parent-1")
        partial = interrupted.report("injected_interruption")
        interrupted.store.finish_run(interrupted.run_id, partial)
        assert interrupted.store.latest_successful_run(MEDIA_ID, mode="refresh") is None
        cursor_checkpoint = interrupted.store.checkpoint(MEDIA_ID, active_edge, "parent-2")
        assert partial["root_protocol_complete"] is True
        assert partial["replies_protocol_complete"] is False
        assert partial["refresh_delta"]["status"] == "PARTIAL"
        assert partial["last_refresh_at"] is None
        assert cursor_checkpoint["after_cursor"] == "p2-cursor"
        assert cursor_checkpoint["pages"] == 1
        assert cursor_checkpoint["complete"] is False
    finally:
        interrupted.store.close()

    resumed = experiment(tmp_path, mode="resume")
    try:
        assert resumed.scan_id == interrupted.scan_id
        assert resumed.reply_checkpoint_edge == active_edge
        assert resumed.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
        assert resumed.store.checkpoint(MEDIA_ID, active_edge, "parent-1") == completed_parent_checkpoint

        async def no_root_recrawl(_args):
            pytest.fail("refresh resume must not recrawl its completed root branch")

        asyncio.run(resumed._collect_legacy_graphql(FakePage(no_root_recrawl)))
        before_duplicates = resumed.duplicates
        seen = []

        async def finish_remaining(args):
            parent, after = args["variables"]["parent_comment_id"], args["variables"]["after"]
            seen.append((parent, after, args["operation"]))
            if parent == "parent-2" and after == "p2-cursor":
                return {"status": 200, "json": True, "payload": child_payload(parent, ("new-p2-last",))}
            if parent == "parent-3" and after is None:
                return {"status": 200, "json": True, "payload": child_payload(parent, ("new-p3",))}
            pytest.fail(f"unexpected resume request {parent=} {after=}")

        asyncio.run(resumed._collect_replies(FakePage(finish_remaining)))
        report = resumed.report("natural_exhaustion")
        resumed.store.finish_run(resumed.run_id, report)
        assert resumed.store.latest_successful_run(MEDIA_ID, mode="refresh") is not None
        assert seen == [
            ("parent-2", "p2-cursor", "PolarisPostCommentsChildrenPaginationtQuery"),
            ("parent-3", None, "PolarisPostChildCommentsQuery"),
        ]
        assert resumed.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
        assert resumed.store.checkpoint(MEDIA_ID, active_edge, "parent-1") == completed_parent_checkpoint
        assert resumed.store.checkpoint(MEDIA_ID, active_edge, "parent-2")["complete"] is True
        assert resumed.store.checkpoint(MEDIA_ID, active_edge, "parent-3")["complete"] is True
        assert resumed.duplicates == before_duplicates
        assert report["replies_protocol_complete"] is True
        assert report["collection_status"]["COLLECTION_PARTIAL"] is False
        assert report["last_refresh_at"] is not None
        assert len(resumed.store.all_comments(MEDIA_ID)) == 10
        assert len({row["id"] for row in resumed.store.all_comments(MEDIA_ID)}) == 10
        assert resumed.store.checkpoint(MEDIA_ID, "replies", "parent-1")["complete"] is True
        assert len(report["reported_count_history"]) == 2
    finally:
        resumed.store.close()


def test_unexpected_html_refresh_is_not_terminal_and_can_resume(tmp_path, monkeypatch):
    async def no_sleep(_seconds):
        return None
    monkeypatch.setattr(browser.asyncio, "sleep", no_sleep)
    seed_refresh_baseline(tmp_path, parent_ids=(PARENT_ID,))
    interrupted = experiment(tmp_path, mode="refresh")
    try:
        async def root_page(_args):
            return {"status": 200, "json": True, "payload": legacy_roots_payload(
                [(PARENT_ID, 1, ())], reported_count=2,
            )}

        asyncio.run(interrupted._collect_legacy_graphql(FakePage(root_page)))
        root_checkpoint = interrupted.store.checkpoint(MEDIA_ID, "comments")
        html_signals = {
            "doctype": True, "html_element": True, "instagram_title": False,
            "app_assets": True, "splash_screen": False,
            "login_marker": False, "challenge_marker": False,
        }

        async def html_response(_args):
            return {"status": 200, "json": False, "payload": None,
                    "contentType": "text/html", "bytes": 16384,
                    "htmlSignals": html_signals, "boundary": None,
                    "responsePath": "/api/graphql", "redirected": False}

        asyncio.run(interrupted._collect_replies(FakePage(html_response)))
        edge = interrupted.reply_checkpoint_edge
        checkpoint = interrupted.store.checkpoint(MEDIA_ID, edge, PARENT_ID)
        report = interrupted.report("unexpected_html")
        interrupted.store.finish_run(interrupted.run_id, report)
        assert checkpoint["complete"] is False
        assert checkpoint["termination_reason"] == "unexpected_html"
        assert checkpoint["pages"] == 0
        assert report["reply_request_observations"][-1]["retrieval_outcome"] == "unexpected_html"
        assert report["reply_request_observations"][-1]["response_evidence"] == {}
        assert report["collection_status"]["COLLECTION_PARTIAL"] is True
        assert report["collection_status"]["OPERATIONAL_FAILURE"] is True
        assert report["collection_status"]["REPLIES_PROTOCOL_COMPLETE"] is False
    finally:
        interrupted.store.close()

    resumed = experiment(tmp_path, mode="resume")
    try:
        assert resumed.reply_checkpoint_edge == edge
        assert resumed.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint

        async def no_root_recrawl(_args):
            pytest.fail("HTML child recovery must not restart completed root collection")

        asyncio.run(resumed._collect_legacy_graphql(FakePage(no_root_recrawl)))
        seen = []

        async def valid_reply(args):
            seen.append((args["variables"]["after"], args["operation"]))
            return {"status": 200, "json": True, "payload": child_payload(
                PARENT_ID, ("recovered-reply",),
            )}

        asyncio.run(resumed._collect_replies(FakePage(valid_reply)))
        report = resumed.report("natural_exhaustion")
        assert seen == [(None, "PolarisPostChildCommentsQuery")]
        assert resumed.store.checkpoint(MEDIA_ID, edge, PARENT_ID)["complete"] is True
        assert resumed.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
        assert [row["id"] for row in resumed.store.comments(MEDIA_ID, PARENT_ID)] == [
            f"old-{PARENT_ID}", "recovered-reply",
        ]
        assert [row["retrieval_outcome"] for row in report["reply_request_observations"][-2:]] == [
            "unexpected_html", "valid_graphql_json",
        ]
        assert report["replies_protocol_complete"] is True
    finally:
        resumed.store.close()


def test_response_metadata_records_only_fields_observed_by_root_operation(tmp_path):
    run = experiment(tmp_path)
    try:
        run.reported_comment_count = 1574
        run._save_response_metadata()
        stored = run.store.get_post(media_id=MEDIA_ID)["post"]
        assert stored["comment_count"] == 1574
        assert stored["comment_count_source"] == "legacy_graphql.edge_media_to_parent_comment.count"
        assert "caption" not in stored
        report = run.report("partial")
        assert "comment_count" in report["post_metadata_fields_observed"]
        assert "stable_media_id" not in report["post_metadata_fields_observed"]
        assert report["root_checkpoint_edge"] == "comments"
        assert report["reported_count_history"][-1]["reported_comment_count"] == 1574
        assert [row["run_id"] for row in report["reported_count_history"]].count(run.run_id) == 1
    finally:
        run.store.close()


def test_reported_count_history_keeps_each_response_timestamp(tmp_path):
    run = experiment(tmp_path)
    try:
        run.reported_comment_count = 1574
        run._save_response_metadata("2026-10-02T04:00:01.000Z")
        run.reported_comment_count = 1576
        run._save_response_metadata("2026-10-02T04:00:02.000Z")

        observations = [
            row for row in run.store.reported_count_history(MEDIA_ID)
            if row["run_id"] == run.run_id
        ]
        assert [(row["reported_comment_count"], row["observed_at"]) for row in observations] == [
            (1574, "2026-10-02T04:00:01.000Z"),
            (1576, "2026-10-02T04:00:02.000Z"),
        ]
    finally:
        run.store.close()


def test_reply_only_run_does_not_add_report_proxy_count_observation(tmp_path):
    run = experiment(tmp_path)
    try:
        run.store.finish_run(run.run_id, {
            "reported_comment_count": 1574,
            "collected_at": "2026-10-02T04:00:03Z",
            "root_protocol_complete": True,
            "performance": {"root_requests_this_run": 0},
        })

        history = run.store.reported_count_history(MEDIA_ID)

        assert all(row["run_id"] != run.run_id for row in history)
    finally:
        run.store.close()


def test_page_handler_runs_qualified_reply_path_after_root_completion(tmp_path, monkeypatch):
    run = experiment(tmp_path)
    save_root(run, root_record(reply_count=1))
    calls = []

    async def collect_replies(page):
        calls.append(page)

    monkeypatch.setattr(run, "_collect_replies", collect_replies)

    class Page(FakePage):
        url = f"https://www.instagram.com/p/{SHORTCODE}/"

        async def title(self):
            return "Instagram"

        def locator(self, _selector):
            class Body:
                async def inner_text(self, **_kwargs):
                    return ""
            return Body()

    class Context:
        page = Page(lambda _args: pytest.fail("completed root traversal should not request another page"))

    try:
        asyncio.run(run.handle_page(Context()))
        assert calls == [Context.page]
    finally:
        run.store.close()


def test_count_reconciliation_and_protocol_completeness_are_separate(tmp_path):
    run = experiment(tmp_path)
    try:
        save_root(run, root_record(reply_count=2))
        save_reply_page(run, [reply_record("reply-1")])
        run.reported_comment_count = 2
        report = run.report("natural_exhaustion")
        assert report["reported_count_consistent"] is True
        assert report["combined_unique_count"] == 2
        assert report["unresolved_count_difference"] == 0
        assert report["root_protocol_complete"] is True
        assert report["replies_protocol_complete"] is True
        assert report["reply_reported_counts_consistent"] is False
        assert report["reply_branches"][0]["status"] == "COMPLETE"
        assert report["complete_parent_branches"] == 1
        assert report["reported_count_semantics_validated"] is False
        assert report["collection_partial"] is False
        assert report["collection_status"]["COUNT_CONSISTENT"] is True
        assert report["collection_status"]["SOURCE_COVERAGE_UNKNOWN"] is True
        assert report["qualification_levels"]["REPLY_COLLECTION_QUALIFIED"] is True
        assert report["qualification_levels"]["CHILD_OPERATION_LIVE_QUALIFIED"] is False
        output = tmp_path / SHORTCODE
        assert (output / "post.json").is_file()
        assert (output / "comments.jsonl").read_text(encoding="utf-8").count("\n") == 1
        assert (output / "replies.jsonl").read_text(encoding="utf-8").count("\n") == 1
        tree = json.loads((output / "comment_tree.json").read_text(encoding="utf-8"))
        assert tree["roots"][0]["replies"][0]["id"] == "reply-1"
        assert (output / "collection_report.json").is_file()
    finally:
        run.store.close()


def test_unattempted_reply_branches_report_partial(tmp_path):
    run = experiment(tmp_path)
    try:
        run.store.save_page(
            media_id=MEDIA_ID, edge="comments", parent_id=None,
            records=[root_record(PARENT_ID, 2), root_record("parent-2", 1)],
            run_id=run.run_id, scan_id=run.scan_id, next_cursor=None,
            has_next=False, current_cursor=None,
        )
        run.reported_comment_count = 4
        report = run.report("natural_exhaustion")
        assert report["reply_parents_advertising_replies"] == 2
        assert report["reply_parents_attempted"] == 0
        assert report["roots_with_incomplete_reply_branches"] == 2
        assert report["unattempted_parent_branches"] == 2
        assert [branch["status"] for branch in report["reply_branches"]] == [
            "NOT_ATTEMPTED", "NOT_ATTEMPTED",
        ]
        assert report["replies_protocol_complete"] is False
        assert report["reported_count_consistent"] is False
        assert report["unresolved_count_difference"] == 2
        assert report["collection_partial"] is True
    finally:
        run.store.close()


def test_global_budget_batches_parents_and_resume_skips_completed_and_root_pages(tmp_path, monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(browser.asyncio, "sleep", no_sleep)
    config = BrowserExperimentConfig(
        target_url=f"https://www.instagram.com/p/{SHORTCODE}/",
        output_root=tmp_path,
        max_http_requests=2,
    )
    run = BrowserCommentExperiment(config)
    root_ids = [PARENT_ID, "parent-2", "parent-3"]
    try:
        run._begin_store(MEDIA_ID)
        run.store.save_page(
            media_id=MEDIA_ID, edge="comments", parent_id=None,
            records=[root_record(parent, 1) for parent in root_ids],
            run_id=run.run_id, scan_id=run.scan_id, next_cursor=None,
            has_next=False, current_cursor=None,
        )
        root_checkpoint = run.store.checkpoint(MEDIA_ID, "comments")
        sequence = []
        active = 0
        max_active = 0

        async def fixture_page(args):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            parent = args["variables"]["parent_comment_id"]
            sequence.append(parent)
            try:
                return {
                    "status": 200, "contentType": "application/json", "json": True,
                    "payload": child_payload(parent_id=parent, ids=(f"reply-{parent}",)),
                }
            finally:
                active -= 1

        asyncio.run(run._collect_replies(FakePage(fixture_page)))
        first_report = run.report("request_budget")
        assert sequence == root_ids[:2]
        assert max_active == 1
        assert first_report["complete_parent_branches"] == 2
        assert first_report["unattempted_parent_branches"] == 1
        assert first_report["reply_stop_reason"] == "request_budget"
        assert first_report["collection_status"]["TRANSPORT_SUCCESS"] is True
        assert first_report["collection_status"]["OPERATIONAL_FAILURE"] is False
        assert run.store.checkpoint(MEDIA_ID, "replies", "parent-3") is None
        assert run.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
        assert len(run.store.all_comments(MEDIA_ID)) == 5
    finally:
        run.store.close()

    resumed = BrowserCommentExperiment(replace(config, max_http_requests=1))
    try:
        resumed._begin_store(MEDIA_ID)

        async def no_root_recrawl(_args):
            pytest.fail("completed root cursor must not be requested on reply resume")

        asyncio.run(resumed._collect_legacy_graphql(FakePage(no_root_recrawl)))
        assert resumed.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
        resumed_sequence = []

        async def last_parent(args):
            parent = args["variables"]["parent_comment_id"]
            resumed_sequence.append(parent)
            return {
                "status": 200, "contentType": "application/json", "json": True,
                "payload": child_payload(parent_id=parent, ids=(f"reply-{parent}",)),
            }

        asyncio.run(resumed._collect_replies(FakePage(last_parent)))
        final_report = resumed.report("natural_exhaustion")
        assert resumed_sequence == ["parent-3"]
        assert final_report["replies_protocol_complete"] is True
        assert final_report["complete_parent_branches"] == 3
        assert final_report["duplicate_records"] == 0
        assert final_report["http_requests_this_run"] == 1
        assert final_report["reply_parents_attempted_this_run"] == 1
        assert final_report["collection_status"]["TRANSPORT_SUCCESS"] is True
        assert len(resumed.store.all_comments(MEDIA_ID)) == 6
        assert resumed.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
    finally:
        resumed.store.close()


def test_global_budget_covers_root_and_reply_requests(tmp_path, monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(browser.asyncio, "sleep", no_sleep)
    run = BrowserCommentExperiment(BrowserExperimentConfig(
        target_url=f"https://www.instagram.com/p/{SHORTCODE}/",
        output_root=tmp_path,
        max_http_requests=1,
    ))
    run._begin_store(MEDIA_ID)
    try:
        async def root_page(_args):
            return {
                "status": 200, "contentType": "application/json", "json": True,
                "payload": legacy_payload(PARENT_ID, has_next=False, cursor=None, reply_count=1),
            }

        asyncio.run(run._collect_legacy_graphql(FakePage(root_page)))

        async def unexpected_reply(_args):
            pytest.fail("root request consumed the global budget")

        asyncio.run(run._collect_replies(FakePage(unexpected_reply)))
        report = run.report("request_budget")
        assert run.http_request_attempts == 1
        assert run.root_request_attempts_this_run == 1
        assert run.reply_request_attempts_this_run == 0
        assert report["root_protocol_complete"] is True
        assert report["replies_protocol_complete"] is False
        assert report["reply_stop_reason"] == "request_budget"
        assert report["collection_status"]["TRANSPORT_SUCCESS"] is True
        assert report["collection_status"]["OPERATIONAL_FAILURE"] is False
    finally:
        run.store.close()


def test_global_budget_saves_reply_cursor_and_resume_uses_only_continuation(tmp_path, monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(browser.asyncio, "sleep", no_sleep)
    config = BrowserExperimentConfig(
        target_url=f"https://www.instagram.com/p/{SHORTCODE}/",
        output_root=tmp_path,
        max_http_requests=1,
    )
    run = BrowserCommentExperiment(config)
    run._begin_store(MEDIA_ID)
    save_root(run, root_record(reply_count=2))
    root_checkpoint = run.store.checkpoint(MEDIA_ID, "comments")
    try:
        async def first_page(args):
            assert args["variables"]["after"] is None
            return {
                "status": 200, "contentType": "application/json", "json": True,
                "payload": child_payload(ids=("reply-1",), has_next=True, cursor="reply-cursor-1"),
            }

        asyncio.run(run._collect_replies(FakePage(first_page)))
        checkpoint = run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)
        assert checkpoint == {
            "after_cursor": "reply-cursor-1", "complete": False,
            "pages": 1, "last_successful_page": 1, "termination_reason": "request_budget",
        }
        assert run.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
        assert [row["id"] for row in run.store.comments(MEDIA_ID, parent_id=PARENT_ID)] == ["reply-1"]
    finally:
        run.store.close()

    resumed = BrowserCommentExperiment(config)
    resumed._begin_store(MEDIA_ID)
    try:
        async def no_root_replay(_args):
            pytest.fail("reply resume must preserve and skip the completed root checkpoint")

        asyncio.run(resumed._collect_legacy_graphql(FakePage(no_root_replay)))
        assert resumed.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
        cursors = []

        async def continuation(args):
            cursors.append(args["variables"]["after"])
            assert args["operation"] == "PolarisPostCommentsChildrenPaginationtQuery"
            return {
                "status": 200, "contentType": "application/json", "json": True,
                "payload": child_payload(ids=("reply-2",)),
            }

        asyncio.run(resumed._collect_replies(FakePage(continuation)))
        assert cursors == ["reply-cursor-1"]
        assert resumed.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)["complete"] is True
        assert len(resumed.store.comments(MEDIA_ID, parent_id=PARENT_ID)) == 2
        assert resumed.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
    finally:
        resumed.store.close()


def test_interruption_after_empty_terminal_page_keeps_branch_complete(tmp_path, monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(browser.asyncio, "sleep", no_sleep)
    run = experiment(tmp_path)
    next_parent = "parent-2"
    try:
        run.store.save_page(
            media_id=MEDIA_ID, edge="comments", parent_id=None,
            records=[root_record(PARENT_ID, 1), root_record(next_parent, 1)],
            run_id=run.run_id, scan_id=run.scan_id, next_cursor=None,
            has_next=False, current_cursor=None,
        )
        root_checkpoint = run.store.checkpoint(MEDIA_ID, "comments")

        async def interrupted_after_empty_terminal(args):
            parent = args["variables"]["parent_comment_id"]
            if parent == PARENT_ID:
                return {
                    "status": 200, "contentType": "application/json", "json": True,
                    "payload": child_payload(ids=(), has_next=False),
                }
            assert parent == next_parent
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(run._collect_replies(FakePage(interrupted_after_empty_terminal)))
        empty_terminal = run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)
        assert empty_terminal["complete"] is True
        assert empty_terminal["pages"] == 1
        assert empty_terminal["termination_reason"] == "natural_exhaustion"
        assert run.store.comments(MEDIA_ID, parent_id=PARENT_ID) == []
        assert run.store.checkpoint(MEDIA_ID, "replies", next_parent) is None
        assert run.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint

        resumed_requests = []

        async def finish_next_parent(args):
            parent = args["variables"]["parent_comment_id"]
            resumed_requests.append(parent)
            assert parent == next_parent
            return {
                "status": 200, "contentType": "application/json", "json": True,
                "payload": child_payload(parent_id=parent, ids=("reply-next",)),
            }

        asyncio.run(run._collect_replies(FakePage(finish_next_parent)))
        report = run.report("resumed_after_empty_terminal")
        assert resumed_requests == [next_parent]
        assert report["replies_protocol_complete"] is True
        assert report["complete_parent_branches"] == 2
        assert report["duplicate_records"] == 0
        assert run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID) == empty_terminal
        assert run.store.checkpoint(MEDIA_ID, "comments") == root_checkpoint
    finally:
        run.store.close()


def test_cursor_exhaustion_and_count_discrepancy_are_separate_statuses(tmp_path):
    run = experiment(tmp_path)
    try:
        save_root(run, root_record(reply_count=1))
        save_reply_page(run, [reply_record("reply-1")])
        run.reported_count_semantics_validated = False
        run.reported_comment_count = 99
        report = run.report("natural_exhaustion")
        status = report["collection_status"]
        assert status["ROOT_PROTOCOL_COMPLETE"] is True
        assert status["REPLIES_PROTOCOL_COMPLETE"] is True
        assert status["COUNT_CONSISTENT"] is False
        assert status["SOURCE_COVERAGE_UNKNOWN"] is True
        assert status["COLLECTION_PARTIAL"] is False
        assert status["OPERATIONAL_FAILURE"] is False
        assert report["unresolved_count_difference"] == 97
    finally:
        run.store.close()


def test_shortcode_decoding_returns_string_identifiers():
    assert decode_shortcode("B") == "1"
    assert decode_shortcode("BA") == "64"
    with pytest.raises(ValueError):
        decode_shortcode("not/a/shortcode")


def test_qualified_legacy_state_migrates_and_resume_skips_completed_roots(tmp_path):
    legacy_dir = tmp_path / "legacy-graphql-qualification" / "legacy-graphql" / SHORTCODE
    legacy_dir.mkdir(parents=True)
    legacy = StateStore(legacy_dir / "state.sqlite")
    legacy.save_post(
        media_id=MEDIA_ID, shortcode=SHORTCODE,
        post={"shortcode": SHORTCODE}, author={"id": None},
    )
    legacy.begin_run("legacy-run", "legacy-scan", MEDIA_ID, "qualification")
    legacy.save_page(
        media_id=MEDIA_ID, edge="comments", parent_id=None, records=[root_record(reply_count=0)],
        run_id="legacy-run", scan_id="legacy-scan", next_cursor=None,
        has_next=False, current_cursor=None,
    )
    legacy.finish_run("legacy-run", {"reported_comment_count": 1})
    legacy.close()
    (legacy_dir / "post.json").write_text('{"shortcode":"post-1"}\n', encoding="utf-8")

    resumed = experiment(tmp_path)

    async def should_not_request(_args):
        pytest.fail("completed root traversal must not make a request")

    page = FakePage(should_not_request)
    try:
        asyncio.run(resumed._collect_legacy_graphql(page))
        assert resumed.output_dir == tmp_path / SHORTCODE
        assert resumed.store.checkpoint(MEDIA_ID, "comments")["termination_reason"] == "natural_exhaustion"
        assert len(resumed.store.comments(MEDIA_ID, parent_id=None)) == 1
        assert (resumed.output_dir / "post.json").is_file()
        assert (legacy_dir / "state.sqlite").is_file()
        assert resumed.scan_id == "legacy-scan"
    finally:
        resumed.store.close()


def test_unexpected_child_response_stops_remaining_branches(tmp_path):
    run = experiment(tmp_path)
    try:
        roots = [root_record(reply_count=1), root_record("parent-2", reply_count=1)]
        run.store.save_page(
            media_id=MEDIA_ID, edge="comments", parent_id=None, records=roots,
            run_id=run.run_id, scan_id=run.scan_id, next_cursor=None,
            has_next=False, current_cursor=None,
        )
        requests = []

        async def non_json(_args):
            requests.append(1)
            return {"status": 200, "json": False, "payload": None, "bytes": 650_000,
                    "contentType": "text/html", "boundary": None}

        asyncio.run(run._collect_replies(FakePage(non_json)))
        assert len(requests) == 1
        assert run.reply_stop_reason == "unexpected_html"
        assert run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID)["termination_reason"] == "unexpected_html"
        assert run.reply_observations[-1]["retrieval_outcome"] == "unexpected_html"
        assert run.store.checkpoint(MEDIA_ID, "replies", "parent-2") is None
    finally:
        run.store.close()


def test_child_response_classification_uses_safe_document_signals():
    from instagram_collector.crawlee_browser import _classify_child_response

    shell = {
        "doctype": True,
        "html_element": True,
        "instagram_title": True,
        "app_assets": True,
    }
    assert _classify_child_response("text/html; charset=utf-8", is_json=False, html_signals=shell) == "normal_application_shell"
    shell.pop("instagram_title")
    assert _classify_child_response("text/html", is_json=False, html_signals=shell) == "application_shell_like"
    assert _classify_child_response("text/html", is_json=False, html_signals={"html_element": True}) == "html_document"
    assert _classify_child_response("text/html", is_json=False, html_signals={"login_marker": True}) == "authentication_or_access_document"
    assert _classify_child_response("application/json", is_json=True) == "json"


def test_child_retrieval_outcomes_keep_html_auth_and_schema_distinct():
    from instagram_collector.crawlee_browser import _child_failure_outcome

    assert _child_failure_outcome({
        "status": 200, "json": False, "payload": None, "contentType": "text/html",
        "htmlSignals": {"html_element": True, "login_marker": False, "challenge_marker": False},
    }) == "unexpected_html"
    assert _child_failure_outcome({
        "status": 401, "json": False, "payload": None, "boundary": "authentication_required",
    }) == "authentication_required"
    assert _child_failure_outcome({
        "status": 200, "json": False, "payload": None, "boundary": "access_restriction",
    }) == "access_restriction"
    assert _child_failure_outcome({
        "status": 200, "json": True, "payload": [], "contentType": "application/json",
    }) == "unexpected_schema"
    assert _child_failure_outcome({
        "status": None, "json": False, "payload": None, "boundary": "network_error",
    }) == "network_failure"


def test_reply_parent_filter_makes_one_branch_experiment_bounded(tmp_path):
    run = BrowserCommentExperiment(BrowserExperimentConfig(
        target_url=f"https://www.instagram.com/p/{SHORTCODE}/",
        output_root=tmp_path,
        reply_parent_id="parent-2",
        max_reply_pages=1,
    ))
    try:
        run._begin_store(MEDIA_ID)
        run.media_id = MEDIA_ID
        run.store.save_page(
            media_id=MEDIA_ID, edge="comments", parent_id=None,
            records=[root_record(PARENT_ID, reply_count=1), root_record("parent-2", reply_count=1), root_record("parent-3", reply_count=1)],
            run_id=run.run_id, scan_id=run.scan_id, next_cursor=None,
            has_next=False, current_cursor=None,
        )
        requests = []

        async def reply_page(args):
            requests.append(args["variables"]["parent_comment_id"])
            return {
                "status": 200, "contentType": "application/json", "json": True,
                "payload": {"data": {"xdt_api__v1__media__media_id__comments__parent_comment_id__child_comments__connection": {
                    "edges": [], "page_info": {"has_next_page": False, "end_cursor": None},
                }}},
            }

        asyncio.run(run._collect_replies(FakePage(reply_page)))
        assert requests == ["parent-2"]
        assert run.store.checkpoint(MEDIA_ID, "replies", "parent-2")["complete"] is True
        assert run.store.checkpoint(MEDIA_ID, "replies", PARENT_ID) is None
        report = run.report("bounded_parent_filter")
        assert report["complete_parent_branches"] == 1
        assert report["unattempted_parent_branches"] == 2
        assert report["replies_protocol_complete"] is False
        assert report["collection_partial"] is True
    finally:
        run.store.close()
