from typing import List, Optional
from datetime import datetime, timedelta
from ouroboros.tools.registry import ToolEntry

def _reminder_handler(ctx, text: str, delay_minutes: Optional[int] = None, at: Optional[str] = None) -> str:
    """Устанавливает напоминание, которое будет отправлено владельцу через указанное время или в определенную дату/время."""
    if delay_minutes is None and at is None:
        return "❌ Ошибка: Необходимо указать либо 'delay_minutes', либо 'at'."

    if delay_minutes is not None and at is not None:
        return "❌ Ошибка: Нельзя указывать одновременно 'delay_minutes' и 'at'."

    current_time = datetime.now()
    reminder_time = None
    delay_message = ""

    if delay_minutes is not None:
        reminder_time = current_time + timedelta(minutes=delay_minutes)
        delay_message = f"через {delay_minutes} мин."
    elif at is not None:
        try:
            if len(at) == 5 and ':' in at:  # HH:MM
                hour, minute = map(int, at.split(':'))
                reminder_time = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if reminder_time <= current_time:
                    reminder_time += timedelta(days=1) # If time passed, schedule for next day
            elif len(at) >= 10 and 'T' in at: # YYYY-MM-DDTHH:MM
                reminder_time = datetime.fromisoformat(at)
            else:
                return "❌ Ошибка: Некорректный формат времени 'at'. Используйте HH:MM или YYYY-MM-DDTHH:MM."
        except ValueError as e:
            return f"❌ Ошибка при парсинге времени 'at': {e}"
        
        time_diff = reminder_time - current_time
        delay_message = f"в {reminder_time.strftime('%Y-%m-%d %H:%M')} (через {int(time_diff.total_seconds() / 60)} мин.)"

    if reminder_time is None:
        return "❌ Ошибка: Не удалось установить время напоминания."

    # Schedule the actual message sending as a background task
    # The supervisor will process send_owner_message with a delay argument
    delay_seconds = int((reminder_time - current_time).total_seconds())
    
    ctx.send_owner_message(text=f"⏰ Напоминание: {text}", reason="reminder", delay=delay_seconds) # <-- Используем ctx.send_owner_message с reason
    
    return f"⏰ Напоминание установлено: \"{text}\" {delay_message}."

def get_tools() -> List[ToolEntry]:
    """ОБЯЗАТЕЛЬНО: реестр вызывает эту функцию при старте."""
    return [
        ToolEntry(
            "reminder_set",
            {
                "name": "reminder_set",
                "description": "Устанавливает напоминание, которое будет отправлено владельцу. Можно указать задержку в минутах или конкретное время.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Текст напоминания."
                        },
                        "delay_minutes": {
                            "type": "integer",
                            "description": "Задержка в минутах до отправки напоминания.",
                            "minimum": 1
                        },\
                        "at": {
                            "type": "string",
                            "description": "Конкретное время для напоминания (HH:MM или YYYY-MM-DDTHH:MM). Если время в HH:MM уже прошло сегодня, напоминание будет установлено на завтра."
                        },
                    },
                    "required": ["text"],
                },
            },\
            _reminder_handler,
        )
    ]
