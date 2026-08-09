import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict

def get_exchange_rate(currency_code: str, date: str = None) -> float:
    """
    Получает курс валюты по отношению к рублю от ЦБ РФ.
    :param currency_code: Трехбуквенный код валюты (например, "USD", "EUR", "CNY").
    :param date: Дата в формате "DD/MM/YYYY". Если не указана, используется текущая дата.
    :return: Курс валюты в рублях.
    """
    if date:
        date_obj = datetime.strptime(date, "%d/%m/%Y")
    else:
        date_obj = datetime.now()

    url = f"https://www.cbr.ru/scripts/XML_daily.asp?date_req={date_obj.strftime('%d/%m/%Y')}"
    
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Ошибка при подключении к API ЦБ РФ: {e}")

    root = ET.fromstring(response.content)
    
    for valute in root.findall('Valute'):
        char_code = valute.find('CharCode').text
        if char_code == currency_code:
            value = float(valute.find('Value').text.replace(',', '.'))
            nominal = int(valute.find('Nominal').text)
            return value / nominal
    
    raise ValueError(f"Курс для валюты '{currency_code}' не найден на дату {date_obj.strftime('%d/%m/%Y')}")

def cbr_currency_convert(amount: float, from_currency: str, to_currency: str, date: str = None) -> Dict:
    """
    Конвертирует указанную сумму из одной валюты в другую, используя курсы ЦБ РФ.
    :param amount: Сумма для конвертации.
    :param from_currency: Трехбуквенный код исходной валюты (например, "USD", "EUR", "CNY", "RUB").
    :param to_currency: Трехбуквенный код целевой валюты (например, "USD", "EUR", "CNY", "RUB").
    :param date: Дата в формате "DD/MM/YYYY". Если не указана, используется текущая дата.
    :return: Словарь с результатом конвертации.
    """
    
    if from_currency == to_currency:
        return {"converted_amount": amount, "from_currency": from_currency, "to_currency": to_currency, "date": date}

    from_rate = 1.0
    if from_currency.upper() != "RUB":
        from_rate = get_exchange_rate(from_currency.upper(), date)

    to_rate = 1.0
    if to_currency.upper() != "RUB":
        to_rate = get_exchange_rate(to_currency.upper(), date)

    amount_in_rubles = amount * from_rate
    converted_amount = amount_in_rubles / to_rate

    return {
        "amount": amount,
        "from_currency": from_currency.upper(),
        "to_currency": to_currency.upper(),
        "converted_amount": round(converted_amount, 2),
        "date": date if date else datetime.now().strftime("%d/%m/%Y")
    }

def get_tools() -> List[Dict]:
    return [
        {
            "name": "cbr_currency_convert",
            "description": "Конвертирует указанную сумму из одной валюты в другую, используя курсы ЦБ РФ (бесплатный API, без ключа). Полезно для TCO расчётов в рублях. Поддерживает RUB как исходную или целевую валюту.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Сумма для конвертации."},
                    "from_currency": {"type": "string", "description": "Трехбуквенный код исходной валюты (например, 'USD', 'EUR', 'CNY', 'RUB')."},
                    "to_currency": {"type": "string", "description": "Трехбуквенный код целевой валюты (например, 'USD', 'EUR', 'CNY', 'RUB')."},
                    "date": {"type": "string", "description": "Дата в формате 'DD/MM/YYYY'. Если не указана, используется текущая дата."}
                },
                "required": ["amount", "from_currency", "to_currency"]
            }
        }
    ]
