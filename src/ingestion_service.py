from datetime import datetime, date
import time
from pathlib import Path
from wireup import service

from src.invoice_extractor import InvoiceExtractor, FinalInvoice
from src.invoice_parser import InvoiceParser, ParsingResult
from src.embedder import IEmbedder
from src.command_invoice_repository import CommandInvoiceRepository
from src.models import InvoiceModel, LineItemModel, ProcessingStatus
from src.utils import calculate_file_hash


@service
class IngestionService:
    def __init__(
        self,
        parser: InvoiceParser,
        extractor: InvoiceExtractor,
        embedder: IEmbedder,
        repository: CommandInvoiceRepository,
    ) -> None:
        self._parser: InvoiceParser = parser
        self._extractor: InvoiceExtractor = extractor
        self._embedder: IEmbedder = embedder
        self._repository: CommandInvoiceRepository = repository

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
