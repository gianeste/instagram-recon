from __future__ import annotations

import json
from pathlib import Path

from instagram_collector.response_fixtures import inspect_response, load_response, normalize_mapped_comments


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures" / "polaris_child_comments_tree.sanitized.json"
MAPPING = ROOT / "fixtures" / "polaris_child_comments_mapping.json"


def test_captured_child_fixture_has_reviewed_shape_and_fields() -> None:
    payload = load_response(FIXTURE)
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    report = inspect_response(payload, operation="PolarisPostChildCommentsQuery")
    assert report["response_shape_fingerprint"] == mapping["response_shape_fingerprint"]
    assert any(path.endswith("comment_like_count") for path in report["candidate_fields"]["like_counts"])

    rows = normalize_mapped_comments(payload, mapping, media_id="fixture-media")
    assert len(rows) == 3
    assert len({row["id"] for row in rows}) == len(rows)
    assert all(isinstance(row["id"], str) and row["id"] for row in rows)
    assert len({row["parent_id"] for row in rows}) == 1
    assert all(isinstance(row["parent_id"], str) and row["parent_id"] for row in rows)
    assert all(isinstance(row["author_id"], str) and row["author_id"] for row in rows)
    assert all(isinstance(row["username"], str) and row["username"] for row in rows)
    assert all(isinstance(row["text"], str) and row["text"] for row in rows)
    assert all(isinstance(row["created_at"], str) and row["created_at"].endswith("Z") for row in rows)
    assert all(isinstance(row["like_count"], int) for row in rows)
    assert all(row["field_status"]["reply_count"] == "returned_null" for row in rows)
