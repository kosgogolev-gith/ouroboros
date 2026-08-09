
import requests
from datetime import datetime
from xml.etree import ElementTree as ET
from typing import List, Dict, Optional, Any

def get_tools() -> List[Dict[str, Any]]:
    """
    Возвращает список инструментов, предоставляемых этим модулем.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "cbr_currency_converter",
                "description": "Конвертирует сумму из одной валюты в другую, используя курсы ЦБ РФ. Полезно для расчетов TCO в рублях.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "amount": {
                            "type": "number",
                            "description": "Сумма для конвертации"
                        },
                        "from_currency": {
                            "type": "string",
                            "description": "Исходная валюта (например, USD, EUR, CNY)"
                        },
                        "to_currency": {
                            "type": "string",
                            "description": "Целевая валюта (например, USD, EUR, RUB)"
                        },
                        "date": {
                            "type": "string",
                            "description": "Дата для курсов валют в формате YYYY-MM-DD (по умолчанию - текущая дата)"
                        }
                    },
                    "required": ["amount", "from_currency", "to_currency"]
                }
            }
        }
    ]

def _fetch_currency_rates(date: Optional[str] = None) -> Dict[str, float]:
    """
    Получает курсы валют с сайта ЦБ РФ за указанную дату.
    Возвращает словарь, где ключ - код валюты, значение - курс в рублях за единицу валюты.
    """
    if date:
        try:
            # Формат даты для ЦБ РФ: DD/MM/YYYY
            parsed_date = datetime.strptime(date, "%Y-%m-%d")
            url_date = parsed_date.strftime("%d/%m/%Y")
        except ValueError:
            return {"error": "Неверный формат даты. Используйте YYYY-MM-DD."}
    else:
        url_date = datetime.now().strftime("%d/%m/%Y")

    url = f"https://www.cbr.ru/scripts/XML_daily.asp?date_req={url_date}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return {"error": f"Ошибка при получении курсов валют с ЦБ РФ: {e}"}

    root = ET.fromstring(response.content)
    rates = {"RUB": 1.0}  # Рубль всегда 1 к 1 к самому себе
    for valute in root.findall('Valute'):
        char_code = valute.find('CharCode').text
        value = valute.find('Value').text.replace(',', '.')
        nominal = valute.find('Nominal').text
        try:
            rates[char_code] = float(value) / int(nominal)
        except (ValueError, TypeError):
            continue  # Пропускаем, если не можем распарсить
    return rates

def cbr_currency_converter(amount: float, from_currency: str, to_currency: str, date: Optional[str] = None) -> Dict[str, Any]:
    """
    Конвертирует сумму из одной валюты в другую, используя курсы ЦБ РФ.
    Args:
        amount (float): Сумма для конвертации.
        from_currency (str): Исходная валюта (например, USD, EUR, CNY).
        to_currency (str): Целевая валюта (например, USD, EUR, RUB).
        date (str, optional): Дата для курсов валют в формате YYYY-MM-DD. По умолчанию - текущая дата.
    Returns:
        dict: Результат конвертации или сообщение об ошибке.
    """
    rates = _fetch_currency_rates(date)

    if "error" in rates:
        return rates

    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if from_currency not in rates:
        return {"error": f"Неизвестная исходная валюта: {from_currency}. Проверьте код валюты (например, USD, EUR, CNY)."}
    if to_currency not in rates:
        return {"error": f"Неизвестная целевая валюта: {to_currency}. Проверьте код валюты (например, USD, EUR, CNY)."}

    amount_in_rub = amount * rates[from_currency]
    converted_amount = amount_in_rub / rates[to_currency]

    return {
        "amount": amount,
        "from_currency": from_currency,
        "to_currency": to_currency,
        "converted_amount": round(converted_amount, 4),
        "rate": round(rates[from_currency] / rates[to_currency], 4),
        "date": date if date else datetime.now().strftime("%Y-%m-%d")
    }
