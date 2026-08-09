
import html2text
from typing import Callable, Literal
from pydantic import BaseModel, Field

from ouroboros.llm import LLM
from ouroboros.tools.registry import register_tool
from ouroboros.tools.core import default_api

class SummaryWebpageResult(BaseModel):
    summary: str = Field(..., description="Краткое содержание страницы")
    conclusion: str = Field(..., description="Вывод из содержания страницы")

def get_tools(llm_client: LLM, browser_action_client: Callable = default_api.browse_page):
    @register_tool
    def summary_webpage(url: str) -> SummaryWebpageResult:
        """
        Делает саммаризацию страницы по ссылке: краткое содержание и вывод.

        Args:
            url: URL страницы для саммаризации.

        Returns:
            Объект SummaryWebpageResult с кратким содержанием и выводами.
        """
        print(f"Приступаю к саммаризации страницы: {url}")
        try:
            page_content_html = browser_action_client(url=url, output="html")
            if not page_content_html or not page_content_html.get('content'):
                return SummaryWebpageResult(
                    summary="Не удалось получить содержимое страницы.",
                    conclusion="Проверьте URL или доступность страницы."
                )

            h = html2text.HTML2Text()
            h.ignore_links = True
            h.ignore_images = True
            page_content_text = h.handle(page_content_html['content'])

            prompt = f"""
            Ты - эксперт по анализу и саммаризации веб-страниц.
            Твоя задача - проанализировать предоставленный текст веб-страницы, выделить ключевые идеи,
            кратко суммировать основное содержание и сделать вывод.

            ---
            Текст страницы:
            {page_content_text[:10000]} # Ограничиваем текст, чтобы не переполнять контекст
            ---

            Предоставь краткое содержание (summary) и вывод (conclusion) в формате JSON, используя поля 'summary' и 'conclusion'.
            """
            
            response = llm_client.completion(prompt, model="google/gemini-2.5-flash", temperature=0.2)
            
            # Предполагаем, что LLM возвращает чистый JSON
            summary_data = response.json() 

            return SummaryWebpageResult(
                summary=summary_data.get("summary", "Не удалось извлечь краткое содержание."),
                conclusion=summary_data.get("conclusion", "Не удалось извлечь вывод.")
            )

        except Exception as e:
            print(f"Ошибка при саммаризации страницы: {e}")
            return SummaryWebpageResult(
                summary="Произошла ошибка при обработке страницы.",
                conclusion=f"Детали ошибки: {e}"
            )

    return [summary_webpage]
