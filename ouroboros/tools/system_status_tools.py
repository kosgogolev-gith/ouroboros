
from typing import List, Dict, Any
import subprocess
import os
import shutil
from datetime import datetime, timedelta

from ouroboros.tools.registry import ToolEntry

def _run_shell_cmd(cmd: List[str]) -> str:
    """Helper to run shell commands and return stdout."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"ERROR: {e.stderr.strip()}"
    except FileNotFoundError:
        return f"ERROR: Command not found: {cmd[0]}"

def system_status() -> Dict[str, Any]:
    """
    Shows everything about the system state:
    uptime of the service, disk usage, RAM usage, budget,
    last errors, and current version (SHA).
    """
    status: Dict[str, Any] = {}

    # Uptime
    try:
        status['uptime'] = str(timedelta(seconds=uptime_seconds))
    except Exception as e:
        status['uptime'] = f"Error getting uptime: {e}"

    # Disk Usage
    try:
        total, used, free = shutil.disk_usage("/")
        status['disk_usage'] = {
            'total_gb': round(total / (1024**3), 2),
            'used_gb': round(used / (1024**3), 2),
            'free_gb': round(free / (1024**3), 2),
        }
    except Exception as e:
        status['disk_usage'] = f"Error getting disk usage: {e}"

    # RAM Usage
    try:
        status['ram_usage'] = {
            'total_gb': round(mem.total / (1024**3), 2),
            'used_gb': round(mem.used / (1024**3), 2),
            'free_gb': round(mem.available / (1024**3), 2),
            'percent_used': mem.percent
        }
    except Exception as e:
        status['ram_usage'] = f"Error getting RAM usage: {e}"

    # Budget (assuming it's passed from context or a global store)
    # For now, we'll use a placeholder or try to read from a known path
    try:
        # This part assumes budget info is available somewhere,
        # e.g., in a state.json on Drive. For now, it's a placeholder.
        # In a real scenario, this would be injected by the supervisor.
        status['budget'] = "N/A (supervisor provides this)"
    except Exception as e:
        status['budget'] = f"Error getting budget: {e}"

    # Last Errors (placeholder, would require parsing logs)
    status['last_errors'] = "N/A (requires log parsing)"

    # Version (SHA)
    try:
        # Assuming current SHA can be fetched from the repo
        sha = _run_shell_cmd(["git", "rev-parse", "HEAD"])
        if "ERROR" not in sha:
            status['version_sha'] = sha
        else:
            status['version_sha'] = f"Error getting SHA: {sha}"
    except Exception as e:
        status['version_sha'] = f"Error getting version SHA: {e}"

    return status

def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry(
            name="system_status",
            description="Shows everything about the system state: uptime of the service, disk usage, RAM usage, budget, last errors, and current version (SHA).",
            parameters=[] # No parameters for this tool
        )
    ]
