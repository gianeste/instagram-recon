from __future__ import annotations

import argparse
from dataclasses import fields

import pytest

from instagram_collector import cli
from instagram_collector.crawlee_browser import (
    BrowserCommentExperiment,
    BrowserExperimentConfig,
    _legacy_page,
)


def test_collector_has_one_live_entry_command():
    parser = cli._parser()
    action = next(item for item in parser._actions if isinstance(item, argparse._SubParsersAction))

    assert set(action.choices) == {"collect", "status", "inspect-response"}
    assert "--legacy-graphql" not in parser.format_help()


def test_collection_config_has_no_alternate_mode_or_persistent_profile():
    names = {field.name for field in fields(BrowserExperimentConfig)}

    assert names == {"target_url", "output_root", "headless", "max_root_pages", "duration_seconds"}


def test_legacy_graphql_page_normalizes_comment_and_cursor(tmp_path):
    media_id, reported, comments, has_next, cursor = _legacy_page(
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
        assert experiment.output_dir == tmp_path / "legacy-graphql" / "post-1"
        experiment.page_title = "Instagram"
        experiment._begin_store("shortcode:post-1")
        report = experiment.report("bounded_collection_finished")
        assert report["collection_method"] == "legacy_graphql_get"
        assert report["browser_backend"] == "CloakBrowser via Crawlee PlaywrightCrawler"
    finally:
        experiment.store.close()


def test_crawlee_plugin_uses_ephemeral_browser():
    pytest.importorskip("crawlee")
    from instagram_collector.crawlee_browser import CloakBrowserPlugin

    plugin = CloakBrowserPlugin(
        browser_launch_options={"headless": True},
        max_open_pages_per_browser=1,
    )
    assert plugin.max_open_pages_per_browser == 1
    assert plugin._user_data_dir is None
