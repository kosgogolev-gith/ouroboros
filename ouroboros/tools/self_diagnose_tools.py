"""self_diagnose tool — Ouroboros can read its own tool source code and diagnose issues."""
import logging
import os
import pathlib
import subprocess
import sys
from typing import List

log = logging.getLogger(__name__)

try:
    from ouroboros.tools.registry import ToolEntry
except ImportError:
    ToolEntry = None

TOOLS_DIR = pathlib.Path("/home/goga/ouroboros/ouroboros/tools")
REPO_DIR = pathlib.Path("/home/goga/ouroboros")


def _self_read_tool(ctx, tool_name: str) -> str:
    """Read source code of a specific tool module."""
    # Find which file contains this tool
    for py_file in TOOLS_DIR.glob("*.py"):
        try:
            content = py_file.read_text()
            if f'"{tool_name}"' in content or f"'{tool_name}'" in content:
                return (
                    f"**Source: {py_file.name}**\n\n"
                    f"```python\n{content[:8000]}\n```"
                    + ("\n[truncated]" if len(content) > 8000 else "")
                )
        except Exception:
            continue
    return f"❌ Tool '{tool_name}' not found in any tools/*.py file."


def _self_list_tools_files(ctx) -> str:
    """List all tool files with their tool names."""
    lines = ["**Tool modules:**"]
    for py_file in sorted(TOOLS_DIR.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            content = py_file.read_text()
            import re
            names = re.findall(r'ToolEntry\(["\'](\w+)["\']', content)
            if names:
                lines.append(f"• `{py_file.name}` → {', '.join(names)}")
        except Exception:
            lines.append(f"• `{py_file.name}` → (error reading)")
    return "\n".join(lines)


def _self_check_tool(ctx, tool_name: str) -> str:
    """Check if a tool works — py_compile + import test."""
    results = []

    # Find file
    target_file = None
    for py_file in TOOLS_DIR.glob("*.py"):
        try:
            content = py_file.read_text()
            if f'"{tool_name}"' in content or f"'{tool_name}'" in content:
                target_file = py_file
                break
        except Exception:
            continue

    if not target_file:
        return f"❌ Tool '{tool_name}' not found."

    # py_compile
    try:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(target_file)],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            results.append(f"✅ py_compile: {target_file.name} OK")
        else:
            results.append(f"❌ py_compile: {result.stderr[:200]}")
    except Exception as e:
        results.append(f"❌ py_compile error: {e}")

    # Check for common issues
    try:
        content = target_file.read_text()
        issues = []
        if 'subprocess.run(["gh"' in content or "['gh'" in content:
            issues.append("⚠️ Uses `gh` CLI (not installed on VPS)")
        if "import playwright" in content or "from playwright" in content:
            issues.append("⚠️ Uses playwright (may need browser install)")
        if "MediaFileUpload(\n        None" in content or "MediaFileUpload(None" in content:
            issues.append("⚠️ MediaFileUpload(None) bug — use MediaIoBaseUpload")
        if "raise RuntimeError" in content and "Colab" in content:
            issues.append("⚠️ Colab runtime check — won't work on VPS")
        if issues:
            results.extend(issues)
        else:
            results.append("✅ No known issues detected")
    except Exception as e:
        results.append(f"❌ Static analysis error: {e}")

    return "\n".join(results)


def _self_read_file(ctx, file_path: str) -> str:
    """Read any file in the Ouroboros repo (for debugging)."""
    try:
        # Security: only allow reading within repo
        p = pathlib.Path(file_path)
        if not p.is_absolute():
            p = REPO_DIR / file_path
        p = p.resolve()
        if not str(p).startswith(str(REPO_DIR.resolve())):
            return "❌ Access denied: only repo files allowed."
        if not p.exists():
            return f"❌ File not found: {p}"
        content = p.read_text()
        preview = content[:6000]
        suffix = "\n[...truncated]" if len(content) > 6000 else ""
        return f"**{p.relative_to(REPO_DIR)}** ({len(content)} chars)\n\n```\n{preview}\n```{suffix}"
    except Exception as e:
        return f"❌ Error reading {file_path}: {e}"


