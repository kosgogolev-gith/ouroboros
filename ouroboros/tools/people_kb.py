"""Persistent people knowledge-base tools backed by SQLite."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Sequence

from ouroboros.tools.registry import ToolContext, ToolEntry


def _db_path(ctx: ToolContext) -> Path:
    """Return the people database location, creating its parent directory."""
    directory = ctx.drive_root / "people_kb"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "people.db"


def _connect(ctx: ToolContext) -> sqlite3.Connection:
    """Open and initialize the people database."""
    connection = sqlite3.connect(str(_db_path(ctx)), timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS people (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT,
            company TEXT,
            context TEXT,
            notes TEXT,
            tags TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(name, company)
        )
        """
    )
    return connection


def _markdown_cell(value: Any) -> str:
    """Make a scalar value safe for a Markdown table cell."""
    if value is None:
        return ""
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Render a compact Markdown table."""
    header_line = "| " + " | ".join(_markdown_cell(item) for item in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_markdown_cell(item) for item in row) + " |" for row in rows]
    return "\n".join([header_line, separator, *body])


def _person_table(rows: Sequence[sqlite3.Row]) -> str:
    """Render people in the compact list/search format."""
    return _markdown_table(
        ("Name", "Role", "Company", "Context", "Tags", "Updated"),
        [
            (
                row["name"],
                row["role"],
                row["company"],
                row["context"],
                row["tags"],
                row["updated_at"],
            )
            for row in rows
        ],
    )


def _people_add(
    ctx: ToolContext,
    name: str,
    role: str = "",
    company: str = "",
    context: str = "",
    notes: str = "",
    tags: str = "",
) -> str:
    """Create a person or replace the mutable fields of an existing profile."""
    name = name.strip()
    company = company.strip()
    if not name:
        return "⚠️ Name must not be empty."

    with _connect(ctx) as connection:
        existing = connection.execute(
            "SELECT id FROM people WHERE name = ? AND company = ?",
            (name, company),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO people (id, name, role, company, context, notes, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name, company) DO UPDATE SET
                role = excluded.role,
                context = excluded.context,
                notes = excluded.notes,
                tags = excluded.tags,
                updated_at = datetime('now')
            """,
            (str(uuid.uuid4()), name, role, company, context, notes, tags),
        )
        action = "added" if existing is None else "updated"

    company_label = f" at {company}" if company else ""
    return f"✅ Person {action}: {name}{company_label}."


def _people_search(ctx: ToolContext, query: str) -> str:
    """Search all people fields and return up to ten matching profiles."""
    query = query.strip()
    if not query:
        return "⚠️ Query must not be empty."

    pattern = f"%{query}%"
    fields = ("id", "name", "role", "company", "context", "notes", "tags", "created_at", "updated_at")
    where_clause = " OR ".join(f"COALESCE({field}, '') LIKE ?" for field in fields)
    with _connect(ctx) as connection:
        rows = connection.execute(
            f"SELECT * FROM people WHERE {where_clause} ORDER BY updated_at DESC, name ASC LIMIT 10",
            (pattern,) * len(fields),
        ).fetchall()

    if not rows:
        return f"No people found for '{query}'."
    return f"## People matching '{query}'\n\n{_person_table(rows)}"


def _people_get(ctx: ToolContext, name: str) -> str:
    """Return all complete profiles for a name."""
    name = name.strip()
    if not name:
        return "⚠️ Name must not be empty."

    with _connect(ctx) as connection:
        rows = connection.execute(
            "SELECT * FROM people WHERE name = ? ORDER BY company ASC, updated_at DESC",
            (name,),
        ).fetchall()

    if not rows:
        return f"Person '{name}' not found."

    profiles = []
    for row in rows:
        company = row["company"] or "—"
        profiles.append(
            "\n".join(
                [
                    f"## {row['name']} — {company}",
                    f"- **ID:** {row['id']}",
                    f"- **Role:** {row['role'] or '—'}",
                    f"- **Context:** {row['context'] or '—'}",
                    f"- **Notes:** {row['notes'] or '—'}",
                    f"- **Tags:** {row['tags'] or '—'}",
                    f"- **Created:** {row['created_at']}",
                    f"- **Updated:** {row['updated_at']}",
                ]
            )
        )
    return "\n\n".join(profiles)


