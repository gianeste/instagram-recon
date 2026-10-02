from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib.util
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TARGET_URL = "https://www.instagram.com/p/Dd9MKlfTDho/"
SHORTCODE = "Dd9MKlfTDho"
ENDPOINT = "https://www.instagram.com/graphql/query/"
QUERY_HASH = "97b41c52301f77ce508f55e66d17620e"
VARIABLES = {"shortcode": SHORTCODE, "first": 50}
OFFLINE_COOKIE = "sessionid=offline-session; ds_user_id=offline-user; csrftoken=offline-csrf; mid=offline-mid"
OFFLINE_USER_AGENT = "OfflineHarness/1.0"
PAGE = {
    "data": {
        "shortcode_media": {
            "edge_media_to_parent_comment": {
                "edges": [
                    {
                        "node": {
                            "id": "offline-comment-1",
                            "text": "offline fixture comment",
                            "owner": {"username": "offline_author"},
                            "like_count": 3,
                            "created_at": 1700000000,
                            "edge_threaded_comments": {
                                "edges": [
                                    {
                                        "node": {
                                            "id": "offline-reply-1",
                                            "text": "offline fixture reply",
                                            "owner": {"username": "offline_replier"},
                                            "like_count": 1,
                                            "created_at": 1700000001,
                                        }
                                    }
                                ]
                            },
                        }
                    }
                ],
                "page_info": {"has_next_page": False, "end_cursor": None},
                "count": 1,
            }
        }
    }
}


def read_local_env() -> dict[str, str]:
    values: dict[str, str] = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                values[name.strip()] = value.strip().strip("\"'")
    values.update({key: value for key, value in os.environ.items() if value})
    return values


def session_config() -> tuple[dict[str, str], dict[str, Any]]:
    values = read_local_env()
    cookies = {}
    for item in values.get("IG_SESSION_COOKIE", "").split(";"):
        if "=" in item:
            name, value = item.split("=", 1)
            cookies[name.strip().lower()] = value.strip()
    config = {
        "sessionid": cookies.get("sessionid", ""),
        "ds_user_id": cookies.get("ds_user_id", ""),
        "csrftoken": cookies.get("csrftoken", ""),
        "mid": cookies.get("mid", ""),
    }
    explicit_csrf = values.get("IG_CSRF_TOKEN", "")
    if explicit_csrf:
        config["csrftoken"] = explicit_csrf
    valid = all(config.values())
    upstream_user_agent = "Mozilla/5.0 (Linux; Android 13; SM-A125F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
    return config, {
        "available": valid,
        "source_keys": ["IG_SESSION_COOKIE", "IG_CSRF_TOKEN"],
        "cookie_names": sorted(cookies),
        "csrf_matches_cookie": bool(explicit_csrf and explicit_csrf == cookies.get("csrftoken")),
        "observed_user_agent_available": bool(values.get("IG_USER_AGENT")),
        "observed_user_agent_matches_upstream": values.get("IG_USER_AGENT") == upstream_user_agent,
        "app_id_matches_upstream": values.get("IG_APP_ID") == "936619743392459",
    }


def cookie_header(config: dict[str, str]) -> str:
    return "; ".join(f"{key}={config[key]}" for key in ("sessionid", "ds_user_id", "csrftoken", "mid"))


def load_module(name: str, path: Path, env: dict[str, str] | None = None):
    if env:
        os.environ.update(env)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_a(config: dict[str, str]):
    env = {
        "SESSIONID": config["sessionid"],
        "DS_USER_ID": config["ds_user_id"],
        "CSRFTOKEN": config["csrftoken"],
        "MID": config["mid"],
    }
    return load_module("legacy_instacomments", HERE / "upstream" / "instacomments" / "instacomments.py", env)


def load_b():
    path = HERE / "upstream" / "InstaScrape"
    sys.path.insert(0, str(path))
    return load_module("legacy_instascrape_main", path / "main.py")


