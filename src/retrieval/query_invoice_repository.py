from typing import Protocol
from datetime import date
from dataclasses import dataclass

from wireup import service

from src.core.models import InvoiceModel, LineItemModel


@dataclass
class VectorSearchFilter:
    """Filters for vector search pre-filtering."""

    delivery_date_from: date | None = None
    delivery_date_to: date | None = None
    total_amount_min: float | None = None
    total_amount_max: float | None = None
    page_number: int | None = None
    invoice_ids: list[str] | None = None
    sender_names: list[str] | None = None


@dataclass
class SearchResult:
    """Result of a vector search."""

    line_item: LineItemModel
    invoice: InvoiceModel
    similarity_score: float  # Cosine similarity or distance score


class IQueryInvoiceRepository(Protocol):
    """Interface for querying invoices with vector search capabilities."""

    async def vector_search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: VectorSearchFilter | None = None,
        min_similarity_score: float = 0.5,
    ) -> list[SearchResult]:
        """
        Perform vector similarity search with pre-filters.

        Args:
            query_embedding: The embedding vector to search for
            top_k: Number of top results to return
            filters: Pre-filters to apply before vector search
            min_similarity_score: Minimum similarity score threshold

        Returns:
            List of SearchResults sorted by similarity score (highest first)
        """
        ...

    async def get_invoice_by_id(self, invoice_id: str) -> InvoiceModel | None:
        """Get an invoice by its ID."""
        ...

    async def get_line_item_by_id(self, line_item_id: str) -> LineItemModel | None:
        """Get a line item by its ID."""
        ...


@service
class BeanieQueryInvoiceRepository(IQueryInvoiceRepository):
    async def vector_search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: VectorSearchFilter | None = None,
        min_similarity_score: float = 0.5,
    ) -> list[SearchResult]:
        """
        Perform vector similarity search with pre-filters.

        Args:
            query_embedding: The embedding vector to search for
            top_k: Number of top results to return
            filters: Pre-filters to apply before vector search
            min_similarity_score: Minimum similarity score threshold

        Returns:
            List of SearchResults sorted by similarity score (highest first)
        """
        # Build the MongoDB aggregation pipeline for vector search
        pipeline = []

        # Apply pre-filters if provided
        match_stage = {"$match": {}}
        if filters:
            if filters.delivery_date_from or filters.delivery_date_to:
                match_stage["$match"]["delivery_date"] = {}
                if filters.delivery_date_from:
                    match_stage["$match"]["delivery_date"]["$gte"] = filters.delivery_date_from.isoformat()
                if filters.delivery_date_to:
                    match_stage["$match"]["delivery_date"]["$lte"] = filters.delivery_date_to.isoformat()

            if filters.total_amount_min is not None or filters.total_amount_max is not None:
                match_stage["$match"]["total_amount"] = {}
                if filters.total_amount_min is not None:
                    match_stage["$match"]["total_amount"]["$gte"] = filters.total_amount_min
                if filters.total_amount_max is not None:
                    match_stage["$match"]["total_amount"]["$lte"] = filters.total_amount_max

            if filters.page_number is not None:
                match_stage["$match"]["page_number"] = filters.page_number

            if filters.sender_names:
                # This requires a lookup to join with invoices collection
                pass

            if filters.invoice_ids:
                match_stage["$match"]["invoice_id"] = {"$in": filters.invoice_ids}

        if match_stage["$match"]:  # Only add match stage if there are filters
            pipeline.append(match_stage)

        # Add the vector search stage
        vector_search_stage = {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "vector",
                "queryVector": query_embedding,
                "numCandidates": max(100, top_k * 10),
                "limit": top_k,
            }
        }

        # Insert vector search as the first stage
        pipeline.insert(0, vector_search_stage)

        # Add lookup to join with invoices
        pipeline.append({
            "$lookup": {
                "from": "invoices",
                "localField": "invoice_id",
                "foreignField": "_id",
                "as": "invoice"
            }
        })

        # Add project stage to format results
        pipeline.append({
            "$project": {
                "line_item": "$$ROOT",
                "invoice": {"$arrayElemAt": ["$invoice", 0]},
                "similarity_score": {"$meta": "vectorSearchScore"}
            }
        })

        # Add match stage to filter by similarity score
        if min_similarity_score > 0:
            pipeline.append({
                "$match": {
                    "similarity_score": {"$gte": min_similarity_score}
                }
            })

        # Execute the pipeline
        results = await LineItemModel.aggregate(pipeline).to_list(length=None)

        # Convert to SearchResult objects
        search_results = []
        for result in results:
            line_item_data = result["line_item"]
            invoice_data = result["invoice"]
            similarity_score = result["similarity_score"]

            # Create LineItemModel and InvoiceModel from the data
            line_item = LineItemModel(
                id=line_item_data.get("id"),
                invoice_id=line_item_data.get("invoice_id"),
                page_number=line_item_data.get("page_number", 0),
                description=line_item_data.get("description", ""),
                quantity=line_item_data.get("quantity"),
                unit_price=line_item_data.get("unit_price"),
                total_amount=line_item_data.get("total_amount"),
                section=line_item_data.get("section", ""),
                item_code=line_item_data.get("item_code"),
                delivery_date=line_item_data.get("delivery_date"),
                search_text=line_item_data.get("search_text", ""),
                vector=line_item_data.get("vector", []),
            )

            invoice = InvoiceModel(
                id=invoice_data.get("id"),
                filename=invoice_data.get("filename", ""),
                file_hash=invoice_data.get("file_hash", ""),
                upload_date=invoice_data.get("upload_date"),
                status=invoice_data.get("status"),
                error_message=invoice_data.get("error_message"),
                total_pages=invoice_data.get("total_pages", 0),
                processing_time_seconds=invoice_data.get("processing_time_seconds", 0.0),
                invoice_number=invoice_data.get("invoice_number"),
                invoice_date=invoice_data.get("invoice_date"),
                sender_name=invoice_data.get("sender_name"),
                receiver_name=invoice_data.get("receiver_name"),
                currency=invoice_data.get("currency", "USD"),
                total_amount=invoice_data.get("total_amount"),
            )

            search_result = SearchResult(
                line_item=line_item,
                invoice=invoice,
                similarity_score=similarity_score
            )
            search_results.append(search_result)

        return search_results

    async def get_invoice_by_id(self, invoice_id: str) -> InvoiceModel | None:
        """Get an invoice by its ID."""
        return await InvoiceModel.get(invoice_id)

    async def get_line_item_by_id(self, line_item_id: str) -> LineItemModel | None:
        """Get a line item by its ID."""
        return await LineItemModel.get(line_item_id)
