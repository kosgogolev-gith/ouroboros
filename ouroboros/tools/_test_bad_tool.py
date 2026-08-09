import psutil
from typing import List
from ouroboros.tools.registry import ToolEntry
def handler(ctx) -> str: return str(psutil.cpu_percent())
def get_tools() -> List[ToolEntry]:
    return [ToolEntry("bad_tool", {"name":"bad_tool","description":"x","parameters":{"type":"object","properties":{},"required":[]}}, handler)]
