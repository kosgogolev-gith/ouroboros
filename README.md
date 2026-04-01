## Changelog

### 6.4.1 (2026-04-01)

**Added:**
- Gmail API integration (`integrations/google/gmail.py`) with full email operations
- New tool functions: `gmail_list`, `gmail_get`, `gmail_send`, `gmail_modify_labels`, `gmail_search` (via `tools/gmail.py`)
- Support for sending emails with attachments (MIME multipart)
- Message label management (add/remove labels)
- Advanced search with Gmail query syntax
- Proper MIME message construction with CC/BCC support
- Base64url encoding/decoding for Gmail API compatibility
- Text extraction from complex message payloads (multipart, nested)

**Changed:**
- Updated `integrations/google/__init__.py` to include gmail exports

### 6.4.0 (2026-03-31)

**Added:**
- Google Drive API integration (`integrations/google/auth.py`, `integrations/google/drive.py`) with OAuth 2.0 support for Colab and local file fallback
- New tool functions: `drive_list`, `drive_read`, `drive_write`, `drive_delete` (via `tools/drive.py`)
- Automatic quota error handling with exponential backoff for Drive operations
- MIME type detection and UTF-8 encoding for text files
- Folder path resolution in Drive (recursive file find)

**Fixed:**
- Vision model fallback routing bug (commits `99f2336`, `879058d`) — now correctly uses `OUROBOROS_VISION_MODEL_FALLBACK_LIST` for image-containing messages

**Changed:**
- Replaced/improved partial Drive functions from legacy `google_api.py`

---

### 6.3.x (previous)
*See git history for earlier versions.*