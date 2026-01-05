import logging
import re
from typing import Annotated, Any

from pydantic import BaseModel
from wireup import Inject, service

from llama_index.llms.google_genai import GoogleGenAI
from llama_index.core.schema import Document
from llama_index.core.program import LLMTextCompletionProgram
from llama_index.core.output_parsers.pydantic import PydanticOutputParser
from llama_index.core.prompts.base import PromptTemplate

from .extracted_schemas import (
    InvoicePage,
    InvoiceSinglePage,
    PageState,
    InvoiceContext,
    LineItem,
)
from src.core.prompts import MULTI_PAGE_PROMPT_TEMPLATE, SINGLE_PAGE_PROMPT_TEMPLATE

logger: logging.Logger = logging.getLogger(__name__)


class ExtractedPage(BaseModel):
    """Represents a single page of an invoice with its extracted line items."""

    page_number: int
    line_items: list[LineItem]


class FinalInvoice(BaseModel):
    metadata: InvoiceContext
    pages: list[ExtractedPage]  # Changed from flat list to page-level breakdown
    pages_processed: int
    processing_type: str  # "single_shot" or "sequential_chain"


@service
class InvoiceExtractor:
    MODEL_NAME = "gemini-2.5-flash"

    def __init__(
        self,
        env: Annotated[str, Inject(param="ENV")],
    ) -> None:
        self.llm = GoogleGenAI(
            model=self.MODEL_NAME,
            temperature=0.0,
            max_retries=3,
        )

        self.multi_page_program: LLMTextCompletionProgram[InvoicePage] = (
            LLMTextCompletionProgram(
                output_parser=PydanticOutputParser(output_cls=InvoicePage),
                output_cls=InvoicePage,
                prompt=PromptTemplate(MULTI_PAGE_PROMPT_TEMPLATE),
                llm=self.llm,
                verbose=env == "development",
            )
        )

        self.single_page_program: LLMTextCompletionProgram[InvoiceSinglePage] = (
            LLMTextCompletionProgram(
                output_parser=PydanticOutputParser(output_cls=InvoiceSinglePage),
                output_cls=InvoiceSinglePage,
                prompt=PromptTemplate(SINGLE_PAGE_PROMPT_TEMPLATE),
                llm=self.llm,
                verbose=env == "development",
            )
        )

    async def extract(self, pages: list[Document]) -> FinalInvoice:
        """
        Router method: Decides whether to use Single-Shot or Sequential-Chain strategy.
        """
        if not pages:
            raise ValueError("No pages provided for extraction.")

        if len(pages) == 1:
            return await self._process_single_page(pages[0])
        else:
            return await self._process_multi_page_chain(pages)

    async def _process_single_page(self, page: Document) -> FinalInvoice:
        """
        Optimized path for 1-page documents.
        """
        logger.info("Detected single-page invoice. Using Single-Shot strategy.")

        clean_text: str = self._clean_text(page.text)

        try:
            result: InvoiceSinglePage = await self.single_page_program.acall(
                page_text=clean_text
            )

            context: InvoiceContext = result.invoice_context

            # Create a single page with its line items
            extracted_page = ExtractedPage(page_number=1, line_items=result.line_items)

            return FinalInvoice(
                metadata=context,
                pages=[extracted_page],
                pages_processed=1,
                processing_type="single_shot",
            )
        except Exception as e:
            logger.error(f"Single page extraction failed: {e}", exc_info=True)
            raise

    async def _process_multi_page_chain(self, pages: list[Document]) -> FinalInvoice:
        """
        Sequential Rolling Context path for 2+ pages.
        """
        logger.info(f"Detected {len(pages)} pages. Using Sequential Chain strategy.")

        extracted_pages: list[ExtractedPage] = []
        aggregated_context = InvoiceContext()  # type: ignore

        # Initial State: "Start"
        current_state = PageState(
            table_status="no_table", active_columns=[], active_section_title="Start"
        )

        for i, page in enumerate(pages):
            page_num: int = i + 1

            try:
                clean_text: str = self._clean_text(page.text)

                # Pass previous state as a strict JSON string
                state_json: str = current_state.model_dump_json()

                result: InvoicePage = await self.multi_page_program.acall(
                    current_page_num=page_num,
                    previous_state=state_json,
                    page_text=clean_text,
                )

                # Create extracted page with its line items
                extracted_page = ExtractedPage(
                    page_number=page_num, line_items=result.line_items
                )
                extracted_pages.append(extracted_page)

                # Merge Context (Update nulls with new values)
                if result.invoice_context:
                    self._merge_context(aggregated_context, result.invoice_context)

                # Update State for next loop
                current_state: PageState = result.next_page_state

            except Exception as e:
                logger.error(f"Chain broke at Page {page_num}: {e}", exc_info=True)
                logger.info(
                    f"Bridging state from Page {page_num - 1} to Page {page_num + 1}"
                )

        return FinalInvoice(
            metadata=aggregated_context,
            pages=extracted_pages,
            pages_processed=len(pages),
            processing_type="sequential_chain",
        )

    def _merge_context(self, target: InvoiceContext, source: InvoiceContext):
        """Merges source into target if target fields are empty."""
        data: dict[str, Any] = source.model_dump(exclude_unset=True)
        for key, value in data.items():
            if value is not None and getattr(target, key) is None:
                setattr(target, key, value)

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
