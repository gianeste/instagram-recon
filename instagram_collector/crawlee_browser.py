"""Collect an Instagram post's root comments through Crawlee + CloakBrowser."""

from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, override
from urllib.parse import urlsplit, urlunsplit

from .collector import normalize_comment
from .response_fixtures import FixtureError
from .storage import StateStore, atomic_write_json, atomic_write_jsonl, utc_now
from .urls import parse_post_url

try:  # Offline tools can still import this module without the browser stack.
    from cloakbrowser.config import IGNORE_DEFAULT_ARGS, get_default_stealth_args
    from cloakbrowser.download import ensure_binary
    from crawlee.browsers import (
        BrowserPool,
        PlaywrightBrowserController,
        PlaywrightBrowserPlugin,
    )
    from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
    from crawlee._types import ConcurrencySettings
except ImportError:  # pragma: no cover - exercised only without optional extras
    BrowserPool = None  # type: ignore[assignment]
    PlaywrightBrowserController = None  # type: ignore[assignment]
    PlaywrightBrowserPlugin = object  # type: ignore[assignment,misc]
    PlaywrightCrawler = None  # type: ignore[assignment]
    PlaywrightCrawlingContext = Any  # type: ignore[assignment,misc]
    ConcurrencySettings = None  # type: ignore[assignment]
    ensure_binary = None  # type: ignore[assignment]
    IGNORE_DEFAULT_ARGS = []
    get_default_stealth_args = None  # type: ignore[assignment]

_LOGIN_MARKERS = ("/accounts/login", "/challenge/", "/checkpoint/")
_CHALLENGE_MARKERS = ("challenge_required", "checkpoint_required", "captcha", "verify it's you")
_LEGACY_QUERY_HASH = "97b41c52301f77ce508f55e66d17620e"
_LEGACY_PAGE_SIZE = 50


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


def _legacy_page(payload: Any, shortcode: str) -> tuple[str, int | None, list[dict[str, Any]], bool, str | None]:
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
    if not isinstance(media_id, (str, int)) or not str(media_id):
        media_id = f"shortcode:{shortcode}"
    if not isinstance(page_info.get("has_next_page"), bool):
        raise FixtureError("Legacy GraphQL response did not include has_next_page")

    records = []
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
    reported_count = edge_info.get("count")
    if not isinstance(reported_count, int):
        reported_count = None
    cursor = page_info.get("end_cursor")
    if not isinstance(cursor, str) or not cursor:
        cursor = None
    return str(media_id), reported_count, records, page_info["has_next_page"], cursor


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


class BrowserExperimentStopped(RuntimeError):
    """A bounded run stopped at an authentication or access boundary."""


@dataclass(frozen=True)
class BrowserExperimentConfig:
    target_url: str
    output_root: Path = Path("data")
    headless: bool = False
    max_root_pages: int = 3
    duration_seconds: float = 120.0

    def __post_init__(self) -> None:
        if self.max_root_pages < 1:
            raise ValueError("max_root_pages must be at least 1")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")


if BrowserPool is not None:

    class CloakBrowserPlugin(PlaywrightBrowserPlugin):
        """Use CloakBrowser's patched Chromium through Crawlee's browser pool."""

        @override
        async def new_browser(self) -> PlaywrightBrowserController:
            if not self._playwright:
                raise RuntimeError("Playwright browser plugin is not initialized")
            if ensure_binary is None or get_default_stealth_args is None:
                raise RuntimeError("CloakBrowser is not installed")

            launch_options = dict(self._browser_launch_options)
            launch_options.pop("executable_path", None)
            launch_options.pop("chromium_sandbox", None)
            existing_args = list(launch_options.pop("args", []))
            launch_options["args"] = [*existing_args, *get_default_stealth_args()]
            launch_options["executable_path"] = ensure_binary()
            launch_options["ignore_default_args"] = IGNORE_DEFAULT_ARGS
            browser = await self._playwright.chromium.launch(**launch_options)
            return PlaywrightBrowserController(
                browser=browser,
                max_open_pages_per_browser=1,
                header_generator=None,
            )

