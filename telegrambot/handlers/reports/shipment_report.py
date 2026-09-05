#!/usr/bin/env python3
"""
Shipment Approval Report (PDF)

When an import shipment is approved, the admin receives a multi-page PDF that
mirrors the Import Shipment dialog:

  * Page 1 – Landed Cost & Margin   (same data as the last dialog tab)
  * Page 2 – Costs & Allocation     (additional costs + CBM allocation matrix)
  * Page 3 – Customs Tax            (tax inputs + per product tax calculation)

All figures are re-computed from the saved shipment the same way the dialog
does, so the PDF matches what the user saw on screen.
"""
import io
import logging
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
)

logger = logging.getLogger(__name__)

# The shipment dialog defaults to this capacity when "Fixed Container" mode is used.
FIXED_CONTAINER_CAPACITY = 68.0


# ---------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------
def _money(value):
    try:
        return f"{float(value or 0.0):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _int_str(value):
    try:
        return f"{int(float(value or 0)):,}"
    except (TypeError, ValueError):
        return "0"


def _pct_str(value):
    try:
        return f"{float(value or 0.0):,.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def _ratio(value):
    try:
        return f"{float(value or 0.0):,.4f}"
    except (TypeError, ValueError):
        return "0.0000"


def _date_str(value):
    if not value:
        return "-"
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")
    return str(value)


