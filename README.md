## Changelog

### 6.4.4 (2026-04-07)

**Added:**
- `spec_compare` tool — compliance matrix comparing vendor equipment offers against stored baseline requirements
- Supports XLSX and PDF vendor documents
- Parses requirements from knowledge base (`requirements-h200`, `requirements-b200x8`)
- Generates ✅/⚠️/❌ status per parameter, flags critical deviations, and summarizes commercial terms

**Removed:**
- Duplicate `spec_analyzer.py` (consolidated into spec_compare)

2026-04-02)

**Added:**
- GitHub REST API integration (`integrations/github.py`) — direct access to GitHub Issues without gh CLI dependency
- New tool functions: `list_github_issues`, `get_github_issue`, `comment_on_issue`, `create_github_issue`, `close_github_issue` (via `tools/github.py`)
- Automatic repository detection from git remote or `GH_REPO` environment variable
- Authentication via `GITHUB_TOKEN` environment variable
- Rate limit handling and proper error reporting
- Pagination support for listing issues

**Changed:**
- Replaced `gh` CLI calls with direct GitHub API calls in `tools/github.py`
- Improved reliability of GitHub issue access in environments without gh CLI

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