"""People knowledge base tools: structured profiles on Google Drive.

Provides add/search/get/list operations for people profiles stored in
knowledge/people/ on Drive. Maintains an index.json and per-person .md files.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)

PEOPLE_DIR = "knowledge/people"
INDEX_FILE = "index.json"

# ---------------------------------------------------------------------------
# Transliteration (Cyrillic → Latin, simple dict-based)
# ---------------------------------------------------------------------------

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _transliterate(text: str) -> str:
    """Transliterate Cyrillic to Latin, lowercase, replace non-alnum with hyphens."""
    result = []
    for ch in text.lower():
        if ch in _TRANSLIT:
            result.append(_TRANSLIT[ch])
        elif ch.isascii() and ch.isalnum():
            result.append(ch)
        else:
            result.append("-")
    slug = "-".join(part for part in "".join(result).split("-") if part)
    return slug or "unknown"


def _make_slug(name: str) -> str:
    """Generate a filesystem-safe slug from a person's name."""
    slug = _transliterate(name.strip())
    # Cap length
    if len(slug) > 80:
        slug = slug[:80].rstrip("-")
    return slug


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _people_dir(ctx: ToolContext) -> Path:
    return ctx.drive_path(PEOPLE_DIR)


def _ensure_dir(ctx: ToolContext) -> Path:
    d = _people_dir(ctx)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_index(ctx: ToolContext) -> List[Dict[str, Any]]:
    index_path = _people_dir(ctx) / INDEX_FILE
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        log.debug("Failed to read people index", exc_info=True)
    return []


def _save_index(ctx: ToolContext, index: List[Dict[str, Any]]) -> None:
    d = _ensure_dir(ctx)
    index_path = d / INDEX_FILE
    tmp = index_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(index_path)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _build_profile_md(name: str, organization: str, role: str,
                      appearance: str, context: str, notes: str,
                      history: str = "") -> str:
    """Build markdown content for a person profile."""
    lines = [f"# {name}", ""]
    if organization:
        lines.append(f"**Организация:** {organization}  ")
    if role:
        lines.append(f"**Должность:** {role}  ")
    lines.append(f"**Добавлен:** {_today()}  ")
    lines.append("")

    if appearance:
        lines.extend(["## Внешность", appearance, ""])
    if context:
        lines.extend(["## Контекст знакомства", context, ""])
    if notes:
        lines.extend(["## Заметки", notes, ""])

    lines.extend(["## История обновлений"])
    if history:
        lines.append(history)
    else:
        lines.append(f"- {_today()}: Первая запись создана")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _people_add(ctx: ToolContext, name: str, organization: str = "",
                role: str = "", appearance: str = "", context: str = "",
                notes: str = "") -> str:
    """Add or update a person in the knowledge base."""
    if not name or not name.strip():
        return "⚠️ Name is required."

    name = name.strip()
    slug = _make_slug(name)
    d = _ensure_dir(ctx)
    index = _load_index(ctx)

    # Check if person already exists (by slug)
    existing = None
    for entry in index:
        if entry.get("slug") == slug:
            existing = entry
            break

    now = _now_iso()
    profile_path = d / f"{slug}.md"

    if existing:
        # Update existing profile — merge fields
        if organization:
            existing["organization"] = organization
        if role:
            existing["role"] = role
        existing["updated"] = now

        # Read existing .md for history section
        old_history = ""
        if profile_path.exists():
            old_content = profile_path.read_text(encoding="utf-8")
            hist_match = re.search(r"## История обновлений\n(.*?)(?:\n## |\Z)",
                                   old_content, re.DOTALL)
            if hist_match:
                old_history = hist_match.group(1).strip()

        history = f"{old_history}\n- {_today()}: Обновлена запись" if old_history else f"- {_today()}: Первая запись создана"

        md = _build_profile_md(
            name=existing.get("name", name),
            organization=existing.get("organization", organization),
            role=existing.get("role", role),
            appearance=appearance or "",
            context=context or "",
            notes=notes or "",
            history=history,
        )
        profile_path.write_text(md, encoding="utf-8")
        _save_index(ctx, index)
        return f"✅ Обновлён профиль: {name} ({slug})"

    # New person
    entry = {
        "slug": slug,
        "name": name,
        "organization": organization,
        "role": role,
        "added": now,
        "updated": now,
    }
    index.append(entry)

    md = _build_profile_md(
        name=name, organization=organization, role=role,
        appearance=appearance, context=context, notes=notes,
    )
    profile_path.write_text(md, encoding="utf-8")
    _save_index(ctx, index)
    return f"✅ Добавлен в базу: {name} ({slug})"


