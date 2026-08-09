import requests
from datetime import datetime
from typing import List, Callable, Any
from xml.etree import ElementTree as ET

class CurrencyConverterError(Exception):
    """Custom exception for currency conversion errors."""
    pass

def _fetch_cbr_rates(date: str = None) -> dict:
    """Fetches currency rates from the CBR API for a given date."""
    if date:
        try:
            # CBR API expects DD/MM/YYYY
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            cbr_date = date_obj.strftime("%d/%m/%Y")
            url = f"https://www.cbr.ru/scripts/XML_daily.asp?date_req={cbr_date}"
        except ValueError:
            raise CurrencyConverterError("Неверный формат даты. Используйте YYYY-MM-DD.")
    else:
        url = "https://www.cbr.ru/scripts/XML_daily.asp"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status() # Raise an exception for HTTP errors
    except requests.exceptions.RequestException as e:
        raise CurrencyConverterError(f"Ошибка при запросе к API ЦБ РФ: {e}")

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as e:
        raise CurrencyConverterError(f"Ошибка при парсинге XML ответа от ЦБ РФ: {e}")

    rates = {"RUB": {"Value": 1.0, "Nominal": 1}} # Add RUB as base currency

    for valute in root.findall('Valute'):
        char_code = valute.find('CharCode').text
        nominal = int(valute.find('Nominal').text)
        value = float(valute.find('Value').text.replace(',', '.'))
        rates[char_code] = {"Value": value, "Nominal": nominal}
    return rates

def cbr_currency_converter(amount: float, from_currency: str, to_currency: str, date: str = None) -> float:
    """
    Конвертирует сумму из одной валюты в другую через API ЦБ РФ.
    Поддерживает RUB как базовую валюту.

    Args:
        amount (float): Сумма для конвертации.
        from_currency (str): Исходная валюта (например, "USD", "EUR", "RUB").
        to_currency (str): Целевая валюта (например, "USD", "EUR", "RUB").
        date (str, optional): Дата для получения курса в формате YYYY-MM-DD. По умолчанию - текущая дата.

    Returns:
        float: Сконвертированная сумма.

    Raises:
        CurrencyConverterError: Если валюта не найдена, произошла ошибка сети или парсинга.
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    rates = _fetch_cbr_rates(date)

    if from_currency not in rates:
        raise CurrencyConverterError(f"Исходная валюта '{from_currency}' не найдена.")
    if to_currency not in rates:
        raise CurrencyConverterError(f"Целевая валюта '{to_currency}' не найдена.")

    from_rate = rates[from_currency]["Value"] / rates[from_currency]["Nominal"]
    to_rate = rates[to_currency]["Value"] / rates[to_currency]["Nominal"]

    # Convert to RUB first, then to target currency
    amount_in_rub = amount * from_rate
    converted_amount = amount_in_rub / to_rate

    return converted_amount

def get_tools() -> List[Callable[..., Any]]:
    return [cbr_currency_converter]
