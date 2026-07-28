"""Task manager tools for Ouroboros agent."""

from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ouroboros.task_manager.db import TaskDB
from ouroboros.tools.registry import ToolContext, ToolEntry
from ouroboros.utils import short, utc_now_iso

_PRIORITIES = ("P0", "P1", "P2", "P3")
_CENTERS = ("service_design_ai", "implementation_support", "platform_engineering")
_FILTERS = ("all", "at_risk", "overdue")

# A deadline this many days out (or already passed) counts as "at risk".
_AT_RISK_WINDOW_DAYS = 7


def _db(ctx: ToolContext) -> TaskDB:
    return TaskDB(ctx.drive_root / "task_manager" / "tasks.db")


def _today() -> dt.date:
    return dt.datetime.now(tz=dt.timezone.utc).date()


def _day_start(day: dt.date) -> str:
    """Midnight UTC of `day`, in the format SQLite's datetime('now') produces."""
    return f"{day.isoformat()} 00:00:00"


def _parse_date(value: Any) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _cell(value: Any) -> str:
    """Make a value safe for a markdown table cell."""
    return str(value if value not in (None, "") else "—").replace("|", "\\|").replace("\n", " ")


def _parse_milestones(raw: str) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """Parse the milestones_json argument. Returns (milestones, error_message)."""
    if not raw or not raw.strip():
        return [], None
    try:
        parsed = json.loads(raw)
    except ValueError as e:
        return [], f"⚠️ milestones_json is not valid JSON: {e}"
    if not isinstance(parsed, list):
        return [], "⚠️ milestones_json must be a JSON array of {name, planned_date} objects."

    milestones = []
    for item in parsed:
        if not isinstance(item, dict) or not item.get("name"):
            return [], "⚠️ Each milestone must be an object with a 'name' and a 'planned_date'."
        milestones.append({
            "name": str(item["name"]),
            "planned_date": str(item.get("planned_date", "")),
        })
    return milestones, None


# --- Tool handlers ---

def _task_add(
    ctx: ToolContext,
    title: str,
    priority: str,
    planned_end: str,
    owner: str = "",
    center: str = "",
    milestones_json: str = "",
) -> str:
    """Register a new task baseline."""
    title = (title or "").strip()
    priority = (priority or "").strip().upper()
    if priority not in _PRIORITIES:
        return f"⚠️ priority must be one of {', '.join(_PRIORITIES)} (got '{priority}')."

    center = (center or "").strip()
    if center and center not in _CENTERS:
        return f"⚠️ center must be one of {', '.join(_CENTERS)} (got '{center}')."

    owner = (owner or "").strip()

    end = _parse_date(planned_end)
    if end is None:
        return f"⚠️ planned_end must be an ISO date (YYYY-MM-DD), got '{planned_end}'."

    milestones, error = _parse_milestones(milestones_json)
    if error:
        return error

    task_id = uuid.uuid4().hex[:8]
    _db(ctx).save_baseline({
        "id": uuid.uuid4().hex,
        "task_id": task_id,
        "version": 1,
        "title": title,
        "priority": priority,
        "owner": owner,
        "center": center,
        "planned_start": _today().isoformat(),
        "planned_end": end.isoformat(),
        "milestones": milestones,
        "dependencies": [],
        "status": "active",
    })

    lines = [
        f"✅ Task registered: **{title}**",
        f"- task_id: `{task_id}`",
        f"- priority: {priority}",
        f"- planned_end: {end.isoformat()}",
    ]
    if owner:
        lines.append(f"- owner: {owner}")
    if center:
        lines.append(f"- center: {center}")
    if milestones:
        lines.append(f"- milestones: {len(milestones)}")
        lines += [f"  - {m['name']} → {m['planned_date'] or '—'}" for m in milestones]
    return "\n".join(lines)


def _task_update(ctx: ToolContext, task_id: str, status_text: str) -> str:
    """Record a free-form status update against a task."""
    db = _db(ctx)
    baseline = db.get_baseline(task_id)
    if baseline is None:
        return f"⚠️ Task {task_id} not found. Use task_list to see registered tasks."

    db.save_update({
        "id": uuid.uuid4().hex,
        "task_id": task_id,
        "raw_text": status_text,
    })
    return f"Update recorded for task {task_id}"


