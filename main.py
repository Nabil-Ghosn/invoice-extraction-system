import logging
import asyncio
import sys
from pathlib import Path
from typing import Annotated
import wireup
from src.env_settings import EnvironmentSettings
from src.invoice_extractor import FinalInvoice, InvoiceExtractor
from src.invoice_parser import InvoiceParser, ParsingResult
import src


@wireup.service
def configure_logging(
    log_level: Annotated[str, wireup.Inject(param="LOG_LEVEL")],
) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def process_invoice_file(file_path: str) -> tuple[ParsingResult, FinalInvoice]:
    """Process a single invoice file and return both parsing and extraction results."""
    container: wireup.AsyncContainer = wireup.create_async_container(
        parameters=EnvironmentSettings.load().model_dump(), service_modules=[src]
    )
    parser: InvoiceParser = await container.get(klass=InvoiceParser)
    extractor: InvoiceExtractor = await container.get(klass=InvoiceExtractor)

    parsing_result: ParsingResult = await parser.parse_invoice(file_path)
    extraction_result: FinalInvoice = await extractor.extract(
        pages=parsing_result.pages
    )

    return parsing_result, extraction_result


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python main.py <invoice_file_path1> [invoice_file_path2] ...")
        sys.exit(1)

    file_paths: list[str] = sys.argv[
        1:
    ]  # Get all file paths from command line arguments

    for file_path in file_paths:
        path_obj = Path(file_path)
        if not path_obj.exists():
            print(f"Error: File not found: {file_path}")
            continue

        print(f"Processing: {file_path}")
        try:
            parsing_result, extraction_result = await process_invoice_file(file_path)
            print(f"Parsing result: {parsing_result}")
            print(f"Extraction result: {extraction_result}")

            # Add a small delay between processing files to avoid rate limiting
            await asyncio.sleep(60)

        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")
            continue


if __name__ == "__main__":
    asyncio.run(main())
