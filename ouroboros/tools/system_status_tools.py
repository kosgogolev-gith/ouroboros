
import datetime
import json
import os
import re
from typing import List, Dict

from ouroboros.tools.registry import ToolEntry

def _get_uptime_string(start_time_iso: str) -> str:
    """Calculates and formats uptime from an ISO 8601 start time."""
    start_time = datetime.datetime.fromisoformat(start_time_iso)
    uptime_delta = datetime.datetime.now() - start_time
    days = uptime_delta.days
    hours, remainder = divmod(uptime_delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days} дней, {hours} часов, {minutes} минут"

def _get_disk_usage() -> Dict[str, str]:
    """Retrieves disk usage using df -h."""
    try:
        from default_api import run_shell
        result = run_shell(cmd=["df", "-h", "/"])
        output = result.get('run_shell_response', {}).get('stdout', '')
        lines = output.strip().split('\\n')
        if len(lines) > 1:
            parts = lines[1].split()
            return {
                "total": parts[1],
                "used": parts[2],\
                "available": parts[3],
                "percent_used": parts[4]
            }
    except Exception as e:
        return {"error": f"Failed to get disk usage: {e}"}
    return {"error": "Could not parse disk usage output"}

def _get_ram_usage() -> Dict[str, str]:
    """Retrieves RAM usage using free -h."""
    try:
        from default_api import run_shell
        result = run_shell(cmd=["free", "-h"])
        output = result.get('run_shell_response', {}).get('stdout', '')
        lines = output.strip().split('\\n')
        if len(lines) > 1:
            # Assuming the second line (index 1) contains Mem info
            parts = lines[1].split()
            return {
                "total": parts[1],
                "used": parts[2],
                "free": parts[3]
            }
    except Exception as e:
        return {"error": f"Failed to get RAM usage: {e}"}
    return {"error": "Could not parse RAM usage output"}


def _system_status_handler(ctx) -> str:
    """Основная логика инструмента system_status."""
    status_report = []

    # Uptime
    # Изменено: доступ к supervisor через getattr для универсальности
    supervisor_data = getattr(ctx, 'supervisor', {})
    launcher_start = supervisor_data.get('launcher_start', '')
    if launcher_start:
        status_report.append(f"Uptime сервиса: {_get_uptime_string(launcher_start)}")
    else:
        status_report.append("Uptime сервиса: Неизвестно (launcher_start не найден)")

    # Disk usage
    disk_info = _get_disk_usage()
    if "error" not in disk_info:
        status_report.append(f"Диск: Всего {disk_info['total']}, Занято {disk_info['used']} ({disk_info['percent_used']}), Свободно {disk_info['available']}")
    else:
        status_report.append(f"Диск: {disk_info['error']}")

    # RAM usage
    ram_info = _get_ram_usage()
    if "error" not in ram_info:
        status_report.append(f"RAM: Всего {ram_info['total']}, Занято {ram_info['used']}, Свободно {ram_info['free']}")
    else:
        status_report.append(f"RAM: {ram_info['error']}")

    # Budget
    # Изменено: доступ к budget через getattr для универсальности
    budget_info = getattr(ctx, 'budget', {})
    if budget_info:
        status_report.append(f"Бюджет: Потрачено ${budget_info.get('spent_usd', 'N/A'):.2f} из ${budget_info.get('total_usd', 'N/A')}.00 (Осталось ${budget_info.get('remaining_usd', 'N/A'):.2f})")
    else:
        status_report.append("Бюджет: Информация недоступна")

    # Version (SHA)
    # Изменено: доступ к git_head через getattr для универсальности
    git_head = getattr(ctx, 'git_head', 'N/A')
    status_report.append(f"Версия (SHA): {git_head}")

    return "\\n".join(status_report)


def get_tools() -> List[ToolEntry]:
    """ОБЯЗАТЕЛЬНО: реестр вызывает эту функцию при старте."""
    return [
        ToolEntry(
            "system_status",
            {
                "name": "system_status",
                "description": "Показывает общее состояние системы: uptime, использование диска, RAM, бюджет, текущую версию (SHA).",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
            _system_status_handler,
        )
    ]
