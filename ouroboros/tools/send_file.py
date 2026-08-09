from typing import Optional, Literal
from pydantic import BaseModel, Field
from ouroboros.supervisor.telegram_gateway import TelegramGateway

class SendFileToolSchema(BaseModel):
    file_path: str = Field(..., description="Local path to the file to send.")
    caption: Optional[str] = Field(None, description="Caption for the file (optional).")
    
class SendFileTool:
    def __init__(self, tg: TelegramGateway):
        self.tg = tg

    def send_file_to_owner(self, file_path: str, caption: Optional[str] = None) -> dict:
        """Send a file to the owner via Telegram.

        Args:
            file_path: Local path to the file to send.
            caption: Caption for the file (optional).
        """
        try:
            # Assume TelegramGateway has a method like send_document or send_photo
            # This will depend on the actual implementation of TelegramGateway
            # For simplicity, let's assume send_document handles most file types
            self.tg.send_document(file_path=file_path, caption=caption, chat_id=self.tg.owner_id)
            return {"status": "success", "message": f"File '{file_path}' sent to owner."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to send file: {e}"}

def get_tools(tg: TelegramGateway):
    return [
        SendFileTool(tg).send_file_to_owner,
    ]
