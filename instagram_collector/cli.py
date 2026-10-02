from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .response_fixtures import (
    FixtureError,
    extract_comment_ids,
    inspect_response,
    load_response,
    normalize_mapped_comments,
)
from .storage import StateStore, atomic_write_json


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m instagram_collector")
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser(
        "collect",
        help="Collect root comments with the legacy GraphQL query via Crawlee + Playwright",
    )
    collect.add_argument("url")
    collect.add_argument("--output", type=Path, default=Path("data"))
    collect.add_argument("--headless", action="store_true")
    collect.add_argument("--max-root-pages", type=_positive_int, default=3)
    collect.add_argument("--max-reply-pages", type=_positive_int, default=10)
    collect.add_argument("--max-http-requests", type=_positive_int, help="Global cap across root and reply GraphQL requests")
    collect.add_argument("--reply-parent-id", help="Limit reply collection to one parent comment ID")
    collect.add_argument("--reply-transport", choices=("browser", "full-form"), default="browser")
    collect.add_argument("--reply-form-env", type=Path, help="Local captured-form .env file (not exported)")
    collect.add_argument("--reply-allow-retarget", action="store_true", help="Experimental: adapt captured form to other media/parent IDs; not qualified")
    collect.add_argument("--duration", type=float, default=120.0)
    modes = collect.add_mutually_exclusive_group()
    modes.add_argument("--resume", dest="run_mode", action="store_const", const="resume")
    modes.add_argument("--refresh", dest="run_mode", action="store_const", const="refresh")
    modes.add_argument("--fresh", dest="run_mode", action="store_const", const="fresh")
    collect.set_defaults(run_mode="resume")

    probe = commands.add_parser("probe-reply", help="Bounded qualification of the captured full-form reply transport")
    probe.add_argument("url")
    probe.add_argument("--media-id", required=True)
    probe.add_argument("--parent-id", required=True)
    probe.add_argument("--reply-form-env", required=True, type=Path)
    probe.add_argument("--max-pages", type=_positive_int, default=1)
    probe.add_argument("--output", type=Path, default=Path("data"))
    probe.add_argument("--reply-allow-retarget", action="store_true")

    status = commands.add_parser("status", help="Show the saved report for a shortcode")
    status.add_argument("shortcode")
    status.add_argument("--output", type=Path, default=Path("data"))

    inspect = commands.add_parser("inspect-response", help="Inspect a sanitized JSON response offline")
    inspect.add_argument("response", type=Path)
    inspect.add_argument("--operation", help="Observed operation name (label only)")
    inspect.add_argument("--comment-id-path", action="append", default=[], metavar="PATH")
    inspect.add_argument("--mapping", type=Path, help="Reviewed JSON field mapping marked verified")
    inspect.add_argument("--media-id", help="Required with --mapping")
    inspect.add_argument("--parent-id", help="Parent ID when importing one reply branch")
    inspect.add_argument("--output", type=Path, help="Write analysis only, never the raw fixture")
    return parser


def _state_path(root: Path, shortcode: str) -> Path:
    candidates = (
        root / shortcode / "state.sqlite",
        root / "legacy-graphql" / shortcode / "state.sqlite",
        root / "legacy-graphql-qualification" / "legacy-graphql" / shortcode / "state.sqlite",
    )
    return next((path for path in candidates if path.exists()), candidates[0])


