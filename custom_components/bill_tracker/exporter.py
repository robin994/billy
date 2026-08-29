"""CSV/XLSX/PDF import-export helpers for Billy.

The XLSX and PDF writers intentionally use only the Python standard library so
Billy does not need heavyweight runtime dependencies inside Home Assistant.
"""
from __future__ import annotations

import csv
import io
import math
import zipfile
from collections import defaultdict
from datetime import datetime
from html import escape as xml_escape
from typing import Any, Iterable

from .errors import billy_error
from .localization import category_label, report_labels

CSV_HEADERS = [
    "id",
    "category",
    "interval_months",
    "amount",
    "currency",
    "provider",
    "contract",
    "consumption",
    "consumption_unit",
    "billing_month",
    "paid",
    "payment_date",
    "due_date",
    "period_start",
    "period_end",
    "payer",
    "split",
    "note",
]

RECURRING_HEADERS = [
    "id",
    "name",
    "kind",
    "amount",
    "currency",
    "interval_months",
    "start_date",
    "end_date",
    "active",
    "auto_renew",
    "renewal_interval_months",
    "installment_count",
    "provider",
    "contract",
    "payer",
    "split",
    "next_due_date",
    "next_renewal_date",
    "monthly_equivalent",
    "remaining_installments",
    "remaining_amount",
    "reimbursement_status",
    "note",
]


def month_key(year: int, month: int) -> str:
    return f"{int(year):04d}-{int(month):02d}"


def month_tuple(value: str | None) -> tuple[int, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.strptime(text, "%Y-%m")
    except ValueError as err:
        raise billy_error("csv_invalid_month", text=text) from err
    return dt.year, dt.month


def iter_months(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    y, m = start
    while (y, m) <= end:
        result.append((y, m))
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return result


def filter_expenses(
    expenses: Iterable[dict[str, Any]],
    *,
    from_month: str | None = None,
    to_month: str | None = None,
    status: str = "all",
    category_id: str | None = None,
) -> list[dict[str, Any]]:
    start = month_tuple(from_month)
    end = month_tuple(to_month)
    if start and end and start > end:
        start, end = end, start
    wanted_status = status if status in {"all", "paid", "unpaid"} else "all"
    wanted_category = str(category_id or "")
    rows = []
    for item in expenses:
        key = (int(item.get("paid_year", 0)), int(item.get("paid_month", 0)))
        if start and key < start:
            continue
        if end and key > end:
            continue
        if wanted_category and wanted_category != "all" and str(item.get("category_id", "")) != wanted_category:
            continue
        paid = bool(item.get("paid", False))
        if wanted_status == "paid" and not paid:
            continue
        if wanted_status == "unpaid" and paid:
            continue
        rows.append(dict(item))
    rows.sort(
        key=lambda x: (
            int(x.get("paid_year", 0)),
            int(x.get("paid_month", 0)),
            str(x.get("created_at", "")),
        ),
        reverse=True,
    )
    return rows


def _split_text(item: dict[str, Any]) -> str:
    parts = []
    for part in item.get("split", []) or []:
        name = str(part.get("name") or part.get("payer_id") or "").strip()
        if not name:
            continue
        parts.append(f"{name}:{float(part.get('percentage', 0) or 0):g}")
    return "|".join(parts)


def expense_to_export_row(item: dict[str, Any], category: dict[str, Any] | None = None, *, currency: str = "EUR") -> dict[str, Any]:
    interval = int((category or {}).get("interval_months", item.get("interval_months", 1)) or 1)
    return {
        "id": str(item.get("id", "")),
        "category": str(item.get("category", "")),
        "interval_months": interval,
        "amount": f"{float(item.get('amount', 0) or 0):.2f}",
        "currency": str(item.get("currency") or currency),
        "provider": str(item.get("provider") or ""),
        "contract": str(item.get("contract") or ""),
        "consumption": "" if item.get("consumption") is None else f"{float(item.get('consumption') or 0):.4f}".rstrip("0").rstrip("."),
        "consumption_unit": str(item.get("consumption_unit") or (category or {}).get("consumption_unit") or ""),
        "billing_month": month_key(int(item.get("paid_year", item.get("year", 0))), int(item.get("paid_month", item.get("month", 0)))),
        "paid": "true" if bool(item.get("paid", False)) else "false",
        "payment_date": str(item.get("payment_date") or ""),
        "due_date": str(item.get("due_date") or ""),
        "period_start": str(item.get("period_start_date") or "")
        or month_key(int(item.get("period_start_year", 0)), int(item.get("period_start_month", 0))),
        "period_end": str(item.get("period_end_date") or "")
        or month_key(int(item.get("period_end_year", 0)), int(item.get("period_end_month", 0))),
        "payer": str(item.get("payer", "")),
        "split": _split_text(item),
        "note": str(item.get("note", "")),
    }


def csv_bytes(rows: list[dict[str, Any]], category_lookup: dict[str, dict[str, Any]], *, currency: str = "EUR") -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_HEADERS, extrasaction="ignore")
    writer.writeheader()
    for item in rows:
        writer.writerow(expense_to_export_row(item, category_lookup.get(str(item.get("category_id", ""))), currency=currency))
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def csv_template_bytes() -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_HEADERS)
    writer.writeheader()
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def recurring_to_export_row(item: dict[str, Any], *, currency: str = "EUR") -> dict[str, Any]:
    return {
        "id": str(item.get("id", "")),
        "name": str(item.get("name", "")),
        "kind": str(item.get("kind", "recurring")),
        "amount": f"{float(item.get('amount', 0) or 0):.2f}",
        "currency": str(item.get("currency") or currency),
        "interval_months": int(item.get("interval_months", 1) or 1),
        "start_date": str(item.get("start_date") or ""),
        "end_date": str(item.get("end_date") or ""),
        "active": "true" if bool(item.get("active", True)) else "false",
        "auto_renew": "true" if bool(item.get("auto_renew", False)) else "false",
        "renewal_interval_months": int(item.get("renewal_interval_months", 12) or 12),
        "installment_count": item.get("installment_count") or "",
        "provider": str(item.get("provider") or ""),
        "contract": str(item.get("contract") or ""),
        "payer": str(item.get("payer") or ""),
        "split": _split_text(item),
        "next_due_date": str(item.get("next_due_date") or ""),
        "next_renewal_date": str(item.get("next_renewal_date") or ""),
        "monthly_equivalent": f"{float(item.get('monthly_equivalent', 0) or 0):.2f}",
        "remaining_installments": item.get("remaining_installments") if item.get("remaining_installments") is not None else "",
        "remaining_amount": f"{float(item.get('remaining_amount', 0) or 0):.2f}" if item.get("remaining_amount") is not None else "",
        "reimbursement_status": str(item.get("reimbursement_status") or "none"),
        "note": str(item.get("note") or ""),
    }


