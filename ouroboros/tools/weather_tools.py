"""Weather tools for Ouroboros — uses wttr.in (no API key needed)."""
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import List

try:
    from ouroboros.tools.registry import ToolEntry
except ImportError:
    ToolEntry = None


def _weather_get(ctx, city: str = "Moscow", days: int = 1, date: str = "") -> str:
    """Get current weather and forecast for a city.
    date: optional, 'tomorrow' or 'YYYY-MM-DD' to get forecast for specific day.
    """
    try:
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "Ouroboros/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read())

        cur = d["current_condition"][0]
        temp = cur["temp_C"]
        feels = cur["FeelsLikeC"]
        humidity = cur["humidity"]
        desc = cur["weatherDesc"][0]["value"]
        wind = cur["windspeedKmph"]
        precip = cur["precipMM"]

        # Handle date filter
        from datetime import datetime, timedelta
        target_date = None
        if date:
            if date.lower() == 'tomorrow':
                target_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            elif date.lower() == 'today':
                target_date = datetime.now().strftime('%Y-%m-%d')
            else:
                target_date = date  # assume YYYY-MM-DD

        if target_date:
            # Return only the forecast for target date
            for w in d.get('weather', []):
                if w['date'] == target_date:
                    max_t = w['maxtempC']
                    min_t = w['mintempC']
                    desc_f = w['hourly'][4]['weatherDesc'][0]['value'] if w.get('hourly') else ''
                    precip_f = w.get('hourly', [{}])[4].get('precipMM', '0') if w.get('hourly') else '0'
                    wind_f = w.get('hourly', [{}])[4].get('windspeedKmph', '?') if w.get('hourly') else '?'
                    return (
                        f"## Погода: {city} на {target_date}\n"
                        f"🌡 {min_t}–{max_t}°C\n"
                        f"☁ {desc_f}\n"
                        f"🌬 Ветер: {wind_f} км/ч | 🌧 Осадки: {precip_f} мм"
                    )
            return f"Прогноз для {city} на {target_date} недоступен (wttr.in даёт прогноз на 3 дня)."

        lines = [
            f"## Погода: {city}",
            f"🌡 Сейчас: **{temp}°C**, ощущается как {feels}°C",
            f"☁ {desc}",
            f"💧 Влажность: {humidity}% | 🌬 Ветер: {wind} км/ч | 🌧 Осадки: {precip} мм",
        ]

        # Forecast
        forecast_days = min(days, len(d.get("weather", [])))
        if forecast_days > 0:
            lines.append("\n**Прогноз:**")
        for w in d["weather"][:forecast_days]:
            w_date = w["date"]
            max_t = w["maxtempC"]
            min_t = w["mintempC"]
            desc_f = w["hourly"][4]["weatherDesc"][0]["value"] if w.get("hourly") else ""
            precip_f = w.get("hourly", [{}])[4].get("precipMM", "0") if w.get("hourly") else "0"
            lines.append(f"• {w_date}: {min_t}–{max_t}°C, {desc_f}, осадки {precip_f} мм")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Ошибка получения погоды для '{city}': {e}"


def _weather_forecast(ctx, city: str = "Moscow", days: int = 3) -> str:
    """Get weather forecast for 1-3 days."""
    return _weather_get(ctx, city=city, days=days)


def get_tools() -> List:
    if ToolEntry is None:
        return []

    return [
        ToolEntry(
            "weather_get",
            {
                "name": "weather_get",
                "description": "Get current weather for a city. Default: Moscow.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name (e.g. Moscow, London)", "default": "Moscow"},
                        "days": {"type": "integer", "description": "Forecast days (1-3)", "default": 1},
                        "date": {"type": "string", "description": "Specific date: 'today', 'tomorrow', or 'YYYY-MM-DD'", "default": ""},
                    },
                    "required": [],
                },
            },
            _weather_get,
        ),
        ToolEntry(
            "weather_forecast",
            {
                "name": "weather_forecast",
                "description": "Get weather forecast for 1-3 days.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "default": "Moscow"},
                        "days": {"type": "integer", "description": "Number of days (1-3)", "default": 3},
                    },
                    "required": [],
                },
            },
            _weather_forecast,
        ),
    ]