def _task_list(ctx: ToolContext, filter: str = "all") -> str:
    """List tasks as a markdown table."""
    mode = (filter or "all").strip().lower()
    if mode not in _FILTERS:
        return f"⚠️ filter must be one of {', '.join(_FILTERS)} (got '{filter}')."

    db = _db(ctx)
    baselines = db.list_baselines("active")

    if mode != "all":
        today = _today()
        cutoff = today + dt.timedelta(days=_AT_RISK_WINDOW_DAYS)
        flagged = {d.get("task_id") for d in db.get_open_deviations()}
        selected = []
        for b in baselines:
            end = _parse_date(b.get("planned_end"))
            if mode == "overdue":
                if end is not None and end < today:
                    selected.append(b)
            elif b.get("task_id") in flagged or (end is not None and end <= cutoff):
                selected.append(b)
        baselines = selected

    if not baselines:
        return f"No tasks match filter '{mode}'."

    rows = [
        "| task_id | title | priority | planned_end | status |",
        "| --- | --- | --- | --- | --- |",
    ]
    rows += [
        "| `{}` | {} | {} | {} | {} |".format(
            _cell(b.get("task_id")), _cell(b.get("title")), _cell(b.get("priority")),
            _cell(b.get("planned_end")), _cell(b.get("status")),
        )
        for b in baselines
    ]
    return f"**Tasks ({mode}): {len(baselines)}**\n\n" + "\n".join(rows)


def _task_approve(ctx: ToolContext, proposal_id: str, comment: str = "") -> str:
    """Approve a pending proposal."""
    comment = (comment or "").strip()
    _db(ctx).log_decision({
        "id": proposal_id,
        "deviation_id": proposal_id,
        "user_action": "approved",
        "user_comment": comment,
        "resolved_at": utc_now_iso(),
    })
    suffix = f" Comment: {comment}" if comment else ""
    return f"✅ Proposal {proposal_id} approved.{suffix}"


def _task_reject(ctx: ToolContext, proposal_id: str, reason: str = "") -> str:
    """Reject a pending proposal."""
    reason = (reason or "").strip()
    _db(ctx).log_decision({
        "id": proposal_id,
        "deviation_id": proposal_id,
        "user_action": "rejected",
        "user_comment": reason,
        "resolved_at": utc_now_iso(),
    })
    suffix = f" Reason: {reason}" if reason else ""
    return f"❌ Proposal {proposal_id} rejected.{suffix}"


def _deviation_line(dev: Dict[str, Any], titles: Dict[str, str]) -> str:
    task_id = dev.get("task_id") or "?"
    label = titles.get(task_id, task_id)
    parts = [f"- **{label}**"]
    if dev.get("milestone_name"):
        parts.append(f"milestone '{dev['milestone_name']}'")
    slip = dev.get("days_slip")
    if slip is not None:
        parts.append(f"{slip}d slip")
    if dev.get("severity"):
        parts.append(str(dev["severity"]))
    if dev.get("root_cause"):
        parts.append(f"cause: {short(dev['root_cause'], 100)}")
    return " — ".join(parts) + f" (id: `{dev.get('id')}`)"


def _task_morning_review(ctx: ToolContext) -> str:
    """Morning briefing: open deviations and upcoming deadlines."""
    db = _db(ctx)
    today = _today()
    cutoff = today + dt.timedelta(days=_AT_RISK_WINDOW_DAYS)

    baselines = db.list_baselines("active")
    titles = {b.get("task_id"): b.get("title") or b.get("task_id") for b in baselines}
    deviations = db.get_open_deviations()

    lines = [f"# 🌅 Morning review — {today.isoformat()}", ""]

    lines.append(f"## Open deviations ({len(deviations)})")
    lines += [_deviation_line(d, titles) for d in deviations] or ["- None. All tasks on plan."]

    upcoming = []
    for b in baselines:
        end = _parse_date(b.get("planned_end"))
        if end is not None and end <= cutoff:
            upcoming.append((end, b))
    upcoming.sort(key=lambda pair: pair[0])

    lines += ["", f"## Deadlines through {cutoff.isoformat()} ({len(upcoming)})"]
    if upcoming:
        for end, b in upcoming:
            flag = " ⚠️ OVERDUE" if end < today else ""
            lines.append(
                f"- **{b.get('title') or b.get('task_id')}** ({b.get('priority') or '—'})"
                f" — due {end.isoformat()}{flag} · `{b.get('task_id')}`"
            )
    else:
        lines.append("- No deadlines in the next week.")

    return "\n".join(lines)


def _task_evening_review(ctx: ToolContext) -> str:
    """Evening wrap-up: updates recorded today and deviations still open."""
    db = _db(ctx)
    today = _today()

    baselines = db.list_baselines("active")
    titles = {b.get("task_id"): b.get("title") or b.get("task_id") for b in baselines}
    updates = db.get_updates_since(_day_start(today))
    deviations = db.get_open_deviations()

    lines = [f"# 🌇 Evening review — {today.isoformat()}", ""]

    lines.append(f"## Updates today ({len(updates)})")
    if updates:
        for u in updates:
            task_id = u.get("task_id") or "?"
            lines.append(f"- **{titles.get(task_id, task_id)}**: {short(u.get('raw_text'), 200)}")
    else:
        lines.append("- No updates recorded today.")

    lines += ["", f"## Still open ({len(deviations)} deviations)"]
    lines += [_deviation_line(d, titles) for d in deviations] or ["- Nothing open."]

    lines += ["", f"Active tasks tracked: {len(baselines)}"]
    return "\n".join(lines)