def recurring_csv_bytes(rows: list[dict[str, Any]], *, currency: str = "EUR") -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=RECURRING_HEADERS, extrasaction="ignore")
    writer.writeheader()
    for item in rows:
        writer.writerow(recurring_to_export_row(item, currency=currency))
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


# ---------------------------------------------------------------------------
# Lightweight XLSX writer (Office Open XML, no external dependency)
# ---------------------------------------------------------------------------


def _excel_col(index: int) -> str:
    result = ""
    value = index
    while value:
        value, rem = divmod(value - 1, 26)
        result = chr(65 + rem) + result
    return result


def _xlsx_cell(ref: str, value: Any, *, style: int = 0) -> str:
    style_attr = f' s="{style}"' if style else ""
    if value is None:
        return f'<c r="{ref}"{style_attr}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"{style_attr}><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    text = xml_escape(str(value), quote=False)
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet_xml(data: list[list[Any]], widths: list[float] | None = None) -> str:
    cols = ""
    if widths:
        cols = "<cols>" + "".join(
            f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>' for i, width in enumerate(widths, 1)
        ) + "</cols>"
    rows = []
    for row_idx, row in enumerate(data, 1):
        cells = []
        for col_idx, value in enumerate(row, 1):
            cells.append(_xlsx_cell(f"{_excel_col(col_idx)}{row_idx}", value, style=1 if row_idx == 1 else 0))
        rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')
    max_col = _excel_col(max((len(x) for x in data), default=1))
    max_row = max(1, len(data))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{max_col}{max_row}"/>'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f'{cols}<sheetData>{"".join(rows)}</sheetData>'
        f'<autoFilter ref="A1:{max_col}{max_row}"/>'
        '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
        '</worksheet>'
    )


