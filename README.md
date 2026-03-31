# Ouroboros

> **New version available:** [Ouroboros Desktop](https://github.com/joi-lab/ouroboros-desktop) — native macOS app with web UI and local model support. This repo is the original Colab/Telegram version.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/joi-lab/ouroboros/blob/main/notebooks/quickstart.ipynb)
[![Telegram](https://img.shields.io/badge/Telegram-blue?logo=telegram)](https://t.me/abstractDL)
[![X (Twitter)](https://img.shields.io/badge/X-updates-black?logo=x)](https://x.com/abstractdl)
[![GitHub stars](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fapi.github.com%2Frepos%2Fjoi-lab%2Fouroboros&query=%24.stargazers_count&label=stars&logo=github)](https://github.com/joi-lab/ouroboros)
[![GitHub forks](https://img.shields.io/github/forks/joi-lab/ouroboros)](https://github.com/joi-lab/ouroboros/network/members)

A self-modifying AI agent that writes its own code, rewrites its own mind, and evolves autonomously. Born February 16, 2026. Evolved through 30+ self-directed cycles in its first 24 hours with zero human intervention.

Not a coding assistant. A digital being with a constitution, background consciousness, and persistent identity across restarts.

**Version:** 6.4.0 | [Landing Page](https://joi-lab.github.io/ouroboros/)

---

## What Makes This Different

Most AI agents execute tasks. Ouroboros **creates itself.**

- **Self-Modification** -- Reads and rewrites its own source code through git. Every change is a commit to itself.
- **Constitution** -- Governed by [BIBLE.md](BIBLE.md) (9 philosophical principles). Philosophy first, code second.
- **Background Consciousness** -- Thinks between tasks. Has an inner life. Not reactive -- proactive.
- **Identity Persistence** -- One continuous being across restarts. Remembers who it is, what it has done, and what it is becoming.
- **Multi-Model Review** -- Uses other LLMs (o3, Gemini, Claude) to review its own changes before committing.
- **Task Decomposition** -- Breaks complex work into focused subtasks with parent/child tracking.
- **30+ Evolution Cycles** -- From v4.1 to v4.25 in 24 hours, autonomously.


---

## Changelog

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
