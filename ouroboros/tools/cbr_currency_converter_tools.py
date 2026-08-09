import xml.etree.ElementTree as ET
import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta

class CBRCurrencyConverter:
    BASE_URL = "https://www.cbr.ru/scripts/XML_daily.asp"

    def _get_rates_for_date(self, date: Optional[str] = None) -> Dict[str, float]:
        if date:
            try:
                # Ensure date is in DD.MM.YYYY format
                datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m.%Y")
            except ValueError:
                raise ValueError("Неверный формат даты. Используйте YYYY-MM-DD.")
            url = f"{self.BASE_URL}?date_req={datetime.strptime(date, '%Y-%m-%d').strftime('%d.%m.%Y')}"
        else:
            url = self.BASE_URL

        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Ошибка при получении данных от ЦБ РФ: {e}")

        root = ET.fromstring(response.content)
        rates = {"RUB": 1.0}  # Add Ruble as a base currency
        for valute in root.findall("Valute"):
            char_code = valute.find("CharCode").text
            value_str = valute.find("Value").text.replace(",", ".")
            nominal_str = valute.find("Nominal").text.replace(",", ".")
            rates[char_code] = float(value_str) / float(nominal_str)
        return rates

    def convert(self, amount: float, from_currency: str, to_currency: str, date: Optional[str] = None) -> float:
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        if from_currency == to_currency:
            return amount

        rates = self._get_rates_for_date(date)

        if from_currency not in rates:
            raise ValueError(f"Валюта источника '{from_currency}' не найдена.")
        if to_currency not in rates:
            raise ValueError(f"Валюта назначения '{to_currency}' не найдена.")

        # Convert to RUB first, then to target currency
        amount_in_rub = amount * rates[from_currency]
        converted_amount = amount_in_rub / rates[to_currency]
        return converted_amount

def get_tools() -> List[Dict]:
    converter = CBRCurrencyConverter()
    return [
        {
            "name": "currency_convert",
            "description": "Конвертирует сумму из одной валюты в другую, используя курсы ЦБ РФ. Дата по умолчанию - текущая.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Сумма для конвертации"},
                    "from_currency": {"type": "string", "description": "Код исходной валюты (например, USD, EUR, RUB)"},
                    "to_currency": {"type": "string", "description": "Код целевой валюты (например, USD, EUR, RUB)"},
                    "date": {"type": "string", "format": "date", "description": "Дата курсов в формате YYYY-MM-DD (опционально, по умолчанию - текущая)"}
                },
                "required": ["amount", "from_currency", "to_currency"]
            }
        }
    ]
