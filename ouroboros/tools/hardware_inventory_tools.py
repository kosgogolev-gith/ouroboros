from typing import List, Dict, Any, Optional
import sqlite3
from ouroboros.tools.registry import ToolEntry
import os

DB_PATH = os.path.join(os.getenv('DRIVE_ROOT', './'), 'memory', 'hardware_inventory.db')

def _init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hardware_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            model TEXT,
            serial_number TEXT UNIQUE,
            purchase_date TEXT,
            parts_info TEXT
        )
    """)
    conn.commit()
    conn.close()

def _add_item(ctx, name: str, model: Optional[str] = None, serial_number: Optional[str] = None, 
              purchase_date: Optional[str] = None, parts_info: Optional[str] = None) -> str:
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO hardware_inventory (name, model, serial_number, purchase_date, parts_info)
            VALUES (?, ?, ?, ?, ?)
        """, (name, model, serial_number, purchase_date, parts_info))
        conn.commit()
        return f"✅ Item '{name}' added successfully."
    except sqlite3.IntegrityError:
        return f"❌ Error: Item with serial number '{serial_number}' already exists."
    except Exception as e:
        return f"❌ Error adding item: {e}"
    finally:
        conn.close()

def _list_items(ctx) -> str:
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name, model, serial_number, purchase_date, parts_info FROM hardware_inventory")
        items = cursor.fetchall()
        if not items:
            return "No hardware items found."
        
        headers = ["ID", "Name", "Model", "Serial Number", "Purchase Date", "Parts Info"]
        rows = [list(item) for item in items]
        
        # Simple formatting for now
        output = []
        output.append("| " + " | ".join(headers) + " |")
        output.append("|" + "---|"*len(headers))
        for row in rows:
            output.append("| " + " | ".join(map(str, row)) + " |")
        return "\n".join(output)
    except Exception as e:
        return f"❌ Error listing items: {e}"
    finally:
        conn.close()

def _get_item(ctx, item_id: int) -> str:
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name, model, serial_number, purchase_date, parts_info FROM hardware_inventory WHERE id = ?", (item_id,))
        item = cursor.fetchone()
        if not item:
            return f"❌ Item with ID {item_id} not found."
        
        headers = ["ID", "Name", "Model", "Serial Number", "Purchase Date", "Parts Info"]
        item_dict = dict(zip(headers, item))
        return f"Item Details:\n" + "\n".join([f"{k}: {v}" for k, v in item_dict.items()])
    except Exception as e:
        return f"❌ Error getting item: {e}"
    finally:
        conn.close()

def _update_item(ctx, item_id: int, name: Optional[str] = None, model: Optional[str] = None, 
                 serial_number: Optional[str] = None, purchase_date: Optional[str] = None, 
                 parts_info: Optional[str] = None) -> str:
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if model is not None:
            updates.append("model = ?")
            params.append(model)
        if serial_number is not None:
            updates.append("serial_number = ?")
            params.append(serial_number)
        if purchase_date is not None:
            updates.append("purchase_date = ?")
            params.append(purchase_date)
        if parts_info is not None:
            updates.append("parts_info = ?")
            params.append(parts_info)

        if not updates:
            return "No fields provided for update."

        params.append(item_id)
        
        cursor.execute(f"UPDATE hardware_inventory SET {', '.join(updates)} WHERE id = ?", tuple(params))
        conn.commit()
        if cursor.rowcount == 0:
            return f"❌ Item with ID {item_id} not found."
        return f"✅ Item with ID {item_id} updated successfully."
    except sqlite3.IntegrityError:
        return f"❌ Error: Serial number '{serial_number}' already exists for another item."
    except Exception as e:
        return f"❌ Error updating item: {e}"
    finally:
        conn.close()

def _delete_item(ctx, item_id: int) -> str:
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM hardware_inventory WHERE id = ?", (item_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return f"❌ Item with ID {item_id} not found."
        return f"✅ Item with ID {item_id} deleted successfully."
    except Exception as e:
        return f"❌ Error deleting item: {e}"
    finally:
        conn.close()


def get_tools() -> List[ToolEntry]:
    _init_db() # Ensure DB is initialized when tools are loaded
    return [
        ToolEntry(
            "hardware_add_item",
            {
                "name": "hardware_add_item",
                "description": "Добавляет новую единицу техники в базу данных.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Название техники (например, 'Холодильник')."},
                        "model": {"type": "string", "description": "Модель техники."},
                        "serial_number": {"type": "string", "description": "Серийный номер техники (должен быть уникальным)."},
                        "purchase_date": {"type": "string", "description": "Дата покупки (формат YYYY-MM-DD)."},
                        "parts_info": {"type": "string", "description": "Информация о запчастях (например, 'Фильтр для воды 123-ABC')."},
                    },
                    "required": ["name"],
                },
            },
            _add_item,
        ),
        ToolEntry(
            "hardware_list_items",
            {
                "name": "hardware_list_items",
                "description": "Отображает список всей техники в базе данных.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
            _list_items,
        ),
        ToolEntry(
            "hardware_get_item",
            {
                "name": "hardware_get_item",
                "description": "Получает детальную информацию о технике по её ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "integer", "description": "ID элемента техники."},
                    },
                    "required": ["item_id"],
                },
            },
            _get_item,
        ),
        ToolEntry(
            "hardware_update_item",
            {
                "name": "hardware_update_item",
                "description": "Обновляет информацию о существующей единице техники по ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "integer", "description": "ID элемента техники."},
                        "name": {"type": "string", "description": "Новое название техники."},
                        "model": {"type": "string", "description": "Новая модель техники."},
                        "serial_number": {"type": "string", "description": "Новый серийный номер техники (должен быть уникальным)."},
                        "purchase_date": {"type": "string", "description": "Новая дата покупки (формат YYYY-MM-DD)."},
                        "parts_info": {"type": "string", "description": "Новая информация о запчастях."},
                    },
                    "required": ["item_id"],
                },
            },
            _update_item,
        ),
        ToolEntry(
            "hardware_delete_item",
            {
                "name": "hardware_delete_item",
                "description": "Удаляет единицу техники из базы данных по её ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "integer", "description": "ID элемента техники."},
                    },
                    "required": ["item_id"],
                },
            },
            _delete_item,
        ),
    ]