def _task_report(ctx: ToolContext) -> str:
    """Weekly report: headline metrics across tracked tasks."""
    db = _db(ctx)
    today = _today()
    week_ago = today - dt.timedelta(days=7)

    baselines = db.list_baselines("active")
    deviations = db.get_open_deviations()
    updates = db.get_updates_since(_day_start(week_ago))

    by_priority = {p: 0 for p in _PRIORITIES}
    overdue = 0
    for b in baselines:
        priority = str(b.get("priority") or "").upper()
        if priority in by_priority:
            by_priority[priority] += 1
        end = _parse_date(b.get("planned_end"))
        if end is not None and end < today:
            overdue += 1

    by_severity: Dict[str, int] = {}
    for d in deviations:
        severity = str(d.get("severity") or "unspecified")
        by_severity[severity] = by_severity.get(severity, 0) + 1

    priority_mix = ", ".join(f"{p}: {n}" for p, n in by_priority.items() if n) or "—"
    severity_mix = ", ".join(f"{s}: {n}" for s, n in sorted(by_severity.items())) or "—"

    return "\n".join([
        f"# 📊 Weekly report — {week_ago.isoformat()} → {today.isoformat()}",
        "",
        f"- Active tasks: **{len(baselines)}** ({priority_mix})",
        f"- Overdue tasks: **{overdue}**",
        f"- Open deviations: **{len(deviations)}** ({severity_mix})",
        f"- Updates this week: **{len(updates)}**",
    ])


# --- Tool registration ---

def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("task_add", {
            "name": "task_add",
            "description": "Register a new tracked task with a planned deadline and optional milestones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short task title"},
                    "priority": {"type": "string", "enum": list(_PRIORITIES),
                                 "description": "Priority: P0 (highest) .. P3"},
                    "planned_end": {"type": "string", "description": "Planned completion date, ISO (YYYY-MM-DD)"},
                    "owner": {"type": "string", "description": "Person accountable for the task"},
                    "center": {"type": "string", "enum": list(_CENTERS),
                               "description": "Owning competence center"},
                    "milestones_json": {
                        "type": "string",
                        "description": 'JSON array of milestones, e.g. [{"name": "Design done", "planned_date": "2026-08-10"}]',
                    },
                },
                "required": ["title", "priority", "planned_end"],
            },
        }, _task_add),
        ToolEntry("task_update", {
            "name": "task_update",
            "description": "Record a free-form status update for a tracked task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task id returned by task_add or task_list"},
                    "status_text": {"type": "string", "description": "Update text as reported, verbatim"},
                },
                "required": ["task_id", "status_text"],
            },
        }, _task_update),
        ToolEntry("task_list", {
            "name": "task_list",
            "description": "List tracked tasks as a markdown table, optionally only those at risk or overdue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {"type": "string", "enum": list(_FILTERS),
                               "description": "'all' (default), 'at_risk' (deadline within a week or open deviation), 'overdue'"},
                },
                "required": [],
            },
        }, _task_list),
        ToolEntry("task_approve", {
            "name": "task_approve",
            "description": "Approve a proposal and log the decision.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {"type": "string", "description": "Id of the proposal to approve"},
                    "comment": {"type": "string", "description": "Optional comment to store with the decision"},
                },
                "required": ["proposal_id"],
            },
        }, _task_approve),
        ToolEntry("task_reject", {
            "name": "task_reject",
            "description": "Reject a proposal and log the decision.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {"type": "string", "description": "Id of the proposal to reject"},
                    "reason": {"type": "string", "description": "Why the proposal was rejected"},
                },
                "required": ["proposal_id"],
            },
        }, _task_reject),
        ToolEntry("task_morning_review", {
            "name": "task_morning_review",
            "description": "Morning briefing: open deviations plus deadlines falling in the next week.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }, _task_morning_review),
        ToolEntry("task_evening_review", {
            "name": "task_evening_review",
            "description": "Evening wrap-up: updates recorded today and deviations still open.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }, _task_evening_review),
        ToolEntry("task_report", {
            "name": "task_report",
            "description": "Weekly report: task counts by priority, overdue tasks, open deviations, update volume.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }, _task_report),
    ]
