from typing import Annotated, Literal
from pydantic import BaseModel, Field


class SearchLineItemsTool(BaseModel):
    """
    The primary tool for querying invoice data.
    Use this for ANY question regarding line items, costs, specific products,
    or details inside a table.

    Examples:
    - "Show me all maintenance costs." (Semantic)
    - "What items are on page 3 of invoice RXC-99?" (Structural + Filter)
    - "List items delivered last week." (Date Filter)
    """

    # --- Semantic Search ---
    query_text: Annotated[
        str | None,
        Field(
            None,
            description=(
                "The semantic search terms. Use this for descriptive queries like "
                "'labor', 'server maintenance', 'cables'. "
                "Leave empty if the user is only asking for structural data (e.g., 'items on page 3')."
            ),
        ),
    ] = None
    # --- Structural Filters (Page & Location) ---
    page_number: Annotated[
        int | None,
        Field(
            None,
            description="Exact page number. Use only if user specifies one specific page.",
        ),
    ] = None
    min_page: Annotated[
        int | None,
        Field(
            None,
            description="Start of a page range (inclusive). Example: for 'pages 10 to 15', set min_page=10.",
        ),
    ] = None
    max_page: Annotated[
        int | None,
        Field(
            None,
            description="End of a page range (inclusive). Example: for 'pages 10 to 15', set max_page=15.",
        ),
    ] = None
    # --- Invoice Context Filters ---
    invoice_number: Annotated[
        str | None,
        Field(
            None,
            description="The alphanumeric invoice number (e.g., 'INV-2024-001'). Prefer this over sender name if available.",
        ),
    ] = None
    sender_name: Annotated[
        str | None,
        Field(
            None,
            description="Filter by the Vendor or Sender name (fuzzy match). Example: 'Amazon', 'Dell'.",
        ),
    ] = None
    # --- Date Filters ---
    # We distinguish between the Invoice's date and the Item's delivery date
    invoice_date_start: Annotated[
        str | None,
        Field(
            None,
            description="Filter items from invoices issued on or after this date (ISO 8601: YYYY-MM-DD).",
        ),
    ] = None
    invoice_date_end: Annotated[
        str | None,
        Field(
            None,
            description="Filter items from invoices issued on or before this date (ISO 8601: YYYY-MM-DD).",
        ),
    ] = None
    # --- Financial Filters ---
    min_amount: Annotated[
        float | None, Field(None, description="Minimum line item total amount.")
    ] = None
    max_amount: Annotated[
        float | None, Field(None, description="Maximum line item total amount.")
    ] = None
    limit: Annotated[
        int,
        Field(
            20,
            description="Maximum number of items to retrieve. Default to 20 unless user asks for 'all' or a specific number.",
        ),
    ] = 20


class SearchInvoicesTool(BaseModel):
    """
    Use this tool ONLY for high-level document questions.
    Do NOT use this for questions about specific line items, products, or costs inside the invoice.

    Examples:
    - "How many invoices did we receive from Google?"
    - "List all invoices processed yesterday."
    - "Check if invoice INV-101 has been processed."
    """

    sender_name: Annotated[
        str | None, Field(None, description="Filter by sender/vendor name.")
    ] = None
    invoice_number: Annotated[
        str | None, Field(None, description="Exact invoice number to look up.")
    ] = None
    status: Annotated[
        Literal["COMPLETED", "FAILED", "PROCESSING"] | None,
        Field(None, description="Filter by processing status."),
    ] = None
    filename_query: Annotated[
        str | None, Field(None, description="Partial match for the filename.")
    ] = None

    start_date: Annotated[
        str | None,
        Field(
            None,
            description="Filter by upload/invoice date (start). Format: YYYY-MM-DD",
        ),
    ] = None
    end_date: Annotated[
        str | None,
        Field(
            None, description="Filter by upload/invoice date (end). Format: YYYY-MM-DD"
        ),
    ] = None
