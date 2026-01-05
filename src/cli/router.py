import asyncio
import sys
from pathlib import Path

from wireup import service
from src.cli.formatter import format_invoices, format_line_items
from src.cli.request_context import IngestionContext, RequestContext, RetrievalContext
from src.core.models import InvoiceProjection, LineItemProjection
from src.ingestion.ingestion_service import IngestionService
from src.retrieval.retrieval_service import RetrievalService


async def handle_ingest(
    ingestion_service: IngestionService, request: RequestContext
) -> None:
    if not request.ingestion:
        raise ValueError("No ingestion context provided")

    for file_path in request.ingestion.file_paths:
        path_obj = Path(file_path)
        if not path_obj.exists():
            print(f"Error: File not found: {file_path}")
            continue

        print(f"Processing: {file_path}")
        try:
            result: str = await ingestion_service.ingest_invoice(file_path)
            print(f"Ingestion result: {result}")

            # Add a small delay between processing files to avoid rate limiting
            await asyncio.sleep(60)

        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")
            continue


async def handle_ask(
    retrieval_service: RetrievalService, request: RequestContext
) -> None:
    if not request.retrieval:
        raise ValueError("No retrieval context provided")

    query: str = request.retrieval.query
    is_llm_generated: bool = request.retrieval.is_llm_generated

    print(f"Query: '{query}'")
    if is_llm_generated:
        print("LLM-generated answer flag is set.")

    result: (
        str | list[LineItemProjection] | list[InvoiceProjection]
    ) = await retrieval_service.retrieve(query, is_llm_generated)

    print("\n--- Retrieval Result ---")
    if result and isinstance(result, list):
        if result and isinstance(result[0], LineItemProjection):
            result = format_line_items(result)  # type: ignore
        elif result and isinstance(result[0], InvoiceProjection):
            result = format_invoices(result)  # type: ignore
    print(result)


def show_usage() -> None:
    print("Usage: python main.py <command> [options]")
    print("Commands:")
    print("  ingest <file_path1> [file_path2] ...  - Ingest invoice files.")
    print(
        "  ask <query> [--llm-generated]        - Ask a question about ingested invoices."
    )
    sys.exit(1)


@service
async def route_command() -> RequestContext:
    if len(sys.argv) < 2:
        show_usage()

    command: str = sys.argv[1]

    if command == "ingest":
        if len(sys.argv) < 3:
            print("Usage: python main.py ingest <file_path1> [file_path2] ...")
            sys.exit(1)
        return RequestContext(ingestion=IngestionContext(file_paths=sys.argv[2:]))
    elif command == "ask":
        args: list[str] = [arg for arg in sys.argv[2:] if arg != "--llm-generated"]
        if not args:
            print("Usage: python main.py ask <query> [--llm-generated]")
            sys.exit(1)

        user_query: str = " ".join(args)
        is_llm_generated: bool = "--llm-generated" in sys.argv
        return RequestContext(retrieval=RetrievalContext(user_query, is_llm_generated))
    else:
        print(f"Unknown command: {command}")
        show_usage()
    raise ValueError(f"Unknown command: {command}")


@service
class CliDispatcher:
    def __init__(
        self,
        request: RequestContext,
        ingestion_service: IngestionService,
        retrieval_service: RetrievalService,
    ) -> None:
        self._request: RequestContext = request
        self._ingestion: IngestionService = ingestion_service
        self._retrieval: RetrievalService = retrieval_service

    async def dispatch(self) -> None:
        if self._request.ingestion:
            await handle_ingest(self._ingestion, self._request)
            return

        if self._request.retrieval:
            await handle_ask(self._retrieval, self._request)
            return

        raise ValueError("Invalid RequestContext")
