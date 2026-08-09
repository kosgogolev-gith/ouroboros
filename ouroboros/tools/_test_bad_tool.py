from typing import List
from ouroboros.tools.registry import ToolEntry
def handler(): return "ok"
def get_tools() -> List[ToolEntry]:
    return [ToolEntry(name="bad_tool", description="bad", parameters=[])]
