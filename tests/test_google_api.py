"""Minimal smoke tests for Google API modules and tools.

These tests verify structural integrity without requiring actual credentials or API calls.
They follow Principle 5: simple, fast, and sufficient for CI.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    import google.auth  # noqa: F401
    _HAS_GOOGLE = True
except ImportError:
    _HAS_GOOGLE = False


@unittest.skipUnless(_HAS_GOOGLE, "google-auth not installed")
class TestGoogleAPIStructure(unittest.TestCase):
    """Test that Google integration modules exist and have correct structure."""

    def test_auth_module_exists(self):
        """integrations/google/auth.py exists and has get_credentials."""
        from ouroboros.integrations.google import auth
        self.assertTrue(hasattr(auth, 'get_credentials'))
        self.assertTrue(hasattr(auth, 'GoogleAuthClient'))

    def test_drive_module_exists(self):
        """integrations/google/drive.py exists with required functions."""
        from ouroboros.integrations.google import drive
        required = ['list_files', 'read_file', 'write_file', 'delete_file']
        for name in required:
            self.assertTrue(hasattr(drive, name), f"Missing {name} in drive module")

    def test_calendar_module_exists(self):
        """integrations/google/calendar.py exists with required functions."""
        from ouroboros.integrations.google import calendar
        required = ['list_events', 'get_event', 'create_event', 'update_event', 'delete_event']
        for name in required:
            self.assertTrue(hasattr(calendar, name), f"Missing {name} in calendar module")

    def test_gmail_module_exists(self):
        """integrations/google/gmail.py exists with required functions."""
        from ouroboros.integrations.google import gmail
        required = ['list_messages', 'get_message', 'send_message', 'modify_labels', 'search_messages']
        for name in required:
            self.assertTrue(hasattr(gmail, name), f"Missing {name} in gmail module")


class TestGoogleToolRegistration(unittest.TestCase):
    """Test that Google tools are registered in the tool registry."""

    def test_tool_wrappers_registered(self):
        """Google API tools are registered in the global tool registry."""
        from ouroboros.tools import ToolRegistry
        import pathlib
        registry = ToolRegistry(
            repo_dir=pathlib.Path('/tmp'),
            drive_root=pathlib.Path('/tmp')
        )
        tools = registry.available_tools()
        expected = [
            'drive_list', 'drive_read', 'drive_write', 'drive_delete',
            'gmail_list', 'gmail_get', 'gmail_send', 'gmail_modify_labels', 'gmail_search',
        ]
        for tool in expected:
            self.assertIn(tool, tools, f"Tool {tool} not registered")


if __name__ == '__main__':
    unittest.main()
