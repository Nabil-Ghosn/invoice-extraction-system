from dataclasses import dataclass


@dataclass
class IngestionContext:
    file_paths: list[str]


@dataclass
class RetrievalContext:
    query: str
    is_llm_generated: bool


@dataclass
class RequestContext:
    ingestion: IngestionContext | None = None
    retrieval: RetrievalContext | None = None
