"""Integration tests for Google APIs (Drive, Calendar, Gmail) modules and tools."""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
import pathlib

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestGoogleAuthClient(unittest.TestCase):
    """Test the GoogleAuthClient in integrations/google/auth.py."""

    def test_auth_client_initialization(self):
        """GoogleAuthClient can be initialized and has required methods."""
        from ouroboros.integrations.google.auth import GoogleAuthClient
        client = GoogleAuthClient()
        self.assertTrue(hasattr(client, 'get_drive_service'))
        self.assertTrue(hasattr(client, 'get_calendar_service'))
        self.assertTrue(hasattr(client, 'get_gmail_service'))
        self.assertTrue(hasattr(client, 'is_authenticated'))

    def test_auth_client_colab_support(self):
        """GoogleAuthClient includes colab auth method."""
        from ouroboros.integrations.google.auth import GoogleAuthClient
        client = GoogleAuthClient()
        self.assertTrue(hasattr(client, '_authenticate_colab'))


class TestDriveModule(unittest.TestCase):
    """Test the Drive API module (integrations/google/drive.py)."""

    def test_drive_module_imports(self):
        """Drive module imports correctly and has expected functions."""
        import ouroboros.integrations.google.drive as drive_module
        expected = ['list_files', 'read_file', 'write_file', 'delete_file']
        for name in expected:
            self.assertTrue(hasattr(drive_module, name), f"Missing {name} in drive module")

    def test_drive_list_files(self):
        """Drive list_files returns expected structure."""
        from ouroboros.integrations.google import drive as drive_module
        with patch.object(drive_module, 'get_drive_service') as mock_get_service:
            mock_service = MagicMock()
            mock_files = MagicMock()
            mock_files.execute.return_value = {'files': [{'name': 'test.txt', 'id': '123'}]}
            mock_service.files.return_value.list.return_value = mock_files
            mock_get_service.return_value = mock_service

            result = drive_module.list_files()
            self.assertIsInstance(result, list)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['name'], 'test.txt')

    def test_drive_read_write_roundtrip(self):
        """Write then read returns same content."""
        from ouroboros.integrations.google import drive as drive_module
        with patch.object(drive_module, 'get_drive_service') as mock_get_service:
            mock_service = MagicMock()
            # Mock write (files.create)
            mock_create = MagicMock()
            mock_create.execute.return_value = {'id': 'file123'}
            mock_service.files.return_value.create.return_value = mock_create
            # Mock read (files.get)
            mock_get = MagicMock()
            mock_get.execute.return_value = {'name': 'test.txt', 'mimeType': 'text/plain'}
            mock_service.files.return_value.get.return_value = mock_get
            # Mock download for read_file
            mock_download = MagicMock()
            mock_download.execute.return_value = None
            # Simulate download writing to fh
            def fake_download(request, fh):
                fh.write(b"Hello, Drive!")
            mock_download.execute.side_effect = fake_download
            mock_service.files.return_value.get_media.return_value = mock_download

            mock_get_service.return_value = mock_service

            # Write
            drive_module.write_file('test.txt', 'Hello, Drive!')
            # Read back
            content = drive_module.read_file('test.txt')
            self.assertEqual(content, 'Hello, Drive!')


class TestCalendarModule(unittest.TestCase):
    """Test the Calendar API module (integrations/google/calendar.py)."""

    def test_calendar_module_imports(self):
        """Calendar module imports correctly and has expected functions."""
        import ouroboros.integrations.google.calendar as cal_module
        expected = ['list_events', 'get_event', 'create_event', 'update_event', 'delete_event']
        for name in expected:
            self.assertTrue(hasattr(cal_module, name), f"Missing {name} in calendar module")

    def test_calendar_create_event_datetime(self):
        """Calendar create_event accepts datetime objects."""
        from ouroboros.integrations.google import calendar as cal_module
        from datetime import datetime
        import pytz
        with patch.object(cal_module, 'get_calendar_service') as mock_get_service:
            mock_service = MagicMock()
            mock_events = MagicMock()
            mock_events.execute.return_value = {'id': 'event123'}
            mock_service.events.return_value.insert.return_value = mock_events
            mock_get_service.return_value = mock_service

            start = datetime(2025, 1, 1, 12, 0, tzinfo=pytz.UTC)
            end = datetime(2025, 1, 1, 13, 0, tzinfo=pytz.UTC)
            event_id = cal_module.create_event(
                summary='Test Event',
                start_time=start,
                end_time=end,
                description='Test description'
            )
            self.assertEqual(event_id, 'event123')
            # Verify the call arguments include proper datetime strings
            call_args = mock_service.events.return_value.insert.call_args
            body = call_args[1]['body']
            self.assertEqual(body['summary'], 'Test Event')
            self.assertIn('start', body)
            self.assertIn('end', body)

    def test_calendar_list_events(self):
        """Calendar list_events returns list of events."""
        from ouroboros.integrations.google import calendar as cal_module
        with patch.object(cal_module, 'get_calendar_service') as mock_get_service:
            mock_service = MagicMock()
            mock_events = MagicMock()
            mock_events.execute.return_value = {
                'items': [
                    {'id': 'ev1', 'summary': 'Event 1'},
                    {'id': 'ev2', 'summary': 'Event 2'}
                ]
            }
            mock_service.events.return_value.list.return_value = mock_events
            mock_get_service.return_value = mock_service

            result = cal_module.list_events()
            self.assertIsInstance(result, list)
            self.assertEqual(len(result), 2)


