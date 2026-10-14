"""Invoice numbering, rendering data and PDF generation."""
from io import BytesIO

from services.settings_service import get_setting, get_store_info
from utils import utcnow


def build_invoice_number(sale_id, when=None):
    """Build a unique, sortable invoice number.

    A zero-padded sale id guarantees uniqueness (it is the primary key) and
    avoids any cross-row counter contention under concurrent checkouts.
    """
    when = when or utcnow()
    prefix = (get_setting("INVOICE_PREFIX", "INV") or "INV").strip().upper()
    return f"{prefix}-{when:%Y%m%d}-{int(sale_id):05d}"


def invoice_context(sale):
    store = get_store_info()
    return {
        "sale": sale,
        "store": store,
        "currency": store["currency"],
    }


def render_invoice_pdf(sale):
    """Return the bytes of a simple A4 invoice PDF for *sale*."""
    # Imported lazily so the app still runs if reportlab is unavailable.
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
        Paragraph,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    store = get_store_info()
    currency = store["currency"]

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Invoice {sale.invoice_number}",
    )
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=9)
    heading = ParagraphStyle("heading", parent=styles["Heading2"], spaceAfter=2)

    elements = []
    elements.append(Paragraph(store["name"] or "SuperMarket", styles["Title"]))
    if store["address"]:
        elements.append(Paragraph(store["address"], small))
    contact = " | ".join(filter(None, [store["phone"], store["email"]]))
    if contact:
        elements.append(Paragraph(contact, small))
    if store["gstin"]:
        elements.append(Paragraph(f"GSTIN: {store['gstin']}", small))
    elements.append(Spacer(1, 8 * mm))

    elements.append(Paragraph("TAX INVOICE", heading))
    meta = [
        ["Invoice No:", sale.invoice_number, "Date:", sale.created_at.strftime("%Y-%m-%d %H:%M")],
        ["Cashier:", sale.cashier.display_name() if sale.cashier else "-", "Payment:", sale.payment_method.title()],
    ]
    if sale.customer_mobile or sale.customer_name:
        meta.append([
            "Customer:", sale.customer_name or "-",
            "Mobile:", sale.customer_mobile or "-",
        ])
    meta_table = Table(meta, colWidths=[25 * mm, 55 * mm, 22 * mm, 55 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.grey),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 6 * mm))

    data = [["#", "Item", "SKU", "Qty", "Unit", "Disc %", "Tax %", "Line total"]]
    for idx, item in enumerate(sale.items, start=1):
        data.append([
            str(idx),
            item.product_name,
            item.sku,
            str(item.quantity),
            f"{currency}{item.unit_price:.2f}",
            f"{item.discount_percent:.0f}",
            f"{item.tax_rate:.0f}",
            f"{currency}{item.line_total:.2f}",
        ])
    table = Table(data, colWidths=[8 * mm, 52 * mm, 22 * mm, 12 * mm, 22 * mm, 16 * mm, 14 * mm, 26 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ff735c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 6 * mm))

    summary = [
        ["Subtotal", f"{currency}{sale.subtotal:.2f}"],
        ["Item discount", f"-{currency}{sale.item_discount:.2f}"],
        [f"Bill discount ({sale.bill_discount_percent:.0f}%)", f"-{currency}{sale.bill_discount:.2f}"],
        ["Tax", f"{currency}{sale.tax_total:.2f}"],
        ["Grand total", f"{currency}{sale.grand_total:.2f}"],
        ["Amount received", f"{currency}{sale.amount_received:.2f}"],
        ["Change due", f"{currency}{sale.change_due:.2f}"],
    ]
    summary_table = Table(summary, colWidths=[60 * mm, 40 * mm], hAlign="RIGHT")
    summary_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, 4), (-1, 4), 0.5, colors.grey),
        ("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold"),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 8 * mm))
    elements.append(Paragraph("Thank you for shopping with us!", small))

    doc.build(elements)
    return buffer.getvalue()
