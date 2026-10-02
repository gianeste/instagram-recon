"""Collect an Instagram post's root comments through Crawlee + Playwright."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .collector import decode_shortcode, normalize_comment
from .response_fixtures import FixtureError
from .storage import StateStore, atomic_write_json, atomic_write_jsonl, utc_now
from .urls import parse_post_url
from .full_form_replies import FullFormReplyTransport

try:  # Offline tools can still import this module without the browser stack.
    from crawlee.browsers import (
        BrowserPool,
        PlaywrightBrowserPlugin,
    )
    from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
    from crawlee._types import ConcurrencySettings
except ImportError:  # pragma: no cover - exercised only without optional extras
    BrowserPool = None  # type: ignore[assignment]
    PlaywrightBrowserPlugin = object  # type: ignore[assignment,misc]
    PlaywrightCrawler = None  # type: ignore[assignment]
    PlaywrightCrawlingContext = Any  # type: ignore[assignment,misc]
    ConcurrencySettings = None  # type: ignore[assignment]

_LOGIN_MARKERS = ("/accounts/login", "/challenge/", "/checkpoint/")
_CHALLENGE_MARKERS = ("challenge_required", "checkpoint_required", "captcha", "verify it's you")
_LEGACY_QUERY_HASH = "97b41c52301f77ce508f55e66d17620e"
_LEGACY_PAGE_SIZE = 50
_CHILD_COMMENTS_INITIAL_OPERATION = "PolarisPostChildCommentsQuery"
_CHILD_COMMENTS_DOC_ID = "28027289793632076"
_CHILD_COMMENTS_CONTINUATION_OPERATION = "PolarisPostCommentsChildrenPaginationtQuery"
_CHILD_COMMENTS_CONTINUATION_DOC_ID = "27229753410037873"
_CHILD_CONNECTION = "xdt_api__v1__media__media_id__comments__parent_comment_id__child_comments__connection"
_REPLY_PAGE_SIZE = 5


def _timing_summary(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)

    def percentile(fraction: float) -> float:
        index = (len(ordered) - 1) * fraction
        lower = int(index)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)

    return {
        "count": len(ordered),
        "total_ms": round(sum(ordered), 3),
        "median_ms": round(percentile(0.5), 3) if ordered else None,
        "p90_ms": round(percentile(0.9), 3) if len(ordered) >= 20 else None,
        "p95_ms": round(percentile(0.95), 3) if len(ordered) >= 20 else None,
    }


def _request_timing_summary(observations: list[dict[str, Any]]) -> dict[str, Any]:
    names = ("network", "headers", "body", "json_decode", "total", "browser_evaluate_ms", "transport_call_ms")
    summary = {
        name: _timing_summary([
            float(observation["request_timing_ms"][name])
            for observation in observations
            if isinstance(observation.get("request_timing_ms"), dict)
            and isinstance(observation["request_timing_ms"].get(name), (int, float))
        ])
        for name in names
    }
    resource_rows = [
        observation["resource_timing"] for observation in observations
        if isinstance(observation.get("resource_timing"), dict)
    ]
    resource_names = ("dns_ms", "connect_ms", "tls_ms", "request_wait_ms", "response_transfer_ms")
    summary["resource_timing"] = {
        "available_samples": len(resource_rows),
        "next_hop_protocols": sorted({
            row["next_hop_protocol"] for row in resource_rows
            if isinstance(row.get("next_hop_protocol"), str) and row["next_hop_protocol"]
        }),
        **{
            name: _timing_summary([
                float(row[name]) for row in resource_rows
                if isinstance(row.get(name), (int, float))
            ])
            for name in resource_names
        },
    }
    return summary


def _load_env_file(path: Path = Path(".env")) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if name:
            os.environ.setdefault(name, value)


def _legacy_session() -> tuple[list[dict[str, Any]], str]:
    _load_env_file()
    jar = SimpleCookie()
    try:
        jar.load(os.environ.get("IG_SESSION_COOKIE", ""))
    except Exception:
        raise ValueError("IG_SESSION_COOKIE is not a valid cookie header") from None

    names = ("sessionid", "ds_user_id", "csrftoken", "mid")
    values = {name: jar[name].value for name in names if name in jar}
    csrf = os.environ.get("IG_CSRF_TOKEN")
    if csrf:
        values["csrftoken"] = csrf
    missing = [name for name in names if not values.get(name)]
    if missing:
        raise ValueError("IG_SESSION_COOKIE is missing required cookies: " + ", ".join(missing))
    app_id = os.environ.get("IG_APP_ID", "")
    if not app_id:
        raise ValueError("Set IG_APP_ID for the GraphQL request")
    cookies = [
        {
            "name": name,
            "value": values[name],
            "domain": "www.instagram.com",
            "path": "/",
            "secure": True,
            "httpOnly": name == "sessionid",
        }
        for name in names
    ]
    return cookies, app_id


def _legacy_page(
    payload: Any, shortcode: str
) -> tuple[str, int | None, list[dict[str, Any]], list[dict[str, Any]], bool, str | None]:
    try:
        media = payload["data"]["shortcode_media"]
        edge_info = media["edge_media_to_parent_comment"]
        edges = edge_info["edges"]
        page_info = edge_info["page_info"]
    except (KeyError, TypeError):
        raise FixtureError("Legacy GraphQL response is missing the parent-comment connection") from None
    if not isinstance(media, dict) or not isinstance(edges, list) or not isinstance(page_info, dict):
        raise FixtureError("Legacy GraphQL parent-comment connection has an unexpected shape")
    returned_shortcode = media.get("shortcode")
    if returned_shortcode is not None and returned_shortcode != shortcode:
        raise FixtureError("Legacy GraphQL response shortcode does not match the requested post")
    media_id = media.get("id")
    if isinstance(media_id, bool) or not isinstance(media_id, (str, int)) or not str(media_id):
        media_id = f"shortcode:{shortcode}"
    if not isinstance(page_info.get("has_next_page"), bool):
        raise FixtureError("Legacy GraphQL response did not include has_next_page")

    records = []
    embedded_replies = []
    for edge in edges:
        node = edge.get("node") if isinstance(edge, dict) else None
        if not isinstance(node, dict):
            raise FixtureError("Legacy GraphQL edge did not include a comment node")
        owner = node.get("owner") if isinstance(node.get("owner"), dict) else {}
        threaded = node.get("edge_threaded_comments")
        reply_count = threaded.get("count") if isinstance(threaded, dict) else None
        raw = {
            "id": node.get("id"),
            "from": {"id": owner.get("id"), "username": owner.get("username")},
            "username": owner.get("username"),
            "text": node.get("text"),
            "timestamp": node.get("created_at"),
            "like_count": node.get("like_count"),
            "reply_count": reply_count,
        }
        records.append(normalize_comment(
            raw,
            str(media_id),
            None,
            source="instagram_legacy_graphql",
            requested_fields={"id", "text", "username", "timestamp", "like_count", "reply_count"},
        ))
        threaded_edges = threaded.get("edges") if isinstance(threaded, dict) else None
        if isinstance(threaded_edges, list):
            for reply_edge in threaded_edges:
                reply_node = reply_edge.get("node") if isinstance(reply_edge, dict) else None
                if not isinstance(reply_node, dict):
                    raise FixtureError("Embedded reply edge did not include a comment node")
                reply_owner = reply_node.get("owner") if isinstance(reply_node.get("owner"), dict) else {}
                declared_parents = (reply_node.get("parent_id"), reply_node.get("parent_comment_id"))
                if any(value is not None and str(value) != records[-1]["id"] for value in declared_parents):
                    raise FixtureError("Embedded reply parent ID does not match its containing root")
                embedded_replies.append(normalize_comment(
                    {
                        "id": reply_node.get("id"),
                        "parent_id": records[-1]["id"],
                        "from": {"id": reply_owner.get("id"), "username": reply_owner.get("username")},
                        "username": reply_owner.get("username"),
                        "text": reply_node.get("text"),
                        "timestamp": reply_node.get("created_at"),
                        "like_count": reply_node.get("like_count"),
                    },
                    str(media_id),
                    None,
                    source="instagram_legacy_graphql_embedded_reply",
                    requested_fields={"id", "parent_id", "text", "username", "timestamp", "like_count"},
                ))
    reported_count = edge_info.get("count")
    if isinstance(reported_count, bool) or not isinstance(reported_count, int) or reported_count < 0:
        reported_count = None
    cursor = page_info.get("end_cursor")
    if not isinstance(cursor, str) or not cursor:
        cursor = None
    return str(media_id), reported_count, records, embedded_replies, page_info["has_next_page"], cursor


def _child_page(
    payload: Any,
    media_id: str,
    parent_id: str,
    *,
    source_operation: str = _CHILD_COMMENTS_INITIAL_OPERATION,
) -> tuple[list[dict[str, Any]], bool, str | None]:
    try:
        connection = payload["data"][_CHILD_CONNECTION]
        edges = connection["edges"]
        page_info = connection["page_info"]
    except (KeyError, TypeError):
        raise FixtureError("Child-comment response is missing its verified connection") from None
    if not isinstance(connection, dict) or not isinstance(edges, list) or not isinstance(page_info, dict):
        raise FixtureError("Child-comment connection has an unexpected shape")
    has_next = page_info.get("has_next_page")
    if not isinstance(has_next, bool):
        raise FixtureError("Child-comment response did not include has_next_page")
    cursor = page_info.get("end_cursor")
    if not isinstance(cursor, str) or not cursor:
        cursor = None

    records = []
    for edge in edges:
        node = edge.get("node") if isinstance(edge, dict) else None
        if not isinstance(node, dict):
            raise FixtureError("Child-comment edge did not include a comment node")
        user = node.get("user") if isinstance(node.get("user"), dict) else {}
        raw = {
            "id": node.get("pk"),
            "parent_id": node.get("parent_comment_id"),
            "from": {"id": user.get("pk", user.get("id")), "username": user.get("username")},
            "username": user.get("username"),
            "text": node.get("text"),
            "timestamp": node.get("created_at"),
            "like_count": node.get("comment_like_count"),
            "reply_count": node.get("child_comment_count"),
        }
        record = normalize_comment(
            raw,
            media_id,
            None,
            source=source_operation,
            requested_fields={"id", "parent_id", "author_id", "author_username", "text", "timestamp", "like_count", "reply_count"},
        )
        if record["parent_id"] != parent_id:
            raise FixtureError("Child-comment response did not establish the requested parent relationship")
        records.append(record)
    return records, has_next, cursor


def _classify_child_response(
    content_type: str,
    *,
    is_json: bool,
    html_signals: dict[str, bool] | None = None,
) -> str:
    if is_json:
        return "json"
    signals = html_signals or {}
    if signals.get("login_marker") or signals.get("challenge_marker"):
        return "authentication_or_access_document"
    if "html" in content_type.lower() or signals.get("html_element"):
        if all(signals.get(key) for key in ("doctype", "html_element")) and (
            signals.get("app_assets") or signals.get("splash_screen")
        ):
            return "normal_application_shell" if signals.get("instagram_title") else "application_shell_like"
        return "html_document"
    return "non_json"


def _safe_browser_error(exc: Exception) -> str:
    message = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    message = re.sub(r"https?://\S+", "<url>", message)
    return message[:160]


def _legacy_shape(payload: Any) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else None
    media = data.get("shortcode_media") if isinstance(data, dict) else None
    connection = media.get("edge_media_to_parent_comment") if isinstance(media, dict) else None
    edges = connection.get("edges") if isinstance(connection, dict) else None
    page_info = connection.get("page_info") if isinstance(connection, dict) else None
    first_node = edges[0].get("node") if isinstance(edges, list) and edges and isinstance(edges[0], dict) else None
    return {
        "top_level_keys": sorted(payload) if isinstance(payload, dict) else [],
        "data_keys": sorted(data) if isinstance(data, dict) else [],
        "media_keys": sorted(media) if isinstance(media, dict) else [],
        "comment_connection_keys": sorted(connection) if isinstance(connection, dict) else [],
        "edge_count": len(edges) if isinstance(edges, list) else None,
        "page_info_keys": sorted(page_info) if isinstance(page_info, dict) else [],
        "has_next_page_type": type(page_info.get("has_next_page")).__name__ if isinstance(page_info, dict) else None,
        "end_cursor_present": bool(page_info.get("end_cursor")) if isinstance(page_info, dict) else False,
        "first_node_keys": sorted(first_node) if isinstance(first_node, dict) else [],
    }


def _safe_url(value: str) -> str:
    parsed = urlsplit(value)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _backup_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as destination_db:
        source_db.backup(destination_db)


def _migrate_legacy_output(root: Path, shortcode: str, destination: Path) -> None:
    candidates = (
        root / "legacy-graphql" / shortcode,
        root / "legacy-graphql-qualification" / "legacy-graphql" / shortcode,
    )
    source = next((path for path in candidates if (path / "state.sqlite").is_file()), None)
    if destination.exists() or source is None:
        return
    _backup_sqlite(source / "state.sqlite", destination)
    for name in ("post.json", "comments.jsonl", "replies.jsonl", "root_pagination.jsonl", "collection_report.json"):
        old, new = source / name, destination.parent / name
        if old.is_file() and not new.exists():
            shutil.copy2(old, new)


class BrowserExperimentStopped(RuntimeError):
    """A bounded run stopped at an authentication or access boundary."""


@dataclass(frozen=True)
class BrowserExperimentConfig:
    target_url: str
    output_root: Path = Path("data")
    headless: bool = False
    max_root_pages: int = 3
    max_reply_pages: int = 10
    max_http_requests: int | None = None
    reply_parent_id: str | None = None
    duration_seconds: float = 120.0
    run_mode: str = "resume"
    reply_transport: str = "browser"
    reply_form_env: Path | None = None
    reply_allow_retarget: bool = False

    def __post_init__(self) -> None:
        if self.max_root_pages < 1:
            raise ValueError("max_root_pages must be at least 1")
        if self.max_reply_pages < 1:
            raise ValueError("max_reply_pages must be at least 1")
        if self.max_http_requests is not None and self.max_http_requests < 1:
            raise ValueError("max_http_requests must be at least 1")
        if self.reply_parent_id is not None and (
            not isinstance(self.reply_parent_id, str) or not self.reply_parent_id.strip()
        ):
            raise ValueError("reply_parent_id must be a non-empty string")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if self.reply_transport not in {"browser", "full-form"}:
            raise ValueError("reply_transport must be browser or full-form")
        if self.reply_transport == "full-form" and self.reply_form_env is None:
            raise ValueError("--reply-form-env is required for full-form replies")
        if self.run_mode not in {"resume", "refresh", "fresh"}:
            raise ValueError("run_mode must be resume, refresh, or fresh")


class BrowserCommentExperiment:
    def __init__(self, config: BrowserExperimentConfig) -> None:
        initialization_started = time.perf_counter()
        self.config = config
        self.full_form_transport: FullFormReplyTransport | None = None
        self.reference = parse_post_url(config.target_url)
        self.output_dir = config.output_root / self.reference.shortcode
        state_path = self.output_dir / "state.sqlite"
        _migrate_legacy_output(config.output_root, self.reference.shortcode, state_path)
        self.store = StateStore(state_path)
        self.started = time.monotonic()
        self.run_id = f"browser-{uuid.uuid4().hex}"
        self.scan_id = f"scan-{uuid.uuid4().hex}"
        self.media_id: str | None = None
        self.root_edge = "comments"
        self.is_refresh_scan = False
        self.run_started_at: str | None = None
        self.run_started = False
        self.post_saved = False
        self.root_pagination: list[dict[str, Any]] = []
        self.reply_pagination: list[dict[str, Any]] = []
        self.reply_observations: list[dict[str, Any]] = []
        self.reply_status_counts: dict[str, int] = {}
        self.reply_stop_reason: str | None = None
        self.previous_report: dict[str, Any] | None = None
        self.reported_count_semantics_validated = False
        self.root_pages = 0
        self.root_pages_this_run = 0
        self.reply_pages = 0
        self.duplicates = 0
        self.http_request_attempts = 0
        self.schema_errors: list[str] = []
        self.page_url: str | None = None
        self.page_title: str | None = None
        self.reported_comment_count: int | None = None
        self.root_protocol_complete = False
        self.legacy_observations: list[dict[str, Any]] = []
        self.legacy_observation_offset = 0
        self.reply_observation_offset = 0
        self.legacy_status_counts: dict[str, int] = {}
        self.legacy_app_id: str | None = None
        self.legacy_cookies: list[dict[str, Any]] = []
        self.legacy_stop_reason: str | None = None
        self.target_identity_verified: bool | None = None
        self.media_id_source: str | None = None
        self.root_cursor_expiration_restarted = False
        self.reply_expiration_restarts: list[str] = []
        self.request_start_intervals_ms: list[float] = []
        self.last_request_start: float | None = None
        self.pacing_sleep_count = 0
        self.pacing_requested_ms = 0.0
        self.pacing_actual_ms = 0.0
        self.normalization_ms = {"root": 0.0, "reply": 0.0}
        self.sqlite_timings_ms: list[dict[str, float]] = []
        self.handler_durations_ms: list[float] = []
        self.first_handler_started: float | None = None
        self.last_handler_finished: float | None = None
        self.crawler_run_started: float | None = None
        self.crawler_run_finished: float | None = None
        self.lifecycle_timings_ms: dict[str, float] = {}
        self._lifecycle_marks: dict[str, float] = {}
        self.response_records_this_run = 0
        self.unique_records_added_this_run = 0
        self.root_request_attempts_this_run = 0
        self.reply_request_attempts_this_run = 0
        self.export_ms = 0.0
        self.lifecycle_timings_ms["collector_initialization"] = (time.perf_counter() - initialization_started) * 1000

    def _request_budget_reached(self) -> bool:
        return (
            self.config.max_http_requests is not None
            and self.http_request_attempts >= self.config.max_http_requests
        )

    def _record_lifecycle_phase(self, name: str, started: float) -> None:
        self.lifecycle_timings_ms[name] = (time.perf_counter() - started) * 1000

    def _begin_store(self, media_id: str) -> None:
        if self.run_started:
            return
        self.media_id = str(media_id)
        latest_run = self.store.latest_run(self.media_id)
        self.previous_report = self.store.latest_report(self.media_id)
        if self.config.run_mode == "refresh":
            self.root_edge = "comments_refresh"
            self.is_refresh_scan = True
            self.store.reset_checkpoints(self.media_id, self.root_edge)
        elif self.config.run_mode == "fresh":
            self.store.reset_checkpoints(self.media_id)
        elif latest_run:
            self.scan_id = latest_run["scan_id"]
            report = latest_run.get("report") or {}
            if latest_run.get("mode") == "refresh" or report.get("root_checkpoint_edge") == "comments_refresh":
                self.root_edge = "comments_refresh"
                self.is_refresh_scan = True

        if self.config.run_mode != "fresh":
            checkpoint = self.store.checkpoint(self.media_id, self.root_edge)
            if checkpoint:
                self.root_pages = checkpoint["pages"]
                self.root_protocol_complete = (
                    checkpoint["complete"]
                    and checkpoint["termination_reason"] == "natural_exhaustion"
                )
                self.legacy_stop_reason = checkpoint["termination_reason"]
        if self.previous_report:
            reported = self.previous_report.get("reported_comment_count")
            self.reported_comment_count = reported if isinstance(reported, int) else None
            if not self.is_refresh_scan:
                observations = self.previous_report.get("legacy_request_observations")
                if isinstance(observations, list):
                    self.legacy_observations = observations.copy()
                status_counts = self.previous_report.get("http_response_status_distribution")
                if isinstance(status_counts, dict):
                    self.legacy_status_counts = {str(key): int(value) for key, value in status_counts.items()}
                self.target_identity_verified = self.previous_report.get("target_identity_verified")
                self.media_id_source = self.previous_report.get("media_id_source")
                self.duplicates = int(self.previous_report.get("duplicate_records", 0) or 0)
                transitions = self.previous_report.get("pagination_transitions")
                if isinstance(transitions, dict) and isinstance(transitions.get("root"), list):
                    self.root_pagination = transitions["root"].copy()
                    self.reply_pagination = transitions.get("replies", []).copy()
                observations = self.previous_report.get("reply_request_observations")
                if isinstance(observations, list):
                    self.reply_observations = observations.copy()
                reply_status_counts = self.previous_report.get("reply_http_response_status_distribution")
                if isinstance(reply_status_counts, dict):
                    self.reply_status_counts = {str(key): int(value) for key, value in reply_status_counts.items()}
        self.legacy_observation_offset = max(
            0, len(self.legacy_observations) - self.root_request_attempts_this_run
        )
        self.reply_observation_offset = len(self.reply_observations)
        stored_post = self.store.get_post(media_id=self.media_id)
        if stored_post:
            saved_count = stored_post["post"].get("comment_count")
            if isinstance(saved_count, int) and not isinstance(saved_count, bool):
                self.reported_comment_count = saved_count
            self.media_id_source = (
                stored_post["post"].get("media_id_source")
                or self.media_id_source
                or "requested_shortcode_surrogate"
            )
        self._save_post_metadata()
        stored_mode = "refresh" if self.is_refresh_scan else self.config.run_mode
        self.run_started_at = self.store.begin_run(
            self.run_id, self.scan_id, self.media_id, stored_mode
        )
        self.run_started = True
    def _save_post_metadata(self) -> None:
        if self.post_saved or not self.media_id:
            return
        source = "instagram_legacy_graphql"
        post = {
            "media_id": self.media_id,
            "media_id_source": self.media_id_source or "requested_shortcode_surrogate",
            "shortcode": self.reference.shortcode,
            "url": self.reference.canonical_url,
            "permalink": self.reference.canonical_url,
            "title": self.page_title,
            "metadata_complete": False,
            "source": source,
            "collected_at": utc_now(),
        }
        author = {"id": None, "username": None, "available": False, "source": source}
        self.store.save_post(
            media_id=self.media_id,
            shortcode=self.reference.shortcode,
            post=post,
            author=author,
        )
        if self.run_started:
            self.store.record_post_observation(self.run_id, self.media_id, post, author)
        self.post_saved = True

    def _save_response_metadata(self, observed_at: str | None = None) -> None:
        if not self.media_id:
            return
        stored = self.store.get_post(media_id=self.media_id)
        if not stored:
            return
        post = stored["post"]
        post["media_id_source"] = self.media_id_source or post.get("media_id_source")
        if self.reported_comment_count is not None:
            post.update({
                "comment_count": self.reported_comment_count,
                "comment_count_source": "legacy_graphql.edge_media_to_parent_comment.count",
                "comment_count_observed_at": observed_at or utc_now(),
            })
        self.store.save_post(
            media_id=self.media_id,
            shortcode=self.reference.shortcode,
            post=post,
            author=stored["author"],
        )
        current = self.store.get_post(media_id=self.media_id)
        if self.run_started and current and self.reported_comment_count is not None:
            self.store.record_post_observation(
                self.run_id, self.media_id, current["post"], current["author"],
                observed_at=current["post"].get("comment_count_observed_at"),
            )

    def _note_request_start(self) -> float:
        started = time.perf_counter()
        if self.last_request_start is not None:
            self.request_start_intervals_ms.append((started - self.last_request_start) * 1000)
        self.last_request_start = started
        return started

    async def _pace(self) -> None:
        self.pacing_sleep_count += 1
        self.pacing_requested_ms += 500
        started = time.perf_counter()
        await asyncio.sleep(0.5)
        self.pacing_actual_ms += (time.perf_counter() - started) * 1000

    async def _check_boundary(self, page: Any) -> None:
        self.page_url = str(page.url)
        lowered_url = self.page_url.lower()
        if any(marker in lowered_url for marker in _LOGIN_MARKERS):
            raise BrowserExperimentStopped("authentication_or_challenge")
        try:
            body_text = (await page.locator("body").inner_text(timeout=2000)).lower()
        except Exception:
            body_text = ""
        if any(marker in body_text for marker in _CHALLENGE_MARKERS):
            raise BrowserExperimentStopped("access_restriction")

    async def handle_page(self, context: PlaywrightCrawlingContext) -> None:
        started = time.perf_counter()
        if self.first_handler_started is None:
            self.first_handler_started = started
        try:
            page = context.page
            self.page_url = str(page.url)
            self.page_title = await page.title()
            await self._check_boundary(page)
            stored = self.store.get_post(shortcode=self.reference.shortcode)
            if stored:
                self._begin_store(stored["media_id"])
            await self._collect_legacy_graphql(page)
            if self.root_protocol_complete:
                await self._collect_replies(page)
        finally:
            finished = time.perf_counter()
            self.handler_durations_ms.append((finished - started) * 1000)
            self.last_handler_finished = finished

    async def _collect_legacy_graphql(self, page: Any) -> None:
        edge = self.root_edge
        checkpoint = self.store.checkpoint(self.media_id, edge) if self.media_id else None
        if (
            self.config.run_mode == "resume"
            and checkpoint
            and checkpoint["termination_reason"] == "cursor_expired"
        ):
            self.store.reset_checkpoints(self.media_id, edge)
            checkpoint = None
            self.root_pages = 0
            self.root_cursor_expiration_restarted = True
            self.root_pagination = []
            self.legacy_observations = []
            self.legacy_status_counts = {}
        if checkpoint and checkpoint["complete"]:
            self.root_pages = checkpoint["pages"]
            self.root_protocol_complete = checkpoint["termination_reason"] == "natural_exhaustion"
            self.legacy_stop_reason = checkpoint["termination_reason"]
            return
        if checkpoint and checkpoint["termination_reason"] in {
            "missing_cursor", "repeated_cursor", "cursor_expired", "unexpected_response",
            "unexpected_schema", "invalid_comment_record", "media_identity_changed",
        }:
            self.legacy_stop_reason = checkpoint["termination_reason"]
            return

        cursor = checkpoint["after_cursor"] if checkpoint else None
        pages = checkpoint["pages"] if checkpoint else 0
        if self._request_budget_reached():
            self.legacy_stop_reason = "request_budget"
            if self.media_id:
                self.store.set_termination(self.media_id, edge, self.legacy_stop_reason)
            return
        if pages >= self.config.max_root_pages:
            self.legacy_stop_reason = "page_budget"
            if self.media_id:
                self.store.set_termination(self.media_id, edge, self.legacy_stop_reason)
            return

        for _ in range(self.config.max_root_pages - pages):
            page_number = pages + 1
            if self._request_budget_reached():
                self.legacy_stop_reason = "request_budget"
                if self.media_id:
                    self.store.set_termination(self.media_id, edge, self.legacy_stop_reason)
                break
            try:
                self.http_request_attempts += 1
                self.root_request_attempts_this_run += 1
                request_started = self._note_request_start()
                result = await page.evaluate(
                    """async ({shortcode, after, appId, queryHash, first}) => {
                      const requestStartedAt = performance.now();
                      const variables = {shortcode, first};
                      if (after) variables.after = after;
                      const url = `https://www.instagram.com/graphql/query/?query_hash=${queryHash}&variables=${encodeURIComponent(JSON.stringify(variables))}`;
                      const controller = new AbortController();
                      const timer = setTimeout(() => controller.abort(), 20000);
                      try {
                        const response = await fetch(url, {
                          credentials: 'include',
                          referrer: location.href,
                          headers: {'Accept': '*/*', 'X-Requested-With': 'XMLHttpRequest', 'X-IG-App-ID': appId},
                          signal: controller.signal,
                        });
                        const headersReceivedAt = performance.now();
                        const body = await response.text();
                        const bodyFinishedAt = performance.now();
                        const resourceEntry = performance.getEntriesByName(response.url)
                          .filter(entry => entry.initiatorType === 'fetch' && entry.startTime >= requestStartedAt).at(-1);
                        const resourceTiming = resourceEntry ? {
                          dns_ms: Math.max(0, resourceEntry.domainLookupEnd - resourceEntry.domainLookupStart),
                          connect_ms: Math.max(0, resourceEntry.connectEnd - resourceEntry.connectStart),
                          tls_ms: resourceEntry.secureConnectionStart > 0
                            ? Math.max(0, resourceEntry.connectEnd - resourceEntry.secureConnectionStart) : null,
                          request_wait_ms: Math.max(0, resourceEntry.responseStart - resourceEntry.requestStart),
                          response_transfer_ms: Math.max(0, resourceEntry.responseEnd - resourceEntry.responseStart),
                          transfer_size_bytes: resourceEntry.transferSize,
                          encoded_body_size_bytes: resourceEntry.encodedBodySize,
                          decoded_body_size_bytes: resourceEntry.decodedBodySize,
                          next_hop_protocol: resourceEntry.nextHopProtocol || null,
                        } : null;
                        const observedAt = new Date().toISOString();
                        const contentType = response.headers.get('Content-Type') || 'unknown';
                        const decodeStartedAt = performance.now();
                        let payload = null;
                        try { payload = JSON.parse(body); } catch (_) {}
                        const decodedAt = performance.now();
                        const diagnostic = payload && typeof payload === 'object'
                          ? JSON.stringify({errors: payload.errors, error: payload.error, message: payload.message, status: payload.status})
                          : body.slice(0, 65536);
                        const lower = diagnostic.toLowerCase();
                        const cursorExpired = lower.includes('cursor') && (lower.includes('expired') || lower.includes('invalid'));
                        const boundary = response.status === 429 ? 'rate_limited'
                          : response.status === 401 || lower.includes('login_required') || lower.includes('/accounts/login') ? 'authentication_required'
                          : lower.includes('challenge_required') || lower.includes('checkpoint_required') || lower.includes('captcha') || lower.includes('verify its you') ? 'access_restriction'
                          : response.status === 403 ? 'access_denied'
                          : null;
                        return {status: response.status, contentType, bytes: new TextEncoder().encode(body).length,
                          json: payload !== null, payload, boundary, cursorExpired, observedAt, resourceTiming,
                          timingsMs: {headers: headersReceivedAt - requestStartedAt,
                            body: bodyFinishedAt - headersReceivedAt,
                            json_decode: decodedAt - decodeStartedAt,
                            network: bodyFinishedAt - requestStartedAt,
                            total: decodedAt - requestStartedAt}};
                      } catch (error) {
                        return {status: null, contentType: 'unknown', bytes: 0, json: false,
                          payload: null, boundary: error && error.name === 'AbortError' ? 'request_timeout' : 'network_error',
                          timingsMs: {network: performance.now() - requestStartedAt}};
                      } finally { clearTimeout(timer); }
                    }""",
                    {
                        "shortcode": self.reference.shortcode,
                        "after": cursor,
                        "appId": self.legacy_app_id,
                        "queryHash": _LEGACY_QUERY_HASH,
                        "first": _LEGACY_PAGE_SIZE,
                    },
                )
                evaluate_ms = (time.perf_counter() - request_started) * 1000
            except Exception as exc:
                self.legacy_stop_reason = "browser_request_error"
                detail = _safe_browser_error(exc)
                self.legacy_observations.append({
                    "page": page_number,
                    "status": None,
                    "content_type": "unknown",
                    "response_bytes": 0,
                    "json": False,
                    "request_error": detail,
                })
                self.schema_errors.append(f"page-{page_number}:{detail}")
                if self.media_id:
                    self.store.set_termination(self.media_id, edge, self.legacy_stop_reason)
                break

            status = result.get("status")
            request_timing = dict(result.get("timingsMs")) if isinstance(result.get("timingsMs"), dict) else {}
            request_timing["browser_evaluate_ms"] = round(evaluate_ms, 3)
            js_total = request_timing.get("total")
            if isinstance(js_total, (int, float)):
                request_timing["browser_evaluate_overhead_ms"] = round(max(0.0, evaluate_ms - js_total), 3)
            status_key = str(status) if status is not None else "network_error"
            self.legacy_status_counts[status_key] = self.legacy_status_counts.get(status_key, 0) + 1
            self.legacy_observations.append({
                "page": page_number,
                "status": status,
                "content_type": str(result.get("contentType", "unknown")).split(";", 1)[0].lower(),
                "response_bytes": int(result.get("bytes", 0) or 0),
                "json": result.get("json") is True,
                "observed_at": result.get("observedAt"),
                "request_timing_ms": request_timing,
                "resource_timing": result.get("resourceTiming") if isinstance(result.get("resourceTiming"), dict) else None,
            })
            if result.get("boundary") or status != 200:
                self.legacy_stop_reason = result.get("boundary") or "http_error"
                if self.media_id:
                    self.store.set_termination(self.media_id, edge, self.legacy_stop_reason)
                break
            if result.get("cursorExpired"):
                self.legacy_stop_reason = "cursor_expired"
                if self.media_id:
                    self.store.set_termination(self.media_id, edge, self.legacy_stop_reason)
                break
            if result.get("json") is not True or not isinstance(result.get("payload"), dict):
                self.legacy_stop_reason = "unexpected_response"
                if self.media_id:
                    self.store.set_termination(self.media_id, edge, self.legacy_stop_reason)
                break

            payload = result["payload"]
            self.legacy_observations[-1]["response_shape"] = _legacy_shape(payload)
            media = payload.get("data", {}).get("shortcode_media") if isinstance(payload.get("data"), dict) else None
            if isinstance(media, dict) and isinstance(media.get("shortcode"), str):
                self.target_identity_verified = media["shortcode"] == self.reference.shortcode
            self.media_id_source = (
                "response" if isinstance(media, dict) and media.get("id") is not None
                else "requested_shortcode_surrogate"
            )
            try:
                normalization_started = time.perf_counter()
                media_id, reported_count, records, embedded, has_next, next_cursor = _legacy_page(
                    payload, self.reference.shortcode
                )
                normalization_elapsed = (time.perf_counter() - normalization_started) * 1000
                self.normalization_ms["root"] += normalization_elapsed
                self.legacy_observations[-1]["normalization_ms"] = round(normalization_elapsed, 3)
            except FixtureError as exc:
                self.legacy_stop_reason = "unexpected_response"
                self.schema_errors.append(f"page-{page_number}:{exc}")
                if self.media_id:
                    self.store.set_termination(self.media_id, edge, self.legacy_stop_reason)
                break
            if self.media_id is not None and self.media_id != media_id:
                self.legacy_stop_reason = "media_identity_changed"
                self.store.set_termination(self.media_id, edge, self.legacy_stop_reason)
                break

            self._begin_store(media_id)
            self._save_post_metadata()
            if reported_count is not None:
                self.reported_comment_count = reported_count
            self._save_response_metadata(result.get("observedAt"))
            try:
                saved = self.store.save_page(
                    media_id=media_id,
                    edge=edge,
                    parent_id=None,
                    records=[*records, *embedded],
                    run_id=self.run_id,
                    scan_id=self.scan_id,
                    next_cursor=next_cursor,
                    has_next=has_next,
                    current_cursor=cursor,
                )
            except ValueError as exc:
                self.legacy_stop_reason = "invalid_comment_record"
                self.root_partial = True
                self.schema_errors.append(f"page-{page_number}:{type(exc).__name__}")
                self.store.set_termination(media_id, edge, self.legacy_stop_reason)
                break
            self.legacy_observations[-1]["sqlite_timings_ms"] = saved["timings_ms"]
            self.sqlite_timings_ms.append(saved["timings_ms"])
            observed_records = len(records) + len(embedded)
            self.response_records_this_run += observed_records
            self.unique_records_added_this_run += observed_records - saved["duplicates"]
            self.root_pages += 1
            self.root_pages_this_run += 1
            pages = saved["pages"]
            self.duplicates += saved["duplicates"]
            self.root_protocol_complete = saved["complete"]
            self.root_pagination.append({
                "page": page_number,
                "request_cursor_present": cursor is not None,
                "next_cursor_present": next_cursor is not None,
                "has_next_page": has_next,
                "edges": len(records),
                "embedded_replies": len(embedded),
            })
            if saved["termination_reason"]:
                self.legacy_stop_reason = saved["termination_reason"]
                break
            cursor = next_cursor
            if self._request_budget_reached():
                self.legacy_stop_reason = "request_budget"
                self.store.set_termination(media_id, edge, self.legacy_stop_reason)
                break
            if pages == self.config.max_root_pages:
                self.legacy_stop_reason = "page_budget"
                self.store.set_termination(media_id, edge, self.legacy_stop_reason)
                break
            await self._pace()

    async def _collect_replies(self, page: Any) -> None:
        if not self.media_id:
            return
        media_id = self.media_id
        request_media_id = (
            decode_shortcode(self.reference.shortcode)
            if media_id == f"shortcode:{self.reference.shortcode}" else media_id
        )
        for root in self.store.comments(media_id, parent_id=None):
            parent_id = root["id"]
            if self.config.reply_parent_id is not None and parent_id != self.config.reply_parent_id:
                continue
            reported_count = root.get("reported_reply_count")
            if not isinstance(reported_count, int) or reported_count <= 0:
                continue
            checkpoint = self.store.checkpoint(media_id, "replies", parent_id)
            if checkpoint and checkpoint["complete"]:
                continue
            if checkpoint and checkpoint["termination_reason"] == "cursor_expired" and self.config.run_mode == "resume":
                self.store.reset_checkpoints(media_id, "replies", parent_id)
                self.reply_expiration_restarts.append(parent_id)
                checkpoint = None
                self.reply_pagination = [
                    row for row in self.reply_pagination if row.get("parent_comment_id") != parent_id
                ]
                self.reply_observations = [
                    row for row in self.reply_observations if row.get("parent_comment_id") != parent_id
                ]
            if checkpoint and checkpoint["termination_reason"] in {
                "missing_cursor", "repeated_cursor", "unexpected_schema",
                "unavailable", "parent_mismatch",
            }:
                continue
            cursor = checkpoint["after_cursor"] if checkpoint else None
            pages = checkpoint["pages"] if checkpoint else 0
            if pages >= self.config.max_reply_pages:
                self.store.set_termination(media_id, "replies", "page_budget", parent_id)
                continue
            if self._request_budget_reached():
                self.reply_stop_reason = "request_budget"
                if pages:
                    self.store.set_termination(media_id, "replies", self.reply_stop_reason, parent_id)
                break

            for _ in range(self.config.max_reply_pages - pages):
                page_number = pages + 1
                if self._request_budget_reached():
                    self.reply_stop_reason = "request_budget"
                    if pages:
                        self.store.set_termination(media_id, "replies", self.reply_stop_reason, parent_id)
                    break
                if cursor is None:
                    operation = _CHILD_COMMENTS_INITIAL_OPERATION
                    doc_id = _CHILD_COMMENTS_DOC_ID
                    variables = {
                        "after": None,
                        "before": None,
                        "media_id": request_media_id,
                        "parent_comment_id": parent_id,
                        "is_chronological": None,
                        "first": None,
                        "last": None,
                        "__relay_internal__pv__PolarisIsLoggedInrelayprovider": True,
                    }
                else:
                    operation = _CHILD_COMMENTS_CONTINUATION_OPERATION
                    doc_id = _CHILD_COMMENTS_CONTINUATION_DOC_ID
                    variables = {
                        "after": cursor,
                        "before": None,
                        "first": _REPLY_PAGE_SIZE,
                        "is_chronological": None,
                        "last": None,
                        "media_id": request_media_id,
                        "parent_comment_id": parent_id,
                        "__relay_internal__pv__PolarisIsLoggedInrelayprovider": True,
                    }
                try:
                    self.http_request_attempts += 1
                    self.reply_request_attempts_this_run += 1
                    request_started = self._note_request_start()
                    if self.full_form_transport is not None:
                        result = await asyncio.to_thread(
                            self.full_form_transport.fetch,
                            request_media_id, parent_id, cursor,
                            referer=self.reference.canonical_url,
                        )
                        adapter_ms = (time.perf_counter() - request_started) * 1000
                    else:
                        result = await page.evaluate(
                        """async ({docId, operation, variables, appId, csrfToken}) => {
                          const requestStartedAt = performance.now();
                          const params = new URLSearchParams();
                          params.set('doc_id', docId);
                          params.set('variables', JSON.stringify(variables));
                          const controller = new AbortController();
                          const timer = setTimeout(() => controller.abort(), 20000);
                          try {
                            const response = await fetch('/api/graphql', {
                              method: 'POST', credentials: 'include', referrer: location.href,
                              headers: {'Accept': '*/*', 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                                'X-Requested-With': 'XMLHttpRequest', 'X-IG-App-ID': appId,
                                'X-FB-Friendly-Name': operation,
                                ...(csrfToken ? {'X-CSRFToken': csrfToken} : {})},
                              body: params.toString(), signal: controller.signal,
                            });
                            const headersReceivedAt = performance.now();
                            const body = await response.text();
                            const bodyFinishedAt = performance.now();
                            const resourceEntry = performance.getEntriesByName(response.url)
                              .filter(entry => entry.initiatorType === 'fetch' && entry.startTime >= requestStartedAt).at(-1);
                            const resourceTiming = resourceEntry ? {
                              dns_ms: Math.max(0, resourceEntry.domainLookupEnd - resourceEntry.domainLookupStart),
                              connect_ms: Math.max(0, resourceEntry.connectEnd - resourceEntry.connectStart),
                              tls_ms: resourceEntry.secureConnectionStart > 0
                                ? Math.max(0, resourceEntry.connectEnd - resourceEntry.secureConnectionStart) : null,
                              request_wait_ms: Math.max(0, resourceEntry.responseStart - resourceEntry.requestStart),
                              response_transfer_ms: Math.max(0, resourceEntry.responseEnd - resourceEntry.responseStart),
                              transfer_size_bytes: resourceEntry.transferSize,
                              encoded_body_size_bytes: resourceEntry.encodedBodySize,
                              decoded_body_size_bytes: resourceEntry.decodedBodySize,
                              next_hop_protocol: resourceEntry.nextHopProtocol || null,
                            } : null;
                            const observedAt = new Date().toISOString();
                            const contentType = response.headers.get('Content-Type') || 'unknown';
                            const decodeStartedAt = performance.now();
                            let payload = null;
                            try { payload = JSON.parse(body); } catch (_) {}
                            const decodedAt = performance.now();
                            const sample = body.slice(0, 16384);
                            const htmlSignals = {
                              doctype: /<!doctype\\s+html/i.test(sample),
                              html_element: /<html(?:\\s|>)/i.test(sample),
                              instagram_title: /<title[^>]*>\\s*instagram\\s*<\\/title>/i.test(sample),
                              app_assets: /<(?:script|link)\\b/i.test(sample) && /(?:instagram|cdninstagram|static)/i.test(sample),
                              splash_screen: /splash.?screen/i.test(sample),
                              login_marker: /log in to instagram|login required/i.test(body.slice(0, 4096)),
                              challenge_marker: /challenge_required|checkpoint_required|captcha|verify its you/i.test(body.slice(0, 4096)),
                            };
                            const diagnostic = payload && typeof payload === 'object'
                              ? JSON.stringify({errors: payload.errors, error: payload.error, message: payload.message, status: payload.status})
                              : body.slice(0, 4096);
                            const lower = diagnostic.toLowerCase();
                            const boundary = response.status === 429 ? 'rate_limited'
                              : response.status === 401 || lower.includes('login_required') ? 'authentication_required'
                              : lower.includes('challenge_required') || lower.includes('checkpoint_required') || lower.includes('captcha') || lower.includes('verify its you') ? 'access_restriction'
                              : response.status === 403 ? 'access_denied' : null;
                            return {status: response.status, contentType, bytes: new TextEncoder().encode(body).length,
                              json: payload !== null, payload, boundary, htmlSignals, observedAt, resourceTiming,
                              timingsMs: {headers: headersReceivedAt - requestStartedAt,
                                body: bodyFinishedAt - headersReceivedAt,
                                json_decode: decodedAt - decodeStartedAt,
                                network: bodyFinishedAt - requestStartedAt,
                                total: decodedAt - requestStartedAt},
                              cursorExpired: lower.includes('cursor') && (lower.includes('expired') || lower.includes('invalid')),
                              unavailable: lower.includes('comment') && (lower.includes('not found') || lower.includes('unavailable') || lower.includes('deleted')),
                              graphqlError: !!(payload && Array.isArray(payload.errors) && payload.errors.length)};
                          } catch (error) {
                            return {status: null, contentType: 'unknown', bytes: 0, json: false, payload: null,
                              boundary: error && error.name === 'AbortError' ? 'request_timeout' : 'network_error',
                              timingsMs: {network: performance.now() - requestStartedAt}};
                          } finally { clearTimeout(timer); }
                        }""",
                            {
                                "docId": doc_id,
                                "operation": operation,
                                "variables": variables,
                                "appId": self.legacy_app_id,
                                "csrfToken": next((cookie["value"] for cookie in self.legacy_cookies if cookie["name"] == "csrftoken"), None),
                            },
                        )
                        adapter_ms = (time.perf_counter() - request_started) * 1000
                except Exception as exc:
                    self.reply_observations.append({"parent_comment_id": parent_id, "page": page_number, "error": _safe_browser_error(exc)})
                    self.store.set_termination(media_id, "replies", "network_error", parent_id)
                    break

                request_timing = dict(result.get("timingsMs")) if isinstance(result.get("timingsMs"), dict) else {}
                if self.full_form_transport is None:
                    request_timing["browser_evaluate_ms"] = round(adapter_ms, 3)
                    js_total = request_timing.get("total")
                    if isinstance(js_total, (int, float)):
                        request_timing["browser_evaluate_overhead_ms"] = round(max(0.0, adapter_ms - js_total), 3)
                else:
                    request_timing["transport_call_ms"] = round(adapter_ms, 3)
                status = result.get("status")
                status_key = str(status) if status is not None else str(result.get("boundary") or "network_error")
                self.reply_status_counts[status_key] = self.reply_status_counts.get(status_key, 0) + 1
                self.reply_observations.append({
                    "parent_comment_id": parent_id,
                    "page": page_number,
                    "operation": operation,
                    "doc_id": doc_id,
                    "method": "POST",
                    "endpoint": "/api/graphql",
                    "transport": self.config.reply_transport,
                    "authentication_evidence": "configured_cookie_session_supplied; endpoint acceptance not established",
                    "status": status,
                    "content_type": str(result.get("contentType", "unknown")).split(";", 1)[0].lower(),
                    "response_bytes": int(result.get("bytes", 0) or 0),
                    "json": result.get("json") is True,
                    "observed_at": result.get("observedAt"),
                    "request_timing_ms": request_timing,
                    "resource_timing": result.get("resourceTiming") if isinstance(result.get("resourceTiming"), dict) else None,
                    "response_classification": _classify_child_response(
                        str(result.get("contentType", "unknown")),
                        is_json=result.get("json") is True,
                        html_signals=result.get("htmlSignals") if isinstance(result.get("htmlSignals"), dict) else None,
                    ),
                    "html_signals": result.get("htmlSignals", {}),
                })
                boundary = result.get("boundary")
                if boundary or status != 200:
                    reason = boundary or "http_error"
                    self.store.set_termination(media_id, "replies", reason, parent_id)
                    if reason in {"rate_limited", "authentication_required", "access_restriction", "access_denied"}:
                        self.reply_stop_reason = reason
                    break
                if result.get("json") is not True or not isinstance(result.get("payload"), dict):
                    self.store.set_termination(media_id, "replies", "unexpected_schema", parent_id)
                    self.reply_observations[-1]["failure_reason"] = "non_json_or_missing_payload"
                    self.reply_stop_reason = "unexpected_schema"
                    break
                if result.get("cursorExpired"):
                    self.store.set_termination(media_id, "replies", "cursor_expired", parent_id)
                    break
                if result.get("unavailable"):
                    self.store.set_termination(media_id, "replies", "unavailable", parent_id)
                    break
                if result.get("graphqlError"):
                    self.store.set_termination(media_id, "replies", "graphql_error", parent_id)
                    self.reply_stop_reason = "graphql_error"
                    break

                try:
                    normalization_started = time.perf_counter()
                    records, has_next, next_cursor = _child_page(
                        result["payload"], media_id, parent_id, source_operation=operation
                    )
                    normalization_elapsed = (time.perf_counter() - normalization_started) * 1000
                    self.normalization_ms["reply"] += normalization_elapsed
                    self.reply_observations[-1]["normalization_ms"] = round(normalization_elapsed, 3)
                    saved = self.store.save_page(
                        media_id=media_id, edge="replies", parent_id=parent_id, records=records,
                        run_id=self.run_id, scan_id=self.scan_id, next_cursor=next_cursor,
                        has_next=has_next, current_cursor=cursor,
                    )
                    self.reply_observations[-1]["sqlite_timings_ms"] = saved["timings_ms"]
                    self.sqlite_timings_ms.append(saved["timings_ms"])
                except FixtureError as exc:
                    reason = "parent_mismatch" if "parent relationship" in str(exc) else "unexpected_schema"
                    self.store.set_termination(media_id, "replies", reason, parent_id)
                    self.reply_observations[-1]["error"] = reason
                    if reason == "unexpected_schema":
                        self.reply_stop_reason = reason
                        break
                    break
                except ValueError:
                    self.store.set_termination(media_id, "replies", "invalid_comment_record", parent_id)
                    break

                pages = saved["pages"]
                self.response_records_this_run += len(records)
                self.unique_records_added_this_run += len(records) - saved["duplicates"]
                self.reply_pages += 1
                self.duplicates += saved["duplicates"]
                self.reply_pagination.append({
                    "parent_comment_id": parent_id,
                    "page": pages,
                    "operation": operation,
                    "doc_id": doc_id,
                    "request_cursor_present": cursor is not None,
                    "next_cursor_present": next_cursor is not None,
                    "has_next_page": has_next,
                    "edges": len(records),
                })
                if saved["termination_reason"]:
                    break
                cursor = next_cursor
                if pages >= self.config.max_reply_pages:
                    reason = "request_budget" if self._request_budget_reached() else "page_budget"
                    self.store.set_termination(media_id, "replies", reason, parent_id)
                    if reason == "request_budget":
                        self.reply_stop_reason = reason
                    break
                if self._request_budget_reached():
                    self.store.set_termination(media_id, "replies", "request_budget", parent_id)
                    self.reply_stop_reason = "request_budget"
                    break
                await self._pace()
            if self.reply_stop_reason:
                break
            await self._pace()

    def _write_outputs(self, report: dict[str, Any]) -> None:
        export_started = time.perf_counter()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.root_pagination:
            atomic_write_jsonl(self.output_dir / "root_pagination.jsonl", self.root_pagination)
        if self.media_id:
            post = self.store.get_post(media_id=self.media_id)
            if post:
                atomic_write_json(self.output_dir / "post.json", post["post"])
                records = self.store.all_comments(self.media_id)
                roots = [record for record in records if record.get("parent_id") is None]
                replies = [record for record in records if record.get("parent_id") is not None]
                replies_by_parent: dict[str, list[dict[str, Any]]] = {}
                for reply in replies:
                    replies_by_parent.setdefault(reply["parent_id"], []).append(reply)
                atomic_write_jsonl(self.output_dir / "comments.jsonl", roots)
                atomic_write_jsonl(self.output_dir / "replies.jsonl", replies)
                atomic_write_json(
                    self.output_dir / "comment_tree.json",
                    {"post": post["post"], "roots": [
                        {**root, "replies": replies_by_parent.get(root["id"], [])}
                        for root in roots
                    ]},
                )
        if self.reply_pagination:
            atomic_write_jsonl(self.output_dir / "reply_pagination.jsonl", self.reply_pagination)
        self.export_ms = (time.perf_counter() - export_started) * 1000
        if isinstance(report.get("performance"), dict):
            report["performance"]["export_files_ms_excluding_report_json"] = round(self.export_ms, 3)
        atomic_write_json(self.output_dir / "collection_report.json", report)

    def report(self, termination_reason: str) -> dict[str, Any]:
        report_started = time.perf_counter()
        root_rows: list[dict[str, Any]] = []
        reply_rows: list[dict[str, Any]] = []
        root_checkpoint = None
        if self.media_id:
            root_rows = self.store.comments(self.media_id, parent_id=None)
            reply_rows = [record for record in self.store.all_comments(self.media_id) if record.get("parent_id") is not None]
            root_checkpoint = self.store.checkpoint(self.media_id, self.root_edge)
            if root_checkpoint:
                self.root_pages = root_checkpoint["pages"]
                self.root_protocol_complete = (
                    root_checkpoint["complete"]
                    and root_checkpoint["termination_reason"] == "natural_exhaustion"
                )

        reply_by_parent: dict[str, list[dict[str, Any]]] = {}
        for reply in reply_rows:
            reply_by_parent.setdefault(reply["parent_id"], []).append(reply)
        reply_branches = []
        roots_with_unknown_reply_count = 0
        for root in root_rows:
            reported = root.get("reported_reply_count")
            if isinstance(reported, bool) or not isinstance(reported, int):
                roots_with_unknown_reply_count += 1
                continue
            if reported <= 0:
                continue
            parent_id = root["id"]
            checkpoint = self.store.checkpoint(self.media_id, "replies", parent_id) if self.media_id else None
            branch_replies = reply_by_parent.get(parent_id, [])
            unique_count = len({row["id"] for row in branch_replies})
            difference = reported - unique_count
            protocol_complete = bool(
                checkpoint
                and checkpoint["complete"]
                and checkpoint["termination_reason"] == "natural_exhaustion"
            )
            count_matches = unique_count == reported
            request_attempted = bool(
                (checkpoint and checkpoint["pages"] > 0)
                or any(row.get("parent_comment_id") == parent_id for row in self.reply_observations)
            )
            reply_branches.append({
                "parent_comment_id": parent_id,
                "reported_reply_count": reported,
                "unique_reply_count": unique_count,
                "pages_observed": checkpoint["pages"] if checkpoint else 0,
                "last_successful_page": checkpoint["last_successful_page"] if checkpoint else 0,
                "termination_reason": checkpoint["termination_reason"] if checkpoint else "not_attempted",
                "protocol_complete": protocol_complete,
                "request_attempted": request_attempted,
                "reported_count_difference": difference,
                "status": "COMPLETE" if protocol_complete else ("PARTIAL" if request_attempted else "NOT_ATTEMPTED"),
            })
        replies_complete = not roots_with_unknown_reply_count and all(
            branch["protocol_complete"] for branch in reply_branches
        )
        root_count = len(root_rows)
        reply_count = len(reply_rows)
        unique_count = root_count + reply_count
        count_consistent = (
            unique_count == self.reported_comment_count
            if self.reported_comment_count is not None else None
        )
        unresolved_difference = (
            self.reported_comment_count - unique_count
            if self.reported_comment_count is not None else None
        )
        root_termination = root_checkpoint["termination_reason"] if root_checkpoint else termination_reason
        overall_termination = (
            self.reply_stop_reason or ("reply_branches_partial" if not replies_complete else root_termination)
        )
        reply_pages = sum(branch["pages_observed"] for branch in reply_branches)
        parents_attempted = sum(branch["request_attempted"] for branch in reply_branches)
        total_reported_replies = sum(branch["reported_reply_count"] for branch in reply_branches)
        reply_counts_consistent = all(
            branch["reported_reply_count"] == branch["unique_reply_count"]
            for branch in reply_branches
        )
        root_ids = {row["id"] for row in root_rows}
        linked_replies = [row for row in reply_rows if row.get("parent_id") in root_ids]
        embedded_replies = sum(
            row.get("source_operation") == "instagram_legacy_graphql_embedded_reply"
            for row in reply_rows
        )
        initial_operation_replies = sum(
            row.get("source_operation") == _CHILD_COMMENTS_INITIAL_OPERATION for row in reply_rows
        )
        continuation_operation_replies = sum(
            row.get("source_operation") == _CHILD_COMMENTS_CONTINUATION_OPERATION for row in reply_rows
        )
        operation_replies = initial_operation_replies + continuation_operation_replies
        multi_page_branch_complete = any(
            branch["pages_observed"] > 1 and branch["protocol_complete"] for branch in reply_branches
        )
        stored_post = self.store.get_post(media_id=self.media_id) if self.media_id else None
        post_metadata = stored_post["post"] if stored_post else {}
        author_metadata = stored_post["author"] if stored_post else {}
        observed_post_metadata = {
            "stable_media_id": self.media_id if self.media_id_source == "response" else None,
            "shortcode": post_metadata.get("shortcode"),
            "canonical_permalink": post_metadata.get("permalink"),
            "owner_id": author_metadata.get("id"),
            "owner_username": author_metadata.get("username"),
            "caption": post_metadata.get("caption"),
            "publication_timestamp": post_metadata.get("publication_timestamp"),
            "media_type": post_metadata.get("media_type"),
            "like_count": post_metadata.get("like_count"),
            "comment_count": self.reported_comment_count,
            "carousel_children": post_metadata.get("carousel_children"),
            "media_dimensions": post_metadata.get("media_dimensions"),
            "reel_metadata": post_metadata.get("reel_metadata"),
        }
        scan_changes = (
            self.store.scan_changes(
                self.media_id, self.scan_id, complete=self.root_protocol_complete
            )
            if self.media_id and self.is_refresh_scan else None
        )
        report_collected_at = utc_now()
        runtime_seconds = round(time.monotonic() - self.started, 3)
        last_successful = self.store.latest_successful_run(self.media_id) if self.media_id else None
        last_successful_refresh = (
            self.store.latest_successful_run(self.media_id, mode="refresh")
            if self.media_id else None
        )
        collection_completed_now = self.root_protocol_complete and self.root_pages_this_run > 0
        last_successful_at = (
            report_collected_at if collection_completed_now
            else last_successful["ended_at"] if last_successful else None
        )
        last_refresh_at = (
            report_collected_at if self.is_refresh_scan and self.root_protocol_complete and self.root_pages_this_run > 0
            else last_successful_refresh["ended_at"] if last_successful_refresh else None
        )
        count_history = self.store.reported_count_history(self.media_id) if self.media_id else []
        observations = [
            *self.legacy_observations[self.legacy_observation_offset:],
            *self.reply_observations[self.reply_observation_offset:],
        ]
        current_reply_observations = self.reply_observations[self.reply_observation_offset:]
        transport_success = (
            None if self.http_request_attempts == 0 else
            len(observations) == self.http_request_attempts
            and all(item.get("status") == 200 and item.get("json") is True for item in observations)
        )
        failed_run_reasons = {
            "browser_start_failed", "crawler_error", "experiment_timeout", "browser_request_error",
            "network_error", "request_timeout", "http_error", "rate_limited",
            "authentication_required", "authentication_or_challenge", "access_restriction",
            "access_denied", "unexpected_response", "unexpected_schema", "graphql_error",
            "parent_mismatch", "unavailable", "invalid_comment_record", "media_identity_changed",
            "missing_cursor", "repeated_cursor", "cursor_expired",
        }
        operational_failure = bool(
            termination_reason in failed_run_reasons
            or self.legacy_stop_reason in failed_run_reasons
            or self.reply_stop_reason in failed_run_reasons
            or root_termination in failed_run_reasons
            or any(branch["termination_reason"] in failed_run_reasons for branch in reply_branches)
            or self.schema_errors
        )
        traversal_partial = not (self.root_protocol_complete and replies_complete)
        collection_partial = traversal_partial or operational_failure
        report = {
            "url": self.reference.canonical_url,
            "canonical_url": _safe_url(self.page_url or self.reference.canonical_url),
            "page_title": self.page_title,
            "shortcode": self.reference.shortcode,
            "media_id": self.media_id,
            "browser_backend": "PlaywrightBrowserPlugin via Crawlee PlaywrightCrawler",
            "session_authentication_status": "cookie_session_supplied",
            "collection_method": "legacy_graphql_get",
            "query_hash": _LEGACY_QUERY_HASH,
            "run_mode": "refresh" if self.is_refresh_scan else self.config.run_mode,
            "run_id": self.run_id,
            "scan_id": self.scan_id,
            "run_started_at": self.run_started_at,
            "last_successful_collection_at": last_successful_at,
            "last_refresh_at": last_refresh_at,
            "root_checkpoint_edge": self.root_edge,
            "target_identity_verified": self.target_identity_verified,
            "media_id_source": self.media_id_source,
            "legacy_request_observations": self.legacy_observations,
            "root_pages_observed": self.root_pages,
            "root_comments_collected": root_count,
            "unique_roots": root_count,
            "reply_pages_observed": reply_pages,
            "replies_collected": reply_count,
            "unique_replies": reply_count,
            "embedded_replies_collected": embedded_replies,
            "reply_records_from_child_operation": operation_replies,
            "reply_records_by_operation": {
                _CHILD_COMMENTS_INITIAL_OPERATION: initial_operation_replies,
                _CHILD_COMMENTS_CONTINUATION_OPERATION: continuation_operation_replies,
            },
            "orphan_reply_records": reply_count - len(linked_replies),
            "unique_comment_ids": unique_count,
            "duplicate_records": self.duplicates,
            "total_http_requests": len(self.legacy_observations) + len(self.reply_observations),
            "http_requests_this_run": self.http_request_attempts,
            "max_http_requests_per_run": self.config.max_http_requests,
            "request_budget_exhausted": bool(
                self.legacy_stop_reason == "request_budget" or self.reply_stop_reason == "request_budget"
            ),
            "reply_parents_attempted_this_run": len({
                row.get("parent_comment_id") for row in current_reply_observations
                if isinstance(row.get("parent_comment_id"), str)
            }),
            "http_request_count_scope": "Root and child GraphQL fetch attempts; browser navigation and page resources are excluded.",
            "http_response_status_distribution": self.legacy_status_counts,
            "reply_http_response_status_distribution": self.reply_status_counts,
            "reply_request_observations": self.reply_observations,
            "reply_operation": _CHILD_COMMENTS_INITIAL_OPERATION,
            "reply_doc_id": _CHILD_COMMENTS_DOC_ID,
            "reply_continuation_operation": _CHILD_COMMENTS_CONTINUATION_OPERATION,
            "reply_continuation_doc_id": _CHILD_COMMENTS_CONTINUATION_DOC_ID,
            "reply_request_method": "POST",
            "reply_request_endpoint": "https://www.instagram.com/api/graphql",
            "reply_request_linkage": (
                "end_cursor_continuation_live_qualified; collector_request_path_not_live_requalified"
            ),
            "reply_page_size": _REPLY_PAGE_SIZE,
            "reply_is_chronological": None,
            "reply_is_chronological_status": "null supplied in linked qualification; ordering unspecified",
            "root_cursor_expiration_restarted": self.root_cursor_expiration_restarted,
            "reply_cursor_expiration_restarted_parents": self.reply_expiration_restarts,
            "reply_parents_advertising_replies": len(reply_branches),
            "reply_parents_attempted": parents_attempted,
            "complete_parent_branches": sum(branch["status"] == "COMPLETE" for branch in reply_branches),
            "partial_parent_branches": sum(branch["status"] == "PARTIAL" for branch in reply_branches),
            "unattempted_parent_branches": sum(branch["status"] == "NOT_ATTEMPTED" for branch in reply_branches),
            "roots_with_unknown_reply_count": roots_with_unknown_reply_count,
            "roots_with_incomplete_reply_branches": sum(
                branch["status"] != "COMPLETE" for branch in reply_branches
            ),
            "reported_reply_count_total": total_reported_replies,
            "reply_branches": reply_branches,
            "pagination_transitions": {"root": self.root_pagination, "replies": self.reply_pagination},
            "termination_reason": overall_termination,
            "root_termination_reason": root_termination,
            "wall_clock_seconds": runtime_seconds,
            "total_runtime_seconds": runtime_seconds,
            "metadata_complete": bool(stored_post and stored_post["post"].get("metadata_complete") is True),
            "post_metadata_observed": bool(self.media_id and self.post_saved and self.page_title),
            "post_metadata_fields_observed": [
                key for key, value in observed_post_metadata.items() if value is not None
            ],
            "post_metadata_collection_scope": (
                "shortcode and permalink come from the requested URL; comment_count comes from "
                "the legacy root response; the archived root operation did not return other post fields"
            ),
            "root_protocol_complete": self.root_protocol_complete,
            "root_cursor_chain_complete": bool(
                root_checkpoint
                and root_checkpoint["complete"]
                and root_checkpoint["termination_reason"] == "natural_exhaustion"
            ),
            "replies_protocol_complete": replies_complete,
            "reply_collection_policy": "sequential_child_operation_after_root_completion",
            "reply_batch_policy": "one_pending_parent_at_a_time_in_root_order; completed_branches_skipped",
            "reply_reported_counts_consistent": reply_counts_consistent,
            "reported_count_consistent": count_consistent,
            "reported_comment_count": self.reported_comment_count,
            "reported_count_history": count_history,
            "combined_unique_count": unique_count,
            "unresolved_count_difference": unresolved_difference,
            "refresh_delta": (
                {
                    "status": "COMPLETE" if self.root_protocol_complete else "PARTIAL",
                    "previously_observed_count": scan_changes["previously_observed_count"],
                    "observed_count": scan_changes["observed_count"],
                    "new_comment_ids": scan_changes["new_ids"],
                    "new_comment_count": len(scan_changes["new_ids"]),
                    "updated_records": scan_changes["updated_fields"],
                    "updated_record_count": len(scan_changes["updated_fields"]),
                    "not_observed_once_ids": scan_changes["not_observed_ids"],
                    "not_observed_once_count": (
                        len(scan_changes["not_observed_ids"])
                        if scan_changes["not_observed_ids"] is not None else None
                    ),
                    "not_observed_means_deleted": False,
                    "coverage_note": (
                        "Sequential traversal of the complete saved ranked cursor chain; ordering is not "
                        "chronological, so a bounded page budget cannot establish complete discovery."
                    ),
                }
                if scan_changes is not None else None
            ),
            "reported_count_semantics_validated": self.reported_count_semantics_validated,
            "collection_status": {
                "TRANSPORT_SUCCESS": transport_success,
                "ROOT_PROTOCOL_COMPLETE": self.root_protocol_complete,
                "REPLIES_PROTOCOL_COMPLETE": replies_complete,
                "COUNT_CONSISTENT": count_consistent,
                "SOURCE_COVERAGE_UNKNOWN": True,
                "COLLECTION_PARTIAL": collection_partial,
                "TRAVERSAL_PARTIAL": traversal_partial,
                "OPERATIONAL_FAILURE": operational_failure,
            },
            "operational_failure": operational_failure,
            "traversal_partial": traversal_partial,
            "run_termination_reason": termination_reason,
            "comment_count_semantics_note": "The arithmetic comparison does not establish whether Instagram's reported count includes replies or uses the same visibility and sorting scope.",
            "reply_parent_filter": self.config.reply_parent_id,
            "reply_transport": self.config.reply_transport,
            "collection_partial": collection_partial,
            "reply_stop_reason": self.reply_stop_reason,
            "schema_errors": self.schema_errors,
            "qualification_levels": {
                "BROWSER_QUALIFIED": bool(self.page_url and self.page_title and termination_reason != "browser_start_failed"),
                "GRAPHQL_RESPONSE_QUALIFIED": self.root_pages > 0,
                "ROOT_PAGINATION_QUALIFIED": self.root_protocol_complete,
                "REPLY_COLLECTION_QUALIFIED": bool(linked_replies),
                "CHILD_OPERATION_LIVE_QUALIFIED": operation_replies > 0,
                "REPLY_PAGINATION_QUALIFIED": multi_page_branch_complete,
            },
            "collected_at": report_collected_at,
        }
        sqlite_summary = {
            name: round(sum(values.get(name, 0.0) for values in self.sqlite_timings_ms), 3)
            for name in ("record_persistence_and_deduplication", "checkpoint", "commit", "transaction")
        }
        crawler_lifecycle_ms = (
            (self.crawler_run_finished - self.crawler_run_started) * 1000
            if self.crawler_run_started is not None and self.crawler_run_finished is not None else None
        )
        handler_ms = sum(self.handler_durations_ms)
        request_timing_rows = [
            item.get("request_timing_ms", {}) for item in observations
            if isinstance(item.get("request_timing_ms"), dict)
        ]
        response_json_decode_ms = sum(
            value for row in request_timing_rows
            if isinstance((value := row.get("json_decode")), (int, float))
        )
        http_execution_ms = sum(
            value for row in request_timing_rows
            if isinstance((value := row.get("network")), (int, float))
        )
        http_session_initialization_ms = sum(
            value for row in request_timing_rows
            if isinstance((value := row.get("session_initialization")), (int, float))
        )
        shutdown_after_handler_ms = (
            (self.crawler_run_finished - self.last_handler_finished) * 1000
            if self.crawler_run_finished is not None and self.last_handler_finished is not None else None
        )
        report["performance"] = {
            "scope": "current run unless request timing samples are explicitly saved across resumes",
            "root_requests_this_run": self.root_request_attempts_this_run,
            "reply_requests_this_run": self.reply_request_attempts_this_run,
            "requests_per_second_this_run": round(self.http_request_attempts / runtime_seconds, 3) if runtime_seconds else None,
            "response_records_per_request_this_run": round(self.response_records_this_run / self.http_request_attempts, 3) if self.http_request_attempts else None,
            "new_unique_records_per_second_this_run": round(self.unique_records_added_this_run / runtime_seconds, 3) if runtime_seconds else None,
            "saved_request_timing_samples": {
                "root": _request_timing_summary(self.legacy_observations),
                "reply": _request_timing_summary(self.reply_observations),
            },
            "http_execution_ms_this_run": round(http_execution_ms, 3),
            "http_session_initialization_ms_this_run": round(http_session_initialization_ms, 3),
            "request_start_interval_ms_this_run": _timing_summary(self.request_start_intervals_ms),
            "pacing": {
                "configured_interval_ms": 500,
                "sleep_count": self.pacing_sleep_count,
                "requested_total_ms": round(self.pacing_requested_ms, 3),
                "actual_total_ms": round(self.pacing_actual_ms, 3),
            },
            "normalization_ms_this_run": {key: round(value, 3) for key, value in self.normalization_ms.items()},
            "response_json_decode_ms_this_run": round(response_json_decode_ms, 3),
            "sqlite_ms_this_run": sqlite_summary,
            "lifecycle_phases_ms": {
                **{key: round(value, 3) for key, value in self.lifecycle_timings_ms.items()},
                "shutdown_after_last_handler": round(shutdown_after_handler_ms, 3) if shutdown_after_handler_ms is not None else None,
                "session_pool_enabled": False,
                "session_pool_note": "Crawlee SessionPool is disabled; configured cookies are measured separately.",
                "request_scheduling_scope": "Crawlee run start until the BrowserPool pre-launch hook, minus measured BrowserPool/plugin initialization; API fetches execute inside the page handler and are not Crawlee-scheduled requests.",
                "shutdown_scope": "Time from the handler finishing until crawler.run returns; includes Crawlee/browser cleanup and other run finalization.",
            },
            "crawlee": {
                "lifecycle_ms": round(crawler_lifecycle_ms, 3) if crawler_lifecycle_ms is not None else None,
                "handler_count": len(self.handler_durations_ms),
                "handler_total_ms": round(handler_ms, 3),
                "time_to_first_handler_ms": (
                    round((self.first_handler_started - self.crawler_run_started) * 1000, 3)
                    if self.first_handler_started is not None and self.crawler_run_started is not None else None
                ),
                "after_last_handler_ms": (
                    round((self.crawler_run_finished - self.last_handler_finished) * 1000, 3)
                    if self.crawler_run_finished is not None and self.last_handler_finished is not None else None
                ),
                "lifecycle_residual_ms": round(max(0.0, crawler_lifecycle_ms - handler_ms), 3) if crawler_lifecycle_ms is not None else None,
                "startup_navigation_scheduling_split_available": bool(
                    "request_scheduling" in self.lifecycle_timings_ms
                    and "browser_controller_initialization" in self.lifecycle_timings_ms
                    and "navigation" in self.lifecycle_timings_ms
                ),
                "lifecycle_residual_interpretation": "Unattributed Crawlee runtime outside the handler; it is not attributed to browser startup.",
            },
            "report_generation_ms": round((time.perf_counter() - report_started) * 1000, 3),
            "export_files_ms_excluding_report_json": None,
        }
        self._write_outputs(report)
        if self.run_started:
            self.store.finish_run(self.run_id, report)
        return report

    async def run(self) -> dict[str, Any]:
        if BrowserPool is None or PlaywrightCrawler is None:
            self.store.close()
            raise RuntimeError("Install the project dependencies to use Playwright")
        try:
            session_started = time.perf_counter()
            self.legacy_cookies, self.legacy_app_id = _legacy_session()
            self._record_lifecycle_phase("session_configuration_load", session_started)
            if self.config.reply_transport == "full-form":
                transport_started = time.perf_counter()
                self.full_form_transport = FullFormReplyTransport(
                    self.config.reply_form_env,
                    allow_retarget=self.config.reply_allow_retarget,
                )
                self._record_lifecycle_phase("full_form_session_initialization", transport_started)
        except (OSError, ValueError):
            self.store.close()
            raise
        crawler = None
        reason = "crawl_finished"
        try:
            crawler_init_started = time.perf_counter()
            plugin = PlaywrightBrowserPlugin(
                browser_launch_options={"headless": self.config.headless},
                max_open_pages_per_browser=1,
            )

            experiment = self

            class TimedBrowserPool(BrowserPool):
                async def __aenter__(pool_self):
                    started = time.perf_counter()
                    try:
                        return await super().__aenter__()
                    finally:
                        experiment._record_lifecycle_phase("browser_runtime_initialization", started)

                async def __aexit__(pool_self, exc_type, exc_value, traceback):
                    started = time.perf_counter()
                    try:
                        return await super().__aexit__(exc_type, exc_value, traceback)
                    finally:
                        experiment._record_lifecycle_phase("browser_pool_shutdown", started)

            pool = TimedBrowserPool(plugins=[plugin])
            crawler = PlaywrightCrawler(
                browser_pool=pool,
                max_requests_per_crawl=1,
                max_request_retries=0,
                max_session_rotations=0,
                retry_on_blocked=False,
                use_session_pool=False,
                abort_on_error=True,
                concurrency_settings=ConcurrencySettings(desired_concurrency=1),
                navigation_timeout=timedelta(seconds=min(45.0, self.config.duration_seconds)),
                request_handler_timeout=timedelta(seconds=self.config.duration_seconds + 15.0),
            )
            self._record_lifecycle_phase("crawlee_and_pool_initialization", crawler_init_started)

            if callable(getattr(pool, "pre_launch_hook", None)):
                @pool.pre_launch_hook
                async def time_browser_launch(_page_id: str, _plugin: Any) -> None:
                    now = time.perf_counter()
                    if self.crawler_run_started is not None and "request_scheduling" not in self.lifecycle_timings_ms:
                        elapsed = (now - self.crawler_run_started) * 1000
                        browser_pool_init = self.lifecycle_timings_ms.get("browser_runtime_initialization", 0.0)
                        self.lifecycle_timings_ms["request_scheduling"] = max(0.0, elapsed - browser_pool_init)
                    self._lifecycle_marks["browser_controller"] = now

            if callable(getattr(pool, "post_launch_hook", None)):
                @pool.post_launch_hook
                async def finish_browser_launch(_page_id: str, _browser: Any) -> None:
                    started = self._lifecycle_marks.pop("browser_controller", None)
                    if started is not None:
                        self._record_lifecycle_phase("browser_controller_initialization", started)

            if callable(getattr(pool, "pre_page_create_hook", None)):
                @pool.pre_page_create_hook
                async def time_page_initialization(
                    _page_id: str, _browser: Any, _options: Any, _proxy: Any,
                ) -> None:
                    self._lifecycle_marks["browser_page_initialization"] = time.perf_counter()

            if callable(getattr(pool, "post_page_create_hook", None)):
                @pool.post_page_create_hook
                async def finish_page_initialization(_page: Any, _browser: Any) -> None:
                    started = self._lifecycle_marks.pop("browser_page_initialization", None)
                    if started is not None:
                        self._record_lifecycle_phase("browser_page_context_initialization", started)

            if callable(getattr(pool, "pre_page_close_hook", None)):
                @pool.pre_page_close_hook
                async def time_page_shutdown(_page: Any, _browser: Any) -> None:
                    self._lifecycle_marks["browser_page_shutdown"] = time.perf_counter()

            if callable(getattr(pool, "post_page_close_hook", None)):
                @pool.post_page_close_hook
                async def finish_page_shutdown(_page_id: str, _browser: Any) -> None:
                    started = self._lifecycle_marks.pop("browser_page_shutdown", None)
                    if started is not None:
                        self._record_lifecycle_phase("browser_page_shutdown", started)

            @crawler.pre_navigation_hook
            async def add_session_cookies(context: Any) -> None:
                started = time.perf_counter()
                await context.page.context.add_cookies(self.legacy_cookies)
                self._record_lifecycle_phase("session_cookie_application", started)
                self._lifecycle_marks["navigation"] = time.perf_counter()

            if callable(getattr(crawler, "post_navigation_hook", None)):
                @crawler.post_navigation_hook
                async def finish_navigation(_context: Any) -> None:
                    started = self._lifecycle_marks.pop("navigation", None)
                    if started is not None:
                        self._record_lifecycle_phase("navigation", started)

            @crawler.router.default_handler
            async def request_handler(context: PlaywrightCrawlingContext) -> None:
                await self.handle_page(context)

            self.crawler_run_started = time.perf_counter()
            self.lifecycle_timings_ms["session_pool_initialization"] = 0.0
            crawl_task = asyncio.create_task(crawler.run([self.reference.canonical_url]))
            try:
                await asyncio.wait_for(asyncio.shield(crawl_task), timeout=self.config.duration_seconds)
            except asyncio.TimeoutError:
                reason = "experiment_timeout"
                crawler.stop("bounded collection timeout")
                try:
                    await asyncio.wait_for(crawl_task, timeout=10.0)
                except asyncio.TimeoutError:
                    crawl_task.cancel()
                    await asyncio.gather(crawl_task, return_exceptions=True)
                except Exception:
                    await asyncio.gather(crawl_task, return_exceptions=True)
            else:
                reason = self.legacy_stop_reason or (
                    "natural_exhaustion" if self.root_protocol_complete else "bounded_collection_finished"
                )
        except asyncio.TimeoutError:
            reason = "experiment_timeout"
        except BrowserExperimentStopped as exc:
            reason = str(exc)
        except Exception:
            reason = "browser_start_failed" if self.page_url is None else "crawler_error"
        finally:
            self.crawler_run_finished = time.perf_counter()
            try:
                report = self.report(reason)
            finally:
                if self.full_form_transport is not None:
                    self.full_form_transport.close()
                self.store.close()
        return report


def run_browser_experiment(config: BrowserExperimentConfig) -> dict[str, Any]:
    return asyncio.run(BrowserCommentExperiment(config).run())
