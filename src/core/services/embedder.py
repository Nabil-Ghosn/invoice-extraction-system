from typing import Annotated, Literal, Protocol, override
from google.genai.types import EmbedContentResponse
from wireup import Inject, abstract, service
from google.genai import Client
from google.genai.types import EmbedContentConfig


@abstract
class IEmbedder(Protocol):
    def embed_text(
        self,
        text: str,
        task_type: Literal["passage", "query"] = "query",
    ) -> list[float]: ...


@service
class GeminiEmbedder(IEmbedder):
    MODEL_NAME = "models/gemini-embedding-001"
    VECTROR_SIZE = 768

    def __init__(self, api_key: Annotated[str, Inject(param="GOOGLE_API_KEY")]) -> None:
        self._client = Client(api_key=api_key)

    @override
    def embed_text(
        self,
        text: str,
        task_type: Literal["passage", "query"] = "query",
    ) -> list[float]:
        if task_type == "passage":
            task = "retrieval_document"
        elif task_type == "query":
            task = "retrieval_query"
        else:
            raise ValueError(f"Unsupported task_type: {task_type}")

        response: EmbedContentResponse = self._client.models.embed_content(
            model=self.MODEL_NAME,
            contents=[text],
            config=EmbedContentConfig(
                output_dimensionality=self.VECTROR_SIZE,
                task_type=task,
            ),
        )
        if not response.embeddings or not response.embeddings[0].values:
            raise ValueError("No embeddings returned")

        return response.embeddings[0].values
