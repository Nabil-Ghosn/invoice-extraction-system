"""
Extensive Invoice Schema Definitions for invoicehome.com
Not used in the project for its complexity, but serves as a reference for future enhancements.
"""

from enum import Enum
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, computed_field

# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------


class DocumentType(str, Enum):
    """Supported document types identified on invoicehome.com"""

    INVOICE = "Invoice"
    TAX_INVOICE = "Tax Invoice"
    PROFORMA_INVOICE = "Proforma Invoice"
    RECEIPT = "Receipt"
    SALES_RECEIPT = "Sales Receipt"
    CASH_RECEIPT = "Cash Receipt"
    QUOTE = "Quote"
    ESTIMATE = "Estimate"
    CREDIT_MEMO = "Credit Memo"
    CREDIT_NOTE = "Credit Note"
    PURCHASE_ORDER = "Purchase Order"
    DELIVERY_NOTE = "Delivery Note"


class PaymentMethod(str, Enum):
    """Payment methods mentioned for the 'Payment Links' and records"""

    CASH = "Cash"
    CHECK = "Check"
    CREDIT_CARD = "Credit Card"
    DEBIT_CARD = "Debit Card"
    PAYPAL = "PayPal"
    STRIPE = "Stripe"
    BANK_TRANSFER = "Bank Transfer"
    OTHER = "Other"


# -----------------------------------------------------------------------------
# Sub-Models
# -----------------------------------------------------------------------------


class Tax(BaseModel):
    """
    Represents a tax applied to a line item or global.
    Supports simple percentage and compound tax as per 'Advanced' features.
    """

    name: str = Field(..., description="Name of the tax (e.g., VAT, GST, Sales Tax)")
    rate: float = Field(..., description="Tax rate in percentage (e.g., 20.0 for 20%)")
    is_compound: bool = Field(
        default=False, description="Whether this is a compound tax"
    )


class Address(BaseModel):
    """
    Represents a party's contact information.
    'From' and 'Bill To' fields allow for Name + Address block.
    """

    name: str | None = Field(None, description="Company or Individual Name")
    address_line: str | None = Field(
        None, description="Full address text (street, city, zip, country)"
    )
    email: str | None = Field(None, description="Email address for sending the invoice")
    phone: str | None = Field(None, description="Phone number")


class LineItem(BaseModel):
    """
    Represents a single row in the invoice.
    Combines Basic (Description, Amount) and Advanced (Qty, Unit Price) fields.
    """

    sku: str | None = Field(
        None, description="Stock Keeping Unit or Item Code (Advanced Form feature)"
    )
    description: str = Field(..., description="Description of product or service")
    quantity: float | None = Field(
        default=1.0, description="Quantity (Advanced Form feature). Default is 1."
    )
    unit_price: float | None = Field(
        None, description="Price per unit (Advanced Form feature)."
    )
    # Note: 'amount' is usually calculated (qty * unit_price), but in Basic forms it might be entered directly.
    amount: float = Field(..., description="Total line item cost")
    taxes: list[Tax] | None = Field(
        default=[], description="List of taxes applied to this specific item"
    )


# -----------------------------------------------------------------------------
# Main Model
# -----------------------------------------------------------------------------


class Invoice(BaseModel):
    """
    Complete Invoice model representing the data structure for invoicehome.com
    """

    # --- Header Information ---
    document_type: DocumentType = Field(
        default=DocumentType.INVOICE,
        description="Type of the document (Invoice, Quote, etc.)",
    )
    invoice_number: str = Field(
        ...,
        description="Unique identifier for the invoice. Auto-populated but editable.",
    )
    po_number: str | None = Field(
        None, description="Purchase Order Number (Advanced Form feature)"
    )

    # --- Dates ---
    date_issued: date = Field(
        ..., description="Date the invoice was written or takes effect"
    )
    due_date: date | None = Field(
        None, description="Date payment is due (Advanced Form feature)"
    )

    # --- Parties ---
    sender: Address = Field(
        ..., description="Information about the entity sending the invoice (From)"
    )
    recipient: Address = Field(
        ..., description="Information about the entity receiving the invoice (Bill To)"
    )
    shipping_address: Address | None = Field(
        None,
        description="Shipping address if different from Bill To (Advanced Form feature)",
    )

    # --- Line Items ---
    items: list[LineItem] = Field(
        ..., min_length=1, description="List of goods or services"
    )

    # --- Financial Totals ---
    currency: str = Field(default="USD", description="Currency code (e.g., USD, EUR)")
    subtotal: float = Field(
        ..., description="The subtotal text literally written on the invoice."
    )

    global_discount: float | None = Field(
        0.0, description="Discount applied to the whole invoice (optional feature)"
    )

    total_tax_amount: float = Field(0.0, description="Total calculated tax")
    global_taxes: list[Tax] | None = Field(
        default=[], description="List of taxes applied to all items"
    )
    total_amount: float = Field(
        ..., description="Final Total: Subtotal - Discount + Tax"
    )

    amount_paid: float | None = Field(
        0.0, description="Amount already paid (Partial Payments feature)"
    )
    balance_due: float | None = Field(
        None, description="Remaining balance. Calculated as Total - Amount Paid"
    )

    # --- Footer & Metadata ---
    terms_and_conditions: str | None = Field(
        None, description="Payment terms, bank details, deadlines (Basic Form)"
    )
    notes: str | None = Field(None, description="Additional notes or comments")

    @computed_field
    def is_mathematically_consistent(self) -> bool:
        """
        Checks if the line items sum up to the extracted subtotal.
        Returns False if there is a discrepancy, allowing the app to flag it.
        """
        if not self.subtotal or not self.items:
            return True  # Cannot validate

        calculated = sum(item.amount for item in self.items)
        # Allow 0.05 discrepancy for OCR/Rounding errors
        return abs(calculated - self.subtotal) < 0.05

    @computed_field
    def discrepancy_message(self) -> str | None:
        if self.is_mathematically_consistent:
            return None

        calculated = sum(item.amount for item in self.items)
        return f"Warning: Extracted subtotal is {self.subtotal}, but items sum to {calculated:.2f}"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_type": "Invoice",
                "invoice_number": "INV-1001",
                "po_number": "PO-998877",
                "date_issued": "2023-10-25",
                "due_date": "2023-11-25",
                "sender": {
                    "name": "Acme Corp",
                    "address_line": "123 Business Rd, Tech City, TX",
                    "email": "billing@acme.com",
                },
                "recipient": {
                    "name": "Jane Doe",
                    "address_line": "456 Client Ln, Residential Area, CA",
                },
                "items": [
                    {
                        "description": "Web Design Services",
                        "quantity": 10,
                        "unit_price": 50.0,
                        "amount": 500.0,
                        "taxes": [{"name": "VAT", "rate": 20.0}],
                    }
                ],
                "subtotal": 500.0,
                "total_tax_amount": 100.0,
                "total_amount": 600.0,
                "terms_and_conditions": "Payment due within 30 days via Bank Transfer.",
            }
        }
    )
