import logging
import re
from datetime import datetime, date
from typing import Protocol, Any

from beanie import PydanticObjectId
from wireup import abstract, service

from src.retrieval.exceptions import DatabaseQueryError, InvalidDateFormatError
from src.core.models import (
    InvoiceModel,
    LineItemModel,
    InvoiceProjection,
    LineItemProjection,
    IdProjection,
)
from src.retrieval.tools import SearchLineItemsTool, SearchInvoicesTool


@abstract
class IQueryInvoiceRepository(Protocol):
    """
    Interface for querying invoice data.
    Input: Domain-level Search Criteria.
    Output: Domain-level Projections.
    """

    async def search_line_items(
        self,
        criteria: SearchLineItemsTool,
        embedding: list[float] | None,
    ) -> list[LineItemProjection]:
        """
        Executes a hybrid search (Vector + Metadata) for line items.
        """
        ...

    async def search_invoices(
        self,
        criteria: SearchInvoicesTool,
    ) -> list[InvoiceProjection]:
        """
        Executes a structured metadata search for invoices.
        """
        ...


@service
class BeanieQueryInvoiceRepository(IQueryInvoiceRepository):
    """
    MongoDB/Beanie implementation of the Repository.
    Encapsulates all Aggregation Pipeline logic with proper error handling.
    """

    def __init__(self) -> None:
        pass

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def search_line_items(
        self,
        criteria: SearchLineItemsTool,
        embedding: list[float] | None,
    ) -> list[LineItemProjection]:
        try:
            # 1. Resolve Invoice Context (Pre-Filter Strategy)
            invoice_ids_filter: (
                list[PydanticObjectId] | None
            ) = await self._resolve_invoice_ids(criteria)

            # 2. Early exit if context filter matched nothing
            if invoice_ids_filter is not None and len(invoice_ids_filter) == 0:
                return []

            # 3. Build and Execute Pipeline
            pipeline: list[dict[str, Any]] = self._build_line_item_pipeline(
                criteria, embedding, invoice_ids_filter
            )
            logging.info(f"Search Line Item MongoDB Query: {pipeline}")

            results: list[LineItemProjection] = await LineItemModel.aggregate(
                pipeline,
                projection_model=LineItemProjection,
            ).to_list(length=None)

            return results

        except InvalidDateFormatError as e:
            raise e  # Bubble up validation errors
        except Exception as e:
            # Wrap DB internals in a domain exception
            raise DatabaseQueryError(
                f"Failed to execute line items search: {str(e)}"
            ) from e

    async def search_invoices(
        self,
        criteria: SearchInvoicesTool,
    ) -> list[InvoiceProjection]:
        try:
            pipeline: list[dict[str, Any]] = self._build_invoice_pipeline(criteria)
            logging.info(f"Search Invoice MongoDB Query: {pipeline}")

            results: list[InvoiceProjection] = await InvoiceModel.aggregate(
                pipeline,
                projection_model=InvoiceProjection,
            ).to_list(length=None)

            return results

        except InvalidDateFormatError:
            raise
        except Exception as e:
            raise DatabaseQueryError(
                f"Failed to execute invoice search: {str(e)}"
            ) from e

    # -------------------------------------------------------------------------
    # Private Helpers - Context Resolution
    # -------------------------------------------------------------------------

    async def _resolve_invoice_ids(
        self,
        criteria: SearchLineItemsTool,
    ) -> list[PydanticObjectId] | None:
        """
        Helper to find Invoice ObjectIds based on metadata filters.
        Returns None if no invoice-level filters are applied.
        """
        # We reuse the invoice filter builder, but map Tool fields to it
        filters: dict[str, Any] = self._build_invoice_match_conditions(
            invoice_number=criteria.invoice_number,
            sender_name=criteria.sender_name,
            date_start=criteria.invoice_date_start,
            date_end=criteria.invoice_date_end,
        )

        if not filters:
            return None

        try:
            # Optimization: Only fetch _id field
            invoices: list[IdProjection] = (
                await InvoiceModel.find(filters).project(IdProjection).to_list()
            )
            return [i.id for i in invoices if i.id]
        except Exception as e:
            raise DatabaseQueryError(f"Failed to resolve invoice context: {str(e)}")

    # -------------------------------------------------------------------------
    # Private Helpers - Pipeline Construction
    # -------------------------------------------------------------------------

    def _build_line_item_pipeline(
        self,
        criteria: SearchLineItemsTool,
        embedding: list[float] | None,
        invoice_ids_filter: list[PydanticObjectId] | None,
    ) -> list[dict[str, Any]]:
        match_conditions: dict[str, Any] = self._build_line_item_match_conditions(
            criteria, invoice_ids_filter
        )
        pipeline: list[dict[str, Any]] = []

        if embedding and criteria.query_text:
            # --- Path A: Semantic Vector Search ---
            pipeline.append(
                {
                    "$vectorSearch": {
                        "index": "vector_index",
                        "path": "vector",
                        "queryVector": embedding,
                        # Dynamic candidates: wider net for better accuracy
                        "numCandidates": max(100, criteria.limit * 10),
                        "limit": criteria.limit,
                        # CRITICAL: Filter applied INSIDE vector search
                        "filter": match_conditions,
                    }
                }
            )
        else:
            # --- Path B: Structured / Keyword Search ---
            if match_conditions:
                pipeline.append({"$match": match_conditions})

            pipeline.append({"$sort": {"invoice_id": 1, "page_number": 1}})
            pipeline.append({"$limit": criteria.limit})

        # Hydrate Results (Join with Invoices)
        pipeline.append(
            {
                "$lookup": {
                    "from": "invoices",
                    "localField": "invoice_id",
                    "foreignField": "_id",
                    "as": "invoice_info",
                }
            }
        )

        # Final Projection
        pipeline.append(
            self._build_line_item_projection(use_vector_score=bool(embedding))
        )

        return pipeline

    def _build_invoice_pipeline(
        self, criteria: SearchInvoicesTool
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = self._build_invoice_match_conditions(
            invoice_number=criteria.invoice_number,
            sender_name=criteria.sender_name,
            filename_query=criteria.filename_query,
            status=criteria.status,
            date_start=criteria.start_date,
            date_end=criteria.end_date,
        )

        pipeline: list[dict[str, Any]] = []
        if filters:
            pipeline.append({"$match": filters})

        pipeline.append({"$sort": {"invoice_date": -1}})
        pipeline.append({"$limit": 50})

        return pipeline

    # -------------------------------------------------------------------------
    # Private Helpers - Condition Builders
    # -------------------------------------------------------------------------

    def _build_line_item_match_conditions(
        self,
        criteria: SearchLineItemsTool,
        invoice_ids_filter: list[PydanticObjectId] | None,
    ) -> dict[str, Any]:
        match_conditions: dict[str, Any] = {}

        # 1. Apply Resolved Invoice IDs
        if invoice_ids_filter is not None:
            match_conditions["invoice_id"] = {"$in": invoice_ids_filter}

        # 2. Page Filters
        if criteria.page_number is not None:
            match_conditions["page_number"] = criteria.page_number
        elif criteria.min_page is not None or criteria.max_page is not None:
            page_filter = {}
            if criteria.min_page is not None:
                page_filter["$gte"] = criteria.min_page
            if criteria.max_page is not None:
                page_filter["$lte"] = criteria.max_page
            match_conditions["page_number"] = page_filter

        # 3. Amount Filters
        amount_filter = self._build_range_filter(
            criteria.min_amount, criteria.max_amount
        )
        if amount_filter:
            match_conditions["total_amount"] = amount_filter

        return match_conditions

    def _build_invoice_match_conditions(
        self,
        invoice_number: str | None = None,
        sender_name: str | None = None,
        filename_query: str | None = None,
        status: str | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
    ) -> dict[str, Any]:
        filters: dict[str, Any] = {}

        if invoice_number:
            filters["invoice_number"] = invoice_number

        if status:
            filters["status"] = status

        if sender_name:
            filters["sender_name"] = {"$regex": re.escape(sender_name), "$options": "i"}

        if filename_query:
            filters["filename"] = {"$regex": re.escape(filename_query), "$options": "i"}

        # Date Filters
        date_filter = {}
        if date_start:
            date_filter["$gte"] = self._parse_date_str(date_start, "date_start")
        if date_end:
            date_filter["$lte"] = self._parse_date_str(date_end, "date_end")

        if date_filter:
            filters["invoice_date"] = date_filter

        return filters

    def _build_line_item_projection(self, use_vector_score: bool) -> dict[str, Any]:
        return {
            "$project": {
                "_id": 0,
                "score": {"$meta": "vectorSearchScore"}
                if use_vector_score
                else {"$literal": 1.0},
                "invoice_id": 1,
                "page_number": 1,
                "description": 1,
                "quantity": 1,
                "quantity_unit": 1,
                "unit_price": 1,
                "total_amount": 1,
                "delivery_date": 1,
                "section": 1,
                "item_code": 1,
                # Flatten joined fields
                "invoice_number": {"$arrayElemAt": ["$invoice_info.invoice_number", 0]},
                "sender_name": {"$arrayElemAt": ["$invoice_info.sender_name", 0]},
                "invoice_date": {"$arrayElemAt": ["$invoice_info.invoice_date", 0]},
            }
        }

    def _build_range_filter(
        self, min_val: float | None, max_val: float | None
    ) -> dict[str, float] | None:
        if min_val is None and max_val is None:
            return None
        f = {}
        if min_val is not None:
            f["$gte"] = min_val
        if max_val is not None:
            f["$lte"] = max_val
        return f

    def _parse_date_str(self, date_str: str, field_name: str) -> date:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError as e:
            raise InvalidDateFormatError(date_str, field_name) from e
