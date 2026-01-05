import re
from datetime import datetime
from typing import Any

from beanie import Document, PydanticObjectId
from wireup import service
from src.retrieval.tools import SearchLineItemsTool, SearchInvoicesTool
from src.core.models import InvoiceModel


@service
class QueryTranslator:
    async def generate_line_item_pipeline(
        self, criteria: SearchLineItemsTool, embedding: list[float] | None
    ) -> list[dict[str, Any]]:
        """
        Generates a MongoDB Aggregation Pipeline for LINE ITEM retrieval.
        """

        # 1. Resolve Invoice Context (Pre-computation)
        # We must find the ObjectIds for filters like 'invoice_number', 'sender_name', 'date'.
        invoice_ids_filter = await self._resolve_invoice_ids(criteria)

        # 2. Build the Match/Filter Dictionary
        match_conditions = {}

        # Context Filter (Resolved IDs)
        if invoice_ids_filter is not None:
            if not invoice_ids_filter:
                # Optimized empty return if metadata filter yielded no invoices
                return [{"$match": {"_id": {"$exists": False}}}]
            match_conditions["invoice_id"] = {"$in": invoice_ids_filter}

        # Page Filters
        if criteria.page_number is not None:
            match_conditions["page_number"] = criteria.page_number
        elif criteria.min_page is not None or criteria.max_page is not None:
            match_conditions["page_number"] = {}
            if criteria.min_page is not None:
                match_conditions["page_number"]["$gte"] = criteria.min_page
            if criteria.max_page is not None:
                match_conditions["page_number"]["$lte"] = criteria.max_page

        # Amount Filters
        if criteria.min_amount is not None or criteria.max_amount is not None:
            match_conditions["total_amount"] = {}
            if criteria.min_amount is not None:
                match_conditions["total_amount"]["$gte"] = criteria.min_amount
            if criteria.max_amount is not None:
                match_conditions["total_amount"]["$lte"] = criteria.max_amount

        # 3. Construct Pipeline
        pipeline = []

        if embedding and criteria.query_text:
            # --- Path A: Semantic Vector Search ---
            pipeline.append(
                {
                    "$vectorSearch": {
                        "index": "vector_index",
                        "path": "vector",
                        "queryVector": embedding,
                        # Dynamic candidate sizing for better accuracy/performance balance
                        "numCandidates": max(100, criteria.limit * 10),
                        "limit": criteria.limit,
                        "filter": match_conditions,
                    }
                }
            )
        else:
            # --- Path B: Structured / Keyword Search ---
            if match_conditions:
                pipeline.append({"$match": match_conditions})

            # Sort by reliability/page order if no semantic score exists
            pipeline.append({"$sort": {"invoice_id": 1, "page_number": 1}})
            pipeline.append({"$limit": criteria.limit})

        # 4. Hydrate Results (Join with Invoices)
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

        # 5. Project / Formatting
        pipeline.append(
            {
                "$project": {
                    "_id": 0,
                    # If vector search wasn't used, provide a dummy score
                    "score": {"$meta": "vectorSearchScore"}
                    if embedding
                    else {"$literal": 1.0},
                    "description": 1,
                    "quantity": 1,
                    "unit_price": 1,
                    "total_amount": 1,
                    "page_number": 1,
                    "delivery_date": 1,
                    "section": 1,
                    "item_code": 1,
                    # Flatten invoice info
                    "invoice_number": {
                        "$arrayElemAt": ["$invoice_info.invoice_number", 0]
                    },
                    "sender_name": {"$arrayElemAt": ["$invoice_info.sender_name", 0]},
                    "invoice_date": {"$arrayElemAt": ["$invoice_info.invoice_date", 0]},
                }
            }
        )

        return pipeline

    def generate_invoice_pipeline(
        self, criteria: SearchInvoicesTool
    ) -> list[dict[str, Any]]:
        """
        Generates a MongoDB Aggregation Pipeline for HIGH-LEVEL INVOICE retrieval.
        Note: This does not use vector search, as the tool is purely structured.
        """
        match_conditions = {}

        # 1. Exact Match Filters
        if criteria.invoice_number:
            match_conditions["invoice_number"] = criteria.invoice_number

        if criteria.status:
            # Match Enum value
            match_conditions["status"] = criteria.status

        # 2. Fuzzy / Regex Filters
        if criteria.sender_name:
            match_conditions["sender_name"] = {
                "$regex": re.escape(criteria.sender_name),
                "$options": "i",
            }

        if criteria.filename_query:
            match_conditions["filename"] = {
                "$regex": re.escape(criteria.filename_query),
                "$options": "i",
            }

        # 3. Date Filters
        # Applies to invoice_date (business date) as primary context
        if criteria.start_date or criteria.end_date:
            date_filter = {}
            if criteria.start_date:
                date_filter["$gte"] = self._parse_date_str(criteria.start_date)
            if criteria.end_date:
                date_filter["$lte"] = self._parse_date_str(criteria.end_date)

            if date_filter:
                match_conditions["invoice_date"] = date_filter

        # 4. Construct Pipeline
        pipeline = []

        if match_conditions:
            pipeline.append({"$match": match_conditions})

        # Default sort by date descending (newest first)
        pipeline.append({"$sort": {"invoice_date": -1}})

        # Hard limit to prevent context overflow if LLM asks for "all invoices"
        pipeline.append({"$limit": 50})

        # 5. Project relevant fields
        pipeline.append(
            {
                "$project": {
                    "_id": 0,
                    "invoice_number": 1,
                    "sender_name": 1,
                    "invoice_date": 1,
                    "total_amount": 1,
                    "currency": 1,
                    "status": 1,
                    "filename": 1,
                    "error_message": 1,
                }
            }
        )

        return pipeline

    async def _resolve_invoice_ids(
        self, criteria: SearchLineItemsTool
    ) -> list[PydanticObjectId] | None:
        """
        Helper to find Invoice ObjectIds based on metadata strings.
        """
        filters = {}

        if criteria.invoice_number:
            filters["invoice_number"] = criteria.invoice_number

        if criteria.sender_name:
            filters["sender_name"] = {
                "$regex": re.escape(criteria.sender_name),
                "$options": "i",
            }

        if criteria.invoice_date_start or criteria.invoice_date_end:
            date_filter = {}
            if criteria.invoice_date_start:
                # Convert string to python date object
                date_filter["$gte"] = self._parse_date_str(criteria.invoice_date_start)
            if criteria.invoice_date_end:
                date_filter["$lte"] = self._parse_date_str(criteria.invoice_date_end)

            if date_filter:
                filters["invoice_date"] = date_filter

        if not filters:
            return None

        # Fetch IDs only
        invoices: list[Document] = await InvoiceModel.find(
            filters, projection_model=Document
        ).to_list()
        return [i.id for i in invoices if i.id]

    def _parse_date_str(self, date_str: str):
        """Helper to safely convert YYYY-MM-DD to datetime.date"""
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return date_str
