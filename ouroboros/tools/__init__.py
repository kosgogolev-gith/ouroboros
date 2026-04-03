"""
Ouroboros — Tool package (plugin architecture).

Re-exports: ToolRegistry, ToolContext, ToolEntry.
To add a tool: create a module in this package, export get_tools().
"""

from ouroboros.tools.registry import ToolRegistry, ToolContext, ToolEntry
from ouroboros.tools import drive
from ouroboros.tools import calendar
from ouroboros.tools import gmail
from ouroboros.tools import github

__all__ = ['ToolRegistry', 'ToolContext', 'ToolEntry', 'drive', 'calendar', 'gmail', 'github']
