"""Tests for GitHub REST API client (no gh CLI dependency)."""

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

# Mock environment for tests
os.environ["GITHUB_TOKEN"] = "mock-token"
os.environ["GITHUB_REPO"] = "test/repo"


class TestGitHubClient:
    def test_init_from_env(self):
        """Detects token and repo from environment."""
        client = GitHubClient()
        assert client.token == "mock-token"
        assert client.repo == "test/repo"

    def test_init_from_params(self):
        """Explicit parameters override environment."""
        client = GitHubClient(token="explicit-token", repo="explicit/repo")
        assert client.token == "explicit-token"
        assert client.repo == "explicit/repo"

    def test_init_missing_token(self):
        """Raises error if no token found."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(AuthenticationError, match="GitHub token"):
                GitHubClient()

    def test_init_missing_repo(self):
        """Raises error if repo not specified."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "tok"}, clear=True):
            with pytest.raises(ValueError, match="repository"):
                GitHubClient()

    def test_list_issues_parsing(self):
        """Parses API response correctly."""
        mock_response = {
            "items": [
                {
                    "number": 1,
                    "title": "Test issue",
                    "state": "open",
                    "user": {"login": "alice"},
                    "labels": [{"name": "bug"}, {"name": "high"}],
                    "body": "Test body",
                }
            ]
        }

        client = GitHubClient()
        with patch.object(client.session, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_get.return_value = mock_resp

            issues = client.list_issues()
            assert len(issues) == 1
            assert issues[0]["number"] == 1
            assert "high" in (l["name"] for l in issues[0]["labels"])

    def test_rate_limit_error(self):
        """Handles 403 rate limit correctly."""
        client = GitHubClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.headers = {"X-RateLimit-Remaining": "0"}
        mock_resp.text = "rate limit exceeded"

        with patch.object(client.session, "get") as mock_get:
            mock_get.return_value = mock_resp
            with pytest.raises(RateLimitError):
                client.list_issues()

    def test_not_found_error(self):
        """Handles 404 correctly."""
        client = GitHubClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "not found"

        with patch.object(client.session, "get") as mock_get:
            mock_get.return_value = mock_resp
            with pytest.raises(NotFoundError):
                client.get_issue(999)

    def test_iter_issues_pagination(self):
        """Follows Link header pagination."""
        client = GitHubClient()
        # Page 1 returns items + Link to page 2
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {"items": [{"number": 1}]}
        resp1.headers = {
            "Link": '<https://api.github.com/...?page=2>; rel="next"'
        }
        # Page 2 returns items + no Link
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {"items": [{"number": 2}]}
        resp2.headers = {}

        with patch.object(client.session, "get") as mock_get:
            mock_get.side_effect = [resp1, resp2]
            issues = list(client.iter_issues())
            assert len(issues) == 2
            assert issues[0]["number"] == 1
            assert issues[1]["number"] == 2
