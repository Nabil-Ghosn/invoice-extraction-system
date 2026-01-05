from typing import Annotated
from google.genai.types import GenerateContentResponse
from wireup import Inject, service
from google.genai import Client
from google.genai.types import GenerateContentConfig
from llama_index.core.prompts.base import PromptTemplate
from src.core.models import LineItemModel
from src.core.prompts import ANSWER_GENERATION_PROMPT


def format_context(items: list[LineItemModel]) -> str:
    context_str = "Found Line Items:\n"
    for item in items:
        context_str += (
            f"- Item: {item.description} | Cost: {item.total_amount} | "
            f"Date: {item.delivery_date} | [Inv: {item.invoice_id}, Page: {item.page_number}]\n"
        )
    return context_str


@service
class AnswerGenerator:
    MODEL_NAME = "models/gemini-2.5-flash"

    def __init__(self, api_key: Annotated[str, Inject(param="GOOGLE_API_KEY")]) -> None:
        self._client = Client(api_key=api_key)
        self._system_prompt_template = PromptTemplate(ANSWER_GENERATION_PROMPT)

    def generate_answer(
        self,
        user_query: str,
        items: list[LineItemModel],
    ) -> str:
        context: str = format_context(items)
        response: GenerateContentResponse = self._client.models.generate_content(
            model=self.MODEL_NAME,
            contents=user_query,
            config=GenerateContentConfig(
                system_instruction=self._system_prompt_template.format(context=context),
                temperature=0.85,
                top_p=0.9,
            ),
        )
        if not response.text:
            raise ValueError("No generated answer returned")

        return response.text
