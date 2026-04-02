"""Minimal smoke tests for Google API modules and tools.

These tests verify structural integrity without requiring actual credentials or API calls.
They follow Principle 5: simple, fast, and sufficient for CI.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestGoogleIntegrationStructure(unittest.TestCase):
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

    def test_tool_wrappers_exist(self):
        """All Google API tool wrappers are importable from ouroboros.tools."""
        from ouroboros.tools import drive as drive_tools
        from ouroboros.tools import calendar as calendar_tools
        from ouroboros.tools import gmail as gmail_tools
        # Drive tools
        for name in ['drive_list', 'drive_read', 'drive_write', 'drive_delete']:
            self.assertTrue(hasattr(drive_tools, name), f"Missing {name} in drive tools")
        # Calendar tools
        for name in ['calendar_list_events', 'calendar_get_event', 'calendar_create_event',
                     'calendar_update_event', 'calendar_delete_event']:
            self.assertTrue(hasattr(calendar_tools, name), f"Missing {name} in calendar tools")
        # Gmail tools
        for name in ['gmail_list', 'gmail_get', 'gmail_send', 'gmail_modify_labels', 'gmail_search']:
            self.assertTrue(hasattr(gmail_tools, name), f"Missing {name} in gmail tools")

    def test_tool_registration(self):
        """Google tools are registered in the global tool registry."""
        from ouroboros.tools.registry import get_registry
        import pathlib
        registry = get_registry(
            repo_dir=pathlib.Path('/content/ouroboros_repo'),
            drive_root=pathlib.Path('/content/ouroboros_data')
        )
        tools = registry.available_tools()
        expected = [
            'drive_list', 'drive_read', 'drive_write', 'drive_delete',
            'calendar_list_events', 'calendar_get_event', 'calendar_create_event',
            'calendar_update_event', 'calendar_delete_event',
            'gmail_list', 'gmail_get', 'gmail_send', 'gmail_modify_labels', 'gmail_search'
        ]
        for tool in expected:
            self.assertIn(tool, tools, f"Tool {tool} not registered")


if __name__ == '__main__':
    unittest.main()
