"""Sales reports, CSV export and printable reports (admin only)."""
import csv
from datetime import datetime, time, timedelta
from io import StringIO

from flask import Blueprint, Response, render_template, request
from routes.decorators import admin_required
from services import report_service
from utils import ValidationError, parse_date, utcnow

reports_bp = Blueprint("reports", __name__)


def _resolve_range():
    period = request.args.get("period", "today")
    today = utcnow().date()

    if period == "today":
        start_date = end_date = today
    elif period == "week":
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    elif period == "month":
        start_date = today.replace(day=1)
        end_date = today
    elif period == "year":
        start_date = today.replace(month=1, day=1)
        end_date = today
    elif period == "custom":
        start_date = parse_date(request.args.get("start"), "Start date") or (today - timedelta(days=30))
        end_date = parse_date(request.args.get("end"), "End date") or today
    else:
        period = "today"
        start_date = end_date = today

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    return (
        period,
        datetime.combine(start_date, time.min),
        datetime.combine(end_date, time.max),
        start_date,
        end_date,
    )


def _build_report():
    period, start, end, start_date, end_date = _resolve_range()
    return {
        "period": period,
        "start": start,
        "end": end,
        "start_date": start_date,
        "end_date": end_date,
        "summary": report_service.summarise(start, end),
        "products": report_service.product_sales(start, end),
        "payments": report_service.payment_summary(start, end),
        "best": report_service.best_sellers(start, end, 5),
        "sales": report_service.sales_in_range(start, end),
    }


@reports_bp.route("/")
@admin_required
def index():
    return render_template("reports.html", report=_build_report())


@reports_bp.route("/print")
@admin_required
def print_report():
    return render_template("report_print.html", report=_build_report())


@reports_bp.route("/export.csv")
@admin_required
def export_csv():
    report = _build_report()
    kind = request.args.get("kind", "sales")
    buffer = StringIO()
    writer = csv.writer(buffer)

    if kind == "products":
        writer.writerow(["Product", "SKU", "Quantity sold", "Revenue"])
        for row in report["products"]:
            writer.writerow([row.product_name, row.sku, row.quantity, f"{row.revenue:.2f}"])
    elif kind == "payments":
        writer.writerow(["Payment method", "Bills", "Amount"])
        for row in report["payments"]:
            writer.writerow([row.payment_method, row.bills, f"{row.amount:.2f}"])
    else:
        writer.writerow(["Invoice", "Date", "Cashier", "Payment", "Subtotal", "Discount", "Tax", "Total", "Status"])
        for sale in report["sales"]:
            writer.writerow([
                sale.invoice_number,
                sale.created_at.strftime("%Y-%m-%d %H:%M"),
                sale.cashier.display_name() if sale.cashier else "-",
                sale.payment_method,
                f"{sale.subtotal:.2f}",
                f"{sale.discount_total:.2f}" if hasattr(sale, "discount_total") else f"{(sale.item_discount + sale.bill_discount):.2f}",
                f"{sale.tax_total:.2f}",
                f"{sale.grand_total:.2f}",
                sale.status,
            ])

    filename = f"report_{kind}_{report['start_date']}_{report['end_date']}.csv"
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
