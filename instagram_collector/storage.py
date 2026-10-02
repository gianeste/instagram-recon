from __future__ import annotations

import json
import os
import sqlite3
import tempfile
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
    def begin_run(self, run_id: str, scan_id: str, media_id: str, mode: str) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO collection_runs(run_id, scan_id, media_id, started_at, mode)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, scan_id, media_id, utc_now(), mode),
            )

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
    ) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO post_observations(media_id, run_id, observed_at, post_json, author_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (media_id, run_id, utc_now(), _json(post), _json(author)),
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

    def reset_checkpoints(self, media_id: str) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM checkpoints WHERE media_id = ?", (media_id,))
            self.connection.execute("DELETE FROM seen_cursors WHERE media_id = ?", (media_id,))

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

        with self.connection:
            previous = self.connection.execute(
                """
                SELECT pages FROM checkpoints
                WHERE media_id = ? AND edge = ? AND parent_key = ?
                """,
                (media_id, edge, parent_key),
            ).fetchone()
            pages = (previous["pages"] if previous else 0) + 1

            for record in records:
                comment_id = str(record.get("id") or "")
                if not comment_id:
                    raise ValueError("comment response item is missing id")
                existing = self.connection.execute(
                    "SELECT data_json FROM comments WHERE media_id = ? AND comment_id = ?",
                    (media_id, comment_id),
                ).fetchone()
                if existing:
                    duplicates += 1
                    merged = _merge(json.loads(existing["data_json"]), record)
                else:
                    merged = record
                record_parent = record.get("parent_id") or parent_id
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

        return {
            "duplicates": duplicates,
            "complete": complete,
            "after_cursor": after_cursor,
            "pages": pages,
            "termination_reason": reason,
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
            SELECT run_id, scan_id, ended_at, report_json FROM collection_runs
            WHERE media_id = ? ORDER BY started_at DESC, rowid DESC LIMIT 1
            """,
            (media_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row["run_id"],
            "scan_id": row["scan_id"],
            "ended_at": row["ended_at"],
            "report": json.loads(row["report_json"]) if row["report_json"] else None,
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