def _monthly_summary(rows: list[dict[str, Any]], range_start: tuple[int, int] | None, range_end: tuple[int, int] | None, labels: dict[str, str]) -> list[list[Any]]:
    if rows:
        min_key = min((int(x["paid_year"]), int(x["paid_month"])) for x in rows)
        max_key = max((int(x["paid_year"]), int(x["paid_month"])) for x in rows)
    else:
        now = datetime.now()
        min_key = max_key = (now.year, now.month)
    start = range_start or min_key
    end = range_end or max_key
    if start > end:
        start, end = end, start
    months = iter_months(start, end)
    paid = defaultdict(float)
    count = defaultdict(int)
    normalized = defaultdict(float)
    for item in rows:
        bill_key = (int(item["paid_year"]), int(item["paid_month"]))
        count[bill_key] += 1
        if bool(item.get("paid", False)):
            paid[bill_key] += float(item.get("amount", 0) or 0)
        sy, sm = int(item.get("period_start_year", item["paid_year"])), int(item.get("period_start_month", item["paid_month"]))
        ey, em = int(item.get("period_end_year", item["paid_year"])), int(item.get("period_end_month", item["paid_month"]))
        competence = iter_months((sy, sm), (ey, em))
        share = float(item.get("amount", 0) or 0) / max(1, len(competence))
        for key in competence:
            if start <= key <= end:
                normalized[key] += share
    table = [[labels["month"], labels["paid_total"], labels["normalized_cost"], labels["bills_count"]]]
    for key in months:
        table.append([month_key(*key), round(paid[key], 2), round(normalized[key], 2), count[key]])
    return table


