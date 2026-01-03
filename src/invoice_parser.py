import asyncio
from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Annotated, Any

from llama_parse import LlamaParse, ResultType
from llama_index.core.schema import Document

from wireup import Inject, service

from .prompts import PARSER_INVOICE_PROMPT

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class ParsingResult:
    """Structured output for the parsing result."""

    filename: str
    content: str
    pages: list[Document]
    metadata: dict[str, Any] = field(default_factory=lambda: dict())
    success: bool = True
    error_message: str | None = None


@service
class InvoiceParser:
    CONCURRENCY_LIMIT = 5

    def __init__(
        self,
        env: Annotated[str, Inject(param="ENV")],
    ) -> None:
        self._semaphore = asyncio.Semaphore(self.CONCURRENCY_LIMIT)
        self.parser: LlamaParse = LlamaParse(
            result_type=ResultType.MD,
            system_prompt=PARSER_INVOICE_PROMPT,
            verbose=env == "development",
            language="en",
        )

    async def parse_invoice(
        self,
        file_path: str,
    ) -> ParsingResult:
        path_obj = Path(file_path)

        if not path_obj.exists():
            logger.error(f"File not found: {file_path}")
            return ParsingResult(
                filename=path_obj.name,
                content="",
                pages=[],
                success=False,
                error_message="File not found",
            )

        logger.info(f"Starting parse for: {path_obj.name}")

        try:
            documents: list[Document] = await self.parser.aload_data(
                file_path=file_path
            )  # TODO: batched asynchronous loading by splitting large files to pages

            if not documents:
                logger.warning(f"No content extracted from {file_path}")
                return ParsingResult(filename=path_obj.name, content="", pages=[])

            full_content: str = "\n\n".join([doc.text for doc in documents])
            metadata: dict[str, Any] = documents[0].metadata if documents else {}

            logger.info(
                f"Successfully parsed {path_obj.name}. Total chars: {len(full_content)}"
            )

            return ParsingResult(
                filename=path_obj.name,
                content=full_content,
                pages=documents,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(
                f"Failed to parse document {file_path}: {str(e)}", exc_info=True
            )
            return ParsingResult(
                filename=path_obj.name,
                content="",
                pages=[],
                success=False,
                error_message=str(e),
            )

    async def parse_invoices_batch(self, file_paths: list[str]) -> list[ParsingResult]:
        """
        Parses multiple invoices concurrently with a semaphore limit.
        """

        async def _bounded_parse(path: str) -> ParsingResult:
            async with self._semaphore:
                return await self.parse_invoice(path)

        results: list[ParsingResult] = await asyncio.gather(
            *[_bounded_parse(p) for p in file_paths]
        )
        return list(results)
