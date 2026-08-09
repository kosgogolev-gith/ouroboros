import requests
from bs4 import BeautifulSoup

# Этот импорт будет заменен на прямой вызов языковой модели
# from ouroboros.llm import LLMClient 

def get_tools():
    return [summary_webpage]

def summary_webpage(url: str) -> str:
    """Делает саммаризацию страницы по ссылке: краткое содержание и вывод.

    Args:
        url: URL страницы для саммаризации.

    Returns:
        Текст с саммаризацией страницы: краткое содержание и вывод.
    """
    try:
        # Использование requests для получения содержимого страницы
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Вызовет исключение для ошибок HTTP
        
        # Парсинг HTML для извлечения читаемого текста
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Удаление скриптов, стилей и других невидимых элементов
        for script in soup(["script", "style"]):
            script.extract()    # rip it out

        text = soup.get_text()

        # Разбиение текста на строки и удаление лишних пробелов
        lines = (line.strip() for line in text.splitlines())
        # Удаление пустых строк
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # Объединение в один текст
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        if not text:
            return "Не удалось извлечь текст со страницы."

        # Здесь будет вызов LLM для саммаризации
        # Пока заглушка:
        summary = f"Краткое содержание страницы по URL: {url}\n\n" \
                  f"Извлеченный текст (первые 500 символов): {text[:500]}..."

        # В будущем:
        # llm_client = LLMClient()
        # summary = llm_client.generate_summary(text) # Пример вызова
        
        return summary
    except requests.exceptions.RequestException as e:
        return f"Ошибка при доступе к странице: {e}"
    except Exception as e:
        return f"Произошла непредвиденная ошибка: {e}"
