"""Historial de ejecuciones en SQLite (siempre redactado)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kp9.httpclient import Response, full_url
from kp9.redact import Redactor
from kp9.resolve import ResolvedRequest

_SCHEMA = """
CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    env TEXT,
    request_path TEXT,
    method TEXT NOT NULL,
    url TEXT NOT NULL,
    request_json TEXT NOT NULL,
    status INTEGER,
    reason TEXT,
    elapsed_ms REAL,
    response_headers TEXT,
    response_body BLOB,
    response_encoding TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_executions_path ON executions (request_path, id);
"""


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    ts: str
    env: str | None
    request_path: str | None
    method: str
    url: str
    request_json: str
    status: int | None
    reason: str | None
    elapsed_ms: float | None
    response_headers: list[tuple[str, str]]
    response_body: bytes | None
    response_encoding: str | None
    error: str | None

    def response(self) -> Response | None:
        if self.status is None:
            return None
        return Response(
            status=self.status,
            reason=self.reason or "",
            headers=self.response_headers,
            body=self.response_body or b"",
            elapsed_ms=self.elapsed_ms or 0.0,
            encoding=self.response_encoding,
        )


def _entry(row: sqlite3.Row) -> HistoryEntry:
    headers = json.loads(row["response_headers"]) if row["response_headers"] else []
    return HistoryEntry(
        id=row["id"],
        ts=row["ts"],
        env=row["env"],
        request_path=row["request_path"],
        method=row["method"],
        url=row["url"],
        request_json=row["request_json"],
        status=row["status"],
        reason=row["reason"],
        elapsed_ms=row["elapsed_ms"],
        response_headers=[(str(k), str(v)) for k, v in headers],
        response_body=row["response_body"],
        response_encoding=row["response_encoding"],
        error=row["error"],
    )


class History:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def record(
        self,
        *,
        req: ResolvedRequest,
        response: Response | None,
        error: str | None,
        redactor: Redactor,
        env: str | None,
        request_path: str | None,
        now: datetime | None = None,
    ) -> int:
        ts = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
        request_doc = {
            "method": req.method,
            "url": req.url,
            "params": req.params,
            "headers": dict(redactor.headers(req.headers)),
            "body": req.body.model_dump(mode="json"),
            "auth": {"type": req.auth.type},
        }
        request_json = json.dumps(redactor.value(request_doc), ensure_ascii=False, indent=2)
        status = reason = headers_json = encoding = None
        elapsed: float | None = None
        body: bytes | None = None
        if response is not None:
            status, reason, elapsed = response.status, response.reason, response.elapsed_ms
            headers_json = json.dumps(redactor.headers(response.headers), ensure_ascii=False)
            if response.is_binary or not response.decodes_cleanly():
                # se guardan los bytes originales (sin perder nada) con los secretos ocultos
                body = redactor.bytes(response.body)
            else:
                body = redactor.text(response.text()).encode("utf-8")
                encoding = "utf-8"
        cursor = self._conn.execute(
            "INSERT INTO executions (ts, env, request_path, method, url, request_json, status, "
            "reason, elapsed_ms, response_headers, response_body, response_encoding, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                env,
                request_path,
                req.method,
                redactor.text(full_url(req)),
                request_json,
                status,
                reason,
                elapsed,
                headers_json,
                body,
                encoding,
                redactor.text(error) if error else None,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid or 0)

    def list(self, limit: int = 500) -> list[HistoryEntry]:
        rows = self._conn.execute(
            "SELECT * FROM executions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_entry(r) for r in rows]

    def get(self, entry_id: int) -> HistoryEntry | None:
        row = self._conn.execute("SELECT * FROM executions WHERE id = ?", (entry_id,)).fetchone()
        return _entry(row) if row else None

    def last_for(self, request_path: str) -> HistoryEntry | None:
        row = self._conn.execute(
            "SELECT * FROM executions WHERE request_path = ? ORDER BY id DESC LIMIT 1",
            (request_path,),
        ).fetchone()
        return _entry(row) if row else None

    def close(self) -> None:
        self._conn.close()