# ---------------------------------------------------------------------
# Pure data extraction (mirrors CalculationsMixin.calculate_landed)
# ---------------------------------------------------------------------
def build_shipment_report(shipment, tax_bank_account_name: str = ""):
    """
    Build a plain-dict snapshot of every number shown in the shipment dialog.

    shipment: ImportShipment ORM object with supplier, bank_account, products,
              costs (+ cost_type / bank_transaction) already loaded.
    tax_bank_account_name: display string for the bank used to pay customs tax.
    """
    exchange_rate = float(shipment.exchange_rate or 0.0)
    target_margin = float(shipment.target_margin or 0.0) / 100.0
    allocation_mode = shipment.allocation_mode or "used_cbm"

    products = [p for p in shipment.products if not p.is_deleted]
    costs = [c for c in shipment.costs if not c.is_deleted]

    # ---- 1. Product list (Tab 1) -------------------------------------
    product_list = []
    for p in products:
        product_list.append({
            "item_number": p.item_number or "",
            "name": p.product_name or "",
            "unit": p.unit or "",
            "cartons": p.cartons or 0,
            "qty_per_carton": p.qty_per_carton or 0,
            "total_quantity": p.total_quantity or 0,
            "unit_price_rmb": p.unit_price_rmb or 0.0,
            "total_cbm": p.total_cbm or 0.0,
        })

    total_cbm_sum = sum(p["total_cbm"] for p in product_list)

    # ---- 2. Costs (Tab 2) --------------------------------------------
    cost_rows = []
    for c in costs:
        paid = c.bank_transaction_id is not None and c.bank_transaction is not None
        bank_name = ""
        paid_date = None
        if paid and c.bank_transaction.bank_account:
            bank = c.bank_transaction.bank_account
            bank_name = f"{bank.bank_name} - {bank.account_name}"
            paid_date = c.bank_transaction.transaction_date
        cost_rows.append({
            "type": c.cost_type.name if c.cost_type else "Unknown",
            "amount": float(c.amount or 0.0),
            "paid": paid,
            "paid_date": paid_date,
            "bank": bank_name,
        })
    total_costs = sum(r["amount"] for r in cost_rows)

    # ---- 3. Tax data (Tab 3) -----------------------------------------
    usd_rate = float(shipment.tax_usd_rate or 0.0)
    freight_ratio = float(shipment.tax_freight_ratio or 0.0)
    rater = float(shipment.tax_rater or 0.0)

    tax_rows = []
    for p in products:
        total_qty = p.total_quantity or 0
        qty_doz = p.tax_qty_per_doz if p.tax_qty_per_doz else (total_qty / 12.0 if total_qty else 0.0)
        tax_rows.append({
            "item_number": p.item_number or "",
            "name": p.product_name or "",
            "qty_doz": float(qty_doz or 0.0),
            "usd_per_dozen": float(p.usd_per_dozen or 0.0),
            "total_usd": float(p.total_usd or 0.0),
            "total_price_etb": float(p.total_price_etb or 0.0),
            "tax_frt_ctn": float(p.tax_frt_ctn or 0.0),
            "tax_dpv_ctn": float(p.tax_dpv_ctn or 0.0),
            "total_tax_etb": float(p.total_tax_etb or 0.0),
            "tax_per_dozen": float(p.tax_per_dozen or 0.0),
            "tax_per_unit": float(p.tax_per_unit or 0.0),
            "unit": "Doz",
        })
    total_tax = sum(r["total_tax_etb"] for r in tax_rows)

    # ---- 4. Allocation + landed cost (Tab 4) --------------------------
    # denominator used by the dialog:
    #   used_cbm -> sum of product CBM ; fixed -> container capacity (68 default)
    if allocation_mode == "fixed":
        denominator = FIXED_CONTAINER_CAPACITY
    else:
        denominator = total_cbm_sum

    allocated_matrix = []   # rows: {name, values:[..], total}
    landed_rows = []
    grand_total_etb = 0.0

    for i, p in enumerate(product_list):
        allocs = []
        if denominator and denominator > 0 and p["total_cbm"] > 0:
            for c in costs:
                allocs.append((float(c.amount or 0.0) / denominator) * p["total_cbm"])
        else:
            allocs = [0.0] * len(costs)

        allocated = sum(allocs)
        fob_etb = p["total_quantity"] * p["unit_price_rmb"] * exchange_rate
        total_tax_product = tax_rows[i]["total_tax_etb"] if i < len(tax_rows) else 0.0
        total_cost = fob_etb + allocated + total_tax_product

        landed_qty = total_cost / p["total_quantity"] if p["total_quantity"] else 0.0
        selling_price = landed_qty * (1 + target_margin) if landed_qty else 0.0

        # market price entered by the user in Tab 4
        market_price = None
        for sp in products:
            if (sp.product_name or "") == p["name"]:
                market_price = sp.market_price
                break
        market_price = float(market_price or 0.0)

        if landed_qty and market_price:
            implied_margin = (market_price - landed_qty) / landed_qty * 100.0
        else:
            implied_margin = 0.0

        landed_rows.append({
            "name": p["name"],
            "cartons": p["cartons"],
            "qty_per_carton": p["qty_per_carton"],
            "total_quantity": p["total_quantity"],
            "fob_etb": fob_etb,
            "allocated": allocated,
            "total_tax": total_tax_product,
            "total_cost": total_cost,
            "landed_unit": landed_qty,
            "selling_price": selling_price,
            "market_price": market_price,
            "implied_margin": implied_margin,
        })
        allocated_matrix.append({
            "name": p["name"],
            "values": allocs,
            "total": allocated,
        })
        grand_total_etb += total_cost

    # ---- 5. Profit analysis summary (mirrors update_profit_summary) ---
    total_selling = sum(
        r["selling_price"] * r["total_quantity"] for r in landed_rows
    )
    total_market = sum(
        r["market_price"] * r["total_quantity"] for r in landed_rows
    )
    profit_target = total_selling - grand_total_etb
    profit_market = total_market - grand_total_etb
    margin_target = (profit_target / grand_total_etb * 100.0) if grand_total_etb else 0.0
    margin_market = (profit_market / grand_total_etb * 100.0) if grand_total_etb else 0.0

    return {
        "shipment_id": shipment.id,
        "supplier": shipment.supplier.supplier_name if shipment.supplier else "",
        "bank": shipment.bank_account.account_name if shipment.bank_account else "",
        "proforma_date": shipment.proforma_date,
        "exchange_rate": exchange_rate,
        "payment_status": shipment.payment_status or "credit",
        "target_margin_pct": float(shipment.target_margin or 0.0),
        "allocation_mode": allocation_mode,
        "tax_paid": shipment.tax_paid,
        "tax_bank_account": tax_bank_account_name,
        "tax_payment_date": shipment.tax_payment_date,
        "product_list": product_list,
        "cost_rows": cost_rows,
        "total_costs": total_costs,
        "allocated_matrix": allocated_matrix,
        "cost_names": [r["type"] for r in cost_rows],
        "tax_rows": tax_rows,
        "usd_rate": usd_rate,
        "total_usd": float(shipment.tax_total_usd or 0.0),
        "sample_frt": float(shipment.tax_sample_frt or 0.0),
        "rater": rater,
        "freight_ratio": freight_ratio,
        "total_tax": total_tax,
        "landed_rows": landed_rows,
        "grand_total_etb": grand_total_etb,
        "total_selling": total_selling,
        "total_market": total_market,
        "profit_target": profit_target,
        "profit_market": profit_market,
        "margin_target": margin_target,
        "margin_market": margin_market,
        "total_cbm_sum": total_cbm_sum,
    }


