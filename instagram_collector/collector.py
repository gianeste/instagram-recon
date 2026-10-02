from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .storage import utc_now


REQUESTED_COMMENT_FIELDS = {
    "id", "text", "username", "timestamp", "like_count", "hidden", "parent_id", "reply_count",
}


def _field_status(raw: dict[str, Any], name: str, requested: set[str]) -> str:
    if name not in requested:
        return "not_requested"
    if name not in raw:
        return "not_returned"
    if raw[name] is None:
        return "returned_null"
    return "returned"


def _timestamp_utc(value: Any) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            seconds = float(value)
            if abs(seconds) > 100_000_000_000:
                seconds /= 1000
            return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_comment(
    raw: dict[str, Any],
    media_id: str,
    parent_id: str | None,
    *,
    source: str = "instagram_comment_response",
    requested_fields: set[str] | None = None,
) -> dict[str, Any]:
    comment_id = raw.get("id")
    if not isinstance(comment_id, (str, int)) or not str(comment_id):
        raise ValueError("Comment response item did not include an id")
    author = raw.get("from") if isinstance(raw.get("from"), dict) else {}
    reported_replies = raw.get("reply_count", raw.get("replies_count"))
    replies = raw.get("replies")
    if reported_replies is None and isinstance(replies, dict):
        total = replies.get("summary", {}).get("total_count")
        reported_replies = total if isinstance(total, int) else None
    return {
        "id": str(comment_id),
        "media_id": media_id,
        "parent_id": parent_id or raw.get("parent_id"),
        "author_id": str(author["id"]) if author.get("id") is not None else None,
        "username": raw.get("username") or author.get("username"),
        "text": raw.get("text"),
        "created_at": _timestamp_utc(raw.get("timestamp")),
        "timestamp_raw": raw.get("timestamp"),
        "like_count": raw.get("like_count"),
        "reported_reply_count": reported_replies,
        "visibility": {"hidden": raw.get("hidden")} if "hidden" in raw else None,
        "field_status": {
            key: _field_status(raw, key, requested_fields or REQUESTED_COMMENT_FIELDS)
            for key in ("id", "text", "username", "timestamp", "like_count", "hidden", "parent_id", "reply_count")
        },
        "source": source,
        "collected_at": utc_now(),
    }
