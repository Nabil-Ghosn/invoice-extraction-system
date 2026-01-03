from typing import Literal
from pydantic import BaseModel, Field

# `_raw` fields are just for auditing. They capture the exact OCR text.
# The main fields are normalized to proper types (e.g., float for amounts).


class LineItem(BaseModel):
    item_code: str | None = Field(
        None, description="SKU or product identifier if present"
    )
    description: str = Field(..., description="Canonical item description text")
    delivery_date: str | None = Field(None, description="ISO 8601 or near-ISO")

    # quantity_raw: str | None = Field(None, description="Raw OCR quantity")
    quantity_value: float | None = Field(
        None, description="Normalized numeric quantity"
    )
    quantity_unit: str | None = Field(
        None, description="Unit e.g. 'kg', 'hours' if present"
    )

    # unit_price_raw: str | None = Field(None, description="Raw OCR unit price")
    unit_price: float | None = Field(None)

    # line_total_amount_raw: str | None = Field(None)
    line_total_amount: float | None = Field(None)

    # Context tagging for Semantic Search
    section: str = Field(
        "General",
        description="The section header under which this item appears (e.g., 'Labor', 'Material', 'Surcharges').",
    )


class InvoiceContext(BaseModel):
    invoice_number: str | None = Field(None)
    invoice_date: str | None = Field(None, description="Issue date in ISO 8601 date")
    sender_name: str | None = Field(None, description="Seller / vendor / issuer name")
    receiver_name: str | None = Field(
        None, description="Buyer / customer / recipient name"
    )
    currency: str | None = Field(
        None, description="ISO 4217 currency code inferred from symbols or labels"
    )
    total_amount: str | None = Field(
        None, description="Raw total (could include commas/symbols)"
    )


class PageState(BaseModel):
    table_status: Literal[
        "no_table", "table_open_headless", "table_open_with_headers"
    ] = Field(
        ...,
        description=(
            "Status of the table at the VERY BOTTOM of this page. "
            "'table_open_headless': Table continues to next page WITHOUT repeating headers. "
            "'table_open_with_headers': Table continues but next page likely has headers. "
            "'no_table': No active table at page break."
        ),
    )
    active_columns: list[str] = Field(
        default_factory=list,
        description="The list of column headers for the table currently open at the bottom of the page.",
    )
    active_section_title: str = Field(
        "General",
        description="The last section header seen. This carries over to the next page.",
    )


class InvoicePage(BaseModel):
    next_page_state: PageState = Field(
        ...,
        description="The state instructions for the worker processing the next page.",
    )
    invoice_context: InvoiceContext | None = Field(
        None,
        description="Any global invoice data (ID, Date, Vendor) found strictly on THIS page.",
    )

    line_items: list[LineItem] = Field(
        default_factory=list, description="Line items detected on this page"
    )


class InvoiceSinglePage(BaseModel):
    invoice_context: InvoiceContext = Field(
        ...,
        description="Global invoice data (ID, Date, Vendor) found on this single page.",
    )

    line_items: list[LineItem] = Field(
        default_factory=list, description="Line items detected on this page"
    )
