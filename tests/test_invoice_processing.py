"""
Test script to process two invoice files and write formatted results to the results directory.
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime
import sys

# Add the project root to the path so we can import from main
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.invoice_parser import InvoiceParser, ParsingResult
from src.invoice_extractor import FinalInvoice, InvoiceExtractor


async def format_and_save_results(
    file_path: str, parsing_result: ParsingResult, extraction_result: FinalInvoice
) -> None:
    """Format the results and save them to the results directory."""
    results_dir: Path = Path("tests") / "results"
    results_dir.mkdir(exist_ok=True)

    # Create a filename based on the original file name
    original_filename: str = Path(file_path).stem
    timestamp: str = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_filename: str = f"{original_filename}_result_{timestamp}"

    # Format parsing result
    parsing_data = {
        "filename": parsing_result.filename,
        "content_length": len(parsing_result.content),
        "num_pages": len(parsing_result.pages),
        "success": parsing_result.success,
        "error_message": parsing_result.error_message,
        "metadata": parsing_result.metadata,
        "content": parsing_result.content,
    }

    # Format extraction result
    extraction_data = {
        "metadata": extraction_result.metadata.model_dump()
        if extraction_result.metadata
        else {},
        "line_items_count": len(
            [item for page in extraction_result.pages for item in page.line_items]
        ),
        "pages": [page.model_dump() for page in extraction_result.pages],
        "pages_processed": extraction_result.pages_processed,
        "processing_type": extraction_result.processing_type,
    }

    # Save parsing result
    # parsing_result_path: Path = results_dir / f"{result_filename}_parsing.json"
    # with open(parsing_result_path, 'w', encoding='utf-8') as f:
    #     json.dump(parsing_data, f, indent=2, default=str)

    # # Save extraction result
    # extraction_result_path: Path = results_dir / f"{result_filename}_extraction.json"
    # with open(extraction_result_path, 'w', encoding='utf-8') as f:
    #     json.dump(extraction_data, f, indent=2, default=str)

    # Save combined result
    combined_data = {
        "file_path": file_path,
        "processing_timestamp": datetime.now().isoformat(),
        "parsing_result": parsing_data,
        "extraction_result": extraction_data,
    }

    combined_result_path: Path = results_dir / f"{result_filename}.json"
    with open(combined_result_path, "w", encoding="utf-8") as f:
        json.dump(combined_data, f, indent=2, default=str)

    print(f"Results saved for {file_path}:")
    # print(f"  - Parsing: {parsing_result_path}")
    # print(f"  - Extraction: {extraction_result_path}")
    print(f"  - Combined: {combined_result_path}")


async def main() -> None:
    """Process two invoice files and save results."""
    # Define the two invoice files to process
    invoice_files: list[Path] = [
        Path("tests") / "data" / "salesinvoice2.pdf",  # Single page invoice
        Path("tests") / "data" / "invoice-1-3.pdf",  # Multi-page invoice
    ]

    print("Starting invoice processing test...")

    for path_obj in invoice_files:
        file_path = str(path_obj)
        if not path_obj.exists():
            print(f"Warning: File not found: {file_path}")
            continue

        print(f"\nProcessing: {file_path}")

        try:
            parser: InvoiceParser = InvoiceParser(env="test")
            extractor: InvoiceExtractor = InvoiceExtractor(env="test")

            parsing_result: ParsingResult = await parser.parse_invoice(file_path)
            extraction_result: FinalInvoice = await extractor.extract(
                pages=parsing_result.pages
            )
            print(f"  Parsing successful: {parsing_result.success}")
            print(f"  Pages processed: {len(parsing_result.pages)}")
            print(
                f"  Line items extracted: {len([item for page in extraction_result.pages for item in page.line_items])}"
            )

            # Format and save results
            await format_and_save_results(file_path, parsing_result, extraction_result)

            # Small delay between processing files
            await asyncio.sleep(60)

        except Exception as e:
            print(f"  Error processing {file_path}: {str(e)}")
            continue

    print("\nInvoice processing test completed!")


if __name__ == "__main__":
    asyncio.run(main())