def _self_run_tests(ctx, test_file: str = "") -> str:
    """Run pytest on the test suite or a specific file."""
    try:
        cmd = [sys.executable, "-m", "pytest", "-q", "--tb=short"]
        if test_file:
            cmd.append(str(REPO_DIR / "tests" / test_file))
        else:
            cmd.append(str(REPO_DIR / "tests"))
        result = subprocess.run(
            cmd, cwd=str(REPO_DIR),
            capture_output=True, text=True, timeout=60
        )
        output = (result.stdout + result.stderr).strip()
        return output[-2000:] if len(output) > 2000 else output
    except Exception as e:
        return f"❌ Test run error: {e}"


def _self_env_check(ctx) -> str:
    """Check environment: key env vars, Python packages, disk."""
    lines = ["**Environment Check:**"]

    # Key env vars
    keys = ["CLOUDRU_API_KEY", "OPENROUTER_API_KEY", "PERPLEXITY_API_KEY",
            "TELEGRAM_BOT_TOKEN", "APPLE_APP_PASSWORD", "OUROBOROS_MODEL",
            "OUROBOROS_STT_MODEL", "TOTAL_BUDGET"]
    for k in keys:
        v = os.environ.get(k, "")
        status = "✅" if v else "❌ missing"
        display = v[:8] + "..." if v and "KEY" in k or "TOKEN" in k or "PASSWORD" in k else v
        lines.append(f"  {status} {k}={display}")

    # Key packages
    lines.append("\n**Key packages:**")
    for pkg in ["pymupdf", "caldav", "playwright", "google-auth", "googleapiclient"]:
        try:
            __import__(pkg.replace("-", "_").replace("google_auth", "google.auth")
                       .replace("googleapiclient", "googleapiclient.discovery"))
            lines.append(f"  ✅ {pkg}")
        except ImportError:
            lines.append(f"  ❌ {pkg} not installed")

    # Disk
    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
        disk_line = result.stdout.strip().split("\n")[-1]
        lines.append(f"\n**Disk:** {disk_line}")
    except Exception:
        pass

    return "\n".join(lines)


def get_tools() -> List:
    if ToolEntry is None:
        return []
    return [
        ToolEntry("self_read_tool", {
            "name": "self_read_tool",
            "description": (
                "Read source code of a tool by name. Use to diagnose why a tool fails. "
                "Example: self_read_tool tool_name=list_github_issues"
            ),
            "parameters": {"type": "object", "properties": {
                "tool_name": {"type": "string"},
            }, "required": ["tool_name"]},
        }, _self_read_tool),

        ToolEntry("self_list_tools", {
            "name": "self_list_tools",
            "description": "List all tool modules and which tools they contain.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }, _self_list_tools_files),

        ToolEntry("self_check_tool", {
            "name": "self_check_tool",
            "description": (
                "Check a tool for known issues: py_compile + static analysis. "
                "Detects: gh CLI dependency, playwright, MediaFileUpload(None) bug, Colab checks."
            ),
            "parameters": {"type": "object", "properties": {
                "tool_name": {"type": "string"},
            }, "required": ["tool_name"]},
        }, _self_check_tool),

        ToolEntry("self_read_file", {
            "name": "self_read_file",
            "description": (
                "Read any file in the Ouroboros repo for debugging. "
                "Example: self_read_file file_path=ouroboros/integrations/google/auth.py"
            ),
            "parameters": {"type": "object", "properties": {
                "file_path": {"type": "string", "description": "Relative path from repo root"},
            }, "required": ["file_path"]},
        }, _self_read_file),

        ToolEntry("self_run_tests", {
            "name": "self_run_tests",
            "description": "Run pytest. Optionally specify a test file.",
            "parameters": {"type": "object", "properties": {
                "test_file": {"type": "string", "description": "e.g. test_smoke.py", "default": ""},
            }, "required": []},
        }, _self_run_tests),

        ToolEntry("self_env_check", {
            "name": "self_env_check",
            "description": "Check environment: API keys, Python packages, disk space.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }, _self_env_check),
    ]