# ---------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------
def generate_shipment_approval_pdf(shipment, tax_bank_account_name: str = "") -> bytes:
    """Build the multi-page approval PDF for a shipment (ORM with relations)."""
    data = build_shipment_report(shipment, tax_bank_account_name)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=10 * mm, leftMargin=10 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ShipTitle", parent=styles["Title"], fontSize=15, spaceAfter=2
    )
    subtitle_style = ParagraphStyle(
        "ShipSub", parent=styles["Normal"], fontSize=9,
        alignment=TA_CENTER, textColor=colors.HexColor("#555555"),
    )
    heading_style = ParagraphStyle(
        "ShipHeading", parent=styles["Heading2"], fontSize=11, spaceBefore=6, spaceAfter=4
    )
    cell_style = ParagraphStyle(
        "ShipCell", parent=styles["Normal"], fontSize=7, leading=9,
    )
    cell_bold = ParagraphStyle(
        "ShipCellBold", parent=cell_style, fontName="Helvetica-Bold",
    )

    story = []
    supplier_line = data["supplier"] or f"Shipment #{data['shipment_id']}"
    story.append(Paragraph(f"Import Shipment #{data['shipment_id']}", title_style))
    story.append(Paragraph(
        f"Supplier: {supplier_line} &nbsp;•&nbsp; Proforma: {_date_str(data['proforma_date'])}"
        f" &nbsp;•&nbsp; 1 RMB = {_ratio(data['exchange_rate'])} ETB",
        subtitle_style,
    ))
    story.append(Spacer(1, 4 * mm))

    # -------------------------------------------------------------
    # Page 1 - Landed Cost & Margin
    # -------------------------------------------------------------
    story.append(Paragraph("1. Landed Cost &amp; Margin", heading_style))

    meta_rows = [
        ["Payment Status", str(data["payment_status"]).capitalize(),
         "Allocation Basis", "Used CBM" if data["allocation_mode"] != "fixed" else "Fixed (68 CBM)"],
        ["Target Margin", f"{data['target_margin_pct']:,.2f}%",
         "Bank / LC", data["bank"] or "-"],
    ]
    meta_table = Table(meta_rows, colWidths=[38 * mm, 55 * mm, 38 * mm, 140 * mm])
    meta_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2f7")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#eef2f7")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 4 * mm))

    landed_header = [
        "Product", "Cartons", "Qty/Carton", "Total Qty", "FOB (ETB)",
        "Allocation (ETB)", "Total Tax (ETB)", "Total Cost (ETB)",
        "Landed Unit (ETB)", "Selling Price (ETB)", "Market Price (ETB)",
        "Implied Margin (%)",
    ]
    landed_data = [landed_header]
    for r in data["landed_rows"]:
        landed_data.append([
            Paragraph(r["name"], cell_style),
            _int_str(r["cartons"]),
            _int_str(r["qty_per_carton"]),
            _int_str(r["total_quantity"]),
            _money(r["fob_etb"]),
            _money(r["allocated"]),
            _money(r["total_tax"]),
            _money(r["total_cost"]),
            _money(r["landed_unit"]),
            _money(r["selling_price"]),
            _money(r["market_price"]),
            _pct_str(r["implied_margin"]),
        ])

    # A4 landscape content width is ~277 mm (297 - 2*10 margins).
    landed_cols = [46, 10, 12, 14, 22, 22, 20, 24, 22, 22, 22, 21]
    landed_cols = [float(w) * mm for w in landed_cols]

    landed_table = Table(landed_data, colWidths=landed_cols, repeatRows=1)
    landed_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#999999")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8fb")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(landed_table)
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph(
        f"Grand Total Landed Cost (ETB): {_money(data['grand_total_etb'])}",
        ParagraphStyle("GrandTotal", parent=styles["Heading3"],
                       fontSize=10, textColor=colors.HexColor("#1a6b3c")),
    ))
    story.append(Spacer(1, 2 * mm))

    profit_rows = [
        ["Total Landed Cost", _money(data["grand_total_etb"])],
        ["Total Selling (Target Margin)", _money(data["total_selling"])],
        ["Total Market Value", _money(data["total_market"])],
        ["Profit (Target Margin)", f"{_money(data['profit_target'])}  ({data['margin_target']:,.2f}%)"],
        ["Profit (Market Price)", f"{_money(data['profit_market'])}  ({data['margin_market']:,.2f}%)"],
        ["Market vs Target Difference", _money(data["profit_market"] - data["profit_target"])],
    ]
    profit_table = Table(profit_rows, colWidths=[100 * mm, 160 * mm])
    profit_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2f7")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(profit_table)

    # -------------------------------------------------------------
    # Page 2 - Costs & Allocation
    # -------------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("2. Costs &amp; Allocation", heading_style))

    if data["cost_rows"]:
        cost_header = ["Cost Type", "Amount (ETB)", "Paid Date", "Bank Account"]
        cost_data = [cost_header]
        for c in data["cost_rows"]:
            cost_data.append([
                Paragraph(c["type"], cell_style),
                _money(c["amount"]),
                _date_str(c["paid_date"]),
                c["bank"] or "-",
            ])
        cost_data.append([
            Paragraph("TOTAL", cell_bold),
            Paragraph(_money(data["total_costs"]), cell_bold),
            "", "",
        ])
        cost_table = Table(
            cost_data,
            colWidths=[70 * mm, 40 * mm, 40 * mm, 120 * mm],
            repeatRows=1,
        )
        cost_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("FONTSIZE", (0, 1), (-1, -1), 7.5),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#999999")),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eef2f7")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]))
        story.append(cost_table)
    else:
        story.append(Paragraph("No additional costs recorded.", styles["Normal"]))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Cost Allocation Breakdown (ETB)", heading_style))
    alloc_header = ["Product"] + list(data["cost_names"]) + ["Total (ETB)"]
    alloc_data = [alloc_header]
    for row in data["allocated_matrix"]:
        alloc_data.append(
            [Paragraph(row["name"], cell_style)]
            + [_money(v) for v in row["values"]]
            + [_money(row["total"])]
        )
    col_totals = [0.0] * len(data["cost_names"])
    for row in data["allocated_matrix"]:
        for j, v in enumerate(row["values"]):
            col_totals[j] += v
    alloc_data.append(
        ["TOTAL"] + [_money(v) for v in col_totals] + [_money(sum(col_totals))]
    )
    n_alloc_cols = len(alloc_header)
    alloc_widths = [60 * mm] + [(175 / max(n_alloc_cols - 1, 1)) * mm] * (n_alloc_cols - 1)
    alloc_table = Table(alloc_data, colWidths=alloc_widths, repeatRows=1)
    alloc_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#999999")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eef2f7")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f5f8fb")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(alloc_table)

    # -------------------------------------------------------------
    # Page 3 - Customs Tax
    # -------------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("3. Customs Tax", heading_style))

    tax_meta = [
        ["USD to ETB Rate", _ratio(data["usd_rate"])],
        ["Total USD", _money(data["total_usd"])],
        ["Sample Freight (ETB)", _money(data["sample_frt"])],
        ["Tax Rater", _ratio(data["rater"])],
        ["Tax Freight Ratio", _ratio(data["freight_ratio"])],
        ["Total Tax Payable (ETB)", _money(data["total_tax"])],
        ["Tax Payment",
         "Paid" if data["tax_paid"] else "Not paid"],
    ]
    if data["tax_paid"]:
        bank_disp = data["tax_bank_account"] or "-"
        tax_meta.append(["Payment Bank", bank_disp])
        tax_meta.append(["Payment Date", _date_str(data["tax_payment_date"])])
    tax_meta_table = Table(tax_meta, colWidths=[70 * mm, 200 * mm])
    tax_meta_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2f7")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(tax_meta_table)
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Product Tax Calculation", heading_style))
    tax_header = [
        "Item #", "Product", "Unit", "Qty/doz", "USD/doz", "Total USD",
        "Total ETB", "FRT Ratio", "FRT/CRT", "DPV/CRT", "Rater",
        "Total Tax ETB", "Tax/doz", "Tax/pcs",
    ]
    tax_data = [tax_header]
    for r in data["tax_rows"]:
        tax_data.append([
            r["item_number"],
            Paragraph(r["name"], cell_style),
            r["unit"],
            _money(r["qty_doz"]),
            _money(r["usd_per_dozen"]),
            _money(r["total_usd"]),
            _money(r["total_price_etb"]),
            _ratio(data["freight_ratio"]),
            _money(r["tax_frt_ctn"]),
            _money(r["tax_dpv_ctn"]),
            _ratio(data["rater"]),
            _money(r["total_tax_etb"]),
            _money(r["tax_per_dozen"]),
            _money(r["tax_per_unit"]),
        ])
    tax_data.append(
        ["", "TOTAL", "", "", "", "", "", "", "", "", "",
         Paragraph(_money(data["total_tax"]), cell_bold), "", ""]
    )

    tax_cols = [14, 38, 8, 13, 16, 18, 20, 15, 18, 20, 13, 22, 16, 16]
    tax_cols = [float(w) * mm for w in tax_cols]
    tax_table = Table(tax_data, colWidths=tax_cols, repeatRows=1)
    tax_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 6.5),
        ("FONTSIZE", (0, 1), (-1, -1), 6.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#999999")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (2, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eef2f7")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f5f8fb")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(tax_table)

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
