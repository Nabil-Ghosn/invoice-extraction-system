from datetime import datetime, date
import time
from pathlib import Path
from wireup import service

from src.ingestion.invoice_extractor import InvoiceExtractor, FinalInvoice
from src.ingestion.invoice_parser import InvoiceParser, ParsingResult
from src.core.services.embedder import IEmbedder
from src.ingestion.command_invoice_repository import ICommandInvoiceRepository
from src.core.models import InvoiceModel, LineItemModel, ProcessingStatus
from src.core.utils import calculate_file_hash


@service
class IngestionService:
    def __init__(
        self,
        parser: InvoiceParser,
        extractor: InvoiceExtractor,
        embedder: IEmbedder,
        repository: ICommandInvoiceRepository,
    ) -> None:
        self._parser: InvoiceParser = parser
        self._extractor: InvoiceExtractor = extractor
        self._embedder: IEmbedder = embedder
        self._repository: ICommandInvoiceRepository = repository

    async def ingest_invoice(self, file_path: str) -> str:
        """
        Main ingestion method that follows the sequence diagram:
        1. Deduplication Check
        2. Parsing
        3. Extraction
        4. Data Transformation & Embedding
        5. Storage
        """
        start_time: float = time.time()

        path_obj = Path(file_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_hash: str = calculate_file_hash(file_path)
        existing_invoice: InvoiceModel | None = await self._repository.get_by_hash(
            file_hash
        )

        if existing_invoice:
            return f"SKIP: Invoice already exists with ID {existing_invoice.id}"

        parsing_result: ParsingResult = await self._parser.parse_invoice(file_path)

        extraction_result: FinalInvoice = await self._extractor.extract(
            pages=parsing_result.pages
        )
        self.__save_results_for_testing(file_path, parsing_result, extraction_result)

        # Calculate processing time so far (before embedding)
        processing_time: float = time.time() - start_time

        invoice_model = InvoiceModel(
            filename=path_obj.name,
            file_hash=file_hash,
            status=ProcessingStatus.COMPLETED,
            total_pages=extraction_result.pages_processed,
            processing_time_seconds=processing_time,
            invoice_number=extraction_result.metadata.invoice_number,
            invoice_date=self._parse_invoice_date(
                extraction_result.metadata.invoice_date
            ),
            sender_name=extraction_result.metadata.sender_name,
            receiver_name=extraction_result.metadata.receiver_name,
            currency=extraction_result.metadata.currency or "USD",
            total_amount=extraction_result.metadata.total_amount,
        )

        saved_invoice: InvoiceModel = await self._repository.save_invoice(invoice_model)
        if not saved_invoice.id:
            return f"ERROR: Failed to save invoice with ID {saved_invoice.id}"

        line_item_models: list[LineItemModel] = []
        for extracted_page in extraction_result.pages:
            for line_item in extracted_page.line_items:
                search_text: str = self._build_search_text(
                    sender_name=extraction_result.metadata.sender_name,
                    section=line_item.section,
                    description=line_item.description,
                    item_code=line_item.item_code,
                )
                vector: list[float] = self._embedder.embed_text(search_text)
                line_item_model = LineItemModel(
                    invoice_id=saved_invoice.id,
                    page_number=extracted_page.page_number,
                    description=line_item.description,
                    quantity=line_item.quantity,
                    unit_price=line_item.unit_price,
                    total_amount=line_item.line_total_amount,
                    section=line_item.section,
                    item_code=line_item.item_code,
                    delivery_date=line_item.delivery_date,
                    quantity_unit=line_item.quantity_unit,
                    search_text=search_text,
                    vector=vector,
                )
                line_item_models.append(line_item_model)
        await self._repository.save_line_items(line_item_models)

        total_processing_time: float = time.time() - start_time
        saved_invoice.processing_time_seconds = total_processing_time
        await saved_invoice.save()

        return f"SUCCESS: Invoice processed and saved with {len(line_item_models)} line items"

    def _build_search_text(
        self,
        sender_name: str | None,
        section: str,
        description: str,
        item_code: str | None,
    ) -> str:
        parts: list[str] = []
        if sender_name:
            parts.append(f"Context: {sender_name}")

        if section and section.lower() not in ["general", "default", "undefined"]:
            parts.append(f"({section})")

        prefix: str = " ".join(parts)
        text: str = f"{prefix} | Item: {description}"

        if item_code:
            text += f" ({item_code})"

        return text

    def _parse_invoice_date(self, date_str: str | None) -> date | None:
        if not date_str:
            return None

        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None

    def __save_results_for_testing(
        self,
        file_path: str,
        parsing_result: ParsingResult,
        extraction_result: FinalInvoice,
    ) -> None:
        """Format the results and save them to the results directory."""
        import json
        import pickle

        results_dir: Path = Path("tests") / "results"
        results_dir.mkdir(exist_ok=True)

        # Create a filename based on the original file name
        original_filename: str = Path(file_path).stem
        timestamp: str = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_filename: str = f"{original_filename}_result_{timestamp}"

        # Save human-readable JSON version
        json_data = {
            "file_path": file_path,
            "processing_timestamp": datetime.now().isoformat(),
            "parsing_result": {
                "filename": parsing_result.filename,
                "content": parsing_result.content,
                "metadata": parsing_result.metadata,
                "success": parsing_result.success,
                "error_message": parsing_result.error_message,
                # Convert Document objects to a more readable format for JSON
                "pages": [
                    {"text": page.text, "metadata": page.metadata}
                    for page in parsing_result.pages
                ],
            },
            "extraction_result": extraction_result.model_dump(),
        }

        json_result_path: Path = results_dir / f"{result_filename}.json"
        with open(json_result_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, default=str)

        # Save pickle version for easy loading
        pickle_data = {
            "file_path": file_path,
            "processing_timestamp": datetime.now().isoformat(),
            "parsing_result": parsing_result,
            "extraction_result": extraction_result,
        }

        pickle_result_path: Path = results_dir / f"{result_filename}.pkl"
        with open(pickle_result_path, "wb") as f:
            pickle.dump(pickle_data, f)

        print(f"Results saved for {file_path}:")
        print(f"  - JSON (human-readable): {json_result_path}")
        print(f"  - Pickle (for loading): {pickle_result_path}")

    def __load_results_for_testing(
        self, file_path: str
    ) -> tuple[ParsingResult, FinalInvoice]:
        """Load the last results for the file path."""
        import pickle

        results_dir: Path = Path("tests") / "results"
        if not results_dir.exists():
            raise FileNotFoundError(f"Results directory does not exist: {results_dir}")

        original_filename: str = Path(file_path).stem

        # Find all pickle result files for this original file
        matching_files: list[Path] = [
            f
            for f in results_dir.iterdir()
            if f.is_file()
            and f.suffix == ".pkl"
            and f.name.startswith(f"{original_filename}_result_")
        ]

        if not matching_files:
            raise FileNotFoundError(f"No saved results found for {file_path}")

        # Sort by modification time to get the most recent one
        latest_file: Path = max(matching_files, key=lambda f: f.stat().st_mtime)

        # Load the results from pickle
        with open(latest_file, "rb") as f:
            data = pickle.load(f)

        parsing_result: ParsingResult = data["parsing_result"]
        extraction_result: FinalInvoice = data["extraction_result"]

        return parsing_result, extraction_result
