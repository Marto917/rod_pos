"""Generador mínimo de .xlsx sin dependencias externas (Open XML)."""
from __future__ import annotations

import os
import zipfile
from xml.sax.saxutils import escape


def _col_letter(idx: int) -> str:
    """1 -> A, 27 -> AA"""
    letters = []
    n = idx
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters.append(chr(65 + rem))
    return "".join(reversed(letters))


def _cell_xml(row: int, col: int, value) -> str:
    ref = "%s%d" % (_col_letter(col), row)
    if value is None:
        return '<c r="%s"/>' % ref
    if isinstance(value, bool):
        return '<c r="%s" t="b"><v>%d</v></c>' % (ref, 1 if value else 0)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return '<c r="%s"><v>%s</v></c>' % (ref, value)
    text = escape(str(value))
    return '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, text)


def write_xlsx(path: str, sheets: dict[str, list[list]]) -> str:
    """
    sheets: { "Hoja1": [[headers...], [row...], ...] }
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    sheet_names = list(sheets.keys())
    if not sheet_names:
        raise ValueError("Se necesita al menos una hoja")

    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
    ]
    for i in range(1, len(sheet_names) + 1):
        content_types.append(
            '<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            % i
        )
    content_types.append("</Types>")

    workbook_rels = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]
    for i, _name in enumerate(sheet_names, start=1):
        workbook_rels.append(
            '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>'
            % (i, i)
        )
    workbook_rels.append("</Relationships>")

    sheets_xml = []
    for i, name in enumerate(sheet_names, start=1):
        safe = escape(name[:31] or ("Hoja%d" % i))
        sheets_xml.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (safe, i, i))

    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>%s</sheets></workbook>" % "".join(sheets_xml)
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "\n".join(content_types))
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", "\n".join(workbook_rels))
        for i, name in enumerate(sheet_names, start=1):
            rows = sheets[name] or [[]]
            row_xml = []
            for r_idx, row in enumerate(rows, start=1):
                cells = []
                for c_idx, val in enumerate(row, start=1):
                    cells.append(_cell_xml(r_idx, c_idx, val))
                row_xml.append('<row r="%d">%s</row>' % (r_idx, "".join(cells)))
            sheet_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                "<sheetData>%s</sheetData></worksheet>" % "".join(row_xml)
            )
            zf.writestr("xl/worksheets/sheet%d.xml" % i, sheet_xml)

    return path
