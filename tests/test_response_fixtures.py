import json

import pytest

from instagram_collector.cli import main
from instagram_collector.response_fixtures import (
    FixtureError,
    extract_comment_ids,
    inspect_response,
    normalize_mapped_comments,
)


def response(text="example"):
    return {
        "data": {
            "comments": {
                "edges": [{
                    "node": {
                        "id": "comment-1",
                        "parent_comment_id": "root-1",
                        "text": text,
                        "created_at": "2026-09-30T12:00:00Z",
                        "user": {"pk": "user-1", "username": "author"},
                        "like_count": 4,
                        "reply_count": 2,
                    }
                }],
                "page_info": {"has_next_page": False, "end_cursor": None},
            }
        }
    }


def test_inspection_discovers_nested_schema_types_and_candidates():
    result = inspect_response(response(), operation="ExampleQuery")
    assert result["operation"] == "ExampleQuery"
    assert result["json_schema"]["type"] == "object"
    assert result["field_types"]["$.data.comments.edges"] == "array"
    assert "$.data.comments.edges[*].node" in result["classified_paths"]["objects"]
    assert "$.data.comments.edges[*].node.id" in result["candidate_fields"]["comment_ids"]
    assert "$.data.comments.edges[*].node.parent_comment_id" in result["relationship_candidates"]["parent_id_fields"]
    assert "$.data.comments.page_info.has_next_page" in result["candidate_fields"]["pagination"]
    assert "$.data.comments.edges[*].node.reply_count" in result["candidate_fields"]["reply_counts"]


def test_inspection_discovers_both_root_pagination_mechanisms():
    result = inspect_response({
        "comments": [],
        "has_more_comments": True,
        "next_max_id": "opaque-max",
        "has_more_headload_comments": False,
        "next_min_id": None,
    })
    assert "$.has_more_comments" in result["candidate_fields"]["pagination"]
    assert "$.next_max_id" in result["candidate_fields"]["pagination"]
    assert "$.has_more_headload_comments" in result["candidate_fields"]["pagination"]
    assert "$.next_min_id" in result["candidate_fields"]["pagination"]


def test_shape_fingerprint_ignores_values_but_tracks_shape():
    first = inspect_response(response("first"))["response_shape_fingerprint"]
    same_shape = inspect_response(response("second"))["response_shape_fingerprint"]
    changed_shape = inspect_response({"data": {"comments": []}})["response_shape_fingerprint"]
    assert first == same_shape
    assert first != changed_shape


def test_field_types_merge_across_array_items():
    result = inspect_response({"items": [{"id": "one", "count": 1}, {"id": 2, "count": None}]})
    assert result["field_types"]["$.items[*].id"] == "integer|string"
    assert result["field_types"]["$.items[*].count"] == "integer|null"


def test_empty_array_has_valid_unconstrained_item_schema():
    result = inspect_response({"items": []})
    assert result["json_schema"]["properties"]["items"] == {"type": "array", "items": {}}


def test_explicit_comment_id_path_extracts_scalar_ids():
    assert extract_comment_ids(response(), "data.comments.edges[*].node.id") == ["comment-1"]


def test_cli_writes_analysis_without_copying_response_values(tmp_path, capsys):
    source = tmp_path / "response.json"
    output = tmp_path / "analysis.json"
    source.write_text(json.dumps(response("text must stay out")), encoding="utf-8")
    assert main([
        "inspect-response", str(source), "--comment-id-path",
        "data.comments.edges[*].node.id", "--output", str(output),
    ]) == 0
    assert "text must stay out" not in output.read_text(encoding="utf-8")
    assert "comment-1" in output.read_text(encoding="utf-8")
    assert capsys.readouterr().out


def test_credential_fields_are_rejected_without_echoing_values():
    with pytest.raises(FixtureError, match="credential-like field") as raised:
        inspect_response({"sessionid": "never-print-this"})
    assert "never-print-this" not in str(raised.value)


def test_verified_mapping_reuses_normalized_comment_model():
    payload = response()
    mapping = {
        "operation": "ExampleChildQuery",
        "verified": True,
        "response_shape_fingerprint": inspect_response(payload)["response_shape_fingerprint"],
        "items_path": "data.comments.edges[*].node",
        "fields": {
            "id": "id",
            "parent_id": "parent_comment_id",
            "author_id": "user.pk",
            "author_username": "user.username",
            "text": "text",
            "timestamp": "created_at",
            "like_count": "like_count",
            "reply_count": "reply_count",
        },
    }
    [comment] = normalize_mapped_comments(payload, mapping, media_id="media-1")
    assert comment["id"] == "comment-1"
    assert comment["media_id"] == "media-1"
    assert comment["parent_id"] == "root-1"
    assert comment["author_id"] == "user-1"
    assert comment["username"] == "author"
    assert comment["created_at"] == "2026-09-30T12:00:00Z"
    assert comment["like_count"] == 4
    assert comment["reported_reply_count"] == 2
    assert comment["source"] == "instagram_response_fixture:ExampleChildQuery"
    assert comment["field_status"]["text"] == "returned"
    assert comment["field_status"]["hidden"] == "not_requested"


def test_normalization_requires_verified_matching_shape():
    payload = response()
    mapping = {
        "verified": False,
        "response_shape_fingerprint": inspect_response(payload)["response_shape_fingerprint"],
        "items_path": "data.comments.edges[*].node",
        "fields": {"id": "id"},
    }
    with pytest.raises(FixtureError, match="explicitly marked verified"):
        normalize_mapped_comments(payload, mapping, media_id="media-1")
    mapping["verified"] = True
    mapping["response_shape_fingerprint"] = "0" * 64
    with pytest.raises(FixtureError, match="does not match"):
        normalize_mapped_comments(payload, mapping, media_id="media-1")


def test_verified_mapping_can_record_live_shape_variation_without_changing_paths():
    payload = response()
    mapping = {
        "operation": "ExampleChildQuery",
        "verified": True,
        "response_shape_fingerprint": inspect_response(payload)["response_shape_fingerprint"],
        "items_path": "data.comments.edges[*].node",
        "fields": {"id": "id", "parent_id": "parent_comment_id", "text": "text"},
    }
    changed = {**payload, "request_context": {"revision": "observed"}}
    with pytest.raises(FixtureError, match="does not match"):
        normalize_mapped_comments(changed, mapping, media_id="media-1")
    [comment] = normalize_mapped_comments(
        changed, mapping, media_id="media-1", allow_shape_variation=True
    )
    assert comment["id"] == "comment-1"
    assert comment["parent_id"] == "root-1"
