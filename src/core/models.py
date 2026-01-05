from datetime import datetime, date, timezone
from enum import Enum
from typing import Annotated
from pydantic import BaseModel, Field
from beanie import Document, Indexed, PydanticObjectId
from pymongo import DESCENDING


class ProcessingStatus(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class InvoiceModel(Document):
    # File Metadata
    filename: str
    file_hash: Annotated[
        str, Indexed(str, unique=True)
    ]  # Prevent duplicate processing of same file
    upload_date: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    # Extraction Metadata
    status: Annotated[ProcessingStatus, Indexed()]
    error_message: str | None = None
    total_pages: int = 0
    processing_time_seconds: float = 0.0

    # Invoice Business Data (Used for Filtering)
    invoice_number: str | None = None
    invoice_date: Annotated[date | None, Indexed(index_type=DESCENDING)] = None
    sender_name: Annotated[str | None, Indexed()] = None
    receiver_name: str | None = None
    currency: str = "USD"
    total_amount: float | None = None

    class Settings:
        name: str = "invoices"


class LineItemModel(Document):
    # Relationship
    invoice_id: Annotated[PydanticObjectId, Indexed()]

    # Location Metadata
    page_number: Annotated[int, Indexed()]

    # The Core Data
    description: str
    quantity: float | None
    unit_price: float | None
    total_amount: float | None
    # Extracted from headers like "Labor" or "Materials"
    section: str

    item_code: str | None = None
    delivery_date: str | None = None  # ISO 8601 or near-ISO
    quantity_unit: str | None = None  # e.g. 'kg', 'hours' if present

    # Constructed as: f"Context: {sender_name} ({section}) | Item: {description} ({item_code})"
    search_text: str
    vector: list[float]

    class Settings:
        name: str = "line_items"

    # Having the vector search set with Atlas UI for vector with pre-filter (page_number, total_amount, delivery_date).


class LineItemProjection(BaseModel):
    invoice_id: PydanticObjectId
    page_number: int

    description: str
    section: str

    quantity: float | None
    quantity_unit: str | None
    unit_price: float | None
    total_amount: float | None

    item_code: str | None
    delivery_date: str | None


class InvoiceProjection(BaseModel):
    filename: str
    file_hash: str
    upload_date: datetime

    status: ProcessingStatus
    error_message: str | None
    total_pages: int
    processing_time_seconds: float

    invoice_number: str | None
    invoice_date: date | None
    sender_name: str | None
    receiver_name: str | None
    currency: str
    total_amount: float | None
