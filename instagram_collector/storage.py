from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _merge(old: Any, new: Any) -> Any:
    if new is None:
        return old
    if isinstance(old, dict) and isinstance(new, dict):
        merged = dict(old)
        for key, value in new.items():
            merged[key] = _merge(old.get(key), value) if key in old else value
        return merged
    return new


_COMMENT_CHANGE_FIELDS = (
    "author_id", "username", "text", "created_at", "timestamp_raw",
    "like_count", "reported_reply_count", "visibility",
)


class StateStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = sqlite3.connect(path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS posts (
                media_id TEXT PRIMARY KEY,
                shortcode TEXT NOT NULL UNIQUE,
                post_json TEXT NOT NULL,
                author_json TEXT NOT NULL,
                collected_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS comments (
                media_id TEXT NOT NULL REFERENCES posts(media_id) ON DELETE CASCADE,
                comment_id TEXT NOT NULL,
                parent_id TEXT,
                last_seen_scan_id TEXT NOT NULL,
                data_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (media_id, comment_id)
            );
            CREATE INDEX IF NOT EXISTS comments_parent
                ON comments(media_id, parent_id);
            CREATE TABLE IF NOT EXISTS comment_observations (
                observation_id INTEGER PRIMARY KEY,
                media_id TEXT NOT NULL REFERENCES posts(media_id) ON DELETE CASCADE,
                run_id TEXT NOT NULL REFERENCES collection_runs(run_id) ON DELETE CASCADE,
                scan_id TEXT NOT NULL,
                comment_id TEXT NOT NULL,
                parent_id TEXT,
                observed_at TEXT NOT NULL,
                data_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
                media_id TEXT NOT NULL REFERENCES posts(media_id) ON DELETE CASCADE,
                edge TEXT NOT NULL,
                parent_key TEXT NOT NULL DEFAULT '',
                after_cursor TEXT,
                complete INTEGER NOT NULL DEFAULT 0,
                pages INTEGER NOT NULL DEFAULT 0,
                termination_reason TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (media_id, edge, parent_key)
            );
            CREATE TABLE IF NOT EXISTS seen_cursors (
                media_id TEXT NOT NULL REFERENCES posts(media_id) ON DELETE CASCADE,
                edge TEXT NOT NULL,
                parent_key TEXT NOT NULL DEFAULT '',
                cursor_value TEXT NOT NULL,
                PRIMARY KEY (media_id, edge, parent_key, cursor_value)
            );
            CREATE TABLE IF NOT EXISTS collection_runs (
                run_id TEXT PRIMARY KEY,
                scan_id TEXT NOT NULL,
                media_id TEXT NOT NULL REFERENCES posts(media_id),
                started_at TEXT NOT NULL,
                ended_at TEXT,
                mode TEXT NOT NULL,
                report_json TEXT
            );
            CREATE TABLE IF NOT EXISTS post_observations (
                observation_id INTEGER PRIMARY KEY,
                media_id TEXT NOT NULL REFERENCES posts(media_id) ON DELETE CASCADE,
                run_id TEXT NOT NULL REFERENCES collection_runs(run_id) ON DELETE CASCADE,
                observed_at TEXT NOT NULL,
                post_json TEXT NOT NULL,
                author_json TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> StateStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_post(self, *, shortcode: str | None = None, media_id: str | None = None) -> dict[str, Any] | None:
        if shortcode is not None:
            row = self.connection.execute(
                "SELECT * FROM posts WHERE shortcode = ?", (shortcode,)
            ).fetchone()
        elif media_id is not None:
            row = self.connection.execute(
                "SELECT * FROM posts WHERE media_id = ?", (media_id,)
            ).fetchone()
        else:
            raise ValueError("shortcode or media_id is required")
        return self._post_row(row) if row else None

    @staticmethod
    def _post_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "media_id": row["media_id"],
            "shortcode": row["shortcode"],
            "post": json.loads(row["post_json"]),
            "author": json.loads(row["author_json"]),
            "collected_at": row["collected_at"],
        }

    def save_post(
        self,
        *,
        media_id: str,
        shortcode: str,
        post: dict[str, Any],
        author: dict[str, Any],
    ) -> None:
        now = utc_now()
        with self.connection:
            row = self.connection.execute(
                "SELECT post_json, author_json FROM posts WHERE media_id = ?",
                (media_id,),
            ).fetchone()
            if row:
                post = _merge(json.loads(row["post_json"]), post)
                author = _merge(json.loads(row["author_json"]), author)
            self.connection.execute(
                """
                INSERT INTO posts(media_id, shortcode, post_json, author_json, collected_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(media_id) DO UPDATE SET
                    post_json = excluded.post_json,
                    author_json = excluded.author_json,
                    collected_at = excluded.collected_at
                """,
                (media_id, shortcode, _json(post), _json(author), now),
            )
    def begin_run(self, run_id: str, scan_id: str, media_id: str, mode: str) -> str:
        started_at = utc_now()
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO collection_runs(run_id, scan_id, media_id, started_at, mode)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, scan_id, media_id, started_at, mode),
            )
        return started_at

    def finish_run(self, run_id: str, report: dict[str, Any]) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE collection_runs SET ended_at = ?, report_json = ? WHERE run_id = ?",
                (utc_now(), _json(report), run_id),
            )

    def record_post_observation(
        self,
        run_id: str,
        media_id: str,
        post: dict[str, Any],
        author: dict[str, Any],
        *,
        observed_at: str | None = None,
    ) -> None:
        observed_at = observed_at or utc_now()
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO post_observations(media_id, run_id, observed_at, post_json, author_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (media_id, run_id, observed_at, _json(post), _json(author)),
            )

    def checkpoint(self, media_id: str, edge: str, parent_id: str | None = None) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT * FROM checkpoints
            WHERE media_id = ? AND edge = ? AND parent_key = ?
            """,
            (media_id, edge, parent_id or ""),
        ).fetchone()
        if row is None:
            return None
        return {
            "after_cursor": row["after_cursor"],
            "complete": bool(row["complete"]),
            "pages": row["pages"],
            "last_successful_page": row["pages"],
            "termination_reason": row["termination_reason"],
        }

    def set_termination(
        self,
        media_id: str,
        edge: str,
        reason: str,
        parent_id: str | None = None,
    ) -> None:
        parent_key = parent_id or ""
        previous = self.checkpoint(media_id, edge, parent_id)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO checkpoints(
                    media_id, edge, parent_key, after_cursor, complete, pages,
                    termination_reason, updated_at
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(media_id, edge, parent_key) DO UPDATE SET
                    complete = 0,
                    termination_reason = excluded.termination_reason,
                    updated_at = excluded.updated_at
                """,
                (
                    media_id,
                    edge,
                    parent_key,
                    previous["after_cursor"] if previous else None,
                    previous["pages"] if previous else 0,
                    reason,
                    utc_now(),
                ),
            )

    def reset_checkpoints(
        self, media_id: str, edge: str | None = None, parent_id: str | None = None
    ) -> None:
        with self.connection:
            if edge is None:
                self.connection.execute("DELETE FROM checkpoints WHERE media_id = ?", (media_id,))
                self.connection.execute("DELETE FROM seen_cursors WHERE media_id = ?", (media_id,))
            else:
                parent_key = parent_id or ""
                self.connection.execute(
                    "DELETE FROM checkpoints WHERE media_id = ? AND edge = ? AND parent_key = ?",
                    (media_id, edge, parent_key),
                )
                self.connection.execute(
                    "DELETE FROM seen_cursors WHERE media_id = ? AND edge = ? AND parent_key = ?",
                    (media_id, edge, parent_key),
                )

    def save_page(
        self,
        *,
        media_id: str,
        edge: str,
        parent_id: str | None,
        records: list[dict[str, Any]],
        run_id: str,
        scan_id: str,
        next_cursor: str | None,
        has_next: bool,
        current_cursor: str | None,
    ) -> dict[str, Any]:
        now = utc_now()
        parent_key = parent_id or ""
        duplicates = 0
        reason: str | None = None
        complete = not has_next
        after_cursor: str | None = None

        transaction_started = time.perf_counter()
        record_started = transaction_started
        self.connection.execute("BEGIN")
        try:
            previous = self.connection.execute(
                """
                SELECT pages FROM checkpoints
                WHERE media_id = ? AND edge = ? AND parent_key = ?
                """,
                (media_id, edge, parent_key),
            ).fetchone()
            pages = (previous["pages"] if previous else 0) + 1

            for record in records:
                raw_id = record.get("id")
                if isinstance(raw_id, bool) or not isinstance(raw_id, (str, int)) or not str(raw_id):
                    raise ValueError("comment response item is missing id")
                comment_id = str(raw_id)
                if str(record.get("media_id")) != media_id:
                    raise ValueError("comment media ID does not match the saved page")
                record_parent = record.get("parent_id")
                if record_parent is None:
                    record_parent = parent_id
                if record_parent is not None:
                    record_parent = str(record_parent)
                if parent_id is not None and record_parent != str(parent_id):
                    raise ValueError("comment parent ID does not match the saved branch")
                existing = self.connection.execute(
                    "SELECT parent_id, data_json FROM comments WHERE media_id = ? AND comment_id = ?",
                    (media_id, comment_id),
                ).fetchone()
                if existing:
                    if existing["parent_id"] != record_parent:
                        raise ValueError("comment ID was observed with a conflicting parent ID")
                    duplicates += 1
                    merged = _merge(json.loads(existing["data_json"]), record)
                else:
                    merged = record
                self.connection.execute(
                    """
                    INSERT INTO comments(
                        media_id, comment_id, parent_id, last_seen_scan_id, data_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(media_id, comment_id) DO UPDATE SET
                        parent_id = COALESCE(excluded.parent_id, comments.parent_id),
                        last_seen_scan_id = excluded.last_seen_scan_id,
                        data_json = excluded.data_json,
                        updated_at = excluded.updated_at
                    """,
                    (media_id, comment_id, record_parent, scan_id, _json(merged), now),
                )
                self.connection.execute(
                    """
                    INSERT INTO comment_observations(
                        media_id, run_id, scan_id, comment_id, parent_id, observed_at, data_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (media_id, run_id, scan_id, comment_id, record_parent, now, _json(record)),
                )

            record_ms = (time.perf_counter() - record_started) * 1000
            checkpoint_started = time.perf_counter()
            if has_next:
                if not next_cursor:
                    reason = "missing_cursor"
                    after_cursor = current_cursor
                elif next_cursor == current_cursor or self.connection.execute(
                    """
                    SELECT 1 FROM seen_cursors
                    WHERE media_id = ? AND edge = ? AND parent_key = ? AND cursor_value = ?
                    """,
                    (media_id, edge, parent_key, next_cursor),
                ).fetchone():
                    reason = "repeated_cursor"
                    after_cursor = current_cursor
                else:
                    complete = False
                    after_cursor = next_cursor
                    self.connection.execute(
                        """
                        INSERT INTO seen_cursors(media_id, edge, parent_key, cursor_value)
                        VALUES (?, ?, ?, ?)
                        """,
                        (media_id, edge, parent_key, next_cursor),
                    )
            else:
                reason = "natural_exhaustion"

            self.connection.execute(
                """
                INSERT INTO checkpoints(
                    media_id, edge, parent_key, after_cursor, complete, pages,
                    termination_reason, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(media_id, edge, parent_key) DO UPDATE SET
                    after_cursor = excluded.after_cursor,
                    complete = excluded.complete,
                    pages = excluded.pages,
                    termination_reason = excluded.termination_reason,
                    updated_at = excluded.updated_at
                """,
                (media_id, edge, parent_key, after_cursor, int(complete), pages, reason, now),
            )
            checkpoint_ms = (time.perf_counter() - checkpoint_started) * 1000
            commit_started = time.perf_counter()
            self.connection.commit()
            commit_ms = (time.perf_counter() - commit_started) * 1000
        except BaseException:
            self.connection.rollback()
            raise
        transaction_ms = (time.perf_counter() - transaction_started) * 1000

        return {
            "duplicates": duplicates,
            "complete": complete,
            "after_cursor": after_cursor,
            "pages": pages,
            "termination_reason": reason,
            "timings_ms": {
                "record_persistence_and_deduplication": round(record_ms, 3),
                "checkpoint": round(checkpoint_ms, 3),
                "commit": round(commit_ms, 3),
                "transaction": round(transaction_ms, 3),
            },
        }

    def comments(
        self,
        media_id: str,
        parent_id: str | None = None,
        scan_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if parent_id is None and scan_id is None:
            rows = self.connection.execute(
                "SELECT data_json FROM comments WHERE media_id = ? AND parent_id IS NULL ORDER BY comment_id",
                (media_id,),
            ).fetchall()
        elif parent_id is None:
            rows = self.connection.execute(
                "SELECT data_json FROM comments WHERE media_id = ? AND parent_id IS NULL AND last_seen_scan_id = ? ORDER BY comment_id",
                (media_id, scan_id),
            ).fetchall()
        elif scan_id is None:
            rows = self.connection.execute(
                "SELECT data_json FROM comments WHERE media_id = ? AND parent_id = ? ORDER BY comment_id",
                (media_id, parent_id),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT data_json FROM comments WHERE media_id = ? AND parent_id = ? AND last_seen_scan_id = ? ORDER BY comment_id",
                (media_id, parent_id, scan_id),
            ).fetchall()
        return [json.loads(row["data_json"]) for row in rows]

    def all_comments(self, media_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT data_json FROM comments WHERE media_id = ? ORDER BY comment_id",
            (media_id,),
        ).fetchall()
        return [json.loads(row["data_json"]) for row in rows]

    def comment_counts(self, media_id: str, scan_id: str | None = None) -> tuple[int, int]:
        if scan_id is not None:
            row = self.connection.execute(
                """
                SELECT
                    SUM(CASE WHEN parent_id IS NULL THEN 1 ELSE 0 END) AS roots,
                    SUM(CASE WHEN parent_id IS NOT NULL THEN 1 ELSE 0 END) AS replies
                FROM comments WHERE media_id = ? AND last_seen_scan_id = ?
                """,
                (media_id, scan_id),
            ).fetchone()
            return int(row["roots"] or 0), int(row["replies"] or 0)
        row = self.connection.execute(
            """
            SELECT
                SUM(CASE WHEN parent_id IS NULL THEN 1 ELSE 0 END) AS roots,
                SUM(CASE WHEN parent_id IS NOT NULL THEN 1 ELSE 0 END) AS replies
            FROM comments WHERE media_id = ?
            """,
            (media_id,),
        ).fetchone()
        return int(row["roots"] or 0), int(row["replies"] or 0)

    def latest_report(self, media_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT report_json FROM collection_runs
            WHERE media_id = ? AND report_json IS NOT NULL
            ORDER BY started_at DESC, rowid DESC LIMIT 1
            """,
            (media_id,),
        ).fetchone()
        return json.loads(row["report_json"]) if row else None

    def latest_run(self, media_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT run_id, scan_id, started_at, ended_at, mode, report_json FROM collection_runs
            WHERE media_id = ? ORDER BY started_at DESC, rowid DESC LIMIT 1
            """,
            (media_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row["run_id"],
            "scan_id": row["scan_id"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "mode": row["mode"],
            "report": json.loads(row["report_json"]) if row["report_json"] else None,
        }

    def latest_successful_run(self, media_id: str, mode: str | None = None) -> dict[str, Any] | None:
        rows = self.connection.execute(
            """
            SELECT run_id, scan_id, started_at, ended_at, mode, report_json
            FROM collection_runs
            WHERE media_id = ? AND ended_at IS NOT NULL AND report_json IS NOT NULL
              AND (? IS NULL OR mode = ?)
            ORDER BY started_at DESC, rowid DESC
            """,
            (media_id, mode, mode),
        )
        for row in rows:
            report = json.loads(row["report_json"])
            if report.get("root_protocol_complete") is True:
                return {
                    "run_id": row["run_id"],
                    "scan_id": row["scan_id"],
                    "started_at": row["started_at"],
                    "ended_at": row["ended_at"],
                    "mode": row["mode"],
                }
        return None

    def reported_count_history(self, media_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT r.run_id, r.scan_id, r.started_at, r.ended_at, r.mode,
                   p.observed_at, p.post_json, r.report_json
            FROM collection_runs r
            LEFT JOIN post_observations p ON p.run_id = r.run_id
            WHERE r.media_id = ?
            ORDER BY r.started_at, r.rowid, p.observation_id
            """,
            (media_id,),
        )
        history = []
        seen_observations: set[tuple[int, str]] = set()
        for row in rows:
            report = json.loads(row["report_json"]) if row["report_json"] else {}
            post = json.loads(row["post_json"]) if row["post_json"] else {}
            reported_count = post.get("comment_count")
            if not isinstance(reported_count, int) or isinstance(reported_count, bool):
                reported_count = report.get("reported_comment_count")
            if not isinstance(reported_count, int) or isinstance(reported_count, bool):
                continue
            report_only = not isinstance(post.get("comment_count"), int) or isinstance(post.get("comment_count"), bool)
            performance = report.get("performance")
            if report_only and isinstance(performance, dict) and performance.get("root_requests_this_run") == 0:
                continue
            observed_at = (
                report.get("collected_at") or row["ended_at"] if report_only
                else post.get("comment_count_observed_at") or row["observed_at"] or row["ended_at"]
            )
            timestamp_basis = (
                "run_report_proxy" if report_only
                else
                "response_payload" if post.get("comment_count_observed_at")
                else "post_observation_snapshot" if row["post_json"] is not None
                else "run_end_proxy"
            )
            if observed_at is not None:
                observation = (reported_count, observed_at)
                if observation in seen_observations:
                    continue
                seen_observations.add(observation)
            history.append({
                "run_id": row["run_id"],
                "scan_id": row["scan_id"],
                "mode": row["mode"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "reported_comment_count": reported_count,
                "observed_at": observed_at,
                "timestamp_basis": timestamp_basis,
                "observation_source": post.get("comment_count_source", "legacy_run_report"),
                "root_protocol_complete": report.get("root_protocol_complete"),
            })
        return history

    def scan_changes(self, media_id: str, scan_id: str, *, complete: bool) -> dict[str, Any]:
        current_rows = self.connection.execute(
            """
            SELECT observation_id, comment_id, data_json FROM comment_observations
            WHERE media_id = ? AND scan_id = ? ORDER BY observation_id
            """,
            (media_id, scan_id),
        ).fetchall()
        current: dict[str, dict[str, Any]] = {}
        for row in current_rows:
            comment_id = row["comment_id"]
            current[comment_id] = _merge(
                current.get(comment_id, {}), json.loads(row["data_json"])
            )

        first_observation = current_rows[0]["observation_id"] if current_rows else None
        prior_rows = self.connection.execute(
            """
            SELECT comment_id, data_json FROM comment_observations
            WHERE media_id = ? AND scan_id <> ? AND (? IS NULL OR observation_id < ?)
            ORDER BY observation_id
            """,
            (media_id, scan_id, first_observation, first_observation),
        ).fetchall()
        prior: dict[str, dict[str, Any]] = {}
        for row in prior_rows:
            comment_id = row["comment_id"]
            prior[comment_id] = _merge(
                prior.get(comment_id, {}), json.loads(row["data_json"])
            )

        new_ids = sorted(current.keys() - prior.keys())
        updated_fields: dict[str, list[str]] = {}
        for comment_id in current.keys() & prior.keys():
            merged = _merge(prior[comment_id], current[comment_id])
            changed = [
                field for field in _COMMENT_CHANGE_FIELDS
                if merged.get(field) != prior[comment_id].get(field)
            ]
            if changed:
                updated_fields[comment_id] = changed

        not_observed_ids: list[str] | None = None
        if complete:
            rows = self.connection.execute(
                """
                SELECT comment_id FROM comments
                WHERE media_id = ? AND last_seen_scan_id <> ?
                ORDER BY comment_id
                """,
                (media_id, scan_id),
            ).fetchall()
            not_observed_ids = [row["comment_id"] for row in rows]

        return {
            "previously_observed_count": len(prior),
            "observed_count": len(current),
            "new_ids": new_ids,
            "updated_fields": updated_fields,
            "not_observed_ids": not_observed_ids,
        }


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def atomic_write_json(path: Path, value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    atomic_write(path, payload)


def atomic_write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    payload = b"".join(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        for value in values
    )
    atomic_write(path, payload)
