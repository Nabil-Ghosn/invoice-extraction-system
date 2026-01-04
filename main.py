import logging
import asyncio
import sys
from pathlib import Path
from typing import Annotated, Any
from beanie import init_beanie
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
import wireup
from src.env_settings import EnvironmentSettings
from src.ingestion_service import IngestionService
import src
from src.models import InvoiceModel, LineItemModel


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
        print("Usage: python main.py <invoice_file_path1> [invoice_file_path2] ...")
        sys.exit(1)

    file_paths: list[str] = sys.argv[
        1:
    ]  # Get all file paths from command line arguments

    # Load environment variables & setup DI container
    environment_config: EnvironmentSettings = EnvironmentSettings.load()
    container: wireup.AsyncContainer = wireup.create_async_container(
        parameters=environment_config.model_dump(), service_modules=[src]
    )

    # Initialize Beanie with MongoDB
    client: AsyncMongoClient[Any] = AsyncMongoClient(environment_config.DATABASE_URI)
    database: AsyncDatabase[Any] = client[environment_config.DATABASE_NAME]
    await init_beanie(database=database, document_models=[InvoiceModel, LineItemModel])

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
            result: str = await ingestion_service.ingest_invoice(file_path)
            print(f"Ingestion result: {result}")

            # Add a small delay between processing files to avoid rate limiting
            await asyncio.sleep(60)

        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")
            continue


if __name__ == "__main__":
    asyncio.run(main())