def media_edges(payload: Any) -> tuple[dict[str, Any], list[Any], dict[str, Any]]:
    media = payload.get("data", {}).get("shortcode_media", {}) if isinstance(payload, dict) else {}
    edge_info = media.get("edge_media_to_parent_comment", {}) if isinstance(media, dict) else {}
    edges = edge_info.get("edges", []) if isinstance(edge_info, dict) else []
    page_info = edge_info.get("page_info", {}) if isinstance(edge_info, dict) else {}
    return edge_info, edges if isinstance(edges, list) else [], page_info if isinstance(page_info, dict) else {}


def preview_records(project: str, module: Any, payload: Any) -> list[dict[str, Any]]:
    _, edges, _ = media_edges(payload)
    parsed: list[dict[str, Any]] = []
    try:
        if project == "instacomments":
            for edge in edges[:10]:
                parsed.append(module.parse_comment_node(edge.get("node", {}), include_replies=True))
        else:
            _, _, parsed = module.parse_parent_comments(payload)
            parsed = parsed[:10]
    except Exception as exc:
        return [{"parser_error_type": type(exc).__name__}]

    result = []
    for item in parsed:
        if project == "instacomments":
            replies = item.get("replies")
            result.append({
                "id": item.get("id"),
                "text": item.get("text"),
                "author": item.get("username"),
                "timestamp": item.get("created_at"),
                "likes": item.get("like_count"),
                "reply_previews": [
                    {
                        "id": reply.get("id"),
                        "text": reply.get("text"),
                        "author": reply.get("username"),
                        "timestamp": reply.get("created_at"),
                        "likes": reply.get("like_count"),
                    }
                    for reply in (replies or [])[:5]
                ],
                "parser_fields": ["id", "text", "author", "timestamp", "likes", "reply_previews"],
            })
        else:
            result.append({
                "id": None,
                "text": item.get("text"),
                "author": item.get("username"),
                "timestamp": item.get("created_at"),
                "likes": None,
                "reply_previews": None,
                "parser_fields": ["text", "author", "timestamp"],
            })
    return result


def result_record(project: str, mode: str, module: Any, status: int | None, content_type: str | None, body: bytes, payload: Any, error: str | None = None) -> dict[str, Any]:
    edge_info, edges, page_info = media_edges(payload)
    media_present = bool(isinstance(payload, dict) and isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("shortcode_media"), dict))
    marker_text = body[:65536].decode("utf-8", errors="ignore").lower()
    restriction = (
        "rate_limited" if status == 429 else
        "access_restricted" if status in {301, 302, 303, 307, 308, 401, 403, 451} or any(marker in marker_text for marker in ("challenge_required", "checkpoint", "login_required", "accounts/login", "login-form", "verify it's you", "captcha")) else
        "http_error" if status is not None and status >= 400 else
        "unexpected_response" if error else
        "none"
    )
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and any(re.search(r"login_required|challenge|required|rate.?limit", json.dumps(e).lower()) for e in errors):
            restriction = "access_restricted"
    try:
        keys = sorted(payload.keys()) if isinstance(payload, dict) else []
    except Exception:
        keys = []
    return {
        "schema_version": 1,
        "project": project,
        "mode": mode,
        "target_url": TARGET_URL,
        "request": {
            "method": "GET",
            "endpoint": ENDPOINT,
            "query_hash": QUERY_HASH,
            "variables": VARIABLES,
            "attempts": 1,
        },
        "response": {
            "status": status,
            "content_type": (content_type or "unknown").split(";", 1)[0].lower(),
            "bytes": len(body),
            "json_parse_success": payload is not None,
            "top_level_keys": keys,
            "shortcode_media_present": media_present,
            "parent_comment_edge_present": bool(edge_info),
            "comment_edges_present": isinstance(edge_info.get("edges"), list),
            "comment_edge_count": len(edges) if isinstance(edge_info.get("edges"), list) else None,
            "page_info_present": isinstance(edge_info.get("page_info"), dict),
            "has_next_page": page_info.get("has_next_page"),
            "end_cursor_present": page_info.get("end_cursor") is not None,
            "restriction": restriction,
            "error_message": error or (restriction if restriction != "none" else None),
        },
        "records_preview": preview_records(project, module, payload) if payload is not None else [],
    }


