"""
Survey Indsight — shared dataset loader.

Handles SurveyXact Excel-XML (.xml) and OOXML (.xlsx) exports.
Auto-detects variable types and normalises all scores to a 0-100 scale
so tools work identically across datasets.

Variable type taxonomy
──────────────────────
  score_1_5   : Likert 1–5 (opt. 6 = N/A)
  score_0_100 : Slider 0/25/50/75/100 (or similar 0-100 range)
  score_1_10  : NPS / satisfaction 1–10
  binary      : Yes/No encoded as 1/2 or 0/1
  status      : statoverall_* completion flags
  text        : Free-text / open-ended
  email       : Respondent e-mail
  other       : Anything else
"""

import re
import sys
import statistics
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


# ── File discovery ─────────────────────────────────────────────────────────────

# Claude skill environments mount a writable output directory here.
# All other environments fall back to writing alongside the source dataset.
CLAUDE_OUTPUT_DIR = Path("/mnt/user-data/outputs")


def get_output_dir(dataset_path: Path) -> Path:
    """Return the directory where output files should be written.

    Prefers /mnt/user-data/outputs when running inside Claude (read-only skill
    folder), otherwise falls back to the dataset's own directory.
    """
    if CLAUDE_OUTPUT_DIR.exists() and CLAUDE_OUTPUT_DIR.is_dir():
        return CLAUDE_OUTPUT_DIR
    return dataset_path.parent


def list_datasets(cwd=None) -> list:
    """Return all dataset files found in the datasets/ folder, sorted by name."""
    base = Path(cwd or Path(__file__).parent.parent)
    datasets_dir = base / "datasets"
    if not datasets_dir.exists():
        return []
    files = []
    for pattern in ("*.xlsx", "*.xml"):
        files += sorted(f for f in datasets_dir.glob(pattern)
                        if not f.name.startswith(".") and ":" not in f.name)
    return files


def find_dataset(cwd=None, explicit_path=None) -> Path:
    if explicit_path:
        p = Path(explicit_path).expanduser().resolve()
        if not p.exists():
            sys.exit(f"❌ File not found: {explicit_path}")
        return p
    files = list_datasets(cwd)
    if not files:
        sys.exit("❌ No .xml or .xlsx file found in datasets/")
    return files[0]


# ── SpreadsheetML (Excel-XML) parser ──────────────────────────────────────────

def _extract_sheet_rows(xml: str, sheet_name: str) -> list:
    match = re.search(rf'ss:Name="{re.escape(sheet_name)}"[\s\S]*?<\/Table>', xml)
    if not match:
        return []
    rows = []
    for row_m in re.finditer(r"<Row[^>]*>([\s\S]*?)<\/Row>", match.group(0)):
        cells = []
        for cell_m in re.finditer(
            r"<Cell[^>]*>[\s\S]*?<Data[^>]*>([\s\S]*?)<\/Data>[\s\S]*?<\/Cell>",
            row_m.group(1),
        ):
            v = cell_m.group(1).strip()
            cells.append(v if v else None)
        rows.append(cells)
    return rows


def _parse_xml(xml_path: Path) -> dict:
    xml = xml_path.read_text(encoding="utf-8")
    xml = xml.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&").replace("&quot;", '"')

    variables = {}
    for row in _extract_sheet_rows(xml, "Variables")[1:]:
        if row and row[0]:
            variables[row[0]] = (row[1] or row[0]) if len(row) > 1 else row[0]

    labels: dict = {}
    for row in _extract_sheet_rows(xml, "Labels"):
        if not row or not row[0]:
            continue
        var, val, lbl = row[0], (row[1] if len(row) > 1 else None), (row[2] if len(row) > 2 else None)
        if var and val:
            labels.setdefault(var, {})[val] = lbl or val

    dataset_rows = _extract_sheet_rows(xml, "Dataset")
    headers = dataset_rows[0] if dataset_rows else []
    respondents = []
    for row in dataset_rows[1:]:
        record = {h: (row[i] if i < len(row) else None) for i, h in enumerate(headers)}
        respondents.append(record)

    return {"variables": variables, "labels": labels,
            "headers": headers, "respondents": respondents, "path": str(xml_path)}


# ── OOXML (.xlsx) parser ───────────────────────────────────────────────────────