def _people_search(ctx: ToolContext, query: str) -> str:
    """Search people knowledge base by name, organization, or role."""
    if not query or not query.strip():
        return "⚠️ Query is required."

    q = query.strip().lower()
    index = _load_index(ctx)
    d = _people_dir(ctx)

    results = []
    for entry in index:
        # Search in index fields
        fields = " ".join([
            entry.get("name", ""),
            entry.get("organization", ""),
            entry.get("role", ""),
        ]).lower()

        if q in fields:
            results.append(entry)
            continue

        # Search in .md file content
        md_path = d / f"{entry['slug']}.md"
        if md_path.exists():
            try:
                content = md_path.read_text(encoding="utf-8").lower()
                if q in content:
                    results.append(entry)
            except OSError:
                pass

    if not results:
        return f"Ничего не найдено по запросу: «{query}»"

    lines = [f"Найдено: {len(results)}"]
    for r in results:
        org = f", {r['organization']}" if r.get("organization") else ""
        role = f" — {r['role']}" if r.get("role") else ""
        lines.append(f"- **{r['name']}**{org}{role}")
    return "\n".join(lines)


def _people_get(ctx: ToolContext, name: str) -> str:
    """Get full profile of a person by name."""
    if not name or not name.strip():
        return "⚠️ Name is required."

    slug = _make_slug(name.strip())
    d = _people_dir(ctx)
    profile_path = d / f"{slug}.md"

    if not profile_path.exists():
        # Try searching by name in index
        index = _load_index(ctx)
        q = name.strip().lower()
        for entry in index:
            if q in entry.get("name", "").lower():
                alt_path = d / f"{entry['slug']}.md"
                if alt_path.exists():
                    return alt_path.read_text(encoding="utf-8")
        return f"Профиль не найден: «{name}». Используйте people_search для поиска."

    return profile_path.read_text(encoding="utf-8")


def _people_list(ctx: ToolContext) -> str:
    """List all people in the knowledge base."""
    index = _load_index(ctx)
    if not index:
        return "База знаний по людям пуста. Используйте people_add для добавления."

    lines = [f"Всего записей: {len(index)}", ""]
    for entry in sorted(index, key=lambda e: e.get("name", "")):
        org = f", {entry['organization']}" if entry.get("organization") else ""
        role = f" — {entry['role']}" if entry.get("role") else ""
        lines.append(f"- **{entry['name']}**{org}{role}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("people_add", {
            "name": "people_add",
            "description": (
                "Add or update a person in the people knowledge base. "
                "Stores name, organization, role, appearance description, "
                "context of meeting, and notes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Full name of the person",
                    },
                    "organization": {
                        "type": "string",
                        "description": "Organization / company",
                    },
                    "role": {
                        "type": "string",
                        "description": "Job title / role",
                    },
                    "appearance": {
                        "type": "string",
                        "description": "Physical appearance description from VLM analysis",
                    },
                    "context": {
                        "type": "string",
                        "description": "Context of how/where the person was met",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Additional notes about the person",
                    },
                },
                "required": ["name"],
            },
        }, _people_add),
        ToolEntry("people_search", {
            "name": "people_search",
            "description": (
                "Search people knowledge base by name, organization, role, "
                "or any text in their profiles."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (name, organization, keyword)",
                    },
                },
                "required": ["query"],
            },
        }, _people_search),
        ToolEntry("people_get", {
            "name": "people_get",
            "description": "Get the full profile of a person by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the person to look up",
                    },
                },
                "required": ["name"],
            },
        }, _people_get),
        ToolEntry("people_list", {
            "name": "people_list",
            "description": "List all people in the knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }, _people_list),
    ]
