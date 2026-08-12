from typing import List, Dict, Any, Optional
from ouroboros.tools.registry import ToolEntry
import sqlite3
import datetime

import pathlib
DATABASE_PATH = str(pathlib.Path.home() / "ouroboros_data" / "hardware_inventory.db")

def _init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hardware_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            model TEXT NOT NULL,
            serial_number TEXT,
            purchase_date TEXT NOT NULL,
            parts TEXT
        )
    """)
    conn.commit()
    conn.close()


def _add_hardware_handler(
    ctx,
    name: str,
    model: str,
    purchase_date: str,
    serial_number: Optional[str] = None,
    parts: Optional[str] = None
) -> str:
    """Adds a new hardware item to the inventory."""
    _init_db()
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO hardware_inventory (name, model, serial_number, purchase_date, parts) VALUES (?, ?, ?, ?, ?)",
            (name, model, serial_number, purchase_date, parts)
        )
        conn.commit()
        conn.close()
        return f"✅ Hardware '{name}' (S/N: {serial_number if serial_number else 'N/A'}) added to inventory."
    except sqlite3.IntegrityError:
        return f"❌ Error: Hardware with serial number '{serial_number}' already exists."
    except Exception as e:
        return f"❌ Error adding hardware: {e}"

def _list_hardware_handler(ctx) -> List[Dict[str, Any]]:
    """Lists all hardware items in the inventory."""
    _init_db()
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, model, serial_number, purchase_date, parts FROM hardware_inventory")
        rows = cursor.fetchall()
        conn.close()
        
        results = []
        for row in rows:
            results.append({
                "id": row[0],
                "name": row[1],
                "model": row[2],
                "serial_number": row[3],
                "purchase_date": row[4],
                "parts": row[5]
            })
        return results
    except Exception as e:
        return f"❌ Error listing hardware: {e}"

def _get_hardware_handler(ctx, name: str) -> Optional[Dict[str, Any]]:
    """Retrieves a single hardware item by name."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, model, serial_number, purchase_date, parts FROM hardware_inventory WHERE name = ?",
            (name,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row[0],
                "name": row[1],
                "model": row[2],
                "serial_number": row[3],
                "purchase_date": row[4],
                "parts": row[5]
            }
        return None
    except Exception as e:
        return f"❌ Error getting hardware: {e}"

def _update_hardware_handler(
    ctx,
    name: str,
    model: Optional[str] = None,
    serial_number: Optional[str] = None,
    purchase_date: Optional[str] = None,
    parts: Optional[str] = None
) -> str:
    """Updates an existing hardware item by name (and optionally serial number if provided)."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        updates = []
        params = []
        if model:
            updates.append("model = ?")
            params.append(model)
        if serial_number is not None:
            updates.append("serial_number = ?")
            params.append(serial_number)
        if purchase_date:
            updates.append("purchase_date = ?")
            params.append(purchase_date)
        if parts:
            updates.append("parts = ?")
            params.append(parts)
        
        if not updates:
            return "⚠️ No update parameters provided."

        query_conditions = ["name = ?"]
        params.append(name)
        
        # If serial_number is provided, use it as an additional condition to narrow down the update
        if serial_number is not None:
            query_conditions.append("serial_number = ?")
            params.append(serial_number)

        query = f"UPDATE hardware_inventory SET {', '.join(updates)} WHERE {' AND '.join(query_conditions)}"
        cursor.execute(query, tuple(params))
        conn.commit()
        conn.close()
        
        if cursor.rowcount > 0:
            return f"✅ Hardware '{name}' updated successfully."
        else:
            return f"⚠️ Hardware '{name}' not found or no changes made."
    except Exception as e:
        return f"❌ Error updating hardware: {e}"

def _delete_hardware_handler(ctx, name: str) -> str:
    """Deletes a hardware item by name."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM hardware_inventory WHERE name = ?",
            (name,)
        )
        conn.commit()
        conn.close()
        
        if cursor.rowcount > 0:
            return f"✅ Hardware '{name}' deleted successfully."
        else:
            return f"⚠️ Hardware '{name}' not found."
    except Exception as e:
        return f"❌ Error deleting hardware: {e}"


def get_tools() -> List[ToolEntry]:
    """Returns the list of ToolEntry objects for hardware inventory."""
    return [
        ToolEntry(
            "hardware_add",
            {
                "name": "hardware_add",
                "description": "Adds a new home appliance to the inventory database.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the appliance"},
                        "model": {"type": "string", "description": "Model of the appliance"},
                        "serial_number": {"type": "string", "description": "Unique serial number", "default": None},
                        "purchase_date": {"type": "string", "description": "Purchase date (YYYY-MM-DD)"},
                        "parts": {"type": "string", "description": "List of typical spare parts", "default": None},
                    },
                    "required": ["name", "model", "purchase_date"],
                },
            },
            _add_hardware_handler,
        ),
        ToolEntry(
            "hardware_list",
            {
                "name": "hardware_list",
                "description": "Lists all home appliances in the inventory database.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
            _list_hardware_handler,
        ),
        ToolEntry(
            "hardware_get",
            {
                "name": "hardware_get",
                "description": "Retrieves a single home appliance by its name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the appliance"},
                    },
                    "required": ["name"],
                },
            },
            _get_hardware_handler,
        ),
        ToolEntry(
            "hardware_update",
            {
                "name": "hardware_update",
                "description": "Updates an existing home appliance by its name (and optionally serial number if provided).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the appliance to update"},
                        "model": {"type": "string", "description": "New model of the appliance", "default": None},
                        "serial_number": {"type": "string", "description": "Unique serial number of the appliance to update", "default": None},
                        "purchase_date": {"type": "string", "description": "New purchase date (YYYY-MM-DD)", "default": None},
                        "parts": {"type": "string", "description": "New list of typical spare parts", "default": None},
                    },
                    "required": ["name"],
                },
            },
            _update_hardware_handler,
        ),
        ToolEntry(
            "hardware_delete",
            {
                "name": "hardware_delete",
                "description": "Deletes a home appliance from the inventory by its name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the appliance to delete"},
                    },
                    "required": ["name"],
                },
            },
            _delete_hardware_handler,
        ),
    ]
