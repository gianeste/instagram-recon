from __future__ import annotations

import argparse
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
        help="Collect root comments with the legacy GraphQL query via Crawlee + CloakBrowser",
    )
    collect.add_argument("url")
    collect.add_argument("--output", type=Path, default=Path("data"))
    collect.add_argument("--headless", action="store_true")
    collect.add_argument("--max-root-pages", type=_positive_int, default=3)
    collect.add_argument("--duration", type=float, default=120.0)

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
    return root / "legacy-graphql" / shortcode / "state.sqlite"


def _collect(args: argparse.Namespace) -> int:
    from .crawlee_browser import BrowserExperimentConfig, run_browser_experiment

    report = run_browser_experiment(
        BrowserExperimentConfig(
            target_url=args.url,
            output_root=args.output,
            headless=args.headless,
            max_root_pages=args.max_root_pages,
            duration_seconds=args.duration,
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report["collection_partial"] else 2


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
        return _inspect_response(args)
    except (FixtureError, ValueError, OSError, RuntimeError) as exc:
        print(f"instagram_collector: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