class FakeRequestsResponse:
    def __init__(self, status: int, payload: Any = None, body: bytes | None = None, content_type: str = "application/json"):
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.content = body if body is not None else json.dumps(payload).encode()
        self.text = self.content.decode("utf-8", errors="replace")
        self._payload = payload

    def json(self):
        if self._payload is not None:
            return self._payload
        return json.loads(self.content)


def check_a_offline(module: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    assert module.PARENT_QUERY_HASH == QUERY_HASH
    parsed = urlparse(TARGET_URL)
    media = module.extract_media(TARGET_URL)
    assert parsed.hostname == "www.instagram.com" and media == ("p", SHORTCODE)
    headers = module.build_headers(TARGET_URL, OFFLINE_COOKIE)
    headers["User-Agent"] = OFFLINE_USER_AGENT
    assert headers["User-Agent"] == OFFLINE_USER_AGENT
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeRequestsResponse(200, PAGE)

    with patch.object(module.requests, "get", side_effect=fake_get):
        payload = module.graphql_request(QUERY_HASH, VARIABLES, headers)
    assert len(calls) == 1
    url, kwargs = calls[0]
    query = parse_qs(urlparse(url).query)
    assert urlparse(url).netloc == "www.instagram.com"
    assert urlparse(url).path == "/graphql/query/"
    assert query["query_hash"] == [QUERY_HASH]
    assert json.loads(query["variables"][0]) == VARIABLES
    assert headers["Referer"] == TARGET_URL
    assert kwargs == {"headers": headers, "timeout": 20, "allow_redirects": False}

    errors = []
    with patch.object(module.requests, "get", side_effect=lambda *_a, **_k: (errors.append(1), FakeRequestsResponse(429, body=b"private-429-marker", content_type="text/plain"))[1]):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            try:
                module.graphql_request(QUERY_HASH, VARIABLES, headers)
            except SystemExit:
                pass
            else:
                raise AssertionError("Project A must stop on HTTP 429")
    assert len(errors) == 1 and "private-429-marker" not in output.getvalue()
    redirect_calls = []
    with patch.object(module.requests, "get", side_effect=lambda *_a, **_k: (redirect_calls.append(1), FakeRequestsResponse(302, body=b"private-redirect-marker", content_type="text/html"))[1]):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            try:
                module.graphql_request(QUERY_HASH, VARIABLES, headers)
            except SystemExit:
                pass
            else:
                raise AssertionError("Project A must stop on redirects")
    assert len(redirect_calls) == 1 and "private-redirect-marker" not in output.getvalue()
    return payload, {"request_count": len(calls), "rate_limit_requests": len(errors), "redirect_requests": len(redirect_calls), "error_body_exposed": False}


async def check_b_offline(module: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    assert module.PARENT_QUERY_HASH == QUERY_HASH
    assert module.extract_shortcode(TARGET_URL) == SHORTCODE
    headers = module.build_headers(SHORTCODE, OFFLINE_COOKIE, media_type="p")
    headers["User-Agent"] = OFFLINE_USER_AGENT
    assert headers["User-Agent"] == OFFLINE_USER_AGENT
    calls = []

    def handler(request):
        calls.append(request)
        return module.httpx.Response(200, headers={"Content-Type": "application/json"}, json=PAGE, request=request)

    async with module.httpx.AsyncClient(http2=True, transport=module.httpx.MockTransport(handler)) as client:
        client.headers.update(headers)
        payload = await module.graphql_request(client, QUERY_HASH, VARIABLES)
    assert len(calls) == 1
    request = calls[0]
    assert request.method == "GET"
    assert str(request.url.copy_with(query=None)) == ENDPOINT
    assert request.url.params["query_hash"] == QUERY_HASH
    assert json.loads(request.url.params["variables"]) == VARIABLES
    assert headers["Referer"] == TARGET_URL

    error_calls = []

    def error_handler(request):
        error_calls.append(request)
        return module.httpx.Response(429, headers={"Content-Type": "text/plain"}, text="private-429-marker", request=request)

    async with module.httpx.AsyncClient(transport=module.httpx.MockTransport(error_handler)) as client:
        try:
            await module.graphql_request(client, QUERY_HASH, VARIABLES)
        except module.ScrapeError as exc:
            assert "private-429-marker" not in str(exc)
        else:
            raise AssertionError("Project B must stop on HTTP 429")
    assert len(error_calls) == 1
    redirect_calls = []

    def redirect_handler(request):
        redirect_calls.append(request)
        return module.httpx.Response(302, headers={"Location": "https://www.instagram.com/accounts/login/", "Content-Type": "text/html"}, text="private-redirect-marker", request=request)

    async with module.httpx.AsyncClient(transport=module.httpx.MockTransport(redirect_handler)) as client:
        try:
            await module.graphql_request(client, QUERY_HASH, VARIABLES)
        except module.ScrapeError as exc:
            assert "private-redirect-marker" not in str(exc)
        else:
            raise AssertionError("Project B must stop on redirects")
    assert len(redirect_calls) == 1
    return payload, {"request_count": len(calls), "rate_limit_requests": len(error_calls), "redirect_requests": len(redirect_calls), "error_body_exposed": False}


def offline() -> dict[str, Any]:
    dummy = {"sessionid": "offline-session", "ds_user_id": "offline-user", "csrftoken": "offline-csrf", "mid": "offline-mid"}
    a = load_a(dummy)
    b = load_b()
    payload_a, safety_a = check_a_offline(a)
    payload_b, safety_b = asyncio.run(check_b_offline(b))
    assert payload_a == payload_b == PAGE
    config, config_status = session_config()
    results = {
        "session_config": config_status,
        "results": [
            result_record("instacomments", "offline_fixture", a, 200, "application/json", json.dumps(PAGE).encode(), payload_a),
            result_record("InstaScrape", "offline_fixture", b, 200, "application/json", json.dumps(PAGE).encode(), payload_b),
        ],
        "safety_checks": {"instacomments": safety_a, "InstaScrape": safety_b},
    }
    serialized = json.dumps(results)
    assert all(value not in serialized for value in config.values() if value)
    assert all(result["request"]["attempts"] == 1 for result in results["results"])
    assert all(result["request"]["query_hash"] == QUERY_HASH for result in results["results"])
    return results


def live_one(module: Any, project: str, config: dict[str, str], user_agent: str) -> dict[str, Any]:
    headers = module.build_headers(TARGET_URL, cookie_header(config)) if project == "instacomments" else module.build_headers(SHORTCODE, cookie_header(config), media_type="p")
    headers["User-Agent"] = user_agent
    payload = None
    error = None
    response_status = None
    content_type = None
    body = b""

    if project == "instacomments":
        original_get = module.requests.get
        responses = []

        def one_get(url, **kwargs):
            response = original_get(url, **kwargs)
            responses.append(response)
            return response

        with patch.object(module.requests, "get", side_effect=one_get):
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    payload = module.graphql_request(QUERY_HASH, VARIABLES, headers)
                except SystemExit:
                    error = "request_stopped"
                except Exception as exc:
                    error = type(exc).__name__
        if responses:
            response = responses[0]
            response_status = response.status_code
            content_type = response.headers.get("Content-Type")
            body = response.content
    else:
        responses = []

        async def on_response(response):
            await response.aread()
            responses.append(response)

        async def request_once():
            async with module.httpx.AsyncClient(
                http2=True,
                timeout=module.httpx.Timeout(20.0, connect=10.0),
                event_hooks={"response": [on_response]},
            ) as client:
                client.headers.update(headers)
                return await module.graphql_request(client, QUERY_HASH, VARIABLES)

        try:
            payload = asyncio.run(request_once())
        except module.ScrapeError:
            error = "request_stopped"
        except module.httpx.RequestError as exc:
            error = type(exc).__name__
        if responses:
            response = responses[0]
            response_status = response.status_code
            content_type = response.headers.get("Content-Type")
            body = response.content

    result = result_record(project, "live_one_request", module, response_status, content_type, body, payload, error)
    if result["response"]["restriction"] in {"rate_limited", "access_restricted"}:
        result["response"]["stop_live_testing"] = True
    return result


def live_pair() -> dict[str, Any]:
    config, status = session_config()
    values = read_local_env()
    if not status["available"] or not status["csrf_matches_cookie"] or not status["observed_user_agent_available"]:
        raise SystemExit("Live test stopped: local session fields are incomplete or inconsistent; no values were printed.")
    a = load_a(config)
    b = load_b()
    first = live_one(a, "instacomments", config, values["IG_USER_AGENT"])
    results = [first]
    if first["response"]["restriction"] in {"rate_limited", "access_restricted"}:
        results.append({
            **result_record("InstaScrape", "not_run", b, None, None, b"", None, "stopped_after_prior_access_restriction"),
            "request": {**result_record("InstaScrape", "not_run", b, None, None, b"", None)["request"], "attempts": 0},
        })
    else:
        results.append(live_one(b, "InstaScrape", config, values["IG_USER_AGENT"]))
    return {"session_config": status, "results": results}


def pagination_page_record(project: str, page_number: int, cursor: str | None, module: Any, status: int | None, content_type: str | None, body: bytes, payload: Any, error: str | None) -> dict[str, Any]:
    edge_info, edges, page_info = media_edges(payload)
    data = payload.get("data") if isinstance(payload, dict) else None
    media = data.get("shortcode_media") if isinstance(data, dict) else None
    marker_text = body[:65536].decode("utf-8", errors="ignore").lower()
    restriction = (
        "rate_limited" if status == 429 else
        "access_restricted" if status in {301, 302, 303, 307, 308, 401, 403, 451} or any(marker in marker_text for marker in ("challenge_required", "checkpoint", "login_required", "accounts/login", "login-form", "verify it's you", "captcha")) else
        "http_error" if status is not None and status >= 400 else
        "unexpected_response" if error else
        "none"
    )
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and any(re.search(r"login_required|challenge|required|rate.?limit", json.dumps(e).lower()) for e in errors):
            restriction = "access_restricted"
    keys = sorted(payload.keys()) if isinstance(payload, dict) else []
    return {
        "page": page_number,
        "cursor_sent": cursor is not None,
        "request_attempts": 1,
        "status": status,
        "content_type": (content_type or "unknown").split(";", 1)[0].lower(),
        "response_bytes": len(body),
        "json_parse_success": payload is not None,
        "top_level_keys": keys,
        "shortcode_media_present": isinstance(media, dict),
        "parent_comment_edge_present": bool(edge_info),
        "comment_edge_count": len(edges) if isinstance(edge_info.get("edges"), list) else None,
        "page_info_present": isinstance(edge_info.get("page_info"), dict),
        "has_next_page": page_info.get("has_next_page"),
        "end_cursor_present": page_info.get("end_cursor") is not None,
        "restriction": restriction,
        "error": error or (restriction if restriction != "none" else None),
    }


def parser_counts(project: str, module: Any, payload: dict[str, Any]) -> dict[str, int]:
    _, edges, _ = media_edges(payload)
    if project == "instacomments":
        records = [module.parse_comment_node(edge.get("node", {}), include_replies=True) for edge in edges]
        return {
            "parsed_records": len(records),
            "records_with_id": sum(record.get("id") is not None for record in records),
            "records_with_text": sum(bool(record.get("text")) for record in records),
            "records_with_author": sum(bool(record.get("username")) for record in records),
            "records_with_timestamp": sum(record.get("created_at") is not None for record in records),
            "records_with_likes": sum(record.get("like_count") is not None for record in records),
            "inline_replies": sum(len(record.get("replies") or []) for record in records),
        }
    _, _, records = module.parse_parent_comments(payload)
    return {
        "parsed_records": len(records),
        "records_with_id": 0,
        "records_with_text": sum(bool(record.get("text")) for record in records),
        "records_with_author": sum(bool(record.get("username")) for record in records),
        "records_with_timestamp": sum(record.get("created_at") is not None for record in records),
        "records_with_likes": 0,
        "inline_replies": 0,
    }


def accumulate_page(result: dict[str, Any], project: str, module: Any, cursor: str | None, cursors: set[str], seen_ids: set[Any], page_number: int, status: int | None, content_type: str | None, body: bytes, payload: Any, error: str | None) -> tuple[str | None, str | None]:
    record = pagination_page_record(project, page_number, cursor, module, status, content_type, body, payload, error)
    result["pages"].append(record)
    result["page_count"] += 1
    if record["restriction"] != "none":
        return None, record["restriction"]
    edge_info, edges, page_info = media_edges(payload)
    if not isinstance(payload, dict) or not isinstance(edge_info.get("edges"), list) or not isinstance(page_info, dict):
        return None, "unexpected_graphql_shape"
    try:
        counts = parser_counts(project, module, payload)
    except Exception as exc:
        return None, f"parser_error:{type(exc).__name__}"
    result["comment_edge_count"] += len(edges)
    for name, count in counts.items():
        result["parser_totals"][name] += count
    for edge in edges:
        node = edge.get("node", {})
        comment_id = node.get("id") if isinstance(node, dict) else None
        if comment_id is not None:
            if comment_id in seen_ids:
                result["duplicate_comment_ids"] += 1
            else:
                seen_ids.add(comment_id)
    has_next = page_info.get("has_next_page")
    if has_next is False:
        return None, "complete"
    if has_next is not True:
        return None, "missing_has_next_page"
    next_cursor = page_info.get("end_cursor")
    if not isinstance(next_cursor, str) or not next_cursor:
        return None, "missing_end_cursor"
    if next_cursor == cursor or next_cursor in cursors:
        return None, "cursor_repeated"
    cursors.add(next_cursor)
    return next_cursor, None


def pagination_result(project: str) -> dict[str, Any]:
    return {
        "project": project,
        "status": "running",
        "stop_reason": None,
        "page_count": 0,
        "comment_edge_count": 0,
        "unique_comment_id_count": 0,
        "duplicate_comment_ids": 0,
        "parser_totals": {"parsed_records": 0, "records_with_id": 0, "records_with_text": 0, "records_with_author": 0, "records_with_timestamp": 0, "records_with_likes": 0, "inline_replies": 0},
        "pages": [],
    }


def paginate_a(module: Any, shortcode: str, target_url: str, config: dict[str, str], user_agent: str, max_pages: int) -> dict[str, Any]:
    result = pagination_result("instacomments")
    headers = module.build_headers(target_url, cookie_header(config))
    headers["User-Agent"] = user_agent
    cursor = None
    cursors: set[str] = set()
    seen_ids: set[Any] = set()
    for page_number in range(1, max_pages + 1):
        variables = {"shortcode": shortcode, "first": 50}
        if cursor is not None:
            variables["after"] = cursor
        responses = []
        original_get = module.requests.get

        def one_get(url, **kwargs):
            response = original_get(url, **kwargs)
            responses.append(response)
            return response

        payload = None
        error = None
        try:
            with patch.object(module.requests, "get", side_effect=one_get):
                with contextlib.redirect_stdout(io.StringIO()):
                    payload = module.graphql_request(QUERY_HASH, variables, headers)
        except SystemExit:
            error = "request_stopped"
        except Exception as exc:
            error = type(exc).__name__
        response = responses[0] if responses else None
        if len(responses) > 1:
            error = "unexpected_multiple_requests"
        status = response.status_code if response else None
        content_type = response.headers.get("Content-Type") if response else None
        body = response.content if response else b""
        next_cursor, stop_reason = accumulate_page(result, "instacomments", module, cursor, cursors, seen_ids, page_number, status, content_type, body, payload, error)
        if stop_reason:
            result["status"] = "completed" if stop_reason == "complete" else "stopped"
            result["stop_reason"] = stop_reason if stop_reason != "complete" else None
            break
        cursor = next_cursor
    else:
        result["status"] = "page_limit_reached"
        result["stop_reason"] = "max_pages_reached"
    result["unique_comment_id_count"] = len(seen_ids)
    return result


async def paginate_b(module: Any, shortcode: str, media_type: str, config: dict[str, str], user_agent: str, max_pages: int) -> dict[str, Any]:
    result = pagination_result("InstaScrape")
    headers = module.build_headers(shortcode, cookie_header(config), media_type=media_type)
    headers["User-Agent"] = user_agent
    responses = []

    async def capture_response(response):
        await response.aread()
        responses.append(response)

    cursor = None
    cursors: set[str] = set()
    seen_ids: set[Any] = set()
    async with module.httpx.AsyncClient(http2=True, timeout=module.httpx.Timeout(20.0, connect=10.0), event_hooks={"response": [capture_response]}) as client:
        client.headers.update(headers)
        for page_number in range(1, max_pages + 1):
            variables = {"shortcode": shortcode, "first": 50}
            if cursor is not None:
                variables["after"] = cursor
            responses.clear()
            payload = None
            error = None
            try:
                payload = await module.graphql_request(client, QUERY_HASH, variables)
            except module.ScrapeError:
                error = "request_stopped"
            except module.httpx.RequestError as exc:
                error = type(exc).__name__
            response = responses[0] if responses else None
            if len(responses) > 1:
                error = "unexpected_multiple_requests"
            status = response.status_code if response else None
            content_type = response.headers.get("Content-Type") if response else None
            body = response.content if response else b""
            next_cursor, stop_reason = accumulate_page(result, "InstaScrape", module, cursor, cursors, seen_ids, page_number, status, content_type, body, payload, error)
            if stop_reason:
                result["status"] = "completed" if stop_reason == "complete" else "stopped"
                result["stop_reason"] = stop_reason if stop_reason != "complete" else None
                break
            cursor = next_cursor
        else:
            result["status"] = "page_limit_reached"
            result["stop_reason"] = "max_pages_reached"
    result["unique_comment_id_count"] = len(seen_ids)
    return result


def live_paginate_pair(target_url: str, max_pages: int) -> dict[str, Any]:
    config, status = session_config()
    values = read_local_env()
    if not status["available"] or not status["csrf_matches_cookie"] or not status["observed_user_agent_available"]:
        raise SystemExit("Live test stopped: local session fields are incomplete or inconsistent; no values were printed.")
    a = load_a(config)
    parsed_media = a.extract_media(target_url)
    if not parsed_media:
        raise SystemExit("Live test stopped: target URL was not recognized as an Instagram post or reel.")
    media_type, shortcode = parsed_media
    b = load_b()
    if b.extract_shortcode(target_url) != shortcode:
        raise SystemExit("Live test stopped: project URL parsers disagree on the shortcode.")
    canonical_url = f"https://www.instagram.com/{media_type}/{shortcode}/"
    first = paginate_a(a, shortcode, canonical_url, config, values["IG_USER_AGENT"], max_pages)
    results = [first]
    if first["status"] != "completed":
        results.append({"project": "InstaScrape", "status": "not_run", "stop_reason": "Project A did not complete without error", "page_count": 0, "pages": []})
    else:
        results.append(asyncio.run(paginate_b(b, shortcode, media_type, config, values["IG_USER_AGENT"], max_pages)))
    return {"target_url": canonical_url, "query_hash": QUERY_HASH, "page_size": 50, "max_pages": max_pages, "session_config": status, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline-first compatibility harness for two legacy Instagram clients")
    parser.add_argument("--live-pair", action="store_true", help="Send at most one sequential request per implementation")
    parser.add_argument("--live-paginate", action="store_true", help="Follow each page cursor sequentially until exhaustion or a safety stop")
    parser.add_argument("--target-url", default=TARGET_URL, help="Instagram post or reel URL for the live test")
    parser.add_argument("--max-pages", type=int, default=100, help="Maximum pages per implementation (default: 100)")
    parser.add_argument("--acknowledge-prior-429", action="store_true", help="Authorize live testing despite the historic 429; any new restriction stops the run")
    parser.add_argument("--output", type=Path, help="Write the same JSON schema to this path")
    args = parser.parse_args()
    if (args.live_pair or args.live_paginate) and not args.acknowledge_prior_429:
        raise SystemExit("Live test blocked: pass --acknowledge-prior-429 to authorize testing after the earlier 429.")
    if args.max_pages < 1:
        raise SystemExit("--max-pages must be at least 1.")
    if args.live_pair and args.live_paginate:
        raise SystemExit("Choose only one of --live-pair or --live-paginate.")
    report = live_paginate_pair(args.target_url, args.max_pages) if args.live_paginate else live_pair() if args.live_pair else offline()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
