from __future__ import annotations

import asyncio
import argparse
from dataclasses import fields
from datetime import timedelta

import pytest

from instagram_collector import cli, crawlee_browser as browser
from instagram_collector.crawlee_browser import (
    BrowserCommentExperiment,
    BrowserExperimentConfig,
    _legacy_page,
)


def test_collector_has_one_live_entry_command():
    parser = cli._parser()
    action = next(item for item in parser._actions if isinstance(item, argparse._SubParsersAction))

    assert set(action.choices) == {"collect", "status", "inspect-response", "probe-reply"}
    assert "--legacy-graphql" not in parser.format_help()


def test_collection_modes_are_explicit_and_mutually_exclusive():
    parser = cli._parser()
    url = "https://www.instagram.com/p/post-1/"
    assert parser.parse_args(["collect", url]).run_mode == "resume"
    assert parser.parse_args(["collect", url, "--reply-parent-id", "parent-1"]).reply_parent_id == "parent-1"
    assert parser.parse_args(["collect", url, "--max-http-requests", "9"]).max_http_requests == 9
    assert parser.parse_args(["collect", url, "--refresh"]).run_mode == "refresh"
    assert parser.parse_args(["collect", url, "--fresh"]).run_mode == "fresh"
    with pytest.raises(SystemExit):
        parser.parse_args(["collect", url, "--fresh", "--refresh"])


def test_collection_config_has_no_alternate_mode_or_persistent_profile():
    names = {field.name for field in fields(BrowserExperimentConfig)}

    assert names == {
        "target_url", "output_root", "headless", "max_root_pages", "max_reply_pages", "max_http_requests", "reply_parent_id", "duration_seconds", "run_mode", "reply_transport", "reply_form_env", "reply_allow_retarget",
    }


def test_cli_exit_code_2_still_marks_count_mismatch_and_partial_runs(tmp_path, monkeypatch, capsys):
    args = cli._parser().parse_args(["collect", "https://www.instagram.com/p/post-1/", "--output", str(tmp_path)])
    report = {
        "collection_partial": False,
        "reported_count_consistent": False,
        "reply_reported_counts_consistent": True,
        "reported_count_semantics_validated": False,
    }
    monkeypatch.setattr(browser, "run_browser_experiment", lambda _config: report)
    assert cli._collect(args) == 2
    assert '"reported_count_consistent": false' in capsys.readouterr().out

    report.update(
        collection_partial=False,
        reported_count_consistent=True,
        reply_reported_counts_consistent=True,
        reported_count_semantics_validated=True,
    )
    assert cli._collect(args) == 0


def test_legacy_graphql_page_normalizes_comment_and_cursor(tmp_path):
    media_id, reported, comments, embedded, has_next, cursor = _legacy_page(
        {
            "data": {
                "shortcode_media": {
                    "shortcode": "post-1",
                    "edge_media_to_parent_comment": {
                        "count": 2,
                        "edges": [{"node": {
                            "id": "comment-1",
                            "owner": {"id": "user-1", "username": "reader"},
                            "text": "hello",
                            "created_at": 1730000000,
                            "edge_threaded_comments": {"count": 1},
                        }}],
                        "page_info": {"has_next_page": True, "end_cursor": "opaque"},
                    },
                }
            }
        },
        "post-1",
    )

    assert (media_id, reported, has_next, cursor) == ("shortcode:post-1", 2, True, "opaque")
    assert embedded == []
    assert comments[0]["id"] == "comment-1"
    assert comments[0]["username"] == "reader"
    assert comments[0]["reported_reply_count"] == 1

    experiment = BrowserCommentExperiment(
        BrowserExperimentConfig(
            target_url="https://www.instagram.com/p/post-1/",
            output_root=tmp_path,
        )
    )
    try:
        assert experiment.output_dir == tmp_path / "post-1"
        experiment.page_title = "Instagram"
        experiment._begin_store("shortcode:post-1")
        report = experiment.report("bounded_collection_finished")
        assert report["collection_method"] == "legacy_graphql_get"
        assert report["browser_backend"] == "PlaywrightBrowserPlugin via Crawlee PlaywrightCrawler"
    finally:
        experiment.store.close()


def test_crawlee_plugin_uses_stock_playwright_without_fingerprint_generator():
    pytest.importorskip("crawlee")
    from crawlee.browsers import PlaywrightBrowserPlugin

    plugin = PlaywrightBrowserPlugin(
        browser_launch_options={"headless": True},
        max_open_pages_per_browser=1,
    )
    assert plugin.max_open_pages_per_browser == 1
    assert plugin._user_data_dir is None
    assert plugin._fingerprint_generator is None


