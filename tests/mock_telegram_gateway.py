from typing import Optional

class MockTelegramGateway:
    def __init__(self, owner_id: int):
        self.owner_id = owner_id

    def send_document(self, file_path: str, caption: Optional[str], chat_id: int):
        print(f"MockTelegramGateway: Sending document {file_path} to {chat_id} with caption {caption}")
        # Simulate success for tests
        return True

    def send_message(self, chat_id: int, text: str, reply_to_message_id: Optional[int] = None):
        print(f"MockTelegramGateway: Sending message to {chat_id}: {text}")
        return True

    def download_file_base64(self, file_id: str) -> str:
        print(f"MockTelegramGateway: Downloading file {file_id}")
        return "mock_base64_content"
