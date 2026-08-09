from typing import Optional, Literal
from pydantic import BaseModel, Field
from ouroboros.tools.registry import ToolContext # Import ToolContext

class SendFileToolSchema(BaseModel):
    file_path: str = Field(..., description="Local path to the file to send.")
    caption: Optional[str] = Field(None, description="Caption for the file (optional).")
    
class SendFileTool:
    def __init__(self, ctx: ToolContext): # Changed to ctx: ToolContext
        self.tg = ctx.tg # Extract tg from ctx

    def send_file_to_owner(self, file_path: str, caption: Optional[str] = None) -> dict:
        """Send a file to the owner via Telegram.

        Args:S
            file_path: Local path to the file to send.
            caption: Caption for the file (optional).
        """
        try:
            self.tg.send_document(file_path=file_path, caption=caption, chat_id=self.tg.owner_id) # owner_id is already in tg
            return {"status": "success", "message": f"File '{file_path}' sent to owner."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to send file: {e}"}

def get_tools(ctx: ToolContext): # Changed to ctx: ToolContext
    return [
        SendFileTool(ctx).send_file_to_owner,
    ]
