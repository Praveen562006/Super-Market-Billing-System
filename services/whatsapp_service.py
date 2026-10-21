"""Build WhatsApp "click to chat" links for delivering a bill.

WhatsApp cannot receive a PDF through ``wa.me`` links, so the bill is rendered
as a formatted text message containing the invoice number, the line items and
the grand total.  The cashier (or the customer) then just presses *send*.
"""
from urllib.parse import quote

from services.settings_service import get_store_info


def normalize_number(mobile):
    """Return the digits of *mobile*, adding the country code when needed."""
    digits = "".join(ch for ch in str(mobile or "") if ch.isdigit())
    if not digits:
        return None
    store = get_store_info()
    country_code = "".join(ch for ch in str(store.get("whatsapp_country_code") or "") if ch.isdigit())
    if country_code and len(digits) == 10:
        digits = f"{country_code}{digits}"
    return digits


def build_message(sale):
    """Return the plain-text bill that will be pre-filled in WhatsApp."""
    store = get_store_info()
    currency = store["currency"]

    lines = [f"*{store['name']}*", f"Invoice: {sale.invoice_number}"]
    if sale.created_at:
        lines.append(f"Date: {sale.created_at:%Y-%m-%d %H:%M}")
    if sale.customer_name:
        lines.append(f"Customer: {sale.customer_name}")
    lines.append("")
    lines.append("Items:")
    for item in sale.items:
        lines.append(
            f"- {item.product_name} x{item.quantity} = {currency}{item.line_total:.2f}"
        )
    lines.append("")
    lines.append(f"Total: {currency}{sale.grand_total:.2f}")
    if store.get("phone"):
        lines.append(f"For queries call {store['phone']}.")
    lines.append("Thank you for shopping with us!")
    return "\n".join(lines)


def build_link(sale, mobile=None):
    """Return a ``https://wa.me/...`` link for *sale*, or ``None`` if no number."""
    number = normalize_number(mobile if mobile is not None else sale.customer_mobile)
    if not number:
        return None
    message = build_message(sale)
    return f"https://wa.me/{number}?text={quote(message)}"
