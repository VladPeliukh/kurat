"""Utilities for generating simple XLSX workbooks without external dependencies."""

from __future__ import annotations

from io import BytesIO
from typing import Iterable, Sequence
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


_CONTENT_TYPES_XML = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
"<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">\n"
"    <Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>\n"
"    <Default Extension=\"xml\" ContentType=\"application/xml\"/>\n"
"    <Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>\n"
"    <Override PartName=\"/xl/worksheets/sheet1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>\n"
"    <Override PartName=\"/xl/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>\n"
"</Types>\n"""

_RELS_XML = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
"<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">\n"
"    <Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/>\n"
"</Relationships>\n"""

_WORKBOOK_XML = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
"<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"\n"
"          xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">\n"
"    <sheets>\n"
"        <sheet name=\"Sheet1\" sheetId=\"1\" r:id=\"rId1\"/>\n"
"    </sheets>\n"
"</workbook>\n"""

_WORKBOOK_RELS_XML = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
"<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">\n"
"    <Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/>\n"
"    <Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/>\n"
"</Relationships>\n"""

_STYLES_XML = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
"<styleSheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">\n"
"    <fonts count=\"1\"><font/></fonts>\n"
"    <fills count=\"1\"><fill><patternFill patternType=\"none\"/></fill></fills>\n"
"    <borders count=\"1\"><border/></borders>\n"
"    <cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs>\n"
"    <cellXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/></cellXfs>\n"
"    <cellStyles count=\"1\"><cellStyle name=\"Normal\" xfId=\"0\" builtinId=\"0\"/></cellStyles>\n"
"</styleSheet>\n"""


def _column_letter(index: int) -> str:
    """Convert 1-based column index to Excel column letters."""

    if index < 1:
        raise ValueError("Column index must be positive")
    letters = []
    while index:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))


def _cell_xml(row: int, column: int, value: object) -> str:
    address = f"{_column_letter(column)}{row}"
    if value is None or value == "":
        return (
            f"<c r=\"{address}\" t=\"inlineStr\"><is><t></t></is></c>"
        )
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"<c r=\"{address}\" t=\"n\"><v>{value}</v></c>"
    text = escape(str(value))
    return (
        f"<c r=\"{address}\" t=\"inlineStr\"><is><t>{text}</t></is></c>"
    )


def _sheet_xml(headers: Sequence[object], rows: Iterable[Sequence[object]]) -> str:
    all_rows = [list(headers)] + [list(row) for row in rows]
    if not all_rows:
        dimension = "A1"
    else:
        last_row = len(all_rows)
        last_col = len(all_rows[0]) if all_rows[0] else 1
        dimension = f"A1:{_column_letter(last_col)}{last_row}"
    lines = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>",
        "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"",
        "           xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">",
        f"  <dimension ref=\"{dimension}\"/>",
        "  <sheetViews><sheetView workbookViewId=\"0\"/></sheetViews>",
        "  <sheetFormatPr defaultRowHeight=\"15\"/>",
        "  <sheetData>",
    ]
    for row_index, row_values in enumerate(all_rows, start=1):
        lines.append(f"    <row r=\"{row_index}\">")
        for column_index, cell_value in enumerate(row_values, start=1):
            lines.append("      " + _cell_xml(row_index, column_index, cell_value))
        lines.append("    </row>")
    lines.extend([
        "  </sheetData>",
        "</worksheet>",
    ])
    return "\n".join(lines) + "\n"


def build_simple_table_xlsx(headers: Sequence[object], rows: Iterable[Sequence[object]]) -> bytes:
    """Return XLSX bytes containing a single sheet with the provided data."""

    buffer = BytesIO()
    sheet_xml = _sheet_xml(headers, rows)
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
        archive.writestr("_rels/.rels", _RELS_XML)
        archive.writestr("xl/workbook.xml", _WORKBOOK_XML)
        archive.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS_XML)
        archive.writestr("xl/styles.xml", _STYLES_XML)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buffer.getvalue()


__all__ = ["build_simple_table_xlsx"]
