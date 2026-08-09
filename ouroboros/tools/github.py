"""GitHub tools via REST API — no gh CLI required."""
from __future__ import annotations
import json, logging, os, subprocess
from typing import Any, Dict, List, Optional
from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)

REPO_OWNER = "kosgogolev-gith"
REPO_NAME  = "ouroboros"


def _api(method: str, path: str, data: dict = None, ctx=None) -> Any:
    """Call GitHub REST API."""
    import urllib.request, urllib.error
    token = (
        os.environ.get("GITHUB_TOKEN")
        or os.environ.get("OUROBOROS_GITHUB_TOKEN")
        or _token_from_git(ctx)
    )
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method.upper())
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def _token_from_git(ctx) -> str:
    """Extract GitHub token from git remote URL."""
    try:
        repo_dir = str(ctx.repo_dir) if ctx else "/home/goga/ouroboros"
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_dir, capture_output=True, text=True, timeout=5
        )
        url = result.stdout.strip()
        # https://TOKEN@github.com/...
        if "@" in url:
            return url.split("//")[1].split("@")[0]
    except Exception:
        pass
    # Fallback: read from .env
    try:
        for line in open("/home/goga/ouroboros.env"):
            line = line.strip()
            if line.startswith("GITHUB_TOKEN="):
                return line.split("=",1)[1]
    except Exception:
        pass
    return ""


def _list_issues(ctx, state: str = "open", limit: int = 10) -> str:
    issues = _api("GET", f"/issues?state={state}&per_page={limit}", ctx=ctx)
    if isinstance(issues, dict) and "error" in issues:
        return f"❌ {issues['error']}"
    if not issues:
        return f"No {state} issues."
    lines = [f"**GitHub Issues ({state}, {len(issues)}):**"]
    for i in issues:
        labels = ", ".join(l["name"] for l in i.get("labels", []))
        lab = f" [{labels}]" if labels else ""
        lines.append(f"#{i['number']} {i['title']}{lab} — {i['state']}")
    return "\n".join(lines)


def _get_issue(ctx, issue_number: int) -> str:
    i = _api("GET", f"/issues/{issue_number}", ctx=ctx)
    if isinstance(i, dict) and "error" in i:
        return f"❌ {i['error']}"
    labels = ", ".join(l["name"] for l in i.get("labels", []))
    body = (i.get("body") or "")[:500]
    return (
        f"**#{i['number']} {i['title']}**\n"
        f"State: {i['state']} | Labels: {labels or 'none'}\n"
        f"Created: {i.get('created_at','')[:10]}\n\n{body}"
    )


def _create_issue(ctx, title: str, body: str = "", labels: str = "") -> str:
    data: Dict[str, Any] = {"title": title, "body": body}
    if labels:
        data["labels"] = [l.strip() for l in labels.split(",")]
    result = _api("POST", "/issues", data=data, ctx=ctx)
    if "error" in result:
        return f"❌ {result['error']}"
    return f"✅ Issue created: #{result['number']} {result['title']}\n{result.get('html_url','')}"


def _close_issue(ctx, issue_number: int, comment: str = "") -> str:
    if comment:
        _api("POST", f"/issues/{issue_number}/comments", {"body": comment}, ctx=ctx)
    result = _api("PATCH", f"/issues/{issue_number}", {"state": "closed"}, ctx=ctx)
    if "error" in result:
        return f"❌ {result['error']}"
    return f"✅ Issue #{issue_number} closed."


def _comment_issue(ctx, issue_number: int, comment: str) -> str:
    result = _api("POST", f"/issues/{issue_number}/comments", {"body": comment}, ctx=ctx)
    if "error" in result:
        return f"❌ {result['error']}"
    return f"✅ Comment added to #{issue_number}"


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("list_github_issues", {
            "name": "list_github_issues",
            "description": "List GitHub issues via API (no gh CLI needed).",
            "parameters": {"type": "object", "properties": {
                "state": {"type": "string", "enum": ["open","closed","all"], "default": "open"},
                "limit": {"type": "integer", "default": 10},
            }, "required": []},
        }, _list_issues),
        ToolEntry("get_github_issue", {
            "name": "get_github_issue",
            "description": "Get a GitHub issue by number.",
            "parameters": {"type": "object", "properties": {
                "issue_number": {"type": "integer"},
            }, "required": ["issue_number"]},
        }, _get_issue),
        ToolEntry("create_github_issue", {
            "name": "create_github_issue",
            "description": "Create a GitHub issue.",
            "parameters": {"type": "object", "properties": {
                "title": {"type": "string"},
                "body": {"type": "string", "default": ""},
                "labels": {"type": "string", "description": "Comma-separated labels", "default": ""},
            }, "required": ["title"]},
        }, _create_issue),
        ToolEntry("close_github_issue", {
            "name": "close_github_issue",
            "description": "Close a GitHub issue.",
            "parameters": {"type": "object", "properties": {
                "issue_number": {"type": "integer"},
                "comment": {"type": "string", "default": ""},
            }, "required": ["issue_number"]},
        }, _close_issue),
        ToolEntry("comment_on_issue", {
            "name": "comment_on_issue",
            "description": "Add a comment to a GitHub issue.",
            "parameters": {"type": "object", "properties": {
                "issue_number": {"type": "integer"},
                "comment": {"type": "string"},
            }, "required": ["issue_number", "comment"]},
        }, _comment_issue),
    ]
