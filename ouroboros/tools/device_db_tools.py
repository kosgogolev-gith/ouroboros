from typing import List, Dict
import sqlite3
import json
from datetime import datetime

from ouroboros.tools.registry import ToolEntry

DB_PATH = "memory/device_db.sqlite"

def _get_db_connection(ctx):
    db_file = ctx.drive_root / DB_PATH
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db(ctx):
    conn = _get_db_connection(ctx)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            model TEXT,
            serial_number TEXT UNIQUE,
            purchase_date TEXT,
            part_types TEXT
        )
    """)
    conn.commit()
    conn.close()

def _add_device_handler(ctx, name: str, model: str, serial_number: str, purchase_date: str = None, part_types: str = None) -> str:
    _init_db(ctx)
    conn = _get_db_connection(ctx)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO devices (name, model, serial_number, purchase_date, part_types)
            VALUES (?, ?, ?, ?, ?)
        """, (name, model, serial_number, purchase_date, part_types))
        conn.commit()
        return f"✅ Устройство '{name}' успешно добавлено."
    except sqlite3.IntegrityError as e:
        return f"❌ Ошибка добавления устройства: {e}. Возможно, имя или серийный номер уже существуют."
    except Exception as e:
        return f"❌ Неизвестная ошибка при добавлении устройства: {e}"
    finally:
        conn.close()

def _list_devices_handler(ctx) -> str:
    _init_db(ctx)
    conn = _get_db_connection(ctx)
    cursor = conn.cursor()
    cursor.execute("SELECT name, model, serial_number, purchase_date, part_types FROM devices")
    devices = cursor.fetchall()
    conn.close()

    if not devices:
        return "Список техники пуст."

    output = ["**Список техники:**"]
    for device in devices:
        output.append(f"- **Название:** {device['name']}, **Модель:** {device['model']}, **Серийный номер:** {device['serial_number']}, **Дата покупки:** {device['purchase_date'] if device['purchase_date'] else 'Н/Д'}, **Типы запчастей:** {device['part_types'] if device['part_types'] else 'Н/Д'}")
    return "\n".join(output)

def _get_device_handler(ctx, name_or_serial: str) -> str:
    _init_db(ctx)
    conn = _get_db_connection(ctx)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, model, serial_number, purchase_date, part_types
        FROM devices
        WHERE name = ? OR serial_number = ?
    """, (name_or_serial, name_or_serial))
    device = cursor.fetchone()
    conn.close()

    if not device:
        return f"❌ Устройство с именем или серийным номером '{name_or_serial}' не найдено."

    return (f"**Информация об устройстве '{device['name']}':**\n"
            f"- **Название:** {device['name']}\n"
            f"- **Модель:** {device['model']}\n"
            f"- **Серийный номер:** {device['serial_number']}\n"
            f"- **Дата покупки:** {device['purchase_date'] if device['purchase_date'] else 'Н/Д'}\n"
            f"- **Типы запчастей:** {device['part_types'] if device['part_types'] else 'Н/Д'}")

def _update_device_handler(ctx, serial_number: str, name: str = None, model: str = None, purchase_date: str = None, part_types: str = None) -> str:
    _init_db(ctx)
    conn = _get_db_connection(ctx)
    cursor = conn.cursor()
    
    update_fields = []
    update_values = []

    if name:
        update_fields.append("name = ?")
        update_values.append(name)
    if model:
        update_fields.append("model = ?")
        update_values.append(model)
    if purchase_date:
        update_fields.append("purchase_date = ?")
        update_values.append(purchase_date)
    if part_types:
        update_fields.append("part_types = ?")
        update_values.append(part_types)

    if not update_fields:
        return "❌ Нет данных для обновления. Укажите хотя бы одно поле для изменения."

    update_values.append(serial_number)
    
    try:
        cursor.execute(f"UPDATE devices SET {', '.join(update_fields)} WHERE serial_number = ?", tuple(update_values))
        conn.commit()
        if cursor.rowcount == 0:
            return f"❌ Устройство с серийным номером '{serial_number}' не найдено."
        return f"✅ Устройство с серийным номером '{serial_number}' успешно обновлено."
    except Exception as e:
        return f"❌ Ошибка при обновлении устройства: {e}"
    finally:
        conn.close()

def _delete_device_handler(ctx, serial_number: str) -> str:
    _init_db(ctx)
    conn = _get_db_connection(ctx)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM devices WHERE serial_number = ?", (serial_number,))
        conn.commit()
        if cursor.rowcount == 0:
            return f"❌ Устройство с серийным номером '{serial_number}' не найдено."
        return f"✅ Устройство с серийным номером '{serial_number}' успешно удалено."
    except Exception as e:
        return f"❌ Ошибка при удалении устройства: {e}"
    finally:
        conn.close()

def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry(
            "add_device",
            {
                "name": "add_device",
                "description": "Добавляет новую единицу техники в базу данных.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Название устройства (например, 'Ноутбук'). Должно быть уникальным."},
                        "model": {"type": "string", "description": "Модель устройства (например, 'MacBook Pro M1')."},
                        "serial_number": {"type": "string", "description": "Серийный номер устройства. Должен быть уникальным."},
                        "purchase_date": {"type": "string", "description": "Дата покупки (формат YYYY-MM-DD, например '2023-01-15')."},
                        "part_types": {"type": "string", "description": "Типы запчастей, через запятую (например, 'RAM, SSD, Батарея')."},
                    },
                    "required": ["name", "model", "serial_number"],
                },
            },
            _add_device_handler,
        ),
        ToolEntry(
            "list_devices",
            {
                "name": "list_devices",
                "description": "Выводит список всех устройств в базе данных.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            _list_devices_handler,
        ),
        ToolEntry(
            "get_device",
            {
                "name": "get_device",
                "description": "Получает информацию о конкретном устройстве по имени или серийному номеру.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name_or_serial": {"type": "string", "description": "Название или серийный номер устройства."},
                    },
                    "required": ["name_or_serial"],
                },
            },
            _get_device_handler,
        ),
        ToolEntry(
            "update_device",
            {
                "name": "update_device",
                "description": "Обновляет информацию об устройстве по серийному номеру. Можно обновить название, модель, дату покупки или типы запчастей.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "serial_number": {"type": "string", "description": "Серийный номер устройства, которое нужно обновить."},
                        "name": {"type": "string", "description": "Новое название устройства."},
                        "model": {"type": "string", "description": "Новая модель устройства."},
                        "purchase_date": {"type": "string", "description": "Новая дата покупки (формат YYYY-MM-DD)."},
                        "part_types": {"type": "string", "description": "Новые типы запчастей, через запятую."},
                    },
                    "required": ["serial_number"],
                },
            },
            _update_device_handler,
        ),
        ToolEntry(
            "delete_device",
            {
                "name": "delete_device",
                "description": "Удаляет устройство из базы данных по серийному номеру.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "serial_number": {"type": "string", "description": "Серийный номер устройства, которое нужно удалить."},
                    },
                    "required": ["serial_number"],
                },
            },
            _delete_device_handler,
        ),
    ]
