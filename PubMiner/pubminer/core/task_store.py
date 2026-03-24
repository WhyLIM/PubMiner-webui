"""SQLite-backed task persistence for local PubMiner runs."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def utcnow_iso() -> str:
    """Return a stable UTC ISO8601 timestamp."""
    return datetime.utcnow().isoformat()


class SQLiteTaskStore:
    """Persist task state locally so runs survive process restarts."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA synchronous=NORMAL;")
        connection.execute("PRAGMA foreign_keys=ON;")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    result_file TEXT,
                    request_payload TEXT,
                    fulltext_report TEXT,
                    citation_report TEXT,
                    extraction_report TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    pmid TEXT NOT NULL,
                    pmcid TEXT,
                    title TEXT NOT NULL DEFAULT '',
                    journal TEXT NOT NULL DEFAULT '',
                    year TEXT NOT NULL DEFAULT '',
                    has_fulltext INTEGER NOT NULL DEFAULT 0,
                    citation_status TEXT NOT NULL DEFAULT 'pending',
                    fulltext_status TEXT NOT NULL DEFAULT 'pending',
                    oa_pdf_status TEXT NOT NULL DEFAULT 'pending',
                    extraction_status TEXT NOT NULL DEFAULT 'pending',
                    result_status TEXT NOT NULL DEFAULT 'pending',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(task_id, pmid),
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS task_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    article_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    fulltext_downloaded INTEGER NOT NULL DEFAULT 0,
                    extraction_success INTEGER NOT NULL DEFAULT 0,
                    extraction_failed INTEGER NOT NULL DEFAULT 0,
                    cached_hits INTEGER NOT NULL DEFAULT 0,
                    pmids TEXT NOT NULL DEFAULT '[]',
                    message TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(task_id, chunk_index),
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS extraction_cache (
                    pmid TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    schema_hash TEXT NOT NULL,
                    text_hash TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (pmid, model_name, schema_hash, text_hash)
                );

                CREATE TABLE IF NOT EXISTS search_sessions (
                    session_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    query TEXT NOT NULL DEFAULT '',
                    total_available INTEGER NOT NULL DEFAULT 0,
                    scope_limit INTEGER NOT NULL DEFAULT 0,
                    pmids TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(conn, "tasks", "request_payload", "TEXT")
            self._ensure_column(conn, "tasks", "extraction_report", "TEXT")
            self._ensure_column(conn, "task_articles", "citation_status", "TEXT NOT NULL DEFAULT 'pending'")
            self._ensure_column(conn, "task_articles", "oa_pdf_status", "TEXT NOT NULL DEFAULT 'pending'")
            self._ensure_column(conn, "task_chunks", "cached_hits", "INTEGER NOT NULL DEFAULT 0")

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
        existing_columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    @staticmethod
    def _encode_json(data: Optional[Dict[str, Any]]) -> Optional[str]:
        if data is None:
            return None
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _decode_json(data: Optional[str]) -> Optional[Dict[str, Any]]:
        if not data:
            return None
        return json.loads(data)

    def create_task(
        self,
        task_id: str,
        pmids: Iterable[str],
        request_payload: Optional[Dict[str, Any]] = None,
        status: str = "pending",
        progress: float = 0.0,
        message: str = "Task queued",
    ) -> None:
        now = utcnow_iso()
        rows = [(task_id, pmid, now, now) for pmid in pmids]

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tasks (
                    task_id, status, progress, message, result_file, request_payload,
                    fulltext_report, citation_report, extraction_report, created_at, updated_at
                ) VALUES (?, ?, ?, ?, NULL, ?, NULL, NULL, NULL, ?, ?)
                """,
                (task_id, status, progress, message, self._encode_json(request_payload), now, now),
            )
            conn.executemany(
                """
                INSERT OR IGNORE INTO task_articles (
                    task_id, pmid, created_at, updated_at
                ) VALUES (?, ?, ?, ?)
                """,
                rows,
            )

    def update_task(
        self,
        task_id: str,
        *,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        result_file: Optional[str] = None,
        fulltext_report: Optional[Dict[str, Any]] = None,
        citation_report: Optional[Dict[str, Any]] = None,
        extraction_report: Optional[Dict[str, Any]] = None,
        request_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        fields: List[str] = []
        values: List[Any] = []

        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if progress is not None:
            fields.append("progress = ?")
            values.append(progress)
        if message is not None:
            fields.append("message = ?")
            values.append(message)
        if result_file is not None:
            fields.append("result_file = ?")
            values.append(result_file)
        if fulltext_report is not None:
            fields.append("fulltext_report = ?")
            values.append(self._encode_json(fulltext_report))
        if citation_report is not None:
            fields.append("citation_report = ?")
            values.append(self._encode_json(citation_report))
        if extraction_report is not None:
            fields.append("extraction_report = ?")
            values.append(self._encode_json(extraction_report))
        if request_payload is not None:
            fields.append("request_payload = ?")
            values.append(self._encode_json(request_payload))

        fields.append("updated_at = ?")
        values.append(utcnow_iso())
        values.append(task_id)

        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE tasks SET {', '.join(fields)} WHERE task_id = ?",
                values,
            )

    def replace_articles(self, task_id: str, articles: Iterable[Dict[str, Any]]) -> None:
        now = utcnow_iso()
        normalized_rows = [
            (
                task_id,
                str(article.get("pmid", "")),
                article.get("pmcid"),
                article.get("title", "") or "",
                article.get("journal", "") or "",
                str(article.get("year", "") or ""),
                1 if article.get("has_fulltext") else 0,
                article.get("citation_status", "pending") or "pending",
                article.get("fulltext_status", "pending") or "pending",
                article.get("oa_pdf_status", "pending") or "pending",
                article.get("extraction_status", "pending") or "pending",
                article.get("result_status", "pending") or "pending",
                article.get("error", "") or "",
                now,
                now,
            )
            for article in articles
            if article.get("pmid")
        ]

        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM task_articles WHERE task_id = ?", (task_id,))
            conn.executemany(
                """
                INSERT INTO task_articles (
                    task_id, pmid, pmcid, title, journal, year, has_fulltext,
                    citation_status, fulltext_status, oa_pdf_status, extraction_status, result_status, error,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                normalized_rows,
            )
            conn.execute(
                "UPDATE tasks SET updated_at = ? WHERE task_id = ?",
                (now, task_id),
            )

    def replace_chunks(self, task_id: str, chunks: Iterable[Dict[str, Any]]) -> None:
        now = utcnow_iso()
        normalized_rows = [
            (
                task_id,
                int(chunk.get("chunk_index", 0)),
                int(chunk.get("article_count", 0)),
                chunk.get("status", "pending") or "pending",
                int(chunk.get("fulltext_downloaded", 0)),
                int(chunk.get("extraction_success", 0)),
                int(chunk.get("extraction_failed", 0)),
                int(chunk.get("cached_hits", 0)),
                json.dumps(chunk.get("pmids", []), ensure_ascii=False),
                chunk.get("message", "") or "",
                now,
                now,
            )
            for chunk in chunks
        ]

        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM task_chunks WHERE task_id = ?", (task_id,))
            conn.executemany(
                """
                INSERT INTO task_chunks (
                    task_id, chunk_index, article_count, status, fulltext_downloaded,
                    extraction_success, extraction_failed, cached_hits, pmids, message,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                normalized_rows,
            )
            conn.execute(
                "UPDATE tasks SET updated_at = ? WHERE task_id = ?",
                (now, task_id),
            )

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            task_row = conn.execute(
                """
                SELECT task_id, status, progress, message, result_file, request_payload,
                       fulltext_report, citation_report, extraction_report, created_at, updated_at
                FROM tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if task_row is None:
                return None

            article_rows = conn.execute(
                """
                SELECT pmid, pmcid, title, journal, year, has_fulltext,
                       citation_status, fulltext_status, oa_pdf_status,
                       extraction_status, result_status, error
                FROM task_articles
                WHERE task_id = ?
                ORDER BY id ASC
                """,
                (task_id,),
            ).fetchall()

            chunk_rows = conn.execute(
                """
                SELECT chunk_index, article_count, status, fulltext_downloaded,
                       extraction_success, extraction_failed, cached_hits, pmids, message
                FROM task_chunks
                WHERE task_id = ?
                ORDER BY chunk_index ASC
                """,
                (task_id,),
            ).fetchall()

        return {
            "task_id": task_row["task_id"],
            "status": task_row["status"],
            "progress": task_row["progress"],
            "message": task_row["message"],
            "result_file": task_row["result_file"],
            "request_payload": self._decode_json(task_row["request_payload"]),
            "fulltext_report": self._decode_json(task_row["fulltext_report"]),
            "citation_report": self._decode_json(task_row["citation_report"]),
            "extraction_report": self._decode_json(task_row["extraction_report"]),
            "article_report": [
                {
                    "pmid": row["pmid"],
                    "pmcid": row["pmcid"],
                    "title": row["title"],
                    "journal": row["journal"],
                    "year": row["year"],
                    "has_fulltext": bool(row["has_fulltext"]),
                    "citation_status": row["citation_status"],
                    "fulltext_status": row["fulltext_status"],
                    "oa_pdf_status": row["oa_pdf_status"],
                    "extraction_status": row["extraction_status"],
                    "result_status": row["result_status"],
                    "error": row["error"],
                }
                for row in article_rows
            ],
            "chunk_report": [
                {
                    "chunk_index": row["chunk_index"],
                    "article_count": row["article_count"],
                    "status": row["status"],
                    "fulltext_downloaded": row["fulltext_downloaded"],
                    "extraction_success": row["extraction_success"],
                    "extraction_failed": row["extraction_failed"],
                    "cached_hits": row["cached_hits"],
                    "pmids": json.loads(row["pmids"] or "[]"),
                    "message": row["message"],
                }
                for row in chunk_rows
            ],
        }

    def get_extraction_cache(
        self,
        *,
        pmid: str,
        model_name: str,
        schema_hash: str,
        text_hash: str,
    ) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT result_json
                FROM extraction_cache
                WHERE pmid = ? AND model_name = ? AND schema_hash = ? AND text_hash = ?
                """,
                (pmid, model_name, schema_hash, text_hash),
            ).fetchone()
            if row is None:
                return None
        return json.loads(row["result_json"])

    def put_extraction_cache(
        self,
        *,
        pmid: str,
        model_name: str,
        schema_hash: str,
        text_hash: str,
        result: Dict[str, Any],
    ) -> None:
        now = utcnow_iso()
        payload = json.dumps(result, ensure_ascii=False)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO extraction_cache (
                    pmid, model_name, schema_hash, text_hash, result_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pmid, model_name, schema_hash, text_hash)
                DO UPDATE SET result_json = excluded.result_json, updated_at = excluded.updated_at
                """,
                (pmid, model_name, schema_hash, text_hash, payload, now, now),
            )

    def save_search_session(
        self,
        *,
        session_id: str,
        source: str,
        query: str,
        total_available: int,
        scope_limit: int,
        pmids: List[str],
    ) -> None:
        now = utcnow_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO search_sessions (
                    session_id, source, query, total_available, scope_limit, pmids, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id)
                DO UPDATE SET
                    source = excluded.source,
                    query = excluded.query,
                    total_available = excluded.total_available,
                    scope_limit = excluded.scope_limit,
                    pmids = excluded.pmids,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    source,
                    query,
                    int(total_available),
                    int(scope_limit),
                    json.dumps(pmids, ensure_ascii=False),
                    now,
                    now,
                ),
            )

    def get_search_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT session_id, source, query, total_available, scope_limit, pmids, created_at, updated_at
                FROM search_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None

        return {
            "session_id": row["session_id"],
            "source": row["source"],
            "query": row["query"],
            "total_available": int(row["total_available"]),
            "scope_limit": int(row["scope_limit"]),
            "pmids": json.loads(row["pmids"] or "[]"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
