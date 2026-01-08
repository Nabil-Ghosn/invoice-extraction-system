from src.core.models import InvoiceProjection, LineItemProjection


def format_line_items(items: list[LineItemProjection]) -> str:
    lines: list[str] = []

    for idx, item in enumerate(items, start=1):
        qty: str = (
            f"{item.quantity:g} {item.quantity_unit}"
            if item.quantity is not None
            else "N/A"
        )

        unit_price: str = (
            f"{item.unit_price:.2f}" if item.unit_price is not None else "N/A"
        )
        total: str = (
            f"{item.total_amount:.2f}" if item.total_amount is not None else "N/A"
        )

        lines.append(
            "\n".join(
                [
                    f"Line Item #{idx}\tvector search score ({item.score})",
                    f"  Page        : {item.page_number}",
                    f"  Section     : {item.section}",
                    f"  Description : {item.description}",
                    f"  Item Code   : {item.item_code or 'N/A'}",
                    f"  Quantity    : {qty}",
                    f"  Unit Price  : {unit_price}",
                    f"  Total       : {total}",
                    f"  Delivery    : {item.delivery_date or 'N/A'}",
                    f"  invoice_number    : {item.invoice_number}",
                    f"  sender_name    : {item.sender_name}",
                    f"  invoice_date    : {item.invoice_date or 'N/A'}",
                ]
            )
        )

    return "\n\n".join(lines)


def format_invoices(invoices: list[InvoiceProjection]) -> str:
    lines: list[str] = []

    for idx, inv in enumerate(invoices, start=1):
        total: str = (
            f"{inv.total_amount:.2f}" if inv.total_amount is not None else "N/A"
        )

        lines.append(
            "\n".join(
                [
                    f"Invoice #{idx}",
                    f"  File        : {inv.filename}",
                    f"  Hash        : {inv.file_hash}",
                    f"  Status      : {inv.status}",
                    f"  Uploaded    : {inv.upload_date.isoformat()}",
                    f"  Pages       : {inv.total_pages}",
                    f"  Proc Time   : {inv.processing_time_seconds:.2f}s",
                    f"  Invoice No. : {inv.invoice_number or 'N/A'}",
                    f"  Date        : {inv.invoice_date or 'N/A'}",
                    f"  Sender      : {inv.sender_name or 'N/A'}",
                    f"  Receiver    : {inv.receiver_name or 'N/A'}",
                    f"  Currency    : {inv.currency}",
                    f"  Total       : {total}",
                    f"  Error       : {inv.error_message or 'None'}",
                ]
            )
        )

    return "\n\n".join(lines)
