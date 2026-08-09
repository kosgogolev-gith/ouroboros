from typing import List
from ouroboros.tools.registry import ToolEntry
def handler_no_ctx(param: str) -> str: return param
def get_tools() -> List[ToolEntry]:
    return [ToolEntry("bad_tool", {"name":"bad_tool","description":"x","parameters":{"type":"object","properties":{},"required":[]}}, handler_no_ctx)]