def _parse_xlsx(xlsx_path: Path) -> dict:
    NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

    with zipfile.ZipFile(xlsx_path) as z:
        shared_strings: list = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{{{NS}}}si"):
                shared_strings.append("".join(t.text or "" for t in si.iter(f"{{{NS}}}t")))

        wb_root = ET.fromstring(z.read("xl/workbook.xml"))
        rels_root = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rel_map = {r.get("Id"): r.get("Target") for r in rels_root}
        sheet_files: dict = {}
        for sheet in wb_root.findall(f".//{{{NS}}}sheet"):
            name = sheet.get("name", "")
            rid = sheet.get(f"{{{REL_NS}}}id", "")
            target = rel_map.get(rid, "")
            if target:
                sheet_files[name] = f"xl/{target}" if not target.startswith("xl/") else target

        def col_index(ref: str) -> int:
            idx = 0
            for ch in ref.upper():
                idx = idx * 26 + (ord(ch) - ord("A") + 1)
            return idx

        def read_sheet(sheet_name: str) -> list:
            path = sheet_files.get(sheet_name)
            if not path or path not in z.namelist():
                return []
            rows = []
            for row_el in ET.fromstring(z.read(path)).findall(f".//{{{NS}}}row"):
                cells_raw: dict = {}
                for c in row_el.findall(f"{{{NS}}}c"):
                    col_ref = "".join(ch for ch in (c.get("r", "") or "") if ch.isalpha())
                    t = c.get("t", "")
                    v_el = c.find(f"{{{NS}}}v")
                    is_el = c.find(f"{{{NS}}}is")
                    val = None
                    if t == "inlineStr" and is_el is not None:
                        val = "".join(te.text or "" for te in is_el.iter(f"{{{NS}}}t")).strip() or None
                    elif v_el is not None and v_el.text is not None:
                        if t == "s":
                            idx = int(v_el.text)
                            val = shared_strings[idx] if idx < len(shared_strings) else ""
                        else:
                            raw = v_el.text
                            try:
                                f = float(raw)
                                val = str(int(f)) if f == int(f) else raw
                            except ValueError:
                                val = raw
                    cells_raw[col_ref] = val
                if not cells_raw:
                    continue
                max_col = max(col_index(k) for k in cells_raw)
                row_list = [None] * max_col
                for ref, val in cells_raw.items():
                    row_list[col_index(ref) - 1] = val
                rows.append(row_list)
            return rows

        variables = {}
        for row in read_sheet("Variables")[1:]:
            if row and row[0]:
                variables[row[0]] = (row[1] or row[0]) if len(row) > 1 else row[0]

        labels: dict = {}
        for row in read_sheet("Labels"):
            if not row or not row[0]:
                continue
            var, val, lbl = row[0], (row[1] if len(row) > 1 else None), (row[2] if len(row) > 2 else None)
            if var and val:
                labels.setdefault(var, {})[str(val)] = lbl or str(val)

        dataset_rows = read_sheet("Dataset")
        headers = [str(h) if h is not None else "" for h in (dataset_rows[0] if dataset_rows else [])]
        respondents = []
        for row in dataset_rows[1:]:
            record = {h: (row[i] if i < len(row) else None) for i, h in enumerate(headers)}
            respondents.append(record)

    return {"variables": variables, "labels": labels,
            "headers": headers, "respondents": respondents, "path": str(xlsx_path)}


# ── Variable type detection ────────────────────────────────────────────────────

_SLIDER_VALUES = {0, 25, 50, 75, 100}
_STATUS_PATTERN = re.compile(r"^statoverall_\d+$")
_EMAIL_PATTERN = re.compile(r"^(email|e.?mail)$", re.I)
_COMMENT_PATTERN = re.compile(r"^(komm?_|comment|s_\d+[a-z])", re.I)


def detect_var_type(name: str, values: list) -> str:
    """Infer the variable type from its name and observed values."""
    if _STATUS_PATTERN.match(name):
        return "status"
    if _EMAIL_PATTERN.match(name):
        return "email"

    # Collect numeric values
    nums = []
    has_text = False
    for v in values:
        if v is None or v == "":
            continue
        try:
            nums.append(float(v))
        except (ValueError, TypeError):
            has_text = True

    if has_text or not nums:
        return "text"

    unique = set(int(x) if x == int(x) else x for x in nums)
    int_unique = {int(x) for x in nums if x == int(x)}

    # Binary yes/no
    if int_unique <= {0, 1} or int_unique <= {1, 2}:
        return "binary"

    # 1–5 Likert (opt. 6 = N/A) — check BEFORE 1-10 since {1-6} ⊂ {1-10}
    if max(nums) <= 6 and int_unique <= set(range(1, 7)):
        return "score_1_5"

    # 0-100 slider (values are multiples of 25, or any continuous 0-100 range)
    if int_unique <= _SLIDER_VALUES or (max(nums) > 10 and max(nums) <= 100):
        return "score_0_100"

    # 1–10 scale (NPS etc.)
    if int_unique <= set(range(0, 11)):
        return "score_1_10"

    return "other"


