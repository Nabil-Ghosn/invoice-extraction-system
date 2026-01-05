from typing import Protocol, override

from wireup import abstract, service
from src.core.models import InvoiceModel, LineItemModel


@abstract
class ICommandInvoiceRepository(Protocol):
    """Repository interface for command operations on invoices and line items."""

    async def get_by_hash(self, file_hash: str) -> InvoiceModel | None:
        """Get an invoice by its file hash."""
        ...

    async def save_invoice(self, invoice_model: InvoiceModel) -> InvoiceModel:
        """Save an invoice and return the saved invoice with ID."""
        ...

    async def save_line_items(self, line_item_models: list[LineItemModel]) -> None:
        """Save multiple line items."""
        ...


@service
class BeanieCommandInvoiceRepository(ICommandInvoiceRepository):
    """Beanie implementation of the command invoice repository."""

    def __init__(self) -> None:
        """Initialize the repository. Beanie models work globally."""
        pass

    @override
    async def get_by_hash(self, file_hash: str) -> InvoiceModel | None:
        return await InvoiceModel.find_one(InvoiceModel.file_hash == file_hash)

    @override
    async def save_invoice(self, invoice_model: InvoiceModel) -> InvoiceModel:
        return await invoice_model.insert()

    @override
    async def save_line_items(self, line_item_models: list[LineItemModel]) -> None:
        if line_item_models:
            await LineItemModel.insert_many(line_item_models)
