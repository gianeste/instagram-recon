"""Opt-in reply transport using locally captured full-form request templates.

This adapter preserves the independently qualified standalone request *shape*.
It does not establish that any captured session metadata remains valid, and
never treats a browser HTML fallback as successful reply data.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage import utc_now

INITIAL = ("PolarisPostChildCommentsQuery", "28027289793632076")
CONTINUATION = ("PolarisPostCommentsChildrenPaginationtQuery", "27229753410037873")
ENDPOINT = "https://www.instagram.com/api/graphql"
REQUIRED_FORM_FIELDS = frozenset({
    "av", "__d", "__user", "__a", "__req", "__hs", "dpr", "__ccg",
    "__rev", "__s", "__hsi", "__dyn", "__csr", "__hsdp", "__hblp",
    "__sjsp", "__comet_req", "fb_dtsg", "jazoest", "lsd", "__spin_r",
    "__spin_b", "__spin_t", "__crn", "fb_api_caller_class",
    "fb_api_req_friendly_name", "server_timestamps", "variables", "doc_id",
})


def _read_environment_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError("The local full-form reply configuration file does not exist")
    result: dict[str, str] = {}
    for original in path.read_text(encoding="utf-8").splitlines():
        line = original.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        value = val.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        result[key.strip()] = value
    return result


@dataclass(frozen=True)
class PreparedReplyRequest:
    operation: str
    doc_id: str
    form: dict[str, str]
    headers: dict[str, str]


class FullFormReplyTransport:
    """Single-session, sequential transport. Never automatically retries failures."""

    def __init__(self, path: Path, *, allow_retarget: bool = False) -> None:
        self._env = _read_environment_file(path)
        self._csrf = self._env.get("CSRF_TOKEN", "")
        if not self._csrf:
            raise ValueError("CSRF_TOKEN is missing from the local reply configuration")
        self._templates: list[tuple[str, dict[str, str], dict[str, Any]]] = []
        identities: set[tuple[str, str]] = set()
        for i, expected in enumerate((INITIAL, CONTINUATION), start=1):
            cookie = self._env.get(f"COOKIE_HEADER_{i}", "")
            raw = self._env.get(f"FORM_DATA_JSON_{i}", "")
            if not cookie or not raw:
                raise ValueError("The local reply configuration requires two captured request templates")
            try:
                form = json.loads(raw)
                if not isinstance(form, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in form.items()):
                    raise ValueError("Invalid form dictionary")
                if REQUIRED_FORM_FIELDS - form.keys():
                    raise ValueError("A captured full-form template is missing required form fields")
                if (form.get("fb_api_req_friendly_name"), form.get("doc_id")) != expected:
                    raise ValueError("The captured reply operation does not match its expected document ID")
                variables = json.loads(form["variables"])
                if not isinstance(variables, dict):
                    raise ValueError("Invalid GraphQL variables")
                media_id, parent_id = variables.get("media_id"), variables.get("parent_comment_id")
                if not all(isinstance(v, str) and v for v in (media_id, parent_id)):
                    raise ValueError("Missing media or parent identity in the captured template")
                if i == 1 and variables.get("after") is not None:
                    raise ValueError("The initial captured template must have a null after cursor")
                if i == 2 and not isinstance(variables.get("after"), str):
                    raise ValueError("The continuation template must use a string after cursor")
                if f"csrftoken={self._csrf}" not in cookie:
                    raise ValueError("The locally captured CSRF token and cookie are inconsistent")
                identities.add((media_id, parent_id))
                self._templates.append((cookie, dict(form), variables))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                # Never echo raw exception content, which could contain credentials.
                raise ValueError(f"Invalid local captured reply request template {i}") from None
        if len(identities) != 1:
            raise ValueError("Initial and continuation templates target different comments")
        self.captured_media_id, self.captured_parent_id = identities.pop()
        self.allow_retarget = allow_retarget
        self._session: Any = None

    def prepare(self, media_id: str, parent_id: str, cursor: str | None, *, referer: str) -> PreparedReplyRequest:
        if not media_id or not parent_id:
            raise ValueError("A media ID and parent ID are required")
        if cursor is not None and (not isinstance(cursor, str) or not cursor):
            raise ValueError("A continuation cursor must be a nonempty string")
        if not self.allow_retarget and (media_id, parent_id) != (self.captured_media_id, self.captured_parent_id):
            raise ValueError("Captured reply templates are scoped to one media/parent; retargeting is unqualified")
        i = 0 if cursor is None else 1
        cookie, template, observed_vars = self._templates[i]
        operation, doc_id = INITIAL if i == 0 else CONTINUATION
        variables = dict(observed_vars)
        variables.update({"media_id": media_id, "parent_comment_id": parent_id, "after": cursor})
        form = dict(template)
        # Maintain the standalone implementation's JSON encoding and POST form structure.
        form["variables"] = json.dumps(variables, ensure_ascii=False, separators=(",", ":"))
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/x-www-form-urlencoded",
            "cookie": cookie,
            "origin": "https://www.instagram.com",
            "priority": "u=1, i",
            "referer": self._env.get("REPLY_REFERER") or referer,
            "sec-ch-prefers-color-scheme": "dark",
            "sec-ch-ua": '"Chromium";v="154", "Microsoft Edge";v="154", "Not A(Brand";v="99"',
            "sec-ch-ua-full-version-list": '"Chromium";v="154.0.8037.58", "Microsoft Edge";v="154.0.4258.48", "Not A(Brand";v="99.0.0.0"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-model": '""',
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-platform-version": '"19.0.0"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36 Edg/154.0.0.0",
            "x-asbd-id": "359341",
            "x-csrftoken": self._csrf,
            "x-fb-friendly-name": operation,
            "x-fb-lsd": form["lsd"],
            "x-ig-app-id": "936619743392459",
            "x-ig-max-touch-points": "0",
        }
        return PreparedReplyRequest(operation, doc_id, form, headers)

    def fetch(self, media_id: str, parent_id: str, cursor: str | None, *, referer: str) -> dict[str, Any]:
        import requests  # Optional dependency: imported only for explicitly selected transport.
        prepared = self.prepare(media_id, parent_id, cursor, referer=referer)
        session_initialization_ms = 0.0
        if self._session is None:
            session_started = time.perf_counter()
            self._session = requests.Session()
            session_initialization_ms = (time.perf_counter() - session_started) * 1000
        started = time.perf_counter()
        try:
            response = self._session.post(
                ENDPOINT, headers=prepared.headers, data=prepared.form,
                timeout=(5, 20), allow_redirects=False, stream=True,
            )
            headers_received = time.perf_counter()
            with response:
                status = response.status_code
                content_type = response.headers.get("Content-Type", "unknown")
                length = 0
                chunks = []
                # Restrict response memory; never persist raw API bodies or session data.
                for chunk in response.iter_content(chunk_size=65536):
                    length += len(chunk)
                    if length > 4 * 1024 * 1024:
                        body_finished = time.perf_counter()
                        return {"status": status, "contentType": content_type, "bytes": length,
                                "json": False, "payload": None, "boundary": "oversize_response",
                                "timingsMs": {
                                    "headers": round((headers_received - started) * 1000, 3),
                                    "body": round((body_finished - headers_received) * 1000, 3),
                                    "json_decode": 0.0,
                                    "session_initialization": round(session_initialization_ms, 3),
                                    "network": round((body_finished - started) * 1000, 3),
                                    "total": round((body_finished - started) * 1000, 3),
                                }}
                    chunks.append(chunk)
                body = b"".join(chunks)
                body_finished = time.perf_counter()
                decode_started = time.perf_counter()
                try:
                    payload = json.loads(body)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    payload = None
                decoded = time.perf_counter()
                if not isinstance(payload, dict):
                    payload = None
                diagnostic = ""
                if payload is not None:
                    diagnostic = str({key: payload.get(key) for key in ("status", "message", "error")}).lower()
                else:
                    diagnostic = body[:4096].decode("utf-8", errors="replace").lower()
                boundary = (
                    "rate_limited" if status == 429 else
                    "authentication_required" if status == 401 or "login_required" in diagnostic else
                    "access_denied" if status == 403 else
                    "access_restriction" if any(x in diagnostic for x in ("challenge_required", "checkpoint_required", "captcha")) else
                    None
                )
                low = body[:16384].decode("utf-8", errors="replace").lower() if payload is None else ""
                return {
                    "status": status, "contentType": content_type, "bytes": length,
                    "json": payload is not None, "payload": payload, "boundary": boundary,
                    "observedAt": utc_now(),
                    "timingsMs": {
                        "headers": round((headers_received - started) * 1000, 3),
                        "body": round((body_finished - headers_received) * 1000, 3),
                        "json_decode": round((decoded - decode_started) * 1000, 3),
                        "session_initialization": round(session_initialization_ms, 3),
                        "network": round((body_finished - started) * 1000, 3),
                        "total": round((decoded - started) * 1000, 3),
                    },
                    "htmlSignals": {
                        "doctype": "<!doctype html" in low, "html_element": "<html" in low,
                        "instagram_title": "<title>instagram</title>" in low,
                        "app_assets": "<script" in low or "<link" in low,
                    },
                    "cursorExpired": "cursor" in diagnostic and ("expired" in diagnostic or "invalid" in diagnostic),
                    "unavailable": "comment" in diagnostic and ("unavailable" in diagnostic or "not found" in diagnostic),
                    "graphqlError": payload is not None and isinstance(payload.get("errors"), list) and bool(payload["errors"]),
                }
        except requests.RequestException:
            return {"status": None, "contentType": "unknown", "bytes": 0,
                    "json": False, "payload": None, "boundary": "network_error",
                    "timingsMs": {
                        "network": round((time.perf_counter() - started) * 1000, 3),
                        "total": round((time.perf_counter() - started) * 1000, 3),
                        "session_initialization": round(session_initialization_ms, 3),
                    }}

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
