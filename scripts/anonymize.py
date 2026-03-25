#!/usr/bin/env python3
"""
Anonymise a SurveyXact dataset by removing personally identifiable information (PII).

What is removed:
  - Columns whose names indicate PII (email, name, address, phone, etc.)
    → cell values replaced with [REMOVED]
  - Email addresses found inside free-text responses
    → replaced with [EMAIL REMOVED]
  - Phone numbers found inside free-text responses
    → replaced with [PHONE REMOVED]
  - URLs found inside free-text responses
    → replaced with [URL REMOVED]

The original file is NOT modified. Output is saved as:
  <dataset_dir>/<stem>_anonymized.xlsx

Works directly on the xlsx zip structure — no third-party dependencies required.

Usage:
  python3 scripts/anonymize.py --dataset datasets/myfile.xlsx
"""

import argparse
import io
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _loader import find_dataset, get_output_dir

# ── PII column name patterns ───────────────────────────────────────────────────
PII_COL_PATTERNS = re.compile(
    r"""(?ix)
    \b(
      e?mail | e\-mail |
      name | navn | vorname | nachname | firstname | lastname |
      fornavn | efternavn | fullname | full_name |
      address | adresse | addr | street | gade | vej | straße |
      zip | postal | postcode | postnr |
      phone | telefon | tlf | tel | mobile | mobil | handy | cellphone |
      ssn | cpr | cvr | personnummer | personnr |
      ip_?address | ipaddr
    )\b
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ── Regex patterns for PII inside free-text ───────────────────────────────────
RE_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.]{2,}", re.IGNORECASE)
RE_PHONE = re.compile(
    r"""(?x)
    (?:\+?\d{1,3}[\s\-.])?         # optional country code
    (?:\(?\d{2,4}\)?[\s\-.]?)      # area code
    \d{2,4}[\s\-.]?                # first group
    \d{2,4}[\s\-.]?                # second group
    \d{2,4}                        # third group
    """,
)
RE_URL = re.compile(r"https?://\S+", re.IGNORECASE)

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ET.register_namespace("", NS)


def _tag(name: str) -> str:
    return f"{{{NS}}}{name}"


def _scrub_text(text: str) -> str:
    """Apply regex-based PII scrubbing to a free-text string."""
    text = RE_EMAIL.sub("[EMAIL REMOVED]", text)
    text = RE_URL.sub("[URL REMOVED]", text)
    text = RE_PHONE.sub("[PHONE REMOVED]", text)
    return text


def _find_dataset_sheet(zf: zipfile.ZipFile) -> str:
    """Return the zip-internal path to the Dataset sheet (e.g. xl/worksheets/sheet3.xml)."""
    wb_xml  = zf.read("xl/workbook.xml").decode("utf-8")
    rel_xml = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")

    wb_root  = ET.fromstring(wb_xml)
    rel_root = ET.fromstring(rel_xml)

    # Map rId → target file
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    rid_to_target = {
        el.get("Id"): el.get("Target")
        for el in rel_root.findall(f"{{{rel_ns}}}Relationship")
    }

    # Find the sheet named "Dataset"
    sheets_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    for sheet_el in wb_root.iter(f"{{{sheets_ns}}}sheet"):
        if sheet_el.get("name", "").lower() == "dataset":
            rid = sheet_el.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = rid_to_target.get(rid, "")
            return "xl/" + target if not target.startswith("xl/") else target

    raise ValueError("No 'Dataset' sheet found in workbook.")


def anonymize(src_path: Path, dst_path: Path | None = None) -> Path:
    if dst_path is None:
        output_dir = get_output_dir(src_path)
        dst_path = output_dir / f"{src_path.stem}_anonymized.xlsx"

    with zipfile.ZipFile(src_path, "r") as zf:
        sheet_path = _find_dataset_sheet(zf)
        sheet_xml  = zf.read(sheet_path).decode("utf-8")
        root = ET.fromstring(sheet_xml)

        # ── Parse header row to find PII column indices ─────────────────────
        sheet_data = root.find(_tag("sheetData"))
        rows = list(sheet_data)
        header_row = rows[0]

        pii_col_indices: set[int] = set()   # 0-based column index
        headers: list[str] = []

        for idx, cell in enumerate(header_row):
            val = ""
            is_el = cell.find(_tag("is"))
            if is_el is not None:
                t_el = is_el.find(_tag("t"))
                val = t_el.text or "" if t_el is not None else ""
            v_el = cell.find(_tag("v"))
            if v_el is not None and not val:
                val = v_el.text or ""
            headers.append(val)
            if PII_COL_PATTERNS.search(val):
                pii_col_indices.add(idx)

        pii_headers = [headers[i] for i in sorted(pii_col_indices)]
        print(f"  PII columns detected: {pii_headers or 'none'}")

        # ── Process data rows ────────────────────────────────────────────────
        cells_wiped     = 0
        text_scrubbed   = 0

        for row in rows[1:]:   # skip header
            for col_idx, cell in enumerate(row):
                is_el = cell.find(_tag("is"))
                if is_el is None:
                    continue   # numeric cell — skip
                t_el = is_el.find(_tag("t"))
                if t_el is None:
                    continue
                original = t_el.text or ""

                if col_idx in pii_col_indices:
                    if original.strip():
                        t_el.text = "[REMOVED]"
                        cells_wiped += 1
                else:
                    scrubbed = _scrub_text(original)
                    if scrubbed != original:
                        t_el.text = scrubbed
                        text_scrubbed += 1

        # ── Write new xlsx ────────────────────────────────────────────────────
        modified_sheet = ET.tostring(root, encoding="unicode", xml_declaration=False)
        modified_sheet = '<?xml version="1.0" encoding="UTF-8"?>\n' + modified_sheet

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as out_zf:
            for item in zf.infolist():
                if item.filename == sheet_path:
                    out_zf.writestr(item, modified_sheet.encode("utf-8"))
                else:
                    out_zf.writestr(item, zf.read(item.filename))

    dst_path.write_bytes(buf.getvalue())

    print(f"  PII cells wiped:       {cells_wiped}")
    print(f"  Text cells scrubbed:   {text_scrubbed}")
    return dst_path


# ── CLI ────────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--dataset", help="Path to dataset file (.xlsx)")
parser.add_argument("--output",  help="Output path for anonymized file (default: <output_dir>/<stem>_anonymized.xlsx)")
args = parser.parse_args()

src = find_dataset(cwd=Path(__file__).parent.parent, explicit_path=args.dataset)

if src.suffix.lower() != ".xlsx":
    sys.exit("❌ Anonymisation currently supports .xlsx files only.")

dst_path = Path(args.output) if args.output else None

print(f"Anonymising: {src}")
dst = anonymize(src, dst_path)
print(f"\n✅ Anonymised dataset saved to: {dst}")
print("   The original file has NOT been modified.")
