"""GitHub tools: issues, comments, reactions — using REST API (no gh CLI)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from ouroboros.integrations.github import GitHubClient, GitHubAPIError, RateLimitError, AuthenticationError, NotFoundError
from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool handlers using REST API
# ---------------------------------------------------------------------------

def _list_issues(ctx: ToolContext, state: str = "open", labels: str = "", limit: int = 20) -> str:
    """List GitHub issues with optional filters."""
    try:
        client = GitHubClient()
    except AuthenticationError as e:
        return f"⚠️ AUTH_ERROR: {e}"
    except ValueError as e:
        return f"⚠️ CONFIG_ERROR: {e}"

    label_list = [l.strip() for l in labels.split(",") if l.strip()] if labels else None

    try:
        issues = client.list_issues(state=state, labels=label_list, limit=limit)
    except RateLimitError as e:
        return f"⚠️ RATE_LIMIT: {e}"
    except GitHubAPIError as e:
        return f"⚠️ API_ERROR: {e} (status={e.status_code})"

    if not issues:
        return f"No {state} issues found."

    lines = [f"**{len(issues)} {state} issue(s):**\n"]
    for issue in issues:
        labels_str = ", ".join(l.get("name", "") for l in issue.get("labels", []))
        author = issue.get("user", {}).get("login", "unknown")
        lines.append(
            f"- **#{issue['number']}** {issue['title']}"
            f" (by @{author}{', labels: ' + labels_str if labels_str else ''})"
        )
        body = (issue.get("body") or "").strip()
        if body:
            preview = body[:200] + ("..." if len(body) > 200 else "")
            lines.append(f"  > {preview}")

    return "\n".join(lines)


def _get_issue(ctx: ToolContext, number: int) -> str:
    """Get a single issue with full details and comments."""
    if number <= 0:
        return "⚠️ issue number must be positive"

    try:
        client = GitHubClient()
    except AuthenticationError as e:
        return f"⚠️ AUTH_ERROR: {e}"
    except ValueError as e:
        return f"⚠️ CONFIG_ERROR: {e}"

    try:
        issue = client.get_issue(number)
    except NotFoundError:
        return f"⚠️ Issue #{number} not found."
    except RateLimitError as e:
        return f"⚠️ RATE_LIMIT: {e}"
    except GitHubAPIError as e:
        return f"⚠️ API_ERROR: {e} (status={e.status_code})"

    labels_str = ", ".join(l.get("name", "") for l in issue.get("labels", []))
    author = issue.get("user", {}).get("login", "unknown")

    lines = [
        f"## Issue #{issue['number']}: {issue['title']}",
        f"**State:** {issue['state']}  |  **Author:** @{author}",
    ]
    if labels_str:
        lines.append(f"**Labels:** {labels_str}")

    body = (issue.get("body") or "").strip()
    if body:
        lines.append(f"\n**Body:**\n{body[:3000]}")

    comments = issue.get("comments", [])
    if comments:
        lines.append(f"\n**Comments ({len(comments)}):**")
        for c in comments[:10]:
            c_author = c.get("user", {}).get("login", "unknown")
            c_body = (c.get("body") or "").strip()[:500]
            lines.append(f"\n@{c_author}:\n{c_body}")

    return "\n".join(lines)


def _comment_on_issue(ctx: ToolContext, number: int, body: str) -> str:
    """Add a comment to an issue."""
    if number <= 0:
        return "⚠️ issue number must be positive"
    if not body or not body.strip():
        return "⚠️ Comment body cannot be empty."

    try:
        client = GitHubClient()
    except AuthenticationError as e:
        return f"⚠️ AUTH_ERROR: {e}"
    except ValueError as e:
        return f"⚠️ CONFIG_ERROR: {e}"

    try:
        client.comment_on_issue(number, body)
        return f"✅ Comment added to issue #{number}."
    except NotFoundError:
        return f"⚠️ Issue #{number} not found."
    except RateLimitError as e:
        return f"⚠️ RATE_LIMIT: {e}"
    except GitHubAPIError as e:
        return f"⚠️ API_ERROR: {e} (status={e.status_code})"


def _close_issue(ctx: ToolContext, number: int, comment: str = "") -> str:
    """Close an issue with optional closing comment."""
    if number <= 0:
        return "⚠️ issue number must be positive"

    try:
        client = GitHubClient()
    except AuthenticationError as e:
        return f"⚠️ AUTH_ERROR: {e}"
    except ValueError as e:
        return f"⚠️ CONFIG_ERROR: {e}"

    try:
        client.close_issue(number, comment if comment.strip() else None)
        return f"✅ Issue #{number} closed."
    except NotFoundError:
        return f"⚠️ Issue #{number} not found."
    except RateLimitError as e:
        return f"⚠️ RATE_LIMIT: {e}"
    except GitHubAPIError as e:
        return f"⚠️ API_ERROR: {e} (status={e.status_code})"


def _create_issue(ctx: ToolContext, title: str, body: str = "", labels: str = "") -> str:
    """Create a new GitHub issue."""
    if not title or not title.strip():
        return "⚠️ Issue title cannot be empty."

    try:
        client = GitHubClient()
    except AuthenticationError as e:
        return f"⚠️ AUTH_ERROR: {e}"
    except ValueError as e:
        return f"⚠️ CONFIG_ERROR: {e}"

    label_list = [l.strip() for l in labels.split(",") if l.strip()] if labels else None

    try:
        issue = client.create_issue(title.strip(), body if body.strip() else None, labels=label_list)
        return f"✅ Issue created: {issue['html_url']} (#{issue['number']})"
    except RateLimitError as e:
        return f"⚠️ RATE_LIMIT: {e}"
    except GitHubAPIError as e:
        return f"⚠️ API_ERROR: {e} (status={e.status_code})"


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("list_github_issues", {
            "name": "list_github_issues",
            "description": "List GitHub issues. Use to check for new tasks, bug reports, or feature requests from the creator or contributors.",
            "parameters": {"type": "object", "properties": {
                "state": {"type": "string", "default": "open", "enum": ["open", "closed", "all"], "description": "Filter by state"},
                "labels": {"type": "string", "default": "", "description": "Filter by label (comma-separated)"},
                "limit": {"type": "integer", "default": 20, "description": "Max issues to return (max 100)"},
            }, "required": []},
        }, _list_issues),

        ToolEntry("get_github_issue", {
            "name": "get_github_issue",
            "description": "Get full details of a GitHub issue including body and comments.",
            "parameters": {"type": "object", "properties": {
                "number": {"type": "integer", "description": "Issue number"},
            }, "required": ["number"]},
        }, _get_issue),

        ToolEntry("comment_on_issue", {
            "name": "comment_on_issue",
            "description": "Add a comment to a GitHub issue. Use to respond to issues, share progress, or ask clarifying questions.",
            "parameters": {"type": "object", "properties": {
                "number": {"type": "integer", "description": "Issue number"},
                "body": {"type": "string", "description": "Comment text (markdown)"},
            }, "required": ["number", "body"]},
        }, _comment_on_issue),

        ToolEntry("close_github_issue", {
            "name": "close_github_issue",
            "description": "Close a GitHub issue with optional closing comment.",
            "parameters": {"type": "object", "properties": {
                "number": {"type": "integer", "description": "Issue number"},
                "comment": {"type": "string", "default": "", "description": "Optional closing comment"},
            }, "required": ["number"]},
        }, _close_issue),

        ToolEntry("create_github_issue", {
            "name": "create_github_issue",
            "description": "Create a new GitHub issue. Use for tracking tasks, documenting bugs, or planning features.",
            "parameters": {"type": "object", "properties": {
                "title": {"type": "string", "description": "Issue title"},
                "body": {"type": "string", "default": "", "description": "Issue body (markdown)"},
                "labels": {"type": "string", "default": "", "description": "Labels (comma-separated)"},
            }, "required": ["title"]},
        }, _create_issue),
    ]