def _people_list(ctx: ToolContext) -> str:
    """List every saved person in a Markdown table."""
    with _connect(ctx) as connection:
        rows = connection.execute(
            "SELECT * FROM people ORDER BY name COLLATE NOCASE ASC, company COLLATE NOCASE ASC"
        ).fetchall()

    if not rows:
        return "People knowledge base is empty. Use people_add to create a profile."
    return f"## People ({len(rows)})\n\n{_person_table(rows)}"


def _people_update(ctx: ToolContext, name: str, notes: str) -> str:
    """Replace notes for every profile matching a name."""
    name = name.strip()
    if not name:
        return "⚠️ Name must not be empty."

    with _connect(ctx) as connection:
        cursor = connection.execute(
            "UPDATE people SET notes = ?, updated_at = datetime('now') WHERE name = ?",
            (notes, name),
        )
        updated = cursor.rowcount

    if updated == 0:
        return f"Person '{name}' not found."
    suffix = "profile" if updated == 1 else "profiles"
    return f"✅ Updated notes for {updated} {suffix} named '{name}'."


def _people_delete(ctx: ToolContext, name: str) -> str:
    """Delete every profile matching a name."""
    name = name.strip()
    if not name:
        return "⚠️ Name must not be empty."

    with _connect(ctx) as connection:
        cursor = connection.execute("DELETE FROM people WHERE name = ?", (name,))
        deleted = cursor.rowcount

    if deleted == 0:
        return f"Person '{name}' not found."
    suffix = "profile" if deleted == 1 else "profiles"
    return f"✅ Deleted {deleted} {suffix} named '{name}'."


def get_tools() -> List[ToolEntry]:
    """Expose people knowledge-base tools to the registry."""
    return [
        ToolEntry(
            "people_add",
            {
                "name": "people_add",
                "description": "Add a person to the persistent people knowledge base, or update an existing name-and-company profile.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Person's name"},
                        "role": {"type": "string", "description": "Role or job title"},
                        "company": {"type": "string", "description": "Company or organization"},
                        "context": {"type": "string", "description": "Relationship or relevant context"},
                        "notes": {"type": "string", "description": "Free-form notes"},
                        "tags": {"type": "string", "description": "Comma-separated tags"},
                    },
                    "required": ["name"],
                },
            },
            _people_add,
        ),
        ToolEntry(
            "people_search",
            {
                "name": "people_search",
                "description": "Search the persistent people knowledge base across all profile fields.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "Text to search for"}},
                    "required": ["query"],
                },
            },
            _people_search,
        ),
        ToolEntry(
            "people_get",
            {
                "name": "people_get",
                "description": "Get the complete saved profile or profiles for a person by name.",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "Person's name"}},
                    "required": ["name"],
                },
            },
            _people_get,
        ),
        ToolEntry(
            "people_list",
            {
                "name": "people_list",
                "description": "List all saved people in a Markdown table.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
            _people_list,
        ),
        ToolEntry(
            "people_update",
            {
                "name": "people_update",
                "description": "Replace notes for all saved profiles with the given name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Person's name"},
                        "notes": {"type": "string", "description": "Replacement notes"},
                    },
                    "required": ["name", "notes"],
                },
            },
            _people_update,
        ),
        ToolEntry(
            "people_delete",
            {
                "name": "people_delete",
                "description": "Delete all saved profiles with the given name.",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "Person's name"}},
                    "required": ["name"],
                },
            },
            _people_delete,
        ),
    ]
