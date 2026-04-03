"""Tests for GitHub REST API client."""

import os
import json
from unittest.mock import patch, MagicMock

import pytest

from ouroboros.integrations.github import (
    GitHubClient,
    GitHubAPIError,
    RateLimitError,
    AuthenticationError,
    NotFoundError,
)

TOKEN = "mock-token"
REPO = "test/repo"


class TestGitHubClient:
    def test_init_from_env(self):
        """Detects token and repo from explicit args (env-based detection is integration test)."""
        client = GitHubClient(token=TOKEN, repo=REPO)
        assert client.token == TOKEN
        assert client.repo == REPO

    def test_init_from_params(self):
        """Explicit parameters override environment."""
        client = GitHubClient(token="explicit-token", repo="explicit/repo")
        assert client.token == "explicit-token"
        assert client.repo == "explicit/repo"

    def test_init_missing_token(self):
        """Raises error if no token found."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(AuthenticationError, match="token"):
                GitHubClient(repo=REPO)

    def test_init_missing_repo(self):
        """Raises error if repo not specified and cannot be detected."""
        # Patch _detect_repo to return None
        with patch.object(GitHubClient, "_detect_repo", return_value=None):
            with pytest.raises(ValueError, match="[Rr]epository"):
                GitHubClient(token=TOKEN)

    def test_list_issues_parsing(self):
        """Parses GitHub API list response (array, not {items: ...})."""
        # GitHub REST API returns an array directly for /repos/{owner}/{repo}/issues
        mock_response_data = [
            {
                "number": 1,
                "title": "Test issue",
                "state": "open",
                "user": {"login": "alice"},
                "labels": [{"name": "bug"}, {"name": "high"}],
                "body": "Test body",
            }
        ]

        client = GitHubClient(token=TOKEN, repo=REPO)
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = (200, mock_response_data)

            issues = client.list_issues()
            assert len(issues) == 1
            assert issues[0]["number"] == 1
            assert any(l["name"] == "high" for l in issues[0]["labels"])

    def test_rate_limit_error(self):
        """Handles 403 rate limit correctly."""
        client = GitHubClient(token=TOKEN, repo=REPO)
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9999999999"}
        mock_resp.text = "rate limit exceeded"

        with patch.object(client.session, "request") as mock_req:
            mock_req.return_value = mock_resp
            with pytest.raises(RateLimitError):
                client.list_issues()

    def test_not_found_error(self):
        """Handles 404 correctly."""
        client = GitHubClient(token=TOKEN, repo=REPO)
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "not found"

        with patch.object(client.session, "request") as mock_req:
            mock_req.return_value = mock_resp
            with pytest.raises(NotFoundError):
                client.get_issue(999)

    def test_iter_issues_pagination(self):
        """Iterates through pages by calling list_issues repeatedly."""
        client = GitHubClient(token=TOKEN, repo=REPO)

        # Per_page=1 so page 1 has 1 item (full batch), page 2 has 0 (stop)
        page_1 = [{"number": 1, "title": "First"}]
        page_2 = []

        call_count = [0]

        def fake_list_issues(**kwargs):
            call_count[0] += 1
            page = kwargs.get("page", 1)
            if page == 1:
                return page_1
            return page_2

        with patch.object(client, "list_issues", side_effect=fake_list_issues):
            issues = list(client.iter_issues(per_page=1))

        assert len(issues) == 1
        assert issues[0]["number"] == 1
