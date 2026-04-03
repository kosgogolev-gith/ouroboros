"""Minimal smoke tests for Google API modules and tools.

These tests verify structural integrity without requiring actual credentials or API calls.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestGoogleIntegrationStructure(unittest.TestCase):
    """Test that Google integration modules exist and have correct structure."""

    def test_auth_module_exists(self):
        """integrations/google/auth.py exists and has get_credentials."""
        try:
            from ouroboros.integrations.google import auth
            self.assertTrue(hasattr(auth, "get_credentials"))
            self.assertTrue(hasattr(auth, "authenticate"))
        except ImportError as e:
            self.skipTest(f"Google auth not available: {e}")

    def test_drive_module_exists(self):
        """integrations/google/drive.py exists with required functions."""
        try:
            from ouroboros.integrations.google import drive
            required = ["list_files", "read_file", "write_file", "delete_file"]
            for name in required:
                self.assertTrue(hasattr(drive, name), f"Missing {name} in drive module")
        except ImportError as e:
            self.skipTest(f"Google drive not available: {e}")

    def test_calendar_module_exists(self):
        """integrations/google/calendar.py exists with required functions."""
        try:
            from ouroboros.integrations.google import calendar
            required = ["list_events", "get_event", "create_event", "update_event", "delete_event"]
            for name in required:
                self.assertTrue(hasattr(calendar, name), f"Missing {name} in calendar module")
        except ImportError as e:
            self.skipTest(f"Google calendar not available: {e}")

    def test_gmail_module_exists(self):
        """integrations/google/gmail.py exists with required functions."""
        try:
            from ouroboros.integrations.google import gmail
            required = ["list_messages", "get_message", "send_message", "modify_labels", "search_messages"]
            for name in required:
                self.assertTrue(hasattr(gmail, name), f"Missing {name} in gmail module")
        except ImportError as e:
            self.skipTest(f"Google gmail not available: {e}")

    def test_tool_wrappers_exist(self):
        """Google API tool wrappers register correct tool names via get_tools()."""
        # drive tools
        try:
            from ouroboros.tools import drive as drive_tools
            tool_names = [t.name for t in drive_tools.get_tools()]
            for name in ["drive_list", "drive_read", "drive_write", "drive_delete"]:
                self.assertIn(name, tool_names, f"Missing {name} in drive tools")
        except ImportError as e:
            self.skipTest(f"Drive tools not available: {e}")

        # gmail tools
        try:
            from ouroboros.tools import gmail as gmail_tools
            tool_names = [t.name for t in gmail_tools.get_tools()]
            for name in ["gmail_list", "gmail_get", "gmail_send", "gmail_modify_labels", "gmail_search"]:
                self.assertIn(name, tool_names, f"Missing {name} in gmail tools")
        except ImportError as e:
            self.skipTest(f"Gmail tools not available: {e}")

    def test_tool_registration(self):
        """Key tools are registered in the ToolRegistry."""
        import pathlib
        from ouroboros.tools.registry import ToolRegistry

        # Build registry using home dir paths (VPS context)
        home = pathlib.Path.home()
        try:
            registry = ToolRegistry(
                repo_dir=home / "ouroboros",
                drive_root=home / "ouroboros_data",
            )
            tools = registry.available_tools()
        except TypeError:
            # Try without arguments if signature differs
            try:
                registry = ToolRegistry()
                tools = registry.available_tools()
            except Exception as e:
                self.skipTest(f"Cannot build ToolRegistry: {e}")
                return

        # Check core tools that must always be present
        core_tools = ["run_shell", "web_search", "send_owner_message"]
        for tool in core_tools:
            self.assertIn(tool, tools, f"Core tool {tool} not registered")


if __name__ == "__main__":
    unittest.main()