def test_request_handler_timeout_tracks_collection_duration(tmp_path, monkeypatch):
    captured = {}

    class Router:
        def default_handler(self, handler):
            return handler

    class FakeCrawler:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.router = Router()

        def pre_navigation_hook(self, handler):
            return handler

        async def run(self, _requests):
            return None

        def stop(self, _reason):
            pass

    class FakePool:
        def __init__(self, **kwargs):
            captured["pool"] = kwargs

        def pre_launch_hook(self, handler):
            return handler

        def post_launch_hook(self, handler):
            return handler

        def pre_page_create_hook(self, handler):
            return handler

        def post_page_create_hook(self, handler):
            return handler

        def pre_page_close_hook(self, handler):
            return handler

        def post_page_close_hook(self, handler):
            return handler

    monkeypatch.setattr(browser, "_legacy_session", lambda: ([], "app-id"))
    monkeypatch.setattr(browser, "PlaywrightBrowserPlugin", lambda **kwargs: captured.setdefault("plugin", kwargs))
    monkeypatch.setattr(browser, "BrowserPool", FakePool)
    monkeypatch.setattr(browser, "PlaywrightCrawler", FakeCrawler)

    experiment = BrowserCommentExperiment(BrowserExperimentConfig(
        target_url="https://www.instagram.com/p/post-1/",
        output_root=tmp_path,
        duration_seconds=120,
    ))
    asyncio.run(experiment.run())

    assert captured["request_handler_timeout"] == timedelta(seconds=135)
    assert captured["plugin"] == {
        "browser_launch_options": {"headless": False},
        "max_open_pages_per_browser": 1,
    }


def test_report_aggregates_request_observations_across_resume_runs(tmp_path):
    experiment = BrowserCommentExperiment(BrowserExperimentConfig(
        target_url="https://www.instagram.com/p/post-1/",
        output_root=tmp_path,
    ))
    try:
        experiment._begin_store("shortcode:post-1")
        experiment.legacy_observations = [{"status": 200}, {"status": 200}]
        experiment.reply_observations = [{"status": 200}]
        experiment.http_request_attempts = 1

        report = experiment.report("bounded_collection_finished")

        assert report["total_http_requests"] == 3
        assert report["http_requests_this_run"] == 1
    finally:
        experiment.store.close()


def test_report_includes_latency_pacing_storage_and_crawlee_timings(tmp_path):
    experiment = BrowserCommentExperiment(BrowserExperimentConfig(
        target_url="https://www.instagram.com/p/post-1/",
        output_root=tmp_path,
    ))
    try:
        experiment._begin_store("shortcode:post-1")
        experiment.legacy_observations = [
            {"request_timing_ms": {"network": value, "headers": value / 2, "body": value / 4, "json_decode": 1, "browser_evaluate_ms": value + 2}}
            for value in range(1, 21)
        ]
        experiment.reply_observations = [{"request_timing_ms": {"network": 5, "json_decode": 1}}]
        experiment.root_request_attempts_this_run = 2
        experiment.reply_request_attempts_this_run = 1
        experiment.http_request_attempts = 3
        experiment.response_records_this_run = 6
        experiment.unique_records_added_this_run = 5
        experiment.request_start_intervals_ms = [500, 550]
        experiment.pacing_sleep_count = 2
        experiment.pacing_requested_ms = 1000
        experiment.pacing_actual_ms = 1003
        experiment.normalization_ms = {"root": 4, "reply": 2}
        experiment.sqlite_timings_ms = [{"record_persistence_and_deduplication": 2, "checkpoint": 1, "commit": 0.5, "transaction": 4}]
        experiment.handler_durations_ms = [2000]
        experiment.first_handler_started = 10
        experiment.last_handler_finished = 12
        experiment.crawler_run_started = 9
        experiment.crawler_run_finished = 13

        report = experiment.report("bounded_collection_finished")
        performance = report["performance"]

        assert performance["saved_request_timing_samples"]["root"]["network"]["count"] == 20
        assert performance["saved_request_timing_samples"]["root"]["network"]["p95_ms"] is not None
        assert performance["http_execution_ms_this_run"] == 215
        assert performance["request_start_interval_ms_this_run"]["median_ms"] == 525
        assert performance["pacing"]["actual_total_ms"] == 1003
        assert performance["sqlite_ms_this_run"]["commit"] == 0.5
        assert performance["crawlee"]["startup_navigation_scheduling_split_available"] is False
        assert performance["lifecycle_phases_ms"]["session_pool_enabled"] is False
        assert performance["response_json_decode_ms_this_run"] == 21
        assert performance["report_generation_ms"] >= 0
    finally:
        experiment.store.close()


def test_global_http_budget_must_be_positive(tmp_path):
    with pytest.raises(ValueError, match="max_http_requests"):
        BrowserExperimentConfig(
            target_url="https://www.instagram.com/p/post-1/",
            output_root=tmp_path,
            max_http_requests=0,
        )