def xlsx_bytes(rows: list[dict[str, Any]], category_lookup: dict[str, dict[str, Any]], *, from_month: str | None, to_month: str | None, currency: str = "EUR", language: str = "en") -> bytes:
    labels = report_labels(language)
    bills = [[
        labels["type"], labels["interval_months"], labels["amount"], labels["currency"], labels["provider"], labels["contract"], labels["consumption"], labels["unit"],
        labels["billing_month"], labels["paid"], labels["payment_date"], labels["due_date"], labels["period_start"], labels["period_end"], labels["payer"], labels["split"], labels["note"], labels["id"],
    ]]
    for item in rows:
        row = expense_to_export_row(item, category_lookup.get(str(item.get("category_id", ""))), currency=currency)
        bills.append([
            category_label(language, category_lookup.get(str(item.get("category_id", ""))), row["category"]), int(row["interval_months"]), float(row["amount"]), row["currency"], row["provider"], row["contract"],
            float(row["consumption"]) if row["consumption"] else None, row["consumption_unit"], row["billing_month"],
            bool(item.get("paid", False)), row["payment_date"], row["due_date"], row["period_start"], row["period_end"],
            row["payer"], row["split"], row["note"], row["id"],
        ])
    summary = _monthly_summary(rows, month_tuple(from_month), month_tuple(to_month), labels)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>''')
        zf.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>''')
        sheet_bills = xml_escape(labels["sheet_bills"], quote=True)
        sheet_summary = xml_escape(labels["sheet_summary"], quote=True)
        zf.writestr("xl/workbook.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="{sheet_bills}" sheetId="1" r:id="rId1"/><sheet name="{sheet_summary}" sheetId="2" r:id="rId2"/></sheets>
</workbook>''')
        zf.writestr("xl/_rels/workbook.xml.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>''')
        zf.writestr("xl/styles.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1976D2"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>''')
        zf.writestr("xl/worksheets/sheet1.xml", _sheet_xml(bills, [24, 15, 14, 10, 22, 22, 14, 10, 14, 10, 14, 14, 14, 14, 20, 28, 36, 34]))
        zf.writestr("xl/worksheets/sheet2.xml", _sheet_xml(summary, [16, 18, 26, 12]))
    return out.getvalue()


def recurring_xlsx_bytes(rows: list[dict[str, Any]], *, currency: str = "EUR") -> bytes:
    table = [RECURRING_HEADERS]
    for item in rows:
        exported = recurring_to_export_row(item, currency=currency)
        table.append([exported[key] for key in RECURRING_HEADERS])

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>''')
        zf.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>''')
        zf.writestr("xl/workbook.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Recurring" sheetId="1" r:id="rId1"/></sheets>
</workbook>''')
        zf.writestr("xl/_rels/workbook.xml.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>''')
        zf.writestr("xl/styles.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1976D2"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>''')
        zf.writestr("xl/worksheets/sheet1.xml", _sheet_xml(table, [28, 24, 16, 14, 10, 15, 16, 16, 10, 12, 18, 18, 22, 22, 20, 28, 16, 16, 20, 20, 18, 20, 36]))
    return out.getvalue()


# ---------------------------------------------------------------------------
# Lightweight PDF report writer (standard PDF fonts, no dependency)
# ---------------------------------------------------------------------------

A4_W = 595.0
A4_H = 842.0


def _pdf_escape(text: Any) -> bytes:
    raw = str(text if text is not None else "").encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _pdf_text(x: float, y: float, text: Any, size: float = 10, bold: bool = False) -> bytes:
    font = b"F2" if bold else b"F1"
    return b"0 g BT /" + font + f" {size:g} Tf {x:.1f} {y:.1f} Td (".encode() + _pdf_escape(text) + b") Tj ET\n"


def _pdf_rect(x: float, y: float, w: float, h: float, *, fill: float | None = None, stroke: float = 0.75) -> bytes:
    parts = []
    if fill is not None:
        parts.append(f"{fill:.3f} g ")
    parts.append(f"{stroke:.2f} w {x:.1f} {y:.1f} {w:.1f} {h:.1f} re ")
    parts.append("B\n" if fill is not None else "S\n")
    return "".join(parts).encode()


def _trend_data(rows: list[dict[str, Any]], start: tuple[int, int], end: tuple[int, int]) -> tuple[list[tuple[int, int]], list[float], list[float]]:
    months = iter_months(start, end)
    paid = defaultdict(float)
    normalized = defaultdict(float)
    for item in rows:
        key = (int(item["paid_year"]), int(item["paid_month"]))
        if bool(item.get("paid", False)) and start <= key <= end:
            paid[key] += float(item.get("amount", 0) or 0)
        sy, sm = int(item.get("period_start_year", item["paid_year"])), int(item.get("period_start_month", item["paid_month"]))
        ey, em = int(item.get("period_end_year", item["paid_year"])), int(item.get("period_end_month", item["paid_month"]))
        comp = iter_months((sy, sm), (ey, em))
        share = float(item.get("amount", 0) or 0) / max(1, len(comp))
        for comp_key in comp:
            if start <= comp_key <= end:
                normalized[comp_key] += share
    return months, [paid[x] for x in months], [normalized[x] for x in months]


def _pdf_chart(title: str, months: list[tuple[int, int]], values: list[float], *, x: float, y: float, w: float, h: float, line: bool = False, currency: str = "EUR", no_data_label: str = "No data") -> bytes:
    out = bytearray()
    out.extend(_pdf_text(x, y + h + 16, title, 11, True))
    if not months:
        out.extend(_pdf_text(x, y + h / 2, no_data_label, 9))
        return bytes(out)
    max_v = max(1.0, max(values, default=0.0) * 1.15)
    out.extend(f"0.82 G 0.5 w {x:.1f} {y:.1f} {w:.1f} {h:.1f} re S\n".encode())
    for step in range(1, 4):
        gy = y + h * step / 4
        out.extend(f"0.92 G 0.4 w {x:.1f} {gy:.1f} m {x+w:.1f} {gy:.1f} l S\n".encode())
    n = len(months)
    step_w = w / max(1, n)
    if line:
        points = []
        for i, value in enumerate(values):
            px = x + step_w * (i + 0.5)
            py = y + (float(value) / max_v) * h
            points.append((px, py))
        if points:
            cmd = ["0.12 0.47 0.82 RG 1.6 w", f"{points[0][0]:.1f} {points[0][1]:.1f} m"]
            cmd += [f"{px:.1f} {py:.1f} l" for px, py in points[1:]]
            cmd.append("S")
            out.extend((" ".join(cmd) + "\n").encode())
            for px, py in points:
                out.extend(f"0.12 0.47 0.82 rg {px-1.7:.1f} {py-1.7:.1f} 3.4 3.4 re f\n".encode())
    else:
        bar_w = max(2.0, min(18.0, step_w * 0.58))
        for i, value in enumerate(values):
            bh = max(0.0, float(value) / max_v * h)
            bx = x + step_w * (i + 0.5) - bar_w / 2
            out.extend(f"0.12 0.47 0.82 rg {bx:.1f} {y:.1f} {bar_w:.1f} {bh:.1f} re f\n".encode())
    every = max(1, math.ceil(n / 9))
    for i, key in enumerate(months):
        if i % every != 0 and i != n - 1:
            continue
        label = f"{key[1]:02d}/{str(key[0])[-2:]}"
        out.extend(_pdf_text(x + step_w * (i + 0.5) - 12, y - 13, label, 7))
    out.extend(_pdf_text(x, y + h - 10, f"max {max_v:.0f} {currency}", 7))
    return bytes(out)


def _wrap(text: str, width: int) -> list[str]:
    words = str(text or "").split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _build_pdf(contents: list[bytes]) -> bytes:
    objects: dict[int, bytes] = {
        1: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        2: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        4: b"<< /Type /Catalog /Pages 3 0 R >>",
    }
    page_ids = []
    next_id = 5
    for content in contents:
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        page_ids.append(page_id)
        objects[page_id] = (
            f"<< /Type /Page /Parent 3 0 R /MediaBox [0 0 {A4_W:g} {A4_H:g}] "
            f"/Resources << /Font << /F1 1 0 R /F2 2 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode()
        objects[content_id] = b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream"
    kids = " ".join(f"{x} 0 R" for x in page_ids)
    objects[3] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode()
    max_id = max(objects)
    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (max_id + 1)
    for obj_id in range(1, max_id + 1):
        body = objects[obj_id]
        offsets[obj_id] = len(result)
        result.extend(f"{obj_id} 0 obj\n".encode())
        result.extend(body)
        result.extend(b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {max_id+1}\n".encode())
    result.extend(b"0000000000 65535 f \n")
    for obj_id in range(1, max_id + 1):
        result.extend(f"{offsets[obj_id]:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {max_id+1} /Root 4 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(result)


def recurring_pdf_bytes(rows: list[dict[str, Any]], *, currency: str = "EUR", language: str = "en") -> bytes:
    title = "Spese ricorrenti" if str(language).lower().startswith("it") else "Recurring expenses"
    pages: list[bytes] = []
    current = bytearray()
    y = A4_H - 54
    current.extend(_pdf_text(42, y, title, 18, True))
    y -= 28
    if not rows:
        current.extend(_pdf_text(42, y, "Nessuna spesa ricorrente" if str(language).lower().startswith("it") else "No recurring expenses", 10))
        return _build_pdf([bytes(current)])

    for item in rows:
        if y < 95:
            pages.append(bytes(current))
            current = bytearray()
            y = A4_H - 54
            current.extend(_pdf_text(42, y, title, 16, True))
            y -= 28
        exported = recurring_to_export_row(item, currency=currency)
        current.extend(_pdf_text(42, y, exported["name"] or "-", 11, True))
        current.extend(_pdf_text(330, y, f"{exported['amount']} {exported['currency']}", 10, True))
        y -= 15
        meta = " · ".join(
            part
            for part in (
                exported["kind"],
                f"{exported['interval_months']}m",
                exported["provider"],
                exported["payer"],
            )
            if part
        )
        current.extend(_pdf_text(42, y, meta, 8))
        y -= 13
        dates = f"{exported['start_date']} -> {exported['end_date'] or '-'} · next {exported['next_due_date'] or '-'}"
        current.extend(_pdf_text(42, y, dates, 8))
        y -= 13
        status = f"{exported['reimbursement_status']} · monthly {exported['monthly_equivalent']} {exported['currency']}"
        current.extend(_pdf_text(42, y, status, 8))
        y -= 19
    pages.append(bytes(current))
    return _build_pdf(pages)


def pdf_bytes(
    rows: list[dict[str, Any]],
    category_lookup: dict[str, dict[str, Any]],
    *,
    from_month: str | None,
    to_month: str | None,
    trend: str = "both",
    currency: str = "EUR",
    language: str = "en",
) -> bytes:
    labels = report_labels(language)
    now = datetime.now()
    if rows:
        data_start = min((int(x["paid_year"]), int(x["paid_month"])) for x in rows)
        data_end = max((int(x["paid_year"]), int(x["paid_month"])) for x in rows)
    else:
        data_start = data_end = (now.year, now.month)
    start = month_tuple(from_month) or data_start
    end = month_tuple(to_month) or data_end
    if start > end:
        start, end = end, start
    months, paid_values, normalized_values = _trend_data(rows, start, end)
    paid_rows = [x for x in rows if bool(x.get("paid", False))]
    unpaid_rows = [x for x in rows if not bool(x.get("paid", False))]
    total = sum(float(x.get("amount", 0) or 0) for x in rows)
    category_totals: dict[str, float] = defaultdict(float)
    for item in rows:
        category = category_lookup.get(str(item.get("category_id", "")))
        display_name = category_label(language, category, str(item.get("category", "")))
        category_totals[display_name] += float(item.get("amount", 0) or 0)

    pages: list[bytes] = []
    p = bytearray()
    p.extend(_pdf_text(42, 802, labels["report_title"], 19, True))
    p.extend(_pdf_text(42, 783, f"{labels['period']}: {month_key(*start)} - {month_key(*end)}", 10))
    p.extend(_pdf_text(420, 802, f"{labels['generated']}: {now:%Y-%m-%d}", 8))

    stats = [
        (labels["bills"], str(len(rows))),
        (labels["total"], f"{total:.2f} {currency}"),
        (labels["paid"], f"{len(paid_rows)} / {sum(float(x.get('amount', 0) or 0) for x in paid_rows):.2f} {currency}"),
        (labels["unpaid"], f"{len(unpaid_rows)} / {sum(float(x.get('amount', 0) or 0) for x in unpaid_rows):.2f} {currency}"),
    ]
    x0 = 42
    for label, value in stats:
        p.extend(_pdf_rect(x0, 724, 122, 46, fill=0.97, stroke=0.4))
        p.extend(_pdf_text(x0 + 8, 752, label, 8))
        p.extend(_pdf_text(x0 + 8, 735, value, 11, True))
        x0 += 132

    chart_y = 485
    trend = trend if trend in {"payments", "normalized", "both"} else "both"
    if trend == "both":
        p.extend(_pdf_chart(labels["payments_trend"], months, paid_values, x=42, y=chart_y, w=245, h=165, line=False, currency=currency, no_data_label=labels["no_data"]))
        p.extend(_pdf_chart(labels["normalized_cost"], months, normalized_values, x=308, y=chart_y, w=245, h=165, line=True, currency=currency, no_data_label=labels["no_data"]))
    elif trend == "payments":
        p.extend(_pdf_chart(labels["payments_trend"], months, paid_values, x=42, y=chart_y, w=511, h=165, line=False, currency=currency, no_data_label=labels["no_data"]))
    else:
        p.extend(_pdf_chart(labels["normalized_cost"], months, normalized_values, x=42, y=chart_y, w=511, h=165, line=True, currency=currency, no_data_label=labels["no_data"]))

    p.extend(_pdf_text(42, 438, labels["totals_by_type"], 12, True))
    y = 418
    for name, amount in sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:12]:
        p.extend(_pdf_text(50, y, str(name)[:42], 9))
        p.extend(_pdf_text(400, y, f"{amount:.2f} {currency}", 9, True))
        y -= 17
        if y < 210:
            break
    p.extend(_pdf_text(42, 190, labels["report_note"], 7))
    pages.append(bytes(p))

    detail_rows = rows or []
    per_page = 20
    for offset in range(0, len(detail_rows), per_page):
        chunk = detail_rows[offset:offset + per_page]
        page = bytearray()
        page.extend(_pdf_text(42, 802, labels["bill_details"], 15, True))
        page.extend(_pdf_text(455, 802, f"{offset+1}-{offset+len(chunk)} / {len(detail_rows)}", 8))
        headers = [(42, labels["month"]), (92, labels["type"]), (260, labels["amount"]), (325, labels["status"]), (385, labels["due_date"]), (465, labels["payment_date"])]
        page.extend(_pdf_rect(38, 764, 520, 24, fill=0.94, stroke=0.3))
        for hx, label in headers:
            page.extend(_pdf_text(hx, 773, label, 8, True))
        yy = 744
        for item in chunk:
            page.extend(f"0.88 G 0.35 w 38 {yy-5:.1f} m 558 {yy-5:.1f} l S\n".encode())
            page.extend(_pdf_text(42, yy, month_key(int(item["paid_year"]), int(item["paid_month"])), 8))
            page.extend(_pdf_text(92, yy, category_label(language, category_lookup.get(str(item.get("category_id", ""))), str(item.get("category", "")))[:27], 8))
            page.extend(_pdf_text(260, yy, f"{float(item.get('amount', 0) or 0):.2f} {currency}", 8))
            page.extend(_pdf_text(325, yy, labels["paid"] if bool(item.get("paid", False)) else labels["unpaid"], 8))
            page.extend(_pdf_text(385, yy, str(item.get("due_date") or "-"), 8))
            page.extend(_pdf_text(465, yy, str(item.get("payment_date") or "-"), 8))
            meta = []
            provider = str(item.get("provider") or "").strip()
            contract = str(item.get("contract") or "").strip()
            if provider or contract:
                meta.append(" / ".join(x for x in (provider, contract) if x))
            if item.get("consumption") is not None and item.get("consumption_unit"):
                meta.append(f"{labels['consumption']}: {float(item.get('consumption') or 0):g} {item.get('consumption_unit')}")
            note = str(item.get("note") or "").strip()
            if note:
                meta.append(note)
            if meta:
                page.extend(_pdf_text(92, yy - 11, _wrap(" · ".join(meta), 68)[0][:68], 6.5))
            yy -= 34
        pages.append(bytes(page))
    return _build_pdf(pages)

CSV_ALIASES = {
    "id": ("id", "expense_id"),
    "category": ("category", "bill_type", "type", "tipo", "bolletta", "categoria"),
    "interval_months": ("interval_months", "interval", "recurrence_months", "frequenza_mesi"),
    "amount": ("amount", "importo", "value", "totale"),
    "currency": ("currency", "valuta"),
    "provider": ("provider", "supplier", "fornitore", "compagnia"),
    "contract": ("contract", "plan", "tariff", "contratto", "offerta"),
    "consumption": ("consumption", "usage", "consumo"),
    "consumption_unit": ("consumption_unit", "unit", "usage_unit", "unita_consumo", "unità_consumo"),
    "billing_month": ("billing_month", "bill_month", "month_date", "mese_bolletta"),
    "year": ("year", "anno"),
    "month": ("month", "mese"),
    "paid": ("paid", "pagata", "status", "stato"),
    "payment_date": ("payment_date", "paid_date", "data_pagamento"),
    "due_date": ("due_date", "expiration_date", "expiry_date", "scadenza", "data_scadenza"),
    "period_start": ("period_start", "competence_start", "periodo_inizio", "competenza_inizio"),
    "period_end": ("period_end", "competence_end", "periodo_fine", "competenza_fine"),
    "payer": ("payer", "paid_by", "pagatore", "pagata_da"),
    "split": ("split", "division", "quote", "divisione"),
    "note": ("note", "notes", "nota", "note_bolletta"),
}


def _normalize_header(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def parse_csv_records(text: str) -> list[tuple[int, dict[str, str]]]:
    raw_text = str(text or "").lstrip("\ufeff")
    if not raw_text.strip():
        raise billy_error("csv_empty")
    sample = raw_text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(raw_text), dialect=dialect)
    if not reader.fieldnames:
        raise billy_error("csv_no_headers")
    normalized_fields = {_normalize_header(name): name for name in reader.fieldnames if name is not None}
    alias_to_original: dict[str, str] = {}
    for canonical, aliases in CSV_ALIASES.items():
        for alias in aliases:
            if alias in normalized_fields:
                alias_to_original[canonical] = normalized_fields[alias]
                break
    if "category" not in alias_to_original or "amount" not in alias_to_original:
        raise billy_error("csv_missing_columns")
    if "billing_month" not in alias_to_original and not ({"year", "month"} <= set(alias_to_original)):
        raise billy_error("csv_missing_period_columns")
    result: list[tuple[int, dict[str, str]]] = []
    for line_no, raw in enumerate(reader, start=2):
        if not raw or not any(str(value or "").strip() for value in raw.values()):
            continue
        row = {}
        for canonical, original in alias_to_original.items():
            row[canonical] = str(raw.get(original, "") or "").strip()
        result.append((line_no, row))
    if not result:
        raise billy_error("csv_no_rows")
    return result


def parse_csv_bool(value: str) -> bool:
    text = str(value or "").strip().casefold()
    if text in {"", "0", "false", "no", "n", "unpaid", "da_pagare", "da pagare", "non_pagata", "non pagata"}:
        return False
    if text in {"1", "true", "yes", "y", "paid", "pagata", "si", "sì"}:
        return True
    raise billy_error("csv_invalid_paid", value=value)


def parse_csv_amount(value: str) -> float:
    text = str(value or "").strip().replace(" ", "")
    if not text:
        raise billy_error("amount_missing")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    return float(text)