def _na_values_for(var_type: str) -> set:
    """Values considered N/A for a given type."""
    return {6} if var_type == "score_1_5" else set()


def normalize_score(value, var_type: str) -> float | None:
    """Convert a raw score to 0-100 scale."""
    try:
        v = float(value)
    except (ValueError, TypeError):
        return None
    if var_type == "score_0_100":
        return v
    if var_type == "score_1_5":
        return (v - 1) / 4 * 100
    if var_type == "score_1_10":
        return (v - 1) / 9 * 100
    if var_type == "binary":
        return v * 100 if v in (0, 1) else (v - 1) * 100
    return v


# ── Main load function ─────────────────────────────────────────────────────────

def load(path=None, cwd=None) -> dict:
    """
    Load a SurveyXact dataset and enrich it with type metadata.

    Returned dict keys:
      variables   : {varName: description}
      labels      : {varName: {scoreStr: labelText}}
      headers     : [all column names]
      respondents : [{varName: rawValue, ...}, ...]
      var_meta    : {varName: {type, na_values, score_vars, normalized_mean, ...}}
      score_vars  : [varNames that are scoreable, sorted by original order]
      path        : str
    """
    p = find_dataset(cwd=cwd, explicit_path=path)
    raw = _parse_xlsx(p) if p.suffix.lower() == ".xlsx" else _parse_xml(p)

    variables = raw["variables"]
    respondents = raw["respondents"]

    # Build per-variable metadata
    var_meta: dict = {}
    score_vars: list = []

    for name in variables:
        all_vals = [r.get(name) for r in respondents]
        vtype = detect_var_type(name, all_vals)
        na_vals = _na_values_for(vtype)

        meta: dict = {"type": vtype, "na_values": na_vals}

        if vtype.startswith("score_") or vtype == "binary":
            # Collect clean numeric values (excluding N/A)
            clean: list = []
            for r in respondents:
                raw_v = r.get(name)
                if raw_v is None or raw_v == "":
                    continue
                try:
                    fv = float(raw_v)
                    if int(fv) in na_vals:
                        continue
                    clean.append(fv)
                except (ValueError, TypeError):
                    pass

            if clean:
                norm = [normalize_score(v, vtype) for v in clean]
                norm = [x for x in norm if x is not None]
                meta["n"] = len(clean)
                meta["raw_mean"] = statistics.mean(clean)
                meta["mean"] = statistics.mean(norm) if norm else None
                meta["median"] = statistics.median(norm) if norm else None
                try:
                    meta["mode"] = statistics.mode(norm)
                except statistics.StatisticsError:
                    meta["mode"] = None
                meta["sd"] = statistics.pstdev(norm) if norm else None
                meta["min_raw"] = min(clean)
                meta["max_raw"] = max(clean)
                score_vars.append(name)
            else:
                meta["n"] = 0

        var_meta[name] = meta

    raw["var_meta"] = var_meta
    raw["score_vars"] = score_vars
    return raw


# ── Helpers used by tools ──────────────────────────────────────────────────────

def get_norm_vals(respondents: list, variable: str, var_meta: dict) -> list:
    """Return normalised (0-100) values for a score variable, N/A excluded."""
    meta = var_meta.get(variable, {})
    vtype = meta.get("type", "other")
    na_vals = meta.get("na_values", set())
    result = []
    for r in respondents:
        raw_v = r.get(variable)
        if raw_v is None or raw_v == "":
            continue
        try:
            fv = float(raw_v)
            if int(fv) in na_vals:
                continue
            n = normalize_score(fv, vtype)
            if n is not None:
                result.append(n)
        except (ValueError, TypeError):
            pass
    return result


def stats(vals: list) -> dict:
    if not vals:
        return {"mean": None, "median": None, "mode": None, "sd": None, "n": 0}
    try:
        mode_val = statistics.mode(vals)
    except statistics.StatisticsError:
        mode_val = None
    return {
        "mean": statistics.mean(vals),
        "median": statistics.median(vals),
        "mode": mode_val,
        "sd": statistics.pstdev(vals),
        "n": len(vals),
    }


def distribution_norm(norm_vals: list, buckets=5) -> dict:
    """Bucket normalised 0-100 values into `buckets` equal-width bins."""
    width = 100 / buckets
    counts = {i: 0 for i in range(buckets)}
    for v in norm_vals:
        idx = min(int(v // width), buckets - 1)
        counts[idx] += 1
    return counts


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
