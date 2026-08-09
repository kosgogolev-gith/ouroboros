import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

def get_currency_rate(currency_code: str, date: Optional[str] = None) -> Optional[float]:
    """
    Получает курс валюты относительно российского рубля на заданную дату.
    :param currency_code: Трехбуквенный код валюты (например, "USD", "EUR").
    :param date: Дата в формате "DD/MM/YYYY". Если не указана, используется текущая дата.
    :return: Курс валюты в рублях за единицу (или за номинал), либо None, если не найдено.
    """
    if date is None:
        date_obj = datetime.now()
    else:
        date_obj = datetime.strptime(date, "%d/%m/%Y")

    url = f"https://www.cbr.ru/scripts/XML_daily.asp?date_req={date_obj.strftime('%d/%m/%Y')}"
    
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к ЦБ РФ: {e}")
        return None

    root = ET.fromstring(response.content)
    for valute in root.findall('Valute'):
        char_code = valute.find('CharCode').text
        if char_code == currency_code:
            value_str = valute.find('Value').text
            nominal_str = valute.find('Nominal').text
            if value_str and nominal_str:
                value = float(value_str.replace(',', '.'))
                nominal = int(nominal_str)
                return value / nominal
    return None

def cbr_currency_converter(
    amount: float,
    from_currency: str,
    to_currency: str,
    date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Конвертирует заданную сумму из одной валюты в другую, используя курсы ЦБ РФ.
    Поддерживает конвертацию через рубль.
    :param amount: Сумма для конвертации.
    :param from_currency: Трехбуквенный код исходной валюты (например, "USD", "EUR", "RUB").
    :param to_currency: Трехбуквенный код целевой валюты (например, "USD", "EUR", "RUB").
    :param date: Дата в формате "DD/MM/YYYY". Если не указана, используется текущая дата.
    :return: Словарь с результатом конвертации и информацией о курсах.
    """
    result: Dict[str, Any] = {
        "success": False,
        "amount": amount,
        "from_currency": from_currency,
        "to_currency": to_currency,
        "converted_amount": None,
        "rate": None,
        "message": "",
        "date": date if date else datetime.now().strftime("%d/%m/%Y")
    }

    if from_currency == to_currency:
        result["converted_amount"] = amount
        result["rate"] = 1.0
        result["success"] = True
        result["message"] = "Исходная и целевая валюты совпадают."
        return result

    # Обработка RUB как одной из валют
    if from_currency == "RUB":
        rate_to = get_currency_rate(to_currency, date)
        if rate_to is None:
            result["message"] = f"Не удалось получить курс {to_currency} на {result['date']}."
            return result
        result["converted_amount"] = amount / rate_to
        result["rate"] = 1 / rate_to
        result["success"] = True
        result["message"] = f"Конвертация RUB в {to_currency} на {result['date']}."
        return result
    
    if to_currency == "RUB":
        rate_from = get_currency_rate(from_currency, date)
        if rate_from is None:
            result["message"] = f"Не удалось получить курс {from_currency} на {result['date']}."
            return result
        result["converted_amount"] = amount * rate_from
        result["rate"] = rate_from
        result["success"] = True
        result["message"] = f"Конвертация {from_currency} в RUB на {result['date']}."
        return result

    # Конвертация через RUB (из from_currency в RUB, затем из RUB в to_currency)
    rate_from_to_rub = get_currency_rate(from_currency, date)
    if rate_from_to_rub is None:
        result["message"] = f"Не удалось получить курс {from_currency} на {result['date']}."
        return result

    amount_in_rub = amount * rate_from_to_rub

    rate_to_from_rub = get_currency_rate(to_currency, date)
    if rate_to_from_rub is None:
        result["message"] = f"Не удалось получить курс {to_currency} на {result['date']}."
        return result

    converted_amount = amount_in_rub / rate_to_from_rub
    effective_rate = (amount * rate_from_to_rub) / (amount_in_rub / rate_to_from_rub) if amount_in_rub != 0 else 0
    
    result["converted_amount"] = converted_amount
    result["rate"] = rate_from_to_rub / rate_to_from_rub
    result["success"] = True
    result["message"] = f"Конвертация {from_currency} в {to_currency} через RUB на {result['date']}."
    return result

def get_tools() -> List[Dict[str, Any]]:
    return [
        {
            "name": "cbr_currency_converter",
            "description": "Конвертирует заданную сумму из одной валюты в другую (или в рубли), используя курсы ЦБ РФ. Поддерживает текущие и исторические курсы. Валюты указываются трехбуквенным кодом (например, USD, EUR, RUB).",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Сумма для конвертации."},
                    "from_currency": {"type": "string", "description": "Трехбуквенный код исходной валюты (например, 'USD', 'EUR', 'RUB')."},
                    "to_currency": {"type": "string", "description": "Трехбуквенный код целевой валюты (например, 'USD', 'EUR', 'RUB')."},
                    "date": {"type": "string", "description": "Дата конвертации в формате 'DD/MM/YYYY'. Если не указана, используется текущая дата."}
                },
                "required": ["amount", "from_currency", "to_currency"]
            }
        }
    ]
