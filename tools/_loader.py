"""
Shared dataset loader for Survey Indsight tools.
Parses SurveyXact Excel-XML exports from the datasets/ folder.
"""

import os
import re
import sys
import statistics
from pathlib import Path


def find_dataset(cwd=None, explicit_path=None):
    """Locate the XML dataset file."""
    if explicit_path:
        return Path(explicit_path)
    base = Path(cwd or Path(__file__).parent.parent)
    datasets_dir = base / "datasets"
    if not datasets_dir.exists():
        sys.exit("❌ No 'datasets/' folder found. Run from the project root.")
    xml_files = sorted(datasets_dir.glob("*.xml"))
    if not xml_files:
        sys.exit("❌ No .xml file found in datasets/")
    return xml_files[0]


def _extract_sheet_rows(xml: str, sheet_name: str) -> list[list[str | None]]:
    """Extract rows from a named worksheet in SpreadsheetML XML."""
    sheet_match = re.search(
        rf'ss:Name="{re.escape(sheet_name)}"[\s\S]*?<\/Table>', xml
    )
    if not sheet_match:
        return []
    sheet_xml = sheet_match.group(0)
    rows = []
    for row_match in re.finditer(r"<Row[^>]*>([\s\S]*?)<\/Row>", sheet_xml):
        cells = []
        for cell_match in re.finditer(
            r"<Cell[^>]*>[\s\S]*?<Data[^>]*>([\s\S]*?)<\/Data>[\s\S]*?<\/Cell>",
            row_match.group(1),
        ):
            val = cell_match.group(1).strip()
            cells.append(val if val else None)
        rows.append(cells)
    return rows


def load(path=None, cwd=None) -> dict:
    """
    Load and parse a SurveyXact XML dataset.

    Returns a dict with:
      variables   : {varName: description}
      labels      : {varName: {scoreStr: labelText}}
      headers     : [column names in dataset order]
      respondents : [{varName: value, ...}, ...]
    """
    xml_path = find_dataset(cwd=cwd, explicit_path=path)
    xml = xml_path.read_text(encoding="utf-8")
    xml = xml.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&").replace("&quot;", '"')

    # Variables: varName -> description
    variables = {}
    for row in _extract_sheet_rows(xml, "Variables")[1:]:
        if row and row[0]:
            variables[row[0]] = (row[1] or row[0]) if len(row) > 1 else row[0]

    # Labels: varName -> {scoreStr -> label}
    labels: dict[str, dict[str, str]] = {}
    for row in _extract_sheet_rows(xml, "Labels"):
        if not row or not row[0]:
            continue
        var, val, label = row[0], (row[1] if len(row) > 1 else None), (row[2] if len(row) > 2 else None)
        if var and val:
            labels.setdefault(var, {})[val] = label or val

    # Dataset: first row = headers
    dataset_rows = _extract_sheet_rows(xml, "Dataset")
    headers = dataset_rows[0] if dataset_rows else []
    respondents = []
    for row in dataset_rows[1:]:
        record = {}
        for i, h in enumerate(headers):
            record[h] = row[i] if i < len(row) else None
        respondents.append(record)

    return {
        "variables": variables,
        "labels": labels,
        "headers": headers,
        "respondents": respondents,
        "path": str(xml_path),
    }


# ── Stats helpers ─────────────────────────────────────────────────────────────

def is_score_var(name: str) -> bool:
    return bool(re.match(r"^s_\d+$", name))


def numeric_vals(respondents: list, variable: str, exclude_na=True) -> list[int]:
    """Return valid numeric scores for a variable."""
    vals = []
    for r in respondents:
        try:
            v = int(r.get(variable) or "")
            if not (exclude_na and v == 6):
                vals.append(v)
        except (ValueError, TypeError):
            pass
    return vals


def stats(vals: list[int]) -> dict:
    """Compute mean, median, mode, stdev for a list of ints."""
    if not vals:
        return {"mean": None, "median": None, "mode": None, "sd": None, "n": 0}
    return {
        "mean": statistics.mean(vals),
        "median": statistics.median(vals),
        "mode": statistics.mode(vals),
        "sd": statistics.pstdev(vals),
        "n": len(vals),
    }


def distribution(vals: list[int], min_score=1, max_score=5) -> dict[int, int]:
    counts = {i: 0 for i in range(min_score, max_score + 1)}
    for v in vals:
        if v in counts:
            counts[v] += 1
    return counts


# ── ASCII chart ───────────────────────────────────────────────────────────────

def bar_chart(title: str, counts: dict, label_map: dict, total: int) -> str:
    BAR = 28
    max_val = max(counts.values(), default=1) or 1
    lines = [f"📊 {title}", "─" * 60]
    for key, count in counts.items():
        label = label_map.get(str(key), f"Score {key}")
        pct = round(count / total * 100) if total else 0
        bar = "█" * round(count / max_val * BAR)
        lines.append(f"{str(key):>2} │ {bar:<{BAR}} {count} ({pct}%)")
        lines.append(f"   │ {label}")
    lines.append("─" * 60)
    lines.append(f"   n = {total} responses")
    return "\n".join(lines)
