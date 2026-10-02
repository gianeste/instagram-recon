from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


class FixtureError(ValueError):
    pass


_SENSITIVE = {
    "authorization", "bearer", "cookie", "setcookie", "sessionid", "csrftoken",
    "accesstoken", "password", "secret", "credential", "credentials", "fbdtsg", "lsd",
}
_CANDIDATES = {
    "comment_ids": {"id", "pk", "commentid", "commentpk"},
    "parent_ids": {"parentid", "parentcommentid", "parentpk"},
    "authors": {"author", "user", "from", "owner", "username", "userid", "authorid"},
    "timestamps": {"timestamp", "createdat", "createdtime", "takenat"},
    "text": {"text", "commenttext", "caption"},
    "like_counts": {"likecount", "likescount", "likes", "commentlikecount"},
    "reply_counts": {"replycount", "repliescount", "childcommentcount"},
    "pagination": {
        "after", "before", "cursor", "endcursor", "minid", "nextminid", "nextmaxid",
        "hasnextpage", "hasmorecomments", "hasmoreheadloadcomments",
        "moreavailable", "next", "nexturl", "paging",
    },
}
_MAPPED_FIELDS = {
    "id", "parent_id", "author_id", "author_username", "username", "text",
    "timestamp", "like_count", "reply_count",
}


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _reject_credentials(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = _normalized_key(str(key))
            if (
                normalized in _SENSITIVE
                or any(part in normalized for part in ("session", "cookie", "csrf", "password", "secret", "credential"))
                or normalized.endswith(("accesstoken", "fbdtsg", "lsd"))
            ):
                raise FixtureError("Response fixture contains a credential-like field; sanitize it before import")
            _reject_credentials(child)
    elif isinstance(value, list):
        for child in value:
            _reject_credentials(child)


def _merge_schema(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    types: set[str] = set()
    for source in (left.get("type"), right.get("type")):
        if isinstance(source, list):
            types.update(source)
        elif isinstance(source, str):
            types.add(source)
    schema: dict[str, Any] = {}
    if types:
        schema["type"] = sorted(types)[0] if len(types) == 1 else sorted(types)
    if "object" in types:
        properties: dict[str, Any] = {}
        for source in (left.get("properties", {}), right.get("properties", {})):
            for key, child in source.items():
                properties[key] = _merge_schema(properties[key], child) if key in properties else child
        schema["properties"] = dict(sorted(properties.items()))
    if "array" in types:
        left_items, right_items = left.get("items", {"type": "unknown"}), right.get("items", {"type": "unknown"})
        schema["items"] = _merge_schema(left_items, right_items)
    return schema


def _schema(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        items = [_schema(item) for item in value]
        merged = items[0] if items else {}
        for item in items[1:]:
            merged = _merge_schema(merged, item)
        return {"type": "array", "items": merged}
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {key: _schema(child) for key, child in sorted(value.items())},
        }
    return {"type": "unknown"}


def _walk(value: Any, path: str = "$", fields: dict[str, str] | None = None) -> tuple[dict[str, str], list[str], list[str]]:
    fields = fields if fields is not None else {}
    objects: list[str] = []
    arrays: list[str] = []
    if isinstance(value, dict):
        objects.append(path)
        for key, child in value.items():
            child_path = f"{path}.{key}"
            types = set(fields.get(child_path, "").split("|")) - {""}
            types.add(_json_type(child))
            fields[child_path] = "|".join(sorted(types))
            _, child_objects, child_arrays = _walk(child, child_path, fields)
            objects.extend(child_objects)
            arrays.extend(child_arrays)
    elif isinstance(value, list):
        arrays.append(path)
        for child in value:
            _, child_objects, child_arrays = _walk(child, f"{path}[*]", fields)
            objects.extend(child_objects)
            arrays.extend(child_arrays)
    return fields, objects, arrays


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def inspect_response(payload: Any, *, operation: str | None = None) -> dict[str, Any]:
    _reject_credentials(payload)
    schema = _schema(payload)
    encoded = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode("utf-8")
    fields, objects, arrays = _walk(payload)
    candidates: dict[str, list[str]] = {name: [] for name in _CANDIDATES}
    reply_collections: list[str] = []
    for path in fields:
        leaf = _normalized_key(path.rsplit(".", 1)[-1].replace("[*]", ""))
        for category, names in _CANDIDATES.items():
            if leaf in names:
                candidates[category].append(path)
        if leaf in {"replies", "childcomments", "childcommentedges"}:
            reply_collections.append(path)
    return {
        "operation": operation,
        "response_shape_fingerprint": hashlib.sha256(encoded).hexdigest(),
        "json_schema": schema,
        "field_types": dict(sorted(fields.items())),
        "classified_paths": {"objects": sorted(set(objects)), "arrays": sorted(set(arrays))},
        "candidate_fields": {name: sorted(paths) for name, paths in candidates.items()},
        "relationship_candidates": {
            "parent_id_fields": sorted(candidates["parent_ids"]),
            "reply_collection_fields": sorted(reply_collections),
        },
    }


def _path_values(value: Any, path: str) -> list[Any]:
    path = path.removeprefix("$.").removeprefix("$")
    if not re.fullmatch(r"\$?(?:[^.\[\]]+|\[\*\])(?:\.?(?:[^.\[\]]+|\[\*\]))*", path):
        raise FixtureError("Field path must use object keys and [*] array steps")
    tokens = re.findall(r"[^.\[\]]+|\[\*\]", path)
    if not tokens:
        raise FixtureError("A non-empty JSON field path is required")
    states = [value]
    for token in tokens:
        next_states: list[Any] = []
        if token == "[*]":
            for state in states:
                if isinstance(state, list):
                    next_states.extend(state)
        else:
            for state in states:
                if isinstance(state, dict) and token in state:
                    next_states.append(state[token])
        states = next_states
    return states


def extract_comment_ids(payload: Any, path: str) -> list[str]:
    _reject_credentials(payload)
    values = _path_values(payload, path)
    if len(values) == 1 and isinstance(values[0], list):
        values = values[0]
    return [str(value) for value in values if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value)]


def normalize_mapped_comments(
    payload: Any,
    mapping: dict[str, Any],
    *,
    media_id: str,
    parent_id: str | None = None,
    allow_shape_variation: bool = False,
) -> list[dict[str, Any]]:
    """Normalize an explicitly reviewed field map.

    Fingerprint matching stays strict by default. A live browser adapter may
    opt into shape variation after it records the live fingerprint; field paths
    and stable IDs are still validated and missing paths remain errors.
    """
    _reject_credentials(mapping)
    if mapping.get("verified") is not True:
        raise FixtureError("Comment field mapping must be explicitly marked verified")
    fingerprint = inspect_response(payload)["response_shape_fingerprint"]
    if not allow_shape_variation and mapping.get("response_shape_fingerprint") != fingerprint:
        raise FixtureError("Response shape does not match the verified field mapping")
    items_path, fields = mapping.get("items_path"), mapping.get("fields")
    if not isinstance(items_path, str) or not isinstance(fields, dict) or not isinstance(fields.get("id"), str):
        raise FixtureError("Verified mapping requires items_path and an id field path")
    if set(fields) - _MAPPED_FIELDS or any(not isinstance(path, str) for path in fields.values()):
        raise FixtureError("Verified mapping contains unsupported comment fields")

    items = _path_values(payload, items_path)
    if len(items) == 1 and isinstance(items[0], list):
        items = items[0]
    if any(not isinstance(item, dict) for item in items):
        raise FixtureError("Mapped comment collection must contain JSON objects")

    from .collector import normalize_comment

    operation = mapping.get("operation")
    source = f"instagram_response_fixture:{operation}" if isinstance(operation, str) and operation else "instagram_response_fixture"
    comments = []
    for item in items:
        raw: dict[str, Any] = {}
        for name, path in fields.items():
            values = _path_values(item, path)
            if values:
                raw[name] = values[0]
        author: dict[str, Any] = {}
        if "author_id" in raw:
            author["id"] = raw.pop("author_id")
        if "author_username" in raw:
            raw["username"] = raw.pop("author_username")
        if author:
            raw["from"] = author
        if raw.get("id") is None:
            raise FixtureError("Mapped comment object is missing its comment ID")
        requested = set(fields)
        if "author_id" in requested:
            requested.add("from")
        if "author_username" in requested:
            requested.add("username")
        comments.append(normalize_comment(
            raw, str(media_id), parent_id, source=source, requested_fields=requested
        ))
    return comments


def load_response(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FixtureError(f"Response fixture is not valid JSON at line {exc.lineno}, column {exc.colno}") from None