class TestGmailModule(unittest.TestCase):
    """Test the Gmail API module (integrations/google/gmail.py)."""

    def test_gmail_module_imports(self):
        """Gmail module imports correctly and has expected functions."""
        import ouroboros.integrations.google.gmail as gmail_module
        expected = ['list_messages', 'get_message', 'send_message', 'modify_labels', 'search_messages']
        for name in expected:
            self.assertTrue(hasattr(gmail_module, name), f"Missing {name} in gmail module")

    def test_gmail_send_message(self):
        """Gmail send_message creates a message and calls API."""
        from ouroboros.integrations.google import gmail as gmail_module
        with patch.object(gmail_module, 'get_gmail_service') as mock_get_service:
            mock_service = MagicMock()
            mock_users =MagicMock()
            mock_messages = MagicMock()
            mock_messages.execute.return_value = {'id': 'msg123'}
            mock_users.messages.return_value = mock_messages
            mock_service.users.return_value = mock_users
            mock_get_service.return_value = mock_service

            msg_id = gmail_module.send_message(
                to='test@example.com',
                subject='Test',
                body='Hello'
            )
            self.assertEqual(msg_id, 'msg123')
            # Verify message creation call
            self.assertTrue(mock_users.messages.return_value.send.called)

    def test_gmail_list_messages(self):
        """Gmail list_messages returns list of message IDs."""
        from ouroboros.integrations.google import gmail as gmail_module
        with patch.object(gmail_module, 'get_gmail_service') as mock_get_service:
            mock_service = MagicMock()
            mock_messages = MagicMock()
            mock_messages.execute.return_value = {
                'messages': [{'id': 'msg1'}, {'id': 'msg2'}]
            }
            mock_service.users.return_value.messages.return_value.list.return_value = mock_messages
            mock_get_service.return_value = mock_service

            result = gmail_module.list_messages()
            self.assertIsInstance(result, list)
            self.assertEqual(len(result), 2)


class TestToolRegistration(unittest.TestCase):
    """Test that Google API tools are properly registered in the tool registry."""

    def test_drive_tools_registered(self):
        """Drive tools are registered: drive_list, drive_read, drive_write, drive_delete."""
        from ouroboros.tools.registry import ToolRegistry
        import pathlib
        registry = ToolRegistry(
            repo_dir=pathlib.Path('/tmp'),
            drive_root=pathlib.Path('/tmp'),
        )
        tools = registry.available_tools()
        for tool in ['drive_list', 'drive_read', 'drive_write', 'drive_delete']:
            self.assertIn(tool, tools, f"{tool} should be registered")

    def test_calendar_tools_registered(self):
        """Calendar tools are registered: calendar_list_events, calendar_get_event, etc."""
        from ouroboros.tools.registry import ToolRegistry
        import pathlib
        registry = ToolRegistry(
            repo_dir=pathlib.Path('/tmp'),
            drive_root=pathlib.Path('/tmp'),
        )
        tools = registry.available_tools()
        for tool in ['calendar_list_events', 'calendar_get_event', 'calendar_create_event',
                     'calendar_update_event', 'calendar_delete_event']:
            self.assertIn(tool, tools, f"{tool} should be registered")

    def test_gmail_tools_registered(self):
        """Gmail tools are registered: gmail_list, gmail_get, gmail_send, gmail_modify_labels, gmail_search."""
        from ouroboros.tools.registry import ToolRegistry
        import pathlib
        registry = ToolRegistry(
            repo_dir=pathlib.Path('/tmp'),
            drive_root=pathlib.Path('/tmp'),
        )
        tools = registry.available_tools()
        for tool in ['gmail_list', 'gmail_get', 'gmail_send', 'gmail_modify_labels', 'gmail_search']:
            self.assertIn(tool, tools, f"{tool} should be registered")


if __name__ == "__main__":
    unittest.main()
