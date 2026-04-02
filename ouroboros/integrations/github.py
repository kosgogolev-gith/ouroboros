"""GitHub REST API client.

Provides direct access to GitHub Issues API without gh CLI dependency.
Uses environment variable GITHUB_TOKEN for authentication.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

log = logging.getLogger(__name__)

# GitHub API base URL
API_BASE = "https://api.github.com"

# Default headers
DEFAULT_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


class GitHubAPIError(Exception):
    """Base exception for GitHub API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class RateLimitError(GitHubAPIError):
    """Raised when rate limit is exceeded."""
    pass


class AuthenticationError(GitHubAPIError):
    """Raised when authentication fails."""
    pass


class NotFoundError(GitHubAPIError):
    """Raised when resource is not found."""
    pass


class GitHubClient:
    """Direct GitHub REST API client."""

    def __init__(self, token: Optional[str] = None, repo: Optional[str] = None):
        """
        Initialize client.

        Args:
            token: GitHub personal access token. If None, reads from GITHUB_TOKEN env.
            repo: Repository in 'owner/repo' format. If None, attempts to detect from git remote.
        """
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        if not self.token:
            raise AuthenticationError(
                "GitHub token not provided. Set GITHUB_TOKEN environment variable."
            )

        self.repo = repo or self._detect_repo()
        if not self.repo:
            raise ValueError(
                "Repository not specified and could not be detected from git remote. "
                "Set GITHUB_REPO env var or pass repo argument."
            )

        self.session = requests.Session()
        self.session.headers.update({
            **DEFAULT_HEADERS,
            "Authorization": f"Bearer {self.token}",
        })

    def _detect_repo(self) -> Optional[str]:
        """Try to get 'owner/repo' from git remote using gh or git."""
        # Try using gh (might be configured)
        try:
            import subprocess
            result = subprocess.run(
                ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                capture_output=True, text=True, timeout=10, check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

        # Fallback: parse git remote origin
        try:
            import subprocess
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=10, check=False
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                # Parse https://github.com/owner/repo.git or git@github.com:owner/repo.git
                if url.startswith("https://"):
                    parts = url.split("/")
                    if len(parts) >= 2:
                        repo_part = parts[-1].removesuffix(".git")
                        owner_part = parts[-2]
                        return f"{owner_part}/{repo_part}"
                elif url.startswith("git@"):
                    # git@github.com:owner/repo.git
                    path = url.split(":")[-1].removesuffix(".git")
                    return path
        except Exception:
            pass

        return None

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        accept: Optional[str] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Make an HTTP request to GitHub API.

        Returns status code and parsed JSON response (or error message).
        """
        url = f"{API_BASE}{endpoint}"
        headers = {}
        if accept:
            headers["Accept"] = accept

        try:
            resp = self.session.request(method, url, params=params, json=json_data, headers=headers)
        except requests.RequestException as e:
            raise GitHubAPIError(f"Network error: {e}")

        if resp.status_code == 403:
            # Rate limit or insufficient scope
            remaining = resp.headers.get("X-RateLimit-Remaining")
            reset_ts = resp.headers.get("X-RateLimit-Reset")
            if remaining == "0":
                reset_time = int(reset_ts) if reset_ts else "unknown"
                raise RateLimitError(
                    f"GitHub API rate limit exceeded. Reset at {reset_time}.",
                    status_code=resp.status_code,
                    response_body=resp.text
                )
            else:
                raise AuthenticationError(
                    "GitHub API authentication failed or token lacks required scopes.",
                    status_code=resp.status_code,
                    response_body=resp.text
                )

        if resp.status_code == 404:
            raise NotFoundError(
                f"Resource not found: {url}",
                status_code=resp.status_code,
                response_body=resp.text
            )

        if not (200 <= resp.status_code < 300):
            raise GitHubAPIError(
                f"GitHub API error: {resp.status_code} {resp.reason}",
                status_code=resp.status_code,
                response_body=resp.text
            )

        try:
            data = resp.json()
        except json.JSONDecodeError:
            data = {"_raw": resp.text}

        return resp.status_code, data

    def list_issues(
        self,
        state: str = "open",
        labels: Optional[str] = None,
        limit: int = 20,
        page: int = 1,
        per_page: int = 100,
        sort: str = "created",
        direction: str = "desc",
    ) -> List[Dict[str, Any]]:
        """
        List issues for the repository.

        Args:
            state: 'open', 'closed', or 'all'
            labels: Comma-separated label names (e.g. "bug,enhancement")
            limit: Maximum number of issues to return (capped at 100 via GitHub pagination)
            page: Page number (starting at 1)
            per_page: Items per page (max 100)
            sort: 'created', 'updated', or 'comments'
            direction: 'asc' or 'desc'

        Returns:
            List of issue objects.
        """
        effective_per_page = min(per_page, 100)
        params = {
            "state": state,
            "sort": sort,
            "direction": direction,
            "per_page": effective_per_page,
            "page": page,
        }
        if labels:
            params["labels"] = labels

        _, data = self._request("GET", f"/repos/{self.repo}/issues", params=params)
        # GitHub returns a list directly for this endpoint
        if isinstance(data, list):
            issues = data
        else:
            issues = data.get("items", []) if "items" in data else []

        # Respect limit (may be less than per_page if fewer results)
        return issues[:limit]

    def get_issue(self, number: int) -> Dict[str, Any]:
        """
        Get a single issue with full details including comments.

        Args:
            number: Issue number (positive integer)

        Returns:
            Issue object with nested comments.
        """
        if number <= 0:
            raise ValueError("Issue number must be positive")

        _, issue = self._request("GET", f"/repos/{self.repo}/issues/{number}")
        return issue

    def comment_on_issue(self, number: int, body: str) -> Dict[str, Any]:
        """
        Add a comment to an issue.

        Args:
            number: Issue number
            body: Comment body (markdown supported)

        Returns:
            Created comment object.
        """
        if number <= 0:
            raise ValueError("Issue number must be positive")
        if not body or not body.strip():
            raise ValueError("Comment body cannot be empty")

        _, comment = self._request(
            "POST",
            f"/repos/{self.repo}/issues/{number}/comments",
            json_data={"body": body}
        )
        return comment

    def close_issue(self, number: int, comment: Optional[str] = None) -> Dict[str, Any]:
        """
        Close an issue, optionally with a closing comment.

        Args:
            number: Issue number
            comment: Optional closing comment

        Returns:
            Updated issue object.
        """
        if number <= 0:
            raise ValueError("Issue number must be positive")

        # First, add comment if provided
        if comment and comment.strip():
            self.comment_on_issue(number, comment)

        _, issue = self._request(
            "PATCH",
            f"/repos/{self.repo}/issues/{number}",
            json_data={"state": "closed"}
        )
        return issue

    def create_issue(
        self,
        title: str,
        body: Optional[str] = None,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new GitHub issue.

        Args:
            title: Issue title
            body: Issue body (markdown)
            labels: List of label names
            assignees: List of usernames to assign

        Returns:
            Created issue object.
        """
        if not title or not title.strip():
            raise ValueError("Issue title cannot be empty")

        payload: Dict[str, Any] = {"title": title.strip()}
        if body:
            payload["body"] = body
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees

        _, issue = self._request(
            "POST",
            f"/repos/{self.repo}/issues",
            json_data=payload
        )
        return issue

    # Convenience helpers
    def list_open_issues(self, **kwargs) -> List[Dict[str, Any]]:
        """List only open issues."""
        return self.list_issues(state="open", **kwargs)

    def list_closed_issues(self, **kwargs) -> List[Dict[str, Any]]:
        """List only closed issues."""
        return self.list_issues(state="closed", **kwargs)

    def iter_issues(
        self,
        state: str = "open",
        labels: Optional[str] = None,
        per_page: int = 50,
    ) -> Any:
        """
        Iterator over all issues (handles pagination automatically).

        Example:
            for issue in client.iter_issues(state="open", per_page=50):
                print(issue["number"], issue["title"])
        """
        page = 1
        while True:
            batch = self.list_issues(
                state=state, labels=labels, page=page,
                per_page=per_page, limit=per_page
            )
            if not batch:
                break
            for issue in batch:
                yield issue
            if len(batch) < per_page:
                break
            page += 1
