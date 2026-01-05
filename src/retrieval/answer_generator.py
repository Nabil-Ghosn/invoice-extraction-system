from typing import Annotated
from google.genai.types import GenerateContentResponse
from wireup import Inject, service
from google.genai import Client
from google.genai.types import GenerateContentConfig
from llama_index.core.prompts.base import PromptTemplate
from src.core.prompts import ANSWER_GENERATION_PROMPT


@service
class AnswerGenerator:
    MODEL_NAME = "models/gemini-2.5-flash"

    def __init__(self, api_key: Annotated[str, Inject(param="GOOGLE_API_KEY")]) -> None:
        self._client = Client(api_key=api_key)
        self._system_prompt_template = PromptTemplate(ANSWER_GENERATION_PROMPT)

    def generate_answer(
        self,
        user_query: str,
        context: str,
    ) -> str:
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