def _collect(args: argparse.Namespace) -> int:
    from .crawlee_browser import BrowserExperimentConfig, run_browser_experiment

    report = run_browser_experiment(
        BrowserExperimentConfig(
            target_url=args.url,
            output_root=args.output,
            headless=args.headless,
            max_root_pages=args.max_root_pages,
            max_reply_pages=args.max_reply_pages,
            max_http_requests=args.max_http_requests,
            reply_parent_id=args.reply_parent_id,
            duration_seconds=args.duration,
            run_mode=args.run_mode,
            reply_transport=args.reply_transport,
            reply_form_env=args.reply_form_env,
            reply_allow_retarget=args.reply_allow_retarget,
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if (
        not report["collection_partial"]
        and report["reported_count_consistent"] is True
        and report["reply_reported_counts_consistent"] is True
        and report["reported_count_semantics_validated"] is True
    ) else 2


def _probe_reply(args: argparse.Namespace) -> int:
    """No Crawlee dependency, no raw response/credential persistence, and no retries."""
    from .crawlee_browser import _child_page
    from .full_form_replies import FullFormReplyTransport
    from .urls import parse_post_url

    if args.max_pages > 3:
        raise ValueError("probe-reply is bounded to at most three pages")
    reference = parse_post_url(args.url)
    transport = FullFormReplyTransport(args.reply_form_env, allow_retarget=args.reply_allow_retarget)
    report = {
        "shortcode": reference.shortcode,
        "media_id": args.media_id,
        "parent_comment_id": args.parent_id,
        "transport": "captured_full_form_reference",
        "transport_live_qualified": False,
        "reply_pagination_qualified": False,
        "pages": [],
        "unique_reply_count": 0,
        "complete": False,
        "termination_reason": "not_started",
    }
    cursor = None
    seen_cursors: set[str] = set()
    seen_ids: set[str] = set()
    try:
        for page_number in range(1, args.max_pages + 1):
            response = transport.fetch(args.media_id, args.parent_id, cursor, referer=reference.canonical_url)
            from .full_form_replies import INITIAL, CONTINUATION
            operation, doc_id = INITIAL if cursor is None else CONTINUATION
            entry = {
                "page": page_number, "operation": operation, "doc_id": doc_id,
                "status": response.get("status"),
                "content_type": str(response.get("contentType", "unknown")).split(";", 1)[0],
                "response_bytes": response.get("bytes", 0),
                "input_cursor_sha256": hashlib.sha256(cursor.encode()).hexdigest() if cursor else None,
            }
            report["pages"].append(entry)
            if response.get("boundary"):
                report["termination_reason"] = str(response["boundary"])
                break
            if response.get("status") != 200:
                report["termination_reason"] = "http_error"
                break
            if response.get("json") is not True or not isinstance(response.get("payload"), dict):
                report["termination_reason"] = "non_json_response"
                break
            if response.get("graphqlError"):
                report["termination_reason"] = "graphql_error"
                break
            try:
                records, has_next, next_cursor = _child_page(response["payload"], args.media_id, args.parent_id,
                    source_operation=operation)
            except FixtureError:
                report["termination_reason"] = "schema_or_parent_mismatch"
                break
            reply_ids = [record["id"] for record in records]
            if len(reply_ids) != len(set(reply_ids)) or seen_ids.intersection(reply_ids):
                report["termination_reason"] = "duplicate_reply_ids"
                break
            seen_ids.update(reply_ids)
            entry.update({
                "reply_count": len(reply_ids), "has_next_page": has_next,
                "end_cursor_sha256": hashlib.sha256(next_cursor.encode()).hexdigest() if next_cursor else None,
                "cursor_source": "preceding_response_end_cursor" if page_number > 1 else None,
            })
            report["transport_live_qualified"] = True
            if not has_next:
                report["complete"] = True
                report["reply_pagination_qualified"] = page_number > 1
                report["termination_reason"] = "natural_exhaustion"
                break
            if not next_cursor or next_cursor in seen_cursors:
                report["termination_reason"] = "missing_or_repeated_cursor"
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        else:
            report["termination_reason"] = "page_budget"
    finally:
        transport.close()
    report["unique_reply_count"] = len(seen_ids)
    output = args.output / reference.shortcode / "reply_probe_report.json"
    atomic_write_json(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["transport_live_qualified"] else 2


def _status(args: argparse.Namespace) -> int:
    path = _state_path(args.output, args.shortcode)
    if not path.exists():
        print(json.dumps({"shortcode": args.shortcode, "exists": False}))
        return 1
    with StateStore(path) as store:
        post = store.get_post(shortcode=args.shortcode)
        if post is None:
            print(json.dumps({"shortcode": args.shortcode, "exists": False}))
            return 1
        report = store.latest_report(post["media_id"])
        latest_run = store.latest_run(post["media_id"])
    run_status = None
    if latest_run is not None:
        run_status = {
            "run_id": latest_run["run_id"],
            "scan_id": latest_run["scan_id"],
            "status": "finished" if latest_run["ended_at"] else "unfinished",
            "report": latest_run["report"],
        }
    print(json.dumps({"shortcode": args.shortcode, "exists": True, "report": report, "latest_run": run_status}, ensure_ascii=False, indent=2))
    return 0


def _inspect_response(args: argparse.Namespace) -> int:
    response_path = args.response.resolve()
    mapping_path = args.mapping.resolve() if args.mapping else None
    output_path = args.output.resolve() if args.output else None
    if output_path in {response_path, mapping_path}:
        raise ValueError("Analysis output must not overwrite the response or mapping file")
    payload = load_response(response_path)
    report = inspect_response(payload, operation=args.operation)
    if args.comment_id_path:
        report["extracted_comment_ids"] = {
            path: extract_comment_ids(payload, path) for path in args.comment_id_path
        }
    if mapping_path:
        if not args.media_id:
            raise ValueError("--media-id is required with --mapping")
        mapping = load_response(mapping_path)
        if not isinstance(mapping, dict):
            raise FixtureError("Comment field mapping must be a JSON object")
        report["normalized_comments"] = normalize_mapped_comments(
            payload, mapping, media_id=args.media_id, parent_id=args.parent_id
        )
    if output_path:
        atomic_write_json(output_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    args = _parser().parse_args(argv)
    try:
        if args.command == "collect":
            return _collect(args)
        if args.command == "status":
            return _status(args)
        if args.command == "probe-reply":
            return _probe_reply(args)
        return _inspect_response(args)
    except (FixtureError, ValueError, OSError, RuntimeError) as exc:
        print(f"instagram_collector: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