else:

    class CloakBrowserPlugin:  # pragma: no cover - optional dependency guard
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("Crawlee and CloakBrowser are required")


class BrowserCommentExperiment:
    def __init__(self, config: BrowserExperimentConfig) -> None:
        self.config = config
        self.reference = parse_post_url(config.target_url)
        self.output_dir = config.output_root / "legacy-graphql" / self.reference.shortcode
        self.store = StateStore(self.output_dir / "state.sqlite")
        self.started = time.monotonic()
        self.run_id = f"browser-{uuid.uuid4().hex}"
        self.scan_id = f"scan-{uuid.uuid4().hex}"
        self.media_id: str | None = None
        self.run_started = False
        self.post_saved = False
        self.root_pagination: list[dict[str, Any]] = []
        self.root_pages = 0
        self.duplicates = 0
        self.schema_errors: list[str] = []
        self.page_url: str | None = None
        self.page_title: str | None = None
        self.reported_comment_count: int | None = None
        self.root_protocol_complete = False
        self.root_partial = False
        self.legacy_observations: list[dict[str, Any]] = []
        self.legacy_status_counts: dict[str, int] = {}
        self.legacy_app_id: str | None = None
        self.legacy_cookies: list[dict[str, Any]] = []
        self.legacy_stop_reason: str | None = None
        self.target_identity_verified: bool | None = None
        self.media_id_source: str | None = None

    def _begin_store(self, media_id: str) -> None:
        if self.run_started:
            return
        self.media_id = str(media_id)
        self.store.reset_checkpoints(self.media_id)
        self._save_post_metadata()
        self.store.begin_run(self.run_id, self.scan_id, self.media_id, "legacy_graphql_collection")
        self.run_started = True
        stored = self.store.get_post(media_id=self.media_id)
        if stored:
            self.store.record_post_observation(
                self.run_id, self.media_id, stored["post"], stored["author"]
            )

    def _save_post_metadata(self) -> None:
        if self.post_saved or not self.media_id:
            return
        source = "instagram_legacy_graphql"
        post = {
            "media_id": self.media_id,
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
        page = context.page
        self.page_url = str(page.url)
        self.page_title = await page.title()
        await self._check_boundary(page)
        await self._collect_legacy_graphql(page)

    async def _collect_legacy_graphql(self, page: Any) -> None:
        cursor: str | None = None
        for page_number in range(1, self.config.max_root_pages + 1):
            try:
                result = await page.evaluate(
                    """async ({shortcode, after, appId, queryHash, first}) => {
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
                        const body = await response.text();
                        const contentType = response.headers.get('Content-Type') || 'unknown';
                        let payload = null;
                        try { payload = JSON.parse(body); } catch (_) {}
                        const diagnostic = payload && typeof payload === 'object'
                          ? JSON.stringify({errors: payload.errors, error: payload.error, message: payload.message, status: payload.status})
                          : body.slice(0, 65536);
                        const lower = diagnostic.toLowerCase();
                        const boundary = response.status === 429 ? 'rate_limited'
                          : response.status === 401 || lower.includes('login_required') || lower.includes('/accounts/login') ? 'authentication_required'
                          : lower.includes('challenge_required') || lower.includes('checkpoint_required') || lower.includes('captcha') || lower.includes('verify its you') ? 'access_restriction'
                          : response.status === 403 ? 'access_denied'
                          : null;
                        return {status: response.status, contentType, bytes: new TextEncoder().encode(body).length,
                          json: payload !== null, payload, boundary};
                      } catch (error) {
                        return {status: null, contentType: 'unknown', bytes: 0, json: false,
                          payload: null, boundary: error && error.name === 'AbortError' ? 'request_timeout' : 'network_error'};
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
                self.root_partial = True
                if self.media_id:
                    self.store.set_termination(self.media_id, "comments", self.legacy_stop_reason)
                break

            status = result.get("status")
            status_key = str(status) if status is not None else "network_error"
            self.legacy_status_counts[status_key] = self.legacy_status_counts.get(status_key, 0) + 1
            self.legacy_observations.append({
                "page": page_number,
                "status": status,
                "content_type": str(result.get("contentType", "unknown")).split(";", 1)[0].lower(),
                "response_bytes": int(result.get("bytes", 0) or 0),
                "json": result.get("json") is True,
            })
            if result.get("boundary") or status != 200:
                self.legacy_stop_reason = result.get("boundary") or "http_error"
                self.root_partial = True
                if self.media_id:
                    self.store.set_termination(self.media_id, "comments", self.legacy_stop_reason)
                break
            if result.get("json") is not True or not isinstance(result.get("payload"), dict):
                self.legacy_stop_reason = "unexpected_response"
                self.root_partial = True
                if self.media_id:
                    self.store.set_termination(self.media_id, "comments", self.legacy_stop_reason)
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
                media_id, reported_count, records, has_next, next_cursor = _legacy_page(
                    payload, self.reference.shortcode
                )
            except FixtureError as exc:
                self.legacy_stop_reason = "unexpected_response"
                self.root_partial = True
                self.schema_errors.append(f"page-{page_number}:{exc}")
                if self.media_id:
                    self.store.set_termination(self.media_id, "comments", self.legacy_stop_reason)
                break
            if self.media_id is not None and self.media_id != media_id:
                self.legacy_stop_reason = "media_identity_changed"
                self.root_partial = True
                self.store.set_termination(self.media_id, "comments", self.legacy_stop_reason)
                break

            self._begin_store(media_id)
            self._save_post_metadata()
            if reported_count is not None:
                self.reported_comment_count = reported_count
            try:
                saved = self.store.save_page(
                    media_id=media_id,
                    edge="comments",
                    parent_id=None,
                    records=records,
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
                self.store.set_termination(media_id, "comments", self.legacy_stop_reason)
                break
            self.root_pages += 1
            self.duplicates += saved["duplicates"]
            self.root_protocol_complete = saved["complete"]
            self.root_pagination.append({
                "page": page_number,
                "request_cursor_present": cursor is not None,
                "next_cursor_present": next_cursor is not None,
                "has_next_page": has_next,
                "edges": len(records),
            })
            if saved["termination_reason"]:
                self.legacy_stop_reason = saved["termination_reason"]
                self.root_partial = not saved["complete"]
                break
            cursor = next_cursor
            if page_number == self.config.max_root_pages:
                self.legacy_stop_reason = "page_budget"
                self.root_partial = True
                self.store.set_termination(media_id, "comments", self.legacy_stop_reason)
                break
            await asyncio.sleep(0.5)

    def _write_outputs(self, report: dict[str, Any]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.root_pagination:
            atomic_write_jsonl(self.output_dir / "root_pagination.jsonl", self.root_pagination)
        if self.media_id:
            post = self.store.get_post(media_id=self.media_id)
            if post:
                atomic_write_json(self.output_dir / "post.json", post["post"])
                roots = self.store.comments(self.media_id, parent_id=None)
                if roots:
                    atomic_write_jsonl(self.output_dir / "comments.jsonl", roots)
        atomic_write_json(self.output_dir / "collection_report.json", report)

    def report(self, termination_reason: str) -> dict[str, Any]:
        root_count = reply_count = unique_ids = 0
        root_rows: list[dict[str, Any]] = []
        if self.media_id:
            root_count, reply_count = self.store.comment_counts(self.media_id, scan_id=self.scan_id)
            unique_ids = len(self.store.all_comments(self.media_id))
            root_rows = self.store.comments(self.media_id, parent_id=None, scan_id=self.scan_id)
        replies_complete = not any((row.get("reported_reply_count") or 0) > 0 for row in root_rows)
        count_consistent = (
            root_count == self.reported_comment_count
            if self.reported_comment_count is not None else None
        )
        stored_post = self.store.get_post(media_id=self.media_id) if self.media_id else None
        collection_partial = not (
            self.root_protocol_complete
            and replies_complete
            and not self.schema_errors
            and termination_reason == "natural_exhaustion"
        )
        report = {
            "url": self.reference.canonical_url,
            "canonical_url": _safe_url(self.page_url or self.reference.canonical_url),
            "page_title": self.page_title,
            "shortcode": self.reference.shortcode,
            "media_id": self.media_id,
            "browser_backend": "CloakBrowser via Crawlee PlaywrightCrawler",
            "session_authentication_status": "cookie_session_supplied",
            "collection_method": "legacy_graphql_get",
            "query_hash": _LEGACY_QUERY_HASH,
            "target_identity_verified": self.target_identity_verified,
            "media_id_source": self.media_id_source,
            "legacy_request_observations": self.legacy_observations,
            "root_pages_observed": self.root_pages,
            "root_comments_collected": root_count,
            "reply_pages_observed": 0,
            "replies_collected": reply_count,
            "unique_comment_ids": unique_ids,
            "duplicate_records": self.duplicates,
            "http_response_status_distribution": self.legacy_status_counts,
            "pagination_transitions": {"root": self.root_pagination, "replies": []},
            "termination_reason": termination_reason,
            "wall_clock_seconds": round(time.monotonic() - self.started, 3),
            "metadata_complete": bool(stored_post and stored_post["post"].get("metadata_complete") is True),
            "post_metadata_observed": bool(self.media_id and self.post_saved and self.page_title),
            "root_protocol_complete": self.root_protocol_complete,
            "replies_protocol_complete": replies_complete,
            "reported_count_consistent": count_consistent,
            "reported_comment_count": self.reported_comment_count,
            "comment_count_semantics_note": "A matching endpoint-reported count does not prove historical or corpus-wide completeness.",
            "collection_partial": collection_partial,
            "schema_errors": self.schema_errors,
            "qualification_levels": {
                "BROWSER_QUALIFIED": bool(self.page_url and self.page_title and termination_reason != "browser_start_failed"),
                "GRAPHQL_RESPONSE_QUALIFIED": self.root_pages > 0,
                "ROOT_PAGINATION_QUALIFIED": self.root_pages >= 2 and not self.root_partial,
                "REPLY_COLLECTION_QUALIFIED": reply_count > 0,
                "REPLY_PAGINATION_QUALIFIED": False,
            },
            "collected_at": utc_now(),
        }
        self._write_outputs(report)
        if self.run_started:
            self.store.finish_run(self.run_id, report)
        return report

    async def run(self) -> dict[str, Any]:
        if BrowserPool is None or PlaywrightCrawler is None:
            self.store.close()
            raise RuntimeError("Install the project dependencies to use CloakBrowser")
        try:
            self.legacy_cookies, self.legacy_app_id = _legacy_session()
        except (OSError, ValueError):
            self.store.close()
            raise
        crawler = None
        reason = "crawl_finished"
        try:
            plugin = CloakBrowserPlugin(
                user_data_dir=None,
                browser_launch_options={"headless": self.config.headless},
                max_open_pages_per_browser=1,
            )
            pool = BrowserPool(plugins=[plugin])
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
            )

            @crawler.pre_navigation_hook
            async def add_session_cookies(context: Any) -> None:
                await context.page.context.add_cookies(self.legacy_cookies)

            @crawler.router.default_handler
            async def request_handler(context: PlaywrightCrawlingContext) -> None:
                await self.handle_page(context)

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
            try:
                report = self.report(reason)
            finally:
                self.store.close()
        return report


def run_browser_experiment(config: BrowserExperimentConfig) -> dict[str, Any]:
    return asyncio.run(BrowserCommentExperiment(config).run())
