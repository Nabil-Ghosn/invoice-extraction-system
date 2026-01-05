import logging
import asyncio
import sys
import json
from pathlib import Path
from typing import Annotated, Any
from beanie import init_beanie
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
import wireup
from src.core.env_settings import EnvironmentSettings
from src.ingestion.ingestion_service import IngestionService
from src.retrieval.retrieval_service import RetrievalService
import src
from src.core.models import InvoiceModel, LineItemModel


@wireup.service
def configure_logging(
    log_level: Annotated[str, wireup.Inject(param="LOG_LEVEL")],
) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python main.py <command> [options]")
        print("Commands:")
        print("  ingest <file_path1> [file_path2] ...  - Ingest invoice files.")
        print(
            "  ask <query> [--llm-generated]        - Ask a question about ingested invoices."
        )
        sys.exit(1)

    command: str = sys.argv[1]

    # Load environment variables & setup DI container
    environment_config: EnvironmentSettings = EnvironmentSettings.load()
    container: wireup.AsyncContainer = wireup.create_async_container(
        parameters=environment_config.model_dump(), service_modules=[src]
    )

    # Initialize Beanie with MongoDB
    client: AsyncMongoClient[Any] = AsyncMongoClient(environment_config.DATABASE_URI)
    database: AsyncDatabase[Any] = client[environment_config.DATABASE_NAME]
    await init_beanie(database=database, document_models=[InvoiceModel, LineItemModel])

    result: str | list[dict[str, Any]]
    if command == "ingest":
        if len(sys.argv) < 3:
            print("Usage: python main.py ingest <file_path1> [file_path2] ...")
            sys.exit(1)

        file_paths: list[str] = sys.argv[2:]
        for file_path in file_paths:
            path_obj = Path(file_path)
            if not path_obj.exists():
                print(f"Error: File not found: {file_path}")
                continue

            print(f"Processing: {file_path}")
            try:
                print("\nUsing new ingestion service:")
                ingestion_service: IngestionService = await container.get(
                    klass=IngestionService
                )
                result = await ingestion_service.ingest_invoice(file_path)
                print(f"Ingestion result: {result}")

                # Add a small delay between processing files to avoid rate limiting
                await asyncio.sleep(60)

            except Exception as e:
                print(f"Error processing {file_path}: {str(e)}")
                continue

    elif command == "ask":
        if len(sys.argv) < 3:
            print("Usage: python main.py ask <query> [--llm-generated]")
            sys.exit(1)

        user_query: str = sys.argv[2]
        is_llm_generated: bool = "--llm-generated" in sys.argv

        print(f"Query: '{user_query}'")
        if is_llm_generated:
            print("LLM-generated answer flag is set.")

        retrieval_service: RetrievalService = await container.get(
            klass=RetrievalService
        )
        result = await retrieval_service.retrieve(user_query, is_llm_generated)

        print("\n--- Retrieval Result ---")
        if isinstance(result, (list, dict)):
            print(json.dumps(result, default=str, indent=2))
        else:
            print(result)

    else:
        print(f"Unknown command: {command}")
        print("Usage: python main.py <command> [options]")
        print("Commands:")
        print("  ingest <file_path1> [file_path2] ...  - Ingest invoice files.")
        print(
            "  ask <query> [--llm-generated]        - Ask a question about ingested invoices."
        )
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
