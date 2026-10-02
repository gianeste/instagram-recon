from __future__ import annotations

import json
from pathlib import Path

from instagram_collector.response_fixtures import inspect_response, load_response, normalize_mapped_comments


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures" / "instagram_root_comments_browser.schema.json"
MAPPING = ROOT / "fixtures" / "instagram_root_comments_mapping.json"


def test_browser_root_schema_projection_normalizes_root_comments() -> None:
    payload = load_response(FIXTURE)
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    report = inspect_response(payload, operation=mapping["operation"])

    assert report["response_shape_fingerprint"] == mapping["response_shape_fingerprint"]
    assert "$.comments[*].comment_like_count" in report["candidate_fields"]["like_counts"]
    assert "$.comments[*].child_comment_count" in report["candidate_fields"]["reply_counts"]
    assert "$.next_min_id" in report["candidate_fields"]["pagination"]
    assert "$.has_more_comments" in report["candidate_fields"]["pagination"]
    assert "$.has_more_headload_comments" in report["candidate_fields"]["pagination"]

    rows = normalize_mapped_comments(payload, mapping, media_id="fixture-media")
    assert len(rows) == 2
    assert len({row["id"] for row in rows}) == len(rows)
    assert all(isinstance(row["id"], str) and row["id"] for row in rows)
    assert all(row["parent_id"] is None for row in rows)
    assert all(isinstance(row["author_id"], str) for row in rows)
    assert all(isinstance(row["username"], str) for row in rows)
    assert all(isinstance(row["text"], str) for row in rows)
    assert all(row["created_at"].endswith("Z") for row in rows)
    assert all(isinstance(row["like_count"], int) for row in rows)
    assert all(isinstance(row["reported_reply_count"], int) for row in rows)


def test_browser_root_page_records_distinct_headload_termination_flags() -> None:
    payload = load_response(FIXTURE)
    assert payload["_fixture_metadata"]["provenance"] == "genuine_authorized_browser_dom_response"
    assert payload["_fixture_metadata"]["observed_comment_count"] == 15
    assert payload["has_more_comments"] is False
    assert payload["has_more_headload_comments"] is True
    assert payload["next_min_id"] == "<redacted-cursor>"
