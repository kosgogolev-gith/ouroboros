from typing import List, Dict, Any, Optional
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# URL API ЦБ РФ для получения курсов валют
CBR_DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
CBR_DAILY_EN_URL = "https://www.cbr.ru/scripts/XML_daily_eng.asp" # For English currency names if needed

def _fetch_exchange_rates(date: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Извлекает курсы валют с сайта ЦБ РФ за указанную дату или на текущий день.
    Возвращает словарь с данными по валютам.
    """
    params = {}
    if date:
        try:
            # Формат даты для ЦБ РФ: DD/MM/YYYY
            formatted_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d/%m/%Y")
            params["date_req"] = formatted_date
        except ValueError:
            raise ValueError("Неверный формат даты. Используйте YYYY-MM-DD.")

    try:
        response = requests.get(CBR_DAILY_URL, params=params, timeout=10)
        response.raise_for_status()  # Вызовет исключение для ошибок HTTP
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Ошибка при подключении к API ЦБ РФ: {e}")

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as e:
        raise ValueError(f"Ошибка при парсинге XML ответа ЦБ РФ: {e}")

    rates = {}
    for valute in root.findall("Valute"):
        char_code = valute.find("CharCode").text
        num_code = valute.find("NumCode").text
        name = valute.find("Name").text
        nominal = int(valute.find("Nominal").text)
        value_str = valute.find("Value").text.replace(",", ".")
        value = float(value_str)

        rates[char_code.upper()] = {
            "num_code": num_code,
            "name": name,
            "nominal": nominal,
            "value": value,
        }
    
    # Добавляем рубль для конвертации
    rates["RUB"] = {"num_code": "643", "name": "Российский рубль", "nominal": 1, "value": 1.0}

    return rates

def cbr_currency_convert(
    amount: float, 
    from_currency: str, 
    to_currency: str, 
    date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Конвертирует указанную сумму из одной валюты в другую по курсу ЦБ РФ.

    Args:
        amount: Сумма для конвертации.
        from_currency: Код исходной валюты (например, "USD", "EUR", "RUB").
        to_currency: Код целевой валюты (например, "RUB", "USD", "EUR").
        date: Дата, на которую запрашивается курс в формате YYYY-MM-DD. 
              Если не указано, используется текущая дата.

    Returns:
        Словарь с результатом конвертации и использованными курсами.
    """
    if not isinstance(amount, (int, float)) or amount < 0:
        raise ValueError("Сумма должна быть положительным числом.")
    if not isinstance(from_currency, str) or not from_currency.strip():
        raise ValueError("Исходная валюта не может быть пустой.")
    if not isinstance(to_currency, str) or not to_currency.strip():
        raise ValueError("Целевая валюта не может быть пустой.")

    from_currency = from_currency.strip().upper()
    to_currency = to_currency.strip().upper()

    rates = _fetch_exchange_rates(date)

    if from_currency not in rates:
        raise ValueError(f"Исходная валюта '{from_currency}' не найдена в курсах ЦБ РФ.")
    if to_currency not in rates:
        raise ValueError(f"Целевая валюта '{to_currency}' не найдена в курсах ЦБ РФ.")

    from_rate_info = rates[from_currency]
    to_rate_info = rates[to_currency]

    # Переводим исходную сумму в рубли
    amount_in_rub = (amount * from_rate_info["value"]) / from_rate_info["nominal"]

    # Переводим рубли в целевую валюту
    converted_amount = (amount_in_rub * to_rate_info["nominal"]) / to_rate_info["value"]

    return {
        "original_amount": amount,
        "from_currency": from_currency,
        "to_currency": to_currency,
        "converted_amount": round(converted_amount, 4),
        "exchange_rate_from_rub": f"1 {from_currency} = {from_rate_info['value'] / from_rate_info['nominal']:.4f} RUB",
        "exchange_rate_to_rub": f"1 {to_currency} = {to_rate_info['value'] / to_rate_info['nominal']:.4f} RUB",
        "date": date if date else datetime.now().strftime("%Y-%m-%d")
    }

def get_tools() -> List[Any]:
    return [cbr_currency_convert]
