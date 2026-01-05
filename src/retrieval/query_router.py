from datetime import date
from typing import Annotated
from wireup import Inject, service
from google.genai import Client
from google.genai.types import (
    GenerateContentConfig,
    GenerateContentResponse,
    FunctionCallingConfig,
    FunctionCallingConfigMode,
    ToolConfig,
    Tool,
    FunctionDeclaration,
    Schema,
)
from llama_index.core.prompts.base import PromptTemplate
from src.retrieval.tools import SearchLineItemsTool, SearchInvoicesTool
from src.core.prompts import QUERY_ROUTER_PROMPT


@service
class QueryRouter:
    MODEL_NAME = "models/gemini-2.5-flash"

    def __init__(self, api_key: Annotated[str, Inject(param="GOOGLE_API_KEY")]) -> None:
        self._client = Client(api_key=api_key)
        self._system_prompt_template = PromptTemplate(QUERY_ROUTER_PROMPT)

    def route(
        self,
        user_query: str,
    ) -> str | SearchLineItemsTool | SearchInvoicesTool:
        response: GenerateContentResponse = self._client.models.generate_content(
            model=self.MODEL_NAME,
            contents=user_query,
            config=GenerateContentConfig(
                candidate_count=1,
                system_instruction=self._system_prompt_template.format(
                    current_date=date.today().isoformat()
                ),
                tools=[
                    Tool(
                        function_declarations=[
                            FunctionDeclaration(
                                name=SearchLineItemsTool.__name__,
                                description=SearchLineItemsTool.__doc__,
                                parameters=Schema(
                                    **SearchLineItemsTool.model_json_schema()
                                ),
                            )
                        ]
                    ),
                    Tool(
                        function_declarations=[
                            FunctionDeclaration(
                                name="SearchInvoicesTool",
                                description=SearchInvoicesTool.__doc__,
                                parameters=Schema(
                                    **SearchInvoicesTool.model_json_schema()
                                ),
                            )
                        ]
                    ),
                ],
                temperature=0.2,
                top_p=0.8,
                tool_config=ToolConfig(
                    function_calling_config=FunctionCallingConfig(
                        mode=FunctionCallingConfigMode.AUTO
                    )
                ),
            ),
        )
        if (
            not response.candidates
            or not response.candidates[0].content
            or not response.candidates[0].content.parts
        ):
            raise ValueError("No generated answer returned")
        if text := response.candidates[0].content.parts[0].text:
            return text
        if function_call := response.candidates[0].content.parts[0].function_call:
            if function_call.name == SearchLineItemsTool.__name__:
                return SearchLineItemsTool(**function_call.args)  # type: ignore
            if function_call.name == SearchInvoicesTool.__name__:
                return SearchInvoicesTool(**function_call.args)  # type: ignore

        raise ValueError("No generated answer returned")
