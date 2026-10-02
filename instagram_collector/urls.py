from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit


class PostURLParseError(ValueError):
    pass


class UnsupportedContentType(PostURLParseError):
    pass


@dataclass(frozen=True)
class PostReference:
    original_url: str
    shortcode: str
    content_type: str
    canonical_url: str
    img_index: int | None = None


_SHORTCODE = re.compile(r"^[A-Za-z0-9_-]{5,64}$")
_ROUTES = {"p": "post", "reel": "reel"}


def parse_post_url(value: str) -> PostReference:
    try:
        parts = urlsplit(value.strip())
    except ValueError as exc:
        raise PostURLParseError("Malformed Instagram URL") from exc

    if parts.scheme not in {"http", "https"}:
        raise PostURLParseError("URL must use http or https")
    if parts.username or parts.password:
        raise PostURLParseError("URL must not contain user information")
    if (parts.hostname or "").lower() not in {
        "instagram.com",
        "www.instagram.com",
        "m.instagram.com",
    }:
        raise PostURLParseError("URL host must be instagram.com")
    if parts.port not in {None, 80, 443}:
        raise PostURLParseError("Unsupported Instagram URL port")

    path = [segment for segment in parts.path.split("/") if segment]
    if len(path) != 2 or path[0].lower() not in _ROUTES:
        raise UnsupportedContentType("Supported URL paths are /p/<shortcode> and /reel/<shortcode>")

    route, shortcode = path[0].lower(), path[1]
    if not _SHORTCODE.fullmatch(shortcode):
        raise PostURLParseError("Invalid Instagram shortcode")

    values = parse_qs(parts.query, keep_blank_values=True)
    img_index: int | None = None
    if "img_index" in values:
        try:
            img_index = int(values["img_index"][0])
        except (IndexError, ValueError) as exc:
            raise PostURLParseError("img_index must be a positive integer") from exc
        if img_index < 1:
            raise PostURLParseError("img_index must be a positive integer")

    content_type = _ROUTES[route]
    canonical_url = f"https://www.instagram.com/{route}/{shortcode}/"
    if img_index is not None:
        canonical_url += f"?img_index={img_index}"

    return PostReference(
        original_url=value,
        shortcode=shortcode,
        content_type=content_type,
        canonical_url=canonical_url,
        img_index=img_index,
    )
