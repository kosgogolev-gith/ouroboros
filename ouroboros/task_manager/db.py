"""SQLite DAO for the task manager: baselines, updates, deviations, decisions, cycles.

Stores project tracking state in a single SQLite file (WAL mode).
Zero dependencies beyond the stdlib.
"""

from __future__ import annotations

import contextlib
import json
import logging
import pathlib
import sqlite3
import uuid
from typing import Any, Dict, Iterator, List, Optional

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS baselines (
    id              TEXT PRIMARY KEY,
    task_id         TEXT,
    version         INTEGER DEFAULT 1,
    title           TEXT,
    priority        TEXT,
    owner           TEXT,
    center          TEXT,
    planned_start   TEXT,
    planned_end     TEXT,
    milestones      TEXT,
    dependencies    TEXT,
    revision_reason TEXT,
    status          TEXT DEFAULT 'active',
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS updates (
    id            TEXT PRIMARY KEY,
    task_id       TEXT,
    raw_text      TEXT,
    parsed_delta  TEXT,
    source_msg_id TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deviations (
    id             TEXT PRIMARY KEY,
    task_id        TEXT,
    baseline_id    TEXT,
    milestone_name TEXT,
    days_slip      INTEGER,
    severity       TEXT,
    root_cause     TEXT,
    cycle_id       TEXT,
    status         TEXT DEFAULT 'open',
    created_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS decisions_log (
    id           TEXT PRIMARY KEY,
    cycle_id     TEXT,
    deviation_id TEXT,
    proposal     TEXT,
    user_action  TEXT,
    user_comment TEXT,
    attempt_n    INTEGER DEFAULT 1,
    created_at   TEXT DEFAULT (datetime('now')),
    resolved_at  TEXT
);

CREATE TABLE IF NOT EXISTS iteration_counters (
    cycle_id     TEXT PRIMARY KEY,
    task_id      TEXT,
    deviation_id TEXT,
    stage        TEXT,
    attempt_n    INTEGER DEFAULT 0,
    started_at   TEXT,
    updated_at   TEXT,
    status       TEXT DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_baselines_task ON baselines(task_id);
CREATE INDEX IF NOT EXISTS idx_updates_task ON updates(task_id);
CREATE INDEX IF NOT EXISTS idx_deviations_status ON deviations(status);
"""

# Writable columns per table. Used to build INSERT statements — never user input,
# so table/column names are safe to interpolate (values stay parameterized).
_COLUMNS: Dict[str, tuple] = {
    "baselines": (
        "id", "task_id", "version", "title", "priority", "owner", "center",
        "planned_start", "planned_end", "milestones", "dependencies",
        "revision_reason", "status", "created_at",
    ),
    "updates": ("id", "task_id", "raw_text", "parsed_delta", "source_msg_id", "created_at"),
    "deviations": (
        "id", "task_id", "baseline_id", "milestone_name", "days_slip",
        "severity", "root_cause", "cycle_id", "status", "created_at",
    ),
    "decisions_log": (
        "id", "cycle_id", "deviation_id", "proposal", "user_action",
        "user_comment", "attempt_n", "created_at", "resolved_at",
    ),
}

# Columns stored as JSON text and decoded back into Python objects on read.
_JSON_COLUMNS: Dict[str, tuple] = {
    "baselines": ("milestones", "dependencies"),
    "updates": ("parsed_delta",),
    "decisions_log": ("proposal",),
}


class TaskDB:
    """Task manager persistence. One short-lived connection per operation."""

    def __init__(self, db_path: pathlib.Path):
        self.db_path = pathlib.Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._tx() as conn:
            conn.executescript(_SCHEMA)

    # --- internals ---

    @contextlib.contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """Open a connection, commit on success, roll back on error, always close."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _decode(table: str, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a row to a dict, parsing JSON-encoded columns."""
        data = dict(row)
        for col in _JSON_COLUMNS.get(table, ()):
            raw = data.get(col)
            if isinstance(raw, str) and raw.strip():
                try:
                    data[col] = json.loads(raw)
                except ValueError:
                    log.debug("task_manager: %s.%s holds non-JSON text", table, col)
        return data

    def _save(self, table: str, data: Dict[str, Any]) -> str:
        """Upsert a row keyed by id. Missing keys fall back to schema defaults."""
        row_id = str(data.get("id") or uuid.uuid4().hex)
        json_cols = _JSON_COLUMNS.get(table, ())
        payload: Dict[str, Any] = {"id": row_id}
        for col in _COLUMNS[table]:
            if col == "id" or col not in data or data[col] is None:
                continue
            value = data[col]
            if col in json_cols and not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False)
            payload[col] = value

        cols = list(payload)
        placeholders = ", ".join("?" for _ in cols)
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        assignments = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "id")
        if assignments:
            sql += f" ON CONFLICT(id) DO UPDATE SET {assignments}"
        with self._tx() as conn:
            conn.execute(sql, [payload[c] for c in cols])
        return row_id

    def _query(self, table: str, sql: str, params: List[Any]) -> List[Dict[str, Any]]:
        with self._tx() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._decode(table, r) for r in rows]

    # --- baselines ---

    def save_baseline(self, b: Dict[str, Any]) -> str:
        return self._save("baselines", b)

    def get_baseline(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Return the most recent baseline version for a task."""
        rows = self._query(
            "baselines",
            "SELECT * FROM baselines WHERE task_id = ? ORDER BY version DESC, created_at DESC LIMIT 1",
            [task_id],
        )
        return rows[0] if rows else None

    def list_baselines(self, status: str = "active") -> List[Dict[str, Any]]:
        """List baselines. Pass status='all' (or empty) to skip filtering."""
        sql = "SELECT * FROM baselines"
        params: List[Any] = []
        if status and status != "all":
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY planned_end IS NULL, planned_end ASC, created_at DESC"
        return self._query("baselines", sql, params)

    # --- updates ---

    def save_update(self, u: Dict[str, Any]) -> str:
        return self._save("updates", u)

    def get_updates_since(self, since_iso: str, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Updates created at or after since_iso. datetime() normalizes both formats."""
        sql = "SELECT * FROM updates WHERE datetime(created_at) >= datetime(?)"
        params: List[Any] = [since_iso]
        if task_id:
            sql += " AND task_id = ?"
            params.append(task_id)
        sql += " ORDER BY created_at DESC"
        return self._query("updates", sql, params)

    # --- deviations ---

    def save_deviation(self, d: Dict[str, Any]) -> str:
        return self._save("deviations", d)

    def get_open_deviations(self) -> List[Dict[str, Any]]:
        return self._query(
            "deviations",
            "SELECT * FROM deviations WHERE status = 'open' ORDER BY days_slip DESC, created_at DESC",
            [],
        )

    # --- decisions ---

    def log_decision(self, entry: Dict[str, Any]) -> str:
        return self._save("decisions_log", entry)

    # --- iteration cycles ---

    def init_cycle(self, task_id: str, deviation_id: Optional[str] = None) -> str:
        """Start an iteration cycle and return its id."""
        cycle_id = uuid.uuid4().hex
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO iteration_counters (cycle_id, task_id, deviation_id, attempt_n,"
                " started_at, updated_at, status)"
                " VALUES (?, ?, ?, 0, datetime('now'), datetime('now'), 'active')",
                [cycle_id, task_id, deviation_id],
            )
        return cycle_id

    def increment_attempt(self, cycle_id: str) -> int:
        """Bump the attempt counter and return its new value (0 if cycle is unknown)."""
        with self._tx() as conn:
            conn.execute(
                "UPDATE iteration_counters SET attempt_n = attempt_n + 1,"
                " updated_at = datetime('now') WHERE cycle_id = ?",
                [cycle_id],
            )
            row = conn.execute(
                "SELECT attempt_n FROM iteration_counters WHERE cycle_id = ?", [cycle_id]
            ).fetchone()
        return int(row["attempt_n"]) if row else 0

    def finish_cycle(self, cycle_id: str, status: str = "done") -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE iteration_counters SET status = ?, updated_at = datetime('now')"
                " WHERE cycle_id = ?",
                [status, cycle_id],
            )
