import requests
from xml.etree import ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Optional

class CurrencyConverter:
    def __init__(self):
        self.cbr_url = "https://www.cbr.ru/scripts/XML_daily.asp"
        self.currency_codes: Dict[str, str] = {}
        self._load_currency_codes()

    def _load_currency_codes(self):
        # Initial load of currency codes
        try:
            response = requests.get(self.cbr_url, timeout=5)
            response.raise_for_status()
            tree = ET.fromstring(response.content)
            for valute in tree.findall('Valute'):
                char_code = valute.find('CharCode').text
                name = valute.find('Name').text
                if char_code and name:
                    self.currency_codes[char_code.upper()] = name
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при загрузке кодов валют: {e}")
            # Fallback for common currencies if initial load fails
            self.currency_codes = {
                "USD": "Доллар США",
                "EUR": "Евро",
                "CNY": "Китайский юань",
                "GBP": "Фунт стерлингов",
                "JPY": "Японская иена",
                "RUB": "Российский рубль" # RUB is handled as base, not fetched from CBR directly
            }

    def _fetch_rates_for_date(self, date: Optional[str] = None) -> Dict[str, float]:
        rates: Dict[str, float] = {}
        target_date_obj: datetime
        if date:
            try:
                target_date_obj = datetime.strptime(date, '%Y-%m-%d')
            except ValueError:
                raise ValueError("Неверный формат даты. Используйте YYYY-MM-DD.")
        else:
            target_date_obj = datetime.now()

        # CBR API requires date in DD/MM/YYYY format
        cbr_date = target_date_obj.strftime('%d/%m/%Y')
        params = {'date_req': cbr_date}

        try:
            response = requests.get(self.cbr_url, params=params, timeout=10)
            response.raise_for_status()
            tree = ET.fromstring(response.content)
            for valute in tree.findall('Valute'):
                char_code = valute.find('CharCode').text
                value_str = valute.find('Value').text
                nominal_str = valute.find('Nominal').text

                if char_code and value_str and nominal_str:
                    try:
                        value = float(value_str.replace(',', '.'))
                        nominal = int(nominal_str)
                        rates[char_code.upper()] = value / nominal
                    except (ValueError, TypeError) as e:
                        print(f"Ошибка парсинга валюты {char_code}: {e}")
            rates['RUB'] = 1.0  # Add Russian Ruble as base currency
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при получении курсов ЦБ РФ для даты {cbr_date}: {e}")
            raise
        except ET.ParseError as e:
            print(f"Ошибка парсинга XML от ЦБ РФ для даты {cbr_date}: {e}")
            raise
        return rates

    def convert_currency(self, amount: float, from_currency: str, to_currency: str, date: Optional[str] = None) -> float:
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        if from_currency == to_currency:
            return amount

        rates = self._fetch_rates_for_date(date)

        if from_currency not in rates:
            raise ValueError(f"Валюта '{from_currency}' не найдена в данных ЦБ РФ.")
        if to_currency not in rates:
            raise ValueError(f"Валюта '{to_currency}' не найдена в данных ЦБ РФ.")

        amount_in_rub = amount * rates[from_currency]
        converted_amount = amount_in_rub / rates[to_currency]
        return converted_amount

converter_instance = CurrencyConverter()

def cbr_currency_converter(amount: float, from_currency: str, to_currency: str, date: Optional[str] = None) -> float:
    """
    Конвертирует сумму из одной валюты в другую, используя курсы ЦБ РФ.
    Поддерживает конвертацию в/из российского рубля.

    Args:
        amount (float): Сумма для конвертации.
        from_currency (str): Исходная валюта (например, "USD", "EUR", "CNY", "RUB").
        to_currency (str): Целевая валюта (например, "USD", "EUR", "CNY", "RUB").
        date (Optional[str]): Дата для получения курса в формате YYYY-MM-DD. По умолчанию - текущая дата.

    Returns:
        float: Сконвертированная сумма.

    Raises:
        ValueError: Если указаны неверные валюты или формат даты.
        requests.exceptions.RequestException: В случае проблем с доступом к API ЦБ РФ.
    """
    return converter_instance.convert_currency(amount, from_currency, to_currency, date)

def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry(
            "cbr_currency_convert",
            {
                "name": "cbr_currency_convert",
                "description": (
                    "Convert currency using CBR (Bank of Russia) official rates. "
                    "Supports all major currencies: USD, EUR, CNY, GBP, JPY, RUB etc. "
                    "Optionally specify a date for historical rates."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "amount": {"type": "number", "description": "Amount to convert"},
                        "from_currency": {"type": "string", "description": "Source currency code (e.g. USD, EUR, CNY)"},
                        "to_currency": {"type": "string", "description": "Target currency code (e.g. RUB, USD)"},
                        "date": {"type": "string", "description": "Date for historical rate YYYY-MM-DD (optional)", "default": ""},
                    },
                    "required": ["amount", "from_currency", "to_currency"],
                },
            },
            lambda ctx, amount, from_currency, to_currency, date="": (
                f"{amount} {from_currency} = "
                f"{round(converter_instance.convert_currency(float(amount), from_currency.upper(), to_currency.upper(), date or None), 2)} "
                f"{to_currency} (курс ЦБ РФ)"
            ),
        )
    ]
