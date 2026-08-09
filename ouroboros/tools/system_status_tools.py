
from typing import List, Dict, Any
import subprocess
import os
import shutil
from datetime import datetime, timedelta
import psutil # Import psutil

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

def system_status(ctx=None) -> Dict[str, Any]: # Changed return type hint to Dict[str, Any]
    """
    Shows everything about the system state:
    uptime of the service, disk usage, RAM usage, budget,
    last errors, and current version (SHA).
    """
    status: Dict[str, Any] = {}

    # Uptime
    try:
        boot_time_timestamp = psutil.boot_time()
        boot_time = datetime.fromtimestamp(boot_time_timestamp)
        uptime = datetime.now() - boot_time
        status['uptime'] = str(uptime).split('.')[0] # Remove microseconds for cleaner output
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
        mem = psutil.virtual_memory()
        status['ram_usage'] = {
            'total_gb': round(mem.total / (1024**3), 2),
            'used_gb': round(mem.used / (1024**3), 2),
            'free_gb': round(mem.available / (1024**3), 2),
            'percent_used': mem.percent
        }
    except Exception as e:
        status['ram_usage'] = f"Error getting RAM usage: {e}"

    # Budget (assuming it's passed from context or a global store)
    try:
        status['budget'] = "N/A (supervisor provides this)"
        if ctx and hasattr(ctx, 'budget') and ctx.budget: # Corrected access to budget
            status['budget'] = f"${ctx.budget.remaining_usd:.2f} / ${ctx.budget.total_usd:.2f}"
    except Exception as e:
        status['budget'] = f"Error getting budget: {e}"

    # Last Errors (placeholder, would require parsing logs)
    status['last_errors'] = "N/A (requires log parsing or supervisor data)"

    # Version (SHA)
    try:
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
            "system_status",
            {
                "name": "system_status",
                "description": "Show system health: service uptime, disk, RAM, budget, last errors, git SHA. No parameters needed.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            system_status,
        )
    ]

