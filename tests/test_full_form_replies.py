"""Fully offline tests: no Instagram requests or credentials are used."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from instagram_collector import crawlee_browser as browser
from instagram_collector.collector import normalize_comment
from instagram_collector.crawlee_browser import BrowserCommentExperiment, BrowserExperimentConfig, _CHILD_CONNECTION
from instagram_collector.full_form_replies import (
    CONTINUATION, INITIAL, REQUIRED_FORM_FIELDS, FullFormReplyTransport,
)


def write_config(path: Path) -> Path:
    entries = {"CSRF_TOKEN": "fake-csrf-for-offline-test"}
    for i, operation in enumerate((INITIAL, CONTINUATION), start=1):
        variables = {
            "after": None if i == 1 else "template-cursor",
            "before": None,
            "first": None if i == 1 else 5,
            "is_chronological": None,
            "last": None,
            "media_id": "media-1", "parent_comment_id": "parent-1",
            "__relay_internal__pv__PolarisIsLoggedInrelayprovider": True,
        }
        form = {k: "fixture-only" for k in REQUIRED_FORM_FIELDS}
        form.update({
            "doc_id": operation[1], "fb_api_req_friendly_name": operation[0],
            "lsd": "fixture-lsd", "variables": json.dumps(variables),
        })
        entries[f"FORM_DATA_JSON_{i}"] = json.dumps(form)
        entries[f"COOKIE_HEADER_{i}"] = "sessionid=fixture; csrftoken=fake-csrf-for-offline-test"
    path.write_text("\n".join(f"{k}={v}" for k, v in entries.items()), encoding="utf-8")
    return path


def test_full_form_transport_keeps_complete_form_and_links_cursor(tmp_path):
    transport = FullFormReplyTransport(write_config(tmp_path / "private.env"))
    first = transport.prepare("media-1", "parent-1", None, referer="https://www.instagram.com/p/post-1/")
    second = transport.prepare("media-1", "parent-1", "cursor-from-page-one", referer="https://www.instagram.com/p/post-1/")
    assert (first.operation, first.doc_id) == INITIAL
    assert (second.operation, second.doc_id) == CONTINUATION
    assert len(first.form) == len(REQUIRED_FORM_FIELDS)
    assert all(k in first.form for k in REQUIRED_FORM_FIELDS)
    assert first.form["fb_dtsg"] == "fixture-only"
    assert json.loads(first.form["variables"])["after"] is None
    assert json.loads(second.form["variables"])["after"] == "cursor-from-page-one"
    assert second.headers["x-fb-friendly-name"] == CONTINUATION[0]
    with pytest.raises(ValueError, match="scoped"):
        transport.prepare("other-media", "parent-1", None, referer="https://www.instagram.com/p/post-1/")
    transport.close()


def test_full_form_requires_explicit_opt_in_for_retarget(tmp_path):
    transport = FullFormReplyTransport(write_config(tmp_path / "private.env"), allow_retarget=True)
    prepared = transport.prepare("other-media", "other-parent", "real-cursor", referer="https://www.instagram.com/p/another/")
    assert json.loads(prepared.form["variables"])["parent_comment_id"] == "other-parent"
    assert json.loads(prepared.form["variables"])["media_id"] == "other-media"
    assert prepared.headers["referer"] == "https://www.instagram.com/p/another/"


def test_full_form_rejects_missing_session_parameters(tmp_path):
    path = write_config(tmp_path / "private.env")
    lines = path.read_text().splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith("FORM_DATA_JSON_1="))
    form = json.loads(lines[index].split("=", 1)[1])
    form.pop("fb_dtsg")
    lines[index] = "FORM_DATA_JSON_1=" + json.dumps(form)
    path.write_text("\n".join(lines), encoding="utf-8")
    with pytest.raises(ValueError, match="template 1"):
        FullFormReplyTransport(path)


def test_full_form_fetch_classifies_success_html_and_rate_limit(tmp_path, monkeypatch):
    transport = FullFormReplyTransport(write_config(tmp_path / "private.env"))
    calls = []
    class FakeResponse:
        def __init__(self, status, mime, data, location=None):
            self.status_code = status
            self.headers = {"Content-Type": mime}
            if location:
                self.headers["Location"] = location
            self.data = data
            self.url = "https://www.instagram.com/api/graphql"
            self.is_redirect = location is not None
            self.is_permanent_redirect = False
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def iter_content(self, chunk_size): yield self.data
    class FakeSession:
        def __init__(self): self.replies = [
            FakeResponse(200, "text/javascript", b'{"data":{"ok":true}}'),
            FakeResponse(200, "text/html", b'<!doctype html><html><title>Instagram</title>'),
            FakeResponse(429, "text/plain", b''),
            FakeResponse(302, "text/html", b'', "/accounts/login/"),
            FakeResponse(302, "text/html", b'', "/challenge/"),
        ]
        def post(self, url, *, headers, data, timeout, allow_redirects, stream):
            calls.append((url, data.copy(), headers["x-fb-friendly-name"]))
            assert allow_redirects is False and stream is True
            return self.replies.pop(0)
        def close(self): pass
    import requests
    monkeypatch.setattr(requests, "Session", FakeSession)
    successes = [transport.fetch("media-1", "parent-1", None, referer="https://www.instagram.com/p/a/") for _ in range(5)]
    assert successes[0]["json"] is True and successes[0]["status"] == 200
    assert successes[1]["json"] is False and successes[1]["htmlSignals"]["doctype"]
    assert successes[2]["boundary"] == "rate_limited"
    assert successes[1]["boundary"] is None
    assert successes[3]["boundary"] == "authentication_required"
    assert successes[3]["responseEvidence"]["loginPath"] is True
    assert successes[4]["boundary"] == "access_restriction"
    assert successes[4]["responseEvidence"]["challengePath"] is True
    assert successes[0]["timingsMs"]["session_initialization"] >= 0
    assert successes[1]["timingsMs"]["session_initialization"] == 0
    assert len(calls) == 5
    transport.close()


def test_integration_persists_linked_pages_and_does_not_replay_roots(tmp_path, monkeypatch):
    async def no_sleep(_): pass
    monkeypatch.setattr(browser.asyncio, "sleep", no_sleep)
    run = BrowserCommentExperiment(BrowserExperimentConfig(
        target_url="https://www.instagram.com/p/post-1/", output_root=tmp_path,
        reply_parent_id="parent-1", max_reply_pages=3,
        reply_transport="full-form", reply_form_env=tmp_path / "unused.env",
    ))
    try:
        run._begin_store("shortcode:post-1")
        root = normalize_comment({"id": "parent-1", "reply_count": 30, "text": "root"},
                                 "shortcode:post-1", None, source="offline-test")
        run.store.save_page(
            media_id="shortcode:post-1", edge="comments", parent_id=None, records=[root],
            run_id=run.run_id, scan_id=run.scan_id, next_cursor=None,
            has_next=False, current_cursor=None,
        )
        root_before = run.store.checkpoint("shortcode:post-1", "comments")
        called = []
        class FakeTransport:
            def fetch(self, media_id, parent_id, cursor, *, referer):
                called.append((media_id, parent_id, cursor))
                which = len(called)
                edges = [{"node": {
                    "pk": f"reply-{which}-{i}", "parent_comment_id": parent_id,
                    "text": "test", "created_at": 1730000000, "user": {"pk": "u-1", "username": "u"},
                    "comment_like_count": 0,
                }} for i in range(15 if which < 3 else 0)]
                return {"status": 200, "contentType": "text/javascript", "json": True,
                        "payload": {"data": {_CHILD_CONNECTION: {
                            "edges": edges,
                            "page_info": {"has_next_page": which < 3,
                                          "end_cursor": f"cursor-{which}" if which < 3 else None},
                        }}}}
        run.full_form_transport = FakeTransport()
        asyncio.run(run._collect_replies(None))
        assert len(called) == 3
        assert [item[2] for item in called] == [None, "cursor-1", "cursor-2"]
        assert len(run.store.comments("shortcode:post-1", parent_id="parent-1")) == 30
        assert run.store.checkpoint("shortcode:post-1", "replies", "parent-1")["complete"] is True
        assert run.store.checkpoint("shortcode:post-1", "comments") == root_before
        assert all(v.get("transport") == "full-form" for v in run.reply_observations)
    finally:
        run.store.close()
