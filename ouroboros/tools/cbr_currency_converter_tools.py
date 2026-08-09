from typing import List, Optional
from datetime import datetime
import requests
import xml.etree.ElementTree as ET

from ouroboros.tools.registry import ToolEntry

def _cbr_currency_converter(
    ctx,
    amount: float,
    from_currency: str,
    to_currency: str,
    date: Optional[str] = None
) -> str:
    """
    Конвертирует сумму из одной валюты в другую, используя курсы ЦБ РФ.
    Поддерживает RUB, USD, EUR, CNY.

    Args:
        amount: Сумма для конвертации.
        from_currency: Исходная валюта (например, "USD", "RUB", "CNY", "EUR").
        to_currency: Целевая валюта (например, "USD", "RUB", "CNY", "EUR").
        date: Дата для получения курса в формате YYYY-MM-DD. По умолчанию - текущая дата.

    Returns:
        Строка с результатом конвертации или сообщением об ошибке.
    """

    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if from_currency == to_currency:
        return f"✅ {amount:.2f} {from_currency} = {amount:.2f} {to_currency}"

    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return "❌ Неверный формат даты. Используйте YYYY-MM-DD."

    url = "https://www.cbr.ru/scripts/XML_daily.asp"
    if date:
        day, month, year = date.split('-')
        url += f"?date_req={day}/{month}/{year}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Поднимает HTTPError для плохих ответов (4xx или 5xx)
    except requests.exceptions.RequestException as e:
        return f"❌ Ошибка при запросе к ЦБ РФ: {e}"

    root = ET.fromstring(response.content)

    rates = {"RUB": 1.0}
    valute_map = {
        "USD": "Доллар США",
        "EUR": "Евро",
        "CNY": "Китайский юань"
    }
    
    # Добавление всех валют из XML в rates, используя код валюты
    for valute in root.findall('Valute'):
        char_code = valute.find('CharCode').text
        value = float(valute.find('Value').text.replace(',', '.'))
        nominal = int(valute.find('Nominal').text)
        rates[char_code] = value / nominal

    # Проверка на наличие всех необходимых валют
    missing_currencies = []
    if from_currency not in rates:
        missing_currencies.append(from_currency)
    if to_currency not in rates:
        missing_currencies.append(to_currency)

    if missing_currencies:
        return f"❌ Не удалось получить курс для валют: {', '.join(missing_currencies)}. Поддерживаемые валюты: RUB, USD, EUR, CNY."

    rate_from_rub = rates[from_currency]
    rate_to_rub = rates[to_currency]

    # Конвертация в рубли, затем из рублей в целевую валюту
    amount_in_rub = amount * rate_from_rub
    converted_amount = amount_in_rub / rate_to_rub

    return f"✅ {amount:.2f} {from_currency} = {converted_amount:.2f} {to_currency} (по курсу ЦБ РФ на {date if date else 'сегодня'})"

def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry(
            "cbr_currency_converter",
            {
                "name": "cbr_currency_converter",
                "description": "Конвертирует сумму из одной валюты в другую по курсам ЦБ РФ. Поддерживает RUB, USD, EUR, CNY.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "amount": {"type": "number", "description": "Сумма для конвертации."},
                        "from_currency": {"type": "string", "description": "Исходная валюта (например, 'USD', 'RUB', 'CNY', 'EUR')."},
                        "to_currency": {"type": "string", "description": "Целевая валюта (например, 'USD', 'RUB', 'CNY', 'EUR')."},
                        "date": {"type": "string", "description": "Дата для получения курса в формате YYYY-MM-DD. По умолчанию - текущая дата."}
                    },
                    "required": ["amount", "from_currency", "to_currency"],
                },
            },
            _cbr_currency_converter,
        )
    ]
