
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

SCHEDULED_TASKS_FILE = os.path.join(os.environ.get("DRIVE_ROOT"), "scheduled_tasks.json")

def _load_tasks() -> Dict[str, Any]:
    """Loads scheduled tasks from the Drive JSON file."""
    if not os.path.exists(SCHEDULED_TASKS_FILE):
        return {"tasks": [], "logs": []}
    with open(SCHEDULED_TASKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_tasks(data: Dict[str, Any]):
    """Saves scheduled tasks to the Drive JSON file."""
    with open(SCHEDULED_TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def add_scheduled_task(task_id: str, description: str, context: Optional[str] = None, due_at: Optional[datetime] = None):
    """Adds a new task to the scheduled tasks list."""
    data = _load_tasks()
    task = {
        "task_id": task_id,
        "description": description,
        "context": context,
        "scheduled_at": datetime.utcnow().isoformat(),
        "due_at": due_at.isoformat() if due_at else None,
        "status": "pending"
    }
    data["tasks"].append(task)
    _save_tasks(data)

def get_scheduled_tasks() -> List[Dict[str, Any]]:
    """Returns a list of all scheduled tasks."""
    return _load_tasks().get("tasks", [])

def get_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "scheduled_task_list",
                "description": "List all currently scheduled background tasks.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "add_default_daily_briefing",
                "description": "Adds the default daily briefing task (5:30 UTC) to scheduled tasks.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    ]

def scheduled_task_list() -> dict:
    """Lists all scheduled tasks."""
    tasks = get_scheduled_tasks()
    if not tasks:
        return {"status": "OK", "message": "No scheduled tasks found."}
    return {"status": "OK", "tasks": tasks}

def add_default_daily_briefing() -> dict:
    """Adds the default daily briefing task (5:30 UTC) to scheduled tasks."""
    # Check if a daily briefing task already exists to avoid duplicates
    tasks = get_scheduled_tasks()
    for task in tasks:
        if "daily briefing" in task["description"].lower() and task["status"] == "pending":
            return {"status": "SKIPPED", "message": "Daily briefing task already scheduled."}

    # Schedule for tomorrow at 5:30 UTC
    tomorrow = datetime.utcnow() + timedelta(days=1)
    due_at = tomorrow.replace(hour=5, minute=30, second=0, microsecond=0)

    task_id = f"daily_briefing_{due_at.strftime('%Y%m%d')}"
    add_scheduled_task(
        task_id=task_id,
        description="Perform daily briefing to owner (weather, calendar, tasks, reminders).",
        due_at=due_at
    )
    return {"status": "OK", "message": f"Daily briefing scheduled for {due_at.isoformat()}."}
