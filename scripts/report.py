#!/usr/bin/env python3
"""
Generate a self-contained HTML report with embedded SVG charts and interactive filtering.
Open the output file in any browser — use the filter bar to slice by language, answer, etc.
Use File → Print → Save as PDF to export.

Usage:
  python3 scripts/report.py                          # auto-detect dataset
  python3 scripts/report.py --dataset datasets/d.xlsx
  python3 scripts/report.py --out my_report.html
  python3 scripts/report.py --title "Q1 2026 Survey"
  python3 scripts/report.py --top 30
"""

import argparse
import html
import json
import sys
import statistics
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, get_output_dir, normalize_score

# ── CLI ───────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--dataset", help="Path to dataset file (.xml or .xlsx)")
parser.add_argument("--out",      help="Output HTML file path (default: <output_dir>/<dataset>.html)")
parser.add_argument("--analysis", help="Path to analysis.json (default: auto-detected)")
parser.add_argument("--title",    help="Custom report title")
parser.add_argument("--top", type=int, default=35, help="Max questions to include in ranking chart")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables  = data["variables"]
labels     = data["labels"]
respondents = data["respondents"]
var_meta   = data["var_meta"]
score_vars = data["score_vars"]
path_str   = data["path"]

dataset_path = Path(path_str)
dataset_stem = dataset_path.stem
output_dir   = get_output_dir(dataset_path)

if args.out:
    out_path = Path(args.out)
else:
    out_path = output_dir / f"{dataset_stem}.html"

title     = args.title or f"Survey Report — {dataset_path.name}"
generated = datetime.now().strftime("%Y-%m-%d %H:%M")

h = lambda s: html.escape(str(s))

# ── Load analysis.json if present ─────────────────────────────────────────────
# Search order: explicit --analysis arg → output_dir → dataset dir

def _find_analysis() -> Path | None:
    if args.analysis:
        p = Path(args.analysis)
        return p if p.exists() else None
    for candidate in [
        output_dir   / f"{dataset_stem}_analysis.json",
        dataset_path.parent / f"{dataset_stem}_analysis.json",
    ]:
        if candidate.exists():
            return candidate
    return None

analysis_path = _find_analysis()
analysis = {}
if analysis_path:
    try:
        analysis = json.load(analysis_path.open(encoding="utf-8")).get("questions", {})
        print(f"ℹ️  Loaded analysis.json ({len(analysis)} questions enriched)")
    except Exception as e:
        print(f"⚠️  Could not load analysis.json: {e}")

# ── Detect filter-worthy variables ───────────────────────────────────────────
# A var is "filterable" if it has a label map with ≤ 20 options (clearly categorical)

def collect_filter_vars(respondents, variables, var_meta, labels, max_options=15):
    """Return list of var IDs useful as interactive filters.

    A var qualifies when it:
    - has a human-readable label map
    - has 2–max_options distinct values in the actual data
    - is NOT a continuous score_0_100 var (those are analysis targets, not segments)
    - is NOT a status/completion flag
    """
    candidates = []
    for v, lmap in labels.items():
        if not lmap:
            continue
        vtype = var_meta.get(v, {}).get("type", "other")
        # Continuous 0-100 sliders are analysis variables, not useful as segment filters
        if vtype in ("status", "score_0_100"):
            continue
        distinct_raw = set(str(r.get(v)) for r in respondents
                           if r.get(v) is not None and str(r.get(v)).strip())
        if len(distinct_raw) < 2 or len(distinct_raw) > max_options:
            continue
        candidates.append(v)
    return candidates

filter_vars = collect_filter_vars(respondents, variables, var_meta, labels)

# ── Build filter options (raw_value → label) per filter var ──────────────────

filter_options = {}
for v in filter_vars:
    lmap = labels.get(v, {})
    distinct = sorted(set(str(r.get(v)) for r in respondents
                         if r.get(v) is not None and str(r.get(v)).strip()),
                      key=lambda x: int(x) if x.isdigit() else x)
    filter_options[v] = [[raw, lmap.get(raw, raw)] for raw in distinct]

# ── Serialize respondent data to compact JSON ─────────────────────────────────

text_vars = [(v, desc) for v, desc in variables.items()
             if var_meta.get(v, {}).get("type") == "text"
             and not v.startswith("statoverall")]

def serialise_respondents(respondents, score_vars, filter_vars, text_vars):
    rows = []
    for r in respondents:
        # Raw score values (int or null)
        s = []
        for v in score_vars:
            raw = r.get(v)
            try:
                s.append(int(float(raw)) if raw is not None and str(raw).strip() else None)
            except (ValueError, TypeError):
                s.append(None)
        # Filter var raw values (string or null)
        f = {}
        for v in filter_vars:
            val = r.get(v)
            f[v] = str(int(float(val))) if val is not None and str(val).strip() else None
        # Text comments
        t = {}
        for tv, _ in text_vars:
            val = r.get(tv)
            if val and str(val).strip():
                t[tv] = str(val).strip()
        row = {"s": s, "f": f}
        if t:
            row["t"] = t
        rows.append(row)
    return rows

respondent_rows = serialise_respondents(respondents, score_vars, filter_vars, text_vars)

survey_data = {
    "meta": {
        "title": title,
        "generated": generated,
        "source": str(path_str),
        "nRespondents": len(respondents),
        "topN": args.top,
    },
    "scoreVars":    score_vars,
    "varLabels":    {v: variables.get(v, v) for v in score_vars},
    "varTypes":     {v: var_meta[v]["type"] for v in score_vars},
    "naValues":     {v: list(var_meta[v].get("na_values", set())) for v in score_vars},
    "labelMaps":    {v: labels.get(v, {}) for v in score_vars},
    "textVars":     {v: desc for v, desc in text_vars},
    "filterVars":   filter_vars,
    "filterLabels": {v: variables.get(v, v) for v in filter_vars},
    "filterOptions": filter_options,
    "respondents":  respondent_rows,
    "analysis":     analysis,   # from analysis.json, empty dict if not present
}

data_json = json.dumps(survey_data, ensure_ascii=False, separators=(",", ":"))

# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
/* ── Reset & base ─────────────────────────────────────────────────────────── */
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; color: #333;
       height: 100vh; overflow: hidden; display: flex; }

/* ── App shell ────────────────────────────────────────────────────────────── */
.app-shell { display: flex; width: 100vw; height: 100vh; }

/* ── Sidebar ──────────────────────────────────────────────────────────────── */
.sidebar {
  width: 215px; min-width: 215px; flex-shrink: 0;
  background: #0c3a51; color: #8ab5cb;
  display: flex; flex-direction: column; overflow-y: auto;
}
.sidebar-brand { padding: 16px 20px 14px; border-bottom: 1px solid rgba(255,255,255,.1); }
.brand-name { display: block; font-size: 18px; font-weight: 700; color: #fff; letter-spacing: -.2px; }
.brand-sub  { font-size: 11px; color: #6a9ab5; display: block; margin-top: 2px; }

.nav-section { flex: 1; padding: 6px 0; }
.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 18px 10px 16px; cursor: pointer;
  color: #8ab5cb; font-size: 13px;
  border-left: 3px solid transparent;
  transition: background .15s, color .15s;
  text-decoration: none;
}
.nav-item:hover  { background: rgba(255,255,255,.07); color: #c8e0ee; }
.nav-item.active { background: rgba(255,255,255,.10); color: #fff; border-left-color: #29a8e0; }
.nav-icon { font-size: 14px; width: 20px; text-align: center; flex-shrink: 0; opacity: .75; }
.nav-item.active .nav-icon { opacity: 1; }
.nav-label { flex: 1; }

/* ── Main area ────────────────────────────────────────────────────────────── */
.main-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }

/* ── Top header ───────────────────────────────────────────────────────────── */
.top-header {
  background: #1078bf; color: #fff; height: 52px;
  padding: 0 24px; display: flex; align-items: center; gap: 16px; flex-shrink: 0;
}
.header-title { font-size: 15px; font-weight: 400; }

/* ── Content area ─────────────────────────────────────────────────────────── */
.content-area { flex: 1; overflow-y: auto; background: #f0f2f5; }
.content-inner { max-width: 1080px; margin: 0 auto; padding: 28px 28px 56px; }

/* ── Page heading ─────────────────────────────────────────────────────────── */
.page-heading { margin-bottom: 20px; }
.page-heading h1 { font-size: 22px; font-weight: 600; color: #1a2a3a; }
.page-heading .meta { color: #888; font-size: 12px; margin-top: 4px; }

/* ── Panel cards ──────────────────────────────────────────────────────────── */
.panel { background: #fff; border: 1px solid #dde2e8; border-radius: 4px; margin-bottom: 18px; overflow: hidden; }
.panel-header {
  padding: 12px 20px 11px; border-bottom: 1px solid #eaecf0;
  display: flex; align-items: baseline; gap: 8px;
}
.panel-title    { font-size: 15px; font-weight: 600; color: #1a2a3a; flex: 1; }
.panel-subtitle { font-size: 12px; color: #888; font-weight: 400; }
.panel-body { padding: 16px 20px; }

/* ── Legacy section / heading overrides ──────────────────────────────────── */
.section { margin-bottom: 0; }
h2 { display: none; }
h3 { font-size: 13px; font-weight: 600; color: #555; margin-bottom: 6px; }

/* ── Summary cards ────────────────────────────────────────────────────────── */
.cards { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 18px; }
.card { background: #fff; border: 1px solid #dde2e8; border-radius: 4px; padding: 16px 20px;
        flex: 1; min-width: 130px; text-align: center; }
.card .big { font-size: 30px; font-weight: 700; line-height: 1.1; color: #1a2a3a; }
.card .lbl { font-size: 11px; color: #888; margin-top: 4px; }
.badge { display:inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }

/* ── Charts ───────────────────────────────────────────────────────────────── */
.chart-wrap { overflow-x: auto; }

/* ── Question grid ────────────────────────────────────────────────────────── */
.question-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px,1fr)); gap: 14px; }
.q-card { background: #f8fafb; border: 1px solid #e0e5ea; border-radius: 4px; padding: 12px; }
.q-card .q-title { font-size: 11px; color: #555; margin-bottom: 8px; line-height: 1.3; min-height: 28px; }
.q-card .q-stats { display:flex; gap:8px; font-size:11px; color:#888; margin-top:6px; }
.q-card .q-mean  { font-size:14px; font-weight:700; color: #1a2a3a; }

/* ── Tables ───────────────────────────────────────────────────────────────── */
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { background: #f4f6f8; text-align: left; padding: 8px 12px; font-weight: 600; color: #444;
     border-bottom: 1px solid #dde2e8; }
td { padding: 7px 12px; border-bottom: 1px solid #f0f2f5; vertical-align: top; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f8fafb; }

/* ── Comment cards ────────────────────────────────────────────────────────── */
.comment-card {
  background: #fff; border: 1px solid #e0e5ea; border-left: 3px solid #1078bf;
  padding: 8px 12px; margin-bottom: 6px; border-radius: 0 4px 4px 0;
  font-size: 12px; line-height: 1.5;
}

/* ── Comment sections ─────────────────────────────────────────────────────── */
.comment-section { margin-bottom: 14px; border: 1px solid #e0e5ea; border-radius: 4px; overflow: hidden; }
.comment-section-header {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  background: #f4f6f8; padding: 11px 16px; cursor: pointer; user-select: none;
}
.comment-section-header:hover { background: #eaecf0; }
.comment-q-title  { font-size: 13px; font-weight: 600; color: #1a2a3a; margin: 0; flex: 1; }
.comment-q-count  { font-size: 11px; color: #1078bf; font-weight: 600; white-space: nowrap; }
.comment-q-toggle { font-size: 12px; color: #1078bf; margin-left: 8px; }
.comment-section-body { padding: 12px 16px; }

/* ── Comment search ───────────────────────────────────────────────────────── */
.comment-search-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.comment-search-wrap {
  display: flex; align-items: center; gap: 6px;
  background: #f8fafb; border: 1px solid #c8d4de; border-radius: 4px;
  padding: 6px 12px; flex: 1; min-width: 220px;
}
.comment-search-wrap:focus-within { border-color: #1078bf; box-shadow: 0 0 0 2px rgba(16,120,191,.12); }
.search-icon { font-size: 13px; opacity: .5; }
#comment-search-clear { background: none; border: none; cursor: pointer; color: #999; font-size: 14px; padding: 0 2px; line-height: 1; }
#comment-search-clear:hover { color: #333; }
.comment-search-count { font-size: 11px; color: #888; white-space: nowrap; }

/* ── Analysis summary & theme chips ──────────────────────────────────────── */
.analysis-summary {
  background: #f4f7fa; border-left: 3px solid #1078bf; padding: 10px 14px;
  border-radius: 0 4px 4px 0; font-size: 12px; line-height: 1.6; color: #444; margin-bottom: 14px;
}
.analysis-summary strong { color: #1078bf; font-size: 11px; display: block; margin-bottom: 4px; }
.theme-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.chip {
  font-size: 11px; padding: 3px 10px; border-radius: 3px; cursor: pointer;
  border: 1px solid #c0cfd9; background: #fff; color: #1078bf; transition: background .15s, color .15s;
}
.chip:hover     { background: #e8f2f9; }
.chip.active    { background: #1078bf; color: #fff; border-color: #1078bf; }
.chip.chip-all  { background: #f0f5f9; }

/* ── Sentiment buttons ────────────────────────────────────────────────────── */
.sentiment-bar { display: flex; gap: 4px; margin-bottom: 12px; align-items: center; }
.sentiment-bar span { font-size: 11px; color: #888; margin-right: 4px; }
.sent-btn {
  font-size: 11px; padding: 3px 9px; border-radius: 3px; cursor: pointer;
  border: 1px solid #ddd; background: #fff; color: #555; transition: background .15s;
}
.sent-btn:hover  { background: #f5f5f5; }
.sent-btn.active { border-color: #555; font-weight: 700; }
.sent-1.active { background: #fde8e8; color: #c0392b; border-color: #c0392b; }
.sent-2.active { background: #fff0e0; color: #c0672b; border-color: #c0672b; }
.sent-3.active { background: #fffde8; color: #856404; border-color: #856404; }
.sent-4.active { background: #e8f4e8; color: #2e7d32; border-color: #2e7d32; }
.sent-5.active { background: #d4edda; color: #155724; border-color: #155724; }
.comment-card .card-meta { display: flex; gap: 6px; align-items: center; margin-bottom: 5px; flex-wrap: wrap; }
.category-tag { font-size: 10px; background: #e8f2f9; color: #1078bf; padding: 1px 7px; border-radius: 3px; font-weight: 600; }
.sent-dot { font-size: 10px; padding: 1px 7px; border-radius: 3px; font-weight: 600; }
.sd-1 { background: #fde8e8; color: #c0392b; }
.sd-2 { background: #fff0e0; color: #c0672b; }
.sd-3 { background: #fffde8; color: #856404; }
.sd-4 { background: #e8f4e8; color: #2e7d32; }
.sd-5 { background: #d4edda; color: #155724; }
.flag-high { color: #c0392b; font-weight: 600; }
.flag-low  { color: #1078bf; font-weight: 600; }
.type-tag  { font-size: 10px; background: #e8f2f9; color: #1078bf; padding: 1px 6px; border-radius: 3px; margin-left: 6px; }
footer { text-align:center; font-size:11px; color:#bbb; margin-top:32px; padding-top: 20px; border-top: 1px solid #e0e5ea; }

/* ── Filter bar ───────────────────────────────────────────────────────────── */
.filter-bar {
  background: #fff; border: 1px solid #dde2e8; border-radius: 4px;
  padding: 12px 16px; margin-bottom: 18px;
  display: flex; flex-wrap: wrap; align-items: center; gap: 12px;
}
.filter-bar .filter-title { font-size: 12px; font-weight: 600; color: #1078bf; white-space: nowrap; }
.filter-group { display: flex; flex-direction: column; gap: 3px; min-width: 140px; }
.filter-group label { font-size: 10px; color: #666; font-weight: 600; text-transform: uppercase; letter-spacing: .4px; }
.filter-group select {
  font-size: 12px; padding: 5px 8px; border: 1px solid #c8d4de; border-radius: 3px;
  background: #fff; color: #333; cursor: pointer;
  appearance: none; -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%231078bf'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 8px center; padding-right: 22px;
}
.filter-group select:focus { outline: 2px solid #1078bf; outline-offset: 1px; }
.filter-actions { display: flex; align-items: flex-end; gap: 8px; margin-top: 2px; }
.btn-reset {
  font-size: 12px; padding: 6px 16px; background: #1078bf; color: #fff;
  border: none; border-radius: 3px; cursor: pointer; font-weight: 600; white-space: nowrap;
}
.btn-reset:hover { background: #0a68a8; }
.filter-status {
  font-size: 11px; color: #555; background: #f4f6f8; padding: 5px 10px;
  border-radius: 3px; border: 1px solid #dde2e8; white-space: nowrap;
}
.filter-active-count {
  display: inline-block; background: #1078bf; color: #fff; border-radius: 10px;
  font-size: 10px; font-weight: 700; padding: 1px 6px; margin-left: 4px; vertical-align: middle;
}
.no-data { color: #888; font-style: italic; padding: 16px 0; }

/* ── Outlier cards ────────────────────────────────────────────────────────── */
.outlier-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(400px,1fr)); gap: 14px; }
.outlier-card { background: #fff; border: 1px solid #dde2e8; border-radius: 4px; overflow: hidden; }
.outlier-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; background: #f4f6f8; border-bottom: 1px solid #dde2e8;
}
.outlier-id { font-size: 12px; font-weight: 600; color: #333; word-break: break-all; }
.outlier-count {
  font-size: 11px; font-weight: 700; background: #1078bf; color: #fff;
  padding: 2px 9px; border-radius: 10px; white-space: nowrap; margin-left: 8px; flex-shrink: 0;
}
.outlier-flag {
  display: grid; grid-template-columns: 26px 1fr auto; align-items: center;
  gap: 8px; padding: 8px 14px; border-bottom: 1px solid #f0f2f5; font-size: 12px;
}
.outlier-flag:last-child { border-bottom: none; }
.dir-badge {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 50%; font-size: 13px; font-weight: 700; flex-shrink: 0;
}
.dir-high { background: #fde8e8; color: #c0392b; }
.dir-low  { background: #e0f0fa; color: #1078bf; }
.flag-label { color: #333; line-height: 1.3; }
.flag-label .var-code { font-size: 10px; color: #aaa; margin-left: 4px; font-family: monospace; }
.flag-scores { text-align: right; white-space: nowrap; }
.flag-their { font-weight: 700; font-size: 13px; }
.flag-avg   { font-size: 10px; color: #888; margin-top: 1px; }
.flag-bar-wrap { grid-column: 1 / -1; padding: 0 0 4px 34px; }
.flag-bar-track { height: 6px; background: #eee; border-radius: 3px; position: relative; overflow: visible; }
.flag-bar-fill  { height: 100%; border-radius: 3px; }
.flag-bar-avg-marker {
  position: absolute; top: -3px; width: 2px; height: 12px;
  background: #555; border-radius: 1px; transform: translateX(-50%);
}
.z-pill {
  display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 8px;
  background: #f0f0f0; color: #555; cursor: help; margin-left: 4px; border-bottom: 1px dashed #bbb;
}
.outlier-more { padding: 8px 14px; font-size: 11px; color: #888; font-style: italic; }

/* ── Print ────────────────────────────────────────────────────────────────── */
@media print {
  .sidebar, .top-header, .filter-bar { display: none !important; }
  body { height: auto; overflow: visible; display: block; }
  .app-shell { display: block; height: auto; }
  .main-area { display: block; height: auto; }
  .content-area { overflow: visible; height: auto; }
  .content-inner { padding: 0; max-width: none; }
  .panel { break-inside: avoid; }
  .q-card, .comment-card { break-inside: avoid; }
}
"""

# ── JavaScript (all rendering + filtering logic) ──────────────────────────────

JS = r"""
const D = window.SURVEY_DATA;

// ── Math helpers ──────────────────────────────────────────────────────────────
function mean(arr) { return arr.reduce((a,b)=>a+b,0)/arr.length; }
function stdev(arr, m) {
  if (arr.length < 2) return 0;
  const mu = m !== undefined ? m : mean(arr);
  return Math.sqrt(arr.reduce((s,x)=>s+(x-mu)**2, 0)/(arr.length-1));
}
function median(sorted) {
  const n = sorted.length;
  return n%2===0 ? (sorted[n/2-1]+sorted[n/2])/2 : sorted[Math.floor(n/2)];
}

// ── Score helpers ─────────────────────────────────────────────────────────────
function normScore(raw, type, naVals) {
  if (raw===null||raw===undefined) return null;
  if (naVals && naVals.includes(raw)) return null;
  if (type==='score_1_5')   return (raw-1)/4*100;
  if (type==='score_0_100') return raw;
  if (type==='score_1_10')  return (raw-1)/9*100;
  if (type==='binary')      return raw<=1 ? raw*100 : (raw-1)*100;
  return null;
}
function scoreColour(pct) {
  pct = Math.max(0, Math.min(100, pct));
  let r, g;
  if (pct<50) { r=220; g=Math.round(pct/50*180); }
  else         { r=Math.round((1-(pct-50)/50)*180); g=170; }
  return `rgb(${r},${g},60)`;
}
function scoreBg(pct)  { return pct>=75?'#d4edda':pct>=50?'#fff3cd':'#f8d7da'; }
function scoreFg(pct)  { return pct>=75?'#155724':pct>=50?'#856404':'#721c24'; }
function badge(v)      { return `<span class="badge" style="background:${scoreBg(v)};color:${scoreFg(v)}">${v.toFixed(1)}</span>`; }
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Compute stats for a filtered subset ──────────────────────────────────────
function computeStats(rList) {
  const stats = {};
  D.scoreVars.forEach((v, vi) => {
    const naVals = D.naValues[v] || [];
    const type   = D.varTypes[v];
    const vals = [];
    rList.forEach(r => {
      const raw = r.s[vi];
      const n = normScore(raw, type, naVals);
      if (n !== null) vals.push(n);
    });
    if (!vals.length) { stats[v] = {n:0, mean:null, sd:null, median:null, normVals:[]}; return; }
    const m = mean(vals);
    stats[v] = {
      n: vals.length,
      mean: m,
      sd: stdev(vals, m),
      median: median([...vals].sort((a,b)=>a-b)),
      normVals: vals,
    };
  });
  return stats;
}

// ── SVG builders ─────────────────────────────────────────────────────────────
function svgGauge(value, size=100) {
  const cx=size/2, cy=size/2+10, r=size/2-10;
  const angle = (1-value/100)*Math.PI;
  const xEnd  = cx + r*Math.cos(angle);
  const yEnd  = cy - r*Math.sin(angle);
  const col   = scoreColour(value);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size/2+20}"
    style="font-family:'Segoe UI',Arial,sans-serif;">
  <path d="M ${cx-r} ${cy} A ${r} ${r} 0 0 1 ${cx+r} ${cy}"
        fill="none" stroke="#e9e9e9" stroke-width="12" stroke-linecap="round"/>
  <path d="M ${cx-r} ${cy} A ${r} ${r} 0 0 1 ${xEnd.toFixed(2)} ${yEnd.toFixed(2)}"
        fill="none" stroke="${col}" stroke-width="12" stroke-linecap="round"/>
  <text x="${cx}" y="${cy+4}" text-anchor="middle" font-size="16" font-weight="bold" fill="#333">${value.toFixed(1)}</text>
  <text x="${cx}" y="${cy+18}" text-anchor="middle" font-size="9" fill="#888">/ 100</text>
</svg>`;
}

function svgHBar(items, width=700, rowH=38, barArea=340, labelW=240, valW=60) {
  const height = rowH * items.length + 20;
  const barX   = labelW + 10;
  const parts  = [`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"
    style="font-family:'Segoe UI',Arial,sans-serif;font-size:12px;">`];

  [25,50,75,100].forEach(pct => {
    const x = barX + pct/100*barArea;
    const col = pct<100?'#ddd':'#bbb';
    parts.push(`<line x1="${x.toFixed(1)}" y1="0" x2="${x.toFixed(1)}" y2="${height}" stroke="${col}" stroke-width="1"/>`);
    parts.push(`<text x="${x.toFixed(1)}" y="${height-2}" text-anchor="middle" fill="#aaa" font-size="10">${pct}</text>`);
  });

  items.forEach((item, i) => {
    const y   = i*rowH;
    const val = item.value||0;
    const barW = val/100*barArea;
    const col  = scoreColour(val);
    const lbl  = esc(item.label.length>42 ? item.label.slice(0,42)+'…' : item.label);
    const sd   = item.sd;
    if (i%2===0)
      parts.push(`<rect x="0" y="${y}" width="${width}" height="${rowH}" fill="#fafafa"/>`);
    parts.push(`<text x="${labelW-6}" y="${y+rowH/2+4}" text-anchor="end" fill="#333" font-size="11">${lbl}</text>`);
    parts.push(`<rect x="${barX}" y="${y+8}" width="${barW.toFixed(1)}" height="${rowH-16}" fill="${col}" rx="3"/>`);
    if (sd !== null && sd !== undefined) {
      const sdX  = barX + (val+sd)/100*barArea;
      const sdX2 = barX + Math.max(0,(val-sd))/100*barArea;
      const midY = y + rowH/2;
      parts.push(`<line x1="${sdX2.toFixed(1)}" y1="${midY}" x2="${sdX.toFixed(1)}" y2="${midY}" stroke="#555" stroke-width="1" opacity="0.5"/>`);
      parts.push(`<line x1="${sdX.toFixed(1)}" y1="${y+10}" x2="${sdX.toFixed(1)}" y2="${y+rowH-10}" stroke="#555" stroke-width="1.5" opacity="0.5"/>`);
    }
    const valX = barX + barW + 6;
    parts.push(`<text x="${valX.toFixed(1)}" y="${y+rowH/2+4}" fill="#333" font-size="11" font-weight="600">${val.toFixed(1)}</text>`);
    const nX = barX + barArea + 8;
    parts.push(`<text x="${nX}" y="${y+rowH/2+4}" fill="#888" font-size="10">n=${item.n}</text>`);
  });
  parts.push('</svg>');
  return parts.join('\n');
}

function svgDist(normVals, varType, labelMap, width=260, height=140) {
  if (!normVals.length) return '';
  let edges, lbls;
  if (varType==='score_1_5') {
    edges = [[0,20],[20,40],[40,60],[60,80],[80,101]];
    lbls  = [1,2,3,4,5].map(i => labelMap[String(i)] || `Score ${i}`);
  } else if (varType==='binary') {
    edges = [[0,50],[50,101]]; lbls = ['No','Yes'];
  } else {
    edges = [[0,20],[20,40],[40,60],[60,80],[80,101]];
    lbls  = ['0–20','20–40','40–60','60–80','80–100'];
  }
  const counts = new Array(edges.length).fill(0);
  normVals.forEach(v => {
    for (let i=0;i<edges.length;i++) {
      if (v>=edges[i][0]&&v<edges[i][1]) { counts[i]++; break; }
      if (i===edges.length-1) counts[i]++;
    }
  });
  const total = normVals.length;
  const maxC  = Math.max(...counts,1);
  const pad=30, chartW=width-pad, chartH=height-35;
  const barW = chartW/edges.length - 4;
  const parts = [`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"
    style="font-family:'Segoe UI',Arial,sans-serif;font-size:10px;">`];

  counts.forEach((count,i) => {
    const bh  = count/maxC*chartH;
    const x   = pad + i*(barW+4);
    const y   = chartH-bh;
    const mid = edges[i][0]+(edges[i][1]-edges[i][0])/2;
    const col = scoreColour(mid);
    const pct = Math.round(count/total*100);
    parts.push(`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${bh.toFixed(1)}" fill="${col}" rx="2"/>`);
    if (count>0)
      parts.push(`<text x="${(x+barW/2).toFixed(1)}" y="${(y-3).toFixed(1)}" text-anchor="middle" fill="#444" font-size="9">${pct}%</text>`);
    const sl = esc(lbls[i]||'');
    const short = sl.length>9 ? sl.slice(0,8)+'…' : sl;
    parts.push(`<text x="${(x+barW/2).toFixed(1)}" y="${height-5}" text-anchor="middle" fill="#666" font-size="9">${short}</text>`);
  });
  parts.push(`<text x="0" y="${height/2}" transform="rotate(-90,8,${height/2})" text-anchor="middle" fill="#999" font-size="9">count</text>`);
  parts.push('</svg>');
  return parts.join('\n');
}

// ── Section renderers ─────────────────────────────────────────────────────────
function renderCards(stats, nFiltered) {
  const scoreVarsWithData = D.scoreVars.filter(v => stats[v]&&stats[v].mean!==null);
  const allMeans = scoreVarsWithData.map(v=>stats[v].mean);
  const overallAvg = allMeans.length ? mean(allMeans) : 0;
  const nScore = scoreVarsWithData.length;

  document.getElementById('sec-cards').innerHTML = `
    <div class="cards">
      <div class="card">
        <div class="big" style="color:#4361ee">${nFiltered.toLocaleString()}</div>
        <div class="lbl">Respondents (filtered)</div>
      </div>
      <div class="card">
        <div class="big" style="color:#4361ee">${nScore}</div>
        <div class="lbl">Score questions</div>
      </div>
      <div class="card">
        <div class="big">${nScore ? svgGauge(overallAvg, 100) : '—'}</div>
        <div class="lbl">Overall avg (0–100)</div>
      </div>
      <div class="card">
        <div class="big" style="color:#4361ee">${Object.keys(D.textVars).length}</div>
        <div class="lbl">Open-ended questions</div>
      </div>
    </div>`;
}

function renderRanking(stats, topN) {
  const ranked = D.scoreVars
    .filter(v => stats[v]&&stats[v].mean!==null)
    .map(v => ({v, label:D.varLabels[v]||v, ...stats[v]}))
    .sort((a,b)=>b.mean-a.mean)
    .slice(0, topN);
  if (!ranked.length) {
    document.getElementById('sec-ranking').innerHTML = '<p class="no-data">No score data available.</p>'; return;
  }
  const items = ranked.map(r=>({label:r.label, value:r.mean, n:r.n, sd:r.sd}));
  document.getElementById('sec-ranking').innerHTML =
    `<div class="chart-wrap">${svgHBar(items)}</div>`;
}

function renderGrid(stats) {
  const ranked = D.scoreVars
    .filter(v => stats[v]&&stats[v].mean!==null)
    .map(v => ({v, label:D.varLabels[v]||v, type:D.varTypes[v], ...stats[v]}))
    .sort((a,b)=>b.mean-a.mean);
  if (!ranked.length) {
    document.getElementById('sec-grid').innerHTML = '<p class="no-data">No score data.</p>'; return;
  }
  const cards = ranked.map(r => {
    const dist = svgDist(r.normVals, r.type, D.labelMaps[r.v]||{});
    return `<div class="q-card">
      <div class="q-title">${esc(r.label)}<span class="type-tag">${esc(r.type)}</span></div>
      <div style="display:flex;align-items:flex-end;gap:10px">
        ${dist}
        <div>
          <div class="q-mean">${badge(r.mean)}</div>
          <div class="q-stats"><span>±${r.sd.toFixed(1)} SD</span><span>n=${r.n.toLocaleString()}</span></div>
          <div class="q-stats" style="margin-top:4px"><span>med ${r.median.toFixed(0)}</span></div>
        </div>
      </div>
    </div>`;
  });
  document.getElementById('sec-grid').innerHTML = `<div class="question-grid">${cards.join('')}</div>`;
}

function renderTopBottom(stats) {
  const ranked = D.scoreVars
    .filter(v => stats[v]&&stats[v].mean!==null)
    .map((v,i) => ({v, label:D.varLabels[v]||v, ...stats[v]}))
    .sort((a,b)=>b.mean-a.mean);
  if (ranked.length < 4) { document.getElementById('sec-topbottom').innerHTML=''; return; }
  const top5 = ranked.slice(0,5);
  const bot5 = [...ranked.slice(-5)].reverse();
  const hdr = '<tr><th>#</th><th>Var</th><th>Description</th><th>Mean</th><th>SD</th><th>N</th></tr>';
  const row = (r,rank,kind) => {
    const col = kind==='top'?'#155724':'#721c24';
    return `<tr>
      <td style="color:${col};font-weight:600">#${rank}</td>
      <td><code style="font-size:11px">${esc(r.v)}</code></td>
      <td>${esc(r.label)}</td>
      <td style="text-align:center">${badge(r.mean)}</td>
      <td style="text-align:center;color:#888">±${r.sd.toFixed(1)}</td>
      <td style="text-align:right;color:#888">${r.n.toLocaleString()}</td>
    </tr>`;
  };
  document.getElementById('sec-topbottom').innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px">
      <div><h3>🏆 Highest scores</h3><table>${hdr}${top5.map((r,i)=>row(r,i+1,'top')).join('')}</table></div>
      <div><h3>⚠️ Lowest scores</h3><table>${hdr}${bot5.map((r,i)=>row(r,ranked.length-i,'bottom')).join('')}</table></div>
    </div>`;
}

// ── Score Distribution Heatmap ────────────────────────────────────────────────
function renderHeatmap(stats) {
  const el = document.getElementById('sec-heatmap');
  const vars = D.scoreVars.filter(v => stats[v] && stats[v].mean !== null);
  if (!vars.length) { el.innerHTML = '<p class="no-data">No score data.</p>'; return; }

  // Buckets: 0-20, 20-40, 40-60, 60-80, 80-100 (normalised 0-100)
  const BUCKETS = ['0–20','20–40','40–60','60–80','80–100'];
  const BUCKET_COLS = ['#e74c3c','#e67e22','#f1c40f','#2ecc71','#27ae60'];
  const BUCKET_EDGES = [[0,20],[20,40],[40,60],[60,80],[80,101]];
  const LABEL_W = 260;
  const CELL_W  = 64;
  const ROW_H   = 28;
  const HDR_H   = 40;
  const totalW  = LABEL_W + CELL_W * BUCKETS.length + 70;
  const totalH  = HDR_H + ROW_H * vars.length + 24;

  // Sort by mean desc (same as ranking)
  const sorted = [...vars].sort((a,b) => stats[b].mean - stats[a].mean);

  let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${totalW}" height="${totalH}"
    style="font-family:'Segoe UI',Arial,sans-serif;font-size:11px;">`;

  // Header
  BUCKETS.forEach((lbl, bi) => {
    const cx = LABEL_W + bi * CELL_W + CELL_W / 2;
    svg += `<text x="${cx}" y="14" text-anchor="middle" fill="#555" font-size="10" font-weight="600">${lbl}</text>`;
    svg += `<rect x="${LABEL_W + bi*CELL_W}" y="18" width="${CELL_W-2}" height="14" rx="3"
      fill="${BUCKET_COLS[bi]}" opacity="0.35"/>`;
  });
  svg += `<text x="${LABEL_W + CELL_W*BUCKETS.length + 8}" y="14" fill="#888" font-size="9">mean</text>`;

  // Separator line
  svg += `<line x1="0" y1="${HDR_H-4}" x2="${totalW}" y2="${HDR_H-4}" stroke="#ddd" stroke-width="1"/>`;

  sorted.forEach((v, ri) => {
    const s = stats[v];
    const y = HDR_H + ri * ROW_H;
    const lbl = D.varLabels[v] || v;
    const short = lbl.length > 42 ? lbl.slice(0,42) + '…' : lbl;

    // Row zebra
    if (ri % 2 === 0)
      svg += `<rect x="0" y="${y}" width="${totalW}" height="${ROW_H}" fill="#fafafa"/>`;

    svg += `<text x="${LABEL_W-8}" y="${y+ROW_H/2+4}" text-anchor="end" fill="#333" font-size="11">${esc(short)}</text>`;

    // Count per bucket
    const total = s.normVals.length;
    const counts = BUCKET_EDGES.map(([lo,hi]) =>
      s.normVals.filter(n => n >= lo && n < hi).length
    );
    // Handle 100 going into last bucket
    const exact100 = s.normVals.filter(n => n >= 80).length;
    counts[4] = exact100;

    const maxPct = Math.max(...counts.map(c => c/total));

    counts.forEach((cnt, bi) => {
      const pct = total > 0 ? cnt / total : 0;
      const alpha = maxPct > 0 ? 0.15 + 0.75 * (pct / maxPct) : 0;
      const cx = LABEL_W + bi * CELL_W;
      svg += `<rect x="${cx+1}" y="${y+3}" width="${CELL_W-3}" height="${ROW_H-6}" rx="3"
        fill="${BUCKET_COLS[bi]}" opacity="${alpha.toFixed(2)}"/>`;
      if (pct > 0.02) {
        const textCol = alpha > 0.55 ? '#fff' : '#333';
        svg += `<text x="${cx + CELL_W/2}" y="${y+ROW_H/2+4}" text-anchor="middle"
          fill="${textCol}" font-size="10" font-weight="${pct>0.35?'700':'400'}">${Math.round(pct*100)}%</text>`;
      }
    });

    // Mean marker
    const meanX = LABEL_W + CELL_W * BUCKETS.length + 8;
    svg += `<text x="${meanX}" y="${y+ROW_H/2+4}" fill="${scoreColour(s.mean)}" font-size="11" font-weight="600">${s.mean.toFixed(1)}</text>`;
  });

  svg += '</svg>';
  el.innerHTML = `<div class="chart-wrap" style="overflow-x:auto">${svg}</div>`;
}

// ── Sentiment Overview ─────────────────────────────────────────────────────────
function renderSentimentOverview(filtered) {
  const el = document.getElementById('sec-sentiment-overview');
  if (!D.analysis) { el.innerHTML = '<p style="color:#aaa;font-style:italic;font-size:13px">No AI analysis loaded — run with summary option to enable sentiment overview.</p>'; return; }

  const SENT_EMOJIS = ['','😟','😕','😐','🙂','😄'];
  const SENT_COLS   = ['','#e74c3c','#e67e22','#aaa','#2ecc71','#27ae60'];
  const qids = Object.keys(D.analysis);
  if (!qids.length) { el.innerHTML = ''; return; }

  // For each question, count sentiments from filtered respondents' answers
  const LABEL_W = 220;
  const BAR_W   = 500;
  const ROW_H   = 34;
  const HDR_H   = 30;
  const totalW  = LABEL_W + BAR_W + 120;
  const totalH  = HDR_H + ROW_H * qids.length + 24;

  // Build text→sentiment lookup once
  const sentMap = {};
  qids.forEach(qid => {
    const qa = D.analysis[qid];
    if (qa && qa.answers) {
      qa.answers.forEach(a => { sentMap[a.text] = a.sentiment; });
    }
  });

  // Collect filtered text answers per qid
  const filteredTexts = {};
  filtered.forEach(r => {
    if (!r.t) return;
    Object.entries(r.t).forEach(([tv, txt]) => {
      if (txt && txt.trim()) {
        if (!filteredTexts[tv]) filteredTexts[tv] = [];
        filteredTexts[tv].push(txt.trim());
      }
    });
  });

  let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${totalW}" height="${totalH}"
    style="font-family:'Segoe UI',Arial,sans-serif;font-size:11px;">`;

  // Header
  svg += `<text x="${LABEL_W + BAR_W/2}" y="16" text-anchor="middle" fill="#555" font-size="10" font-weight="600">← Negative · Neutral · Positive →</text>`;
  svg += `<line x1="0" y1="${HDR_H-4}" x2="${totalW}" y2="${HDR_H-4}" stroke="#ddd" stroke-width="1"/>`;

  qids.forEach((qid, ri) => {
    const qa = D.analysis[qid];
    const label = (qa && qa.label) || qid;
    const short = label.length > 38 ? label.slice(0,38) + '…' : label;
    const y = HDR_H + ri * ROW_H;

    if (ri % 2 === 0) svg += `<rect x="0" y="${y}" width="${totalW}" height="${ROW_H}" fill="#fafafa"/>`;
    svg += `<text x="${LABEL_W-8}" y="${y+ROW_H/2+4}" text-anchor="end" fill="#333" font-size="11">${esc(short)}</text>`;

    const texts = filteredTexts[qid] || [];
    const counts = [0,0,0,0,0,0]; // index 1-5
    let matched = 0;
    texts.forEach(t => {
      const s = sentMap[t];
      if (s >= 1 && s <= 5) { counts[s]++; matched++; }
    });

    if (matched === 0) {
      svg += `<text x="${LABEL_W+8}" y="${y+ROW_H/2+4}" fill="#ccc" font-size="10">no data</text>`;
    } else {
      let xOff = 0;
      for (let s = 1; s <= 5; s++) {
        if (!counts[s]) continue;
        const pct = counts[s] / matched;
        const bw  = pct * BAR_W;
        svg += `<rect x="${LABEL_W + xOff}" y="${y+6}" width="${bw.toFixed(1)}" height="${ROW_H-12}" fill="${SENT_COLS[s]}" opacity="0.82"/>`;
        if (bw > 18) {
          svg += `<text x="${(LABEL_W + xOff + bw/2).toFixed(1)}" y="${y+ROW_H/2+4}" text-anchor="middle"
            fill="#fff" font-size="${bw > 30 ? 12 : 9}">${Math.round(pct*100)}%</text>`;
        }
        xOff += bw;
      }
      // Emoji legend on right
      const legendX = LABEL_W + BAR_W + 10;
      const parts = [];
      for (let s = 1; s <= 5; s++) {
        if (counts[s]) parts.push(`${SENT_EMOJIS[s]} ${Math.round(counts[s]/matched*100)}%`);
      }
      svg += `<text x="${legendX}" y="${y+ROW_H/2+4}" fill="#666" font-size="10">${esc(parts.join('  '))}</text>`;
    }
  });

  svg += '</svg>';

  // Colour legend below
  const legendItems = [1,2,3,4,5].map(s =>
    `<span style="display:inline-flex;align-items:center;gap:4px;margin-right:12px">
      <span style="width:14px;height:14px;border-radius:3px;background:${SENT_COLS[s]};display:inline-block;opacity:0.82"></span>
      <span style="font-size:12px">${SENT_EMOJIS[s]} ${['','Very negative','Negative','Neutral','Positive','Very positive'][s]}</span>
    </span>`
  ).join('');

  el.innerHTML = `<div class="chart-wrap" style="overflow-x:auto">${svg}</div>
    <div style="margin-top:10px;padding:8px 12px;background:#f9f9f9;border-radius:6px;border:1px solid #eee">${legendItems}</div>`;
}

function renderComments(filtered) {
  // Group answers (with analysis metadata if available) by question ID
  const byQid = {};
  filtered.forEach(r => {
    const t = r.t || {};
    Object.entries(t).forEach(([tv, txt]) => {
      if (txt && txt.trim()) {
        if (!byQid[tv]) byQid[tv] = [];
        byQid[tv].push(txt.trim());
      }
    });
  });

  const heading = document.getElementById('sec-comments-heading');
  const container = document.getElementById('sec-comments');
  const qids = Object.keys(D.textVars).filter(q => byQid[q] && byQid[q].length > 0);
  const totalCount = qids.reduce((s, q) => s + byQid[q].length, 0);

  if (!totalCount) {
    heading.textContent = 'Open-ended Responses';
    container.innerHTML = '<p class="no-data">No comments in this selection.</p>';
    return;
  }
  heading.textContent = `Open-ended Responses`;

  // Per-section filter state: {qid: {search, activeTheme, activeSent}}
  const qState = {};

  // Build enriched answer list per question, merging analysis.json if available
  function buildAnswers(qid) {
    const rawTexts = byQid[qid] || [];
    const aq = D.analysis && D.analysis[qid];
    if (!aq || !aq.answers) return rawTexts.map(t => ({text: t}));
    // Match by text (analysis was produced on full dataset; filter may reduce set)
    const analysisMap = {};
    aq.answers.forEach(a => { analysisMap[a.text] = a; });
    return rawTexts.map(t => analysisMap[t] || {text: t});
  }

  // Render answer cards with optional category/sentiment badges
  function cardsHtml(answers) {
    if (!answers.length) return '<p class="no-data">No responses match your search.</p>';
    return answers.map(a => {
      let meta = '';
      if (a.category) meta += `<span class="category-tag">${esc(a.category)}</span>`;
      if (a.sentiment) {
        const labels = {1:'😟 Very negative',2:'😕 Negative',3:'😐 Neutral',4:'🙂 Positive',5:'😄 Very positive'};
        meta += `<span class="sent-dot sd-${a.sentiment}">${labels[a.sentiment]||a.sentiment}</span>`;
      }
      return `<div class="comment-card">
        ${meta ? `<div class="card-meta">${meta}</div>` : ''}
        ${esc(a.text)}
      </div>`;
    }).join('');
  }

  // Apply all active filters for a question and re-render its cards
  window._qAllAnswers = {};
  function applyQFilters(qid) {
    const all  = window._qAllAnswers[qid] || [];
    const st   = qState[qid] || {};
    const q    = (st.search || '').toLowerCase();
    const theme = st.activeTheme || null;
    const sents = st.activeSents || new Set();
    const matched = all.filter(a => {
      if (q && !a.text.toLowerCase().includes(q)) return false;
      if (theme && a.category !== theme) return false;
      if (sents.size && !sents.has(a.sentiment)) return false;
      return true;
    });
    const el = document.getElementById('qcards-' + qid);
    const ct = document.getElementById('qcount-' + qid);
    if (el) el.innerHTML = cardsHtml(matched);
    const total = all.length;
    if (ct) ct.textContent = matched.length < total
      ? `${matched.length.toLocaleString()} of ${total.toLocaleString()} match`
      : `${total.toLocaleString()} responses`;
  }

  window.filterQComments = function(qid, query) {
    if (!qState[qid]) qState[qid] = {};
    qState[qid].search = query;
    applyQFilters(qid);
  };

  window.clearQSearch = function(qid) {
    const inp = document.getElementById('qsearch-' + qid);
    if (inp) inp.value = '';
    if (qState[qid]) qState[qid].search = '';
    applyQFilters(qid);
  };

  window.setQTheme = function(qid, theme) {
    if (!qState[qid]) qState[qid] = {};
    qState[qid].activeTheme = (qState[qid].activeTheme === theme) ? null : theme;
    // Update chip styles
    const wrap = document.getElementById('qthemes-' + qid);
    if (wrap) wrap.querySelectorAll('.chip').forEach(c => {
      c.classList.toggle('active', c.dataset.theme === qState[qid].activeTheme);
    });
    applyQFilters(qid);
  };

  window.toggleQSent = function(qid, sent) {
    if (!qState[qid]) qState[qid] = {};
    if (!qState[qid].activeSents) qState[qid].activeSents = new Set();
    const s = qState[qid].activeSents;
    s.has(sent) ? s.delete(sent) : s.add(sent);
    // Update button styles
    const wrap = document.getElementById('qsents-' + qid);
    if (wrap) wrap.querySelectorAll('.sent-btn').forEach(b => {
      b.classList.toggle('active', s.has(Number(b.dataset.sent)));
    });
    applyQFilters(qid);
  };

  window.toggleQSection = function(qid) {
    const body = document.getElementById('qbody-' + qid);
    const tog  = document.getElementById('qtog-' + qid);
    if (!body) return;
    const hidden = body.style.display === 'none';
    body.style.display = hidden ? '' : 'none';
    if (tog) tog.textContent = hidden ? '▲' : '▼';
  };

  const SENT_LABELS = {1:'😟 1',2:'😕 2',3:'😐 3',4:'🙂 4',5:'😄 5'};

  const sections = qids.map(qid => {
    const label   = D.textVars[qid] || qid;
    const answers = buildAnswers(qid);
    window._qAllAnswers[qid] = answers;
    qState[qid] = {search:'', activeTheme:null, activeSents:new Set()};

    const aq = D.analysis && D.analysis[qid];

    // Summary block
    const summaryHtml = aq && aq.summary
      ? `<div class="analysis-summary"><strong>✨ AI Summary</strong>${esc(aq.summary)}</div>`
      : '';

    // Theme chips
    let themesHtml = '';
    if (aq && aq.themes && aq.themes.length) {
      const chips = aq.themes.map(t =>
        `<button class="chip" data-theme="${esc(t)}" onclick="setQTheme('${qid}','${esc(t)}')">${esc(t)}</button>`
      ).join('');
      themesHtml = `<div class="theme-chips" id="qthemes-${qid}">${chips}</div>`;
    }

    // Sentiment filter
    const sentHtml = aq && aq.answers && aq.answers.some(a => a.sentiment)
      ? `<div class="sentiment-bar" id="qsents-${qid}">
          <span>Sentiment:</span>
          ${[1,2,3,4,5].map(s =>
            `<button class="sent-btn sent-${s}" data-sent="${s}" onclick="toggleQSent('${qid}',${s})">${SENT_LABELS[s]}</button>`
          ).join('')}
        </div>`
      : '';

    return `
      <div class="comment-section">
        <div class="comment-section-header" onclick="toggleQSection('${qid}')">
          <h3 class="comment-q-title">${esc(label)}</h3>
          <span class="comment-q-count">${answers.length.toLocaleString()} responses</span>
          <span class="comment-q-toggle" id="qtog-${qid}">▲</span>
        </div>
        <div class="comment-section-body" id="qbody-${qid}">
          ${summaryHtml}
          ${themesHtml}
          ${sentHtml}
          <div class="comment-search-bar">
            <div class="comment-search-wrap">
              <span class="search-icon">🔍</span>
              <input id="qsearch-${qid}" type="text" placeholder="Search these responses…"
                     oninput="filterQComments('${qid}', this.value)"
                     style="flex:1;font-size:13px;border:none;outline:none;background:transparent;padding:4px 0"/>
              <button onclick="clearQSearch('${qid}')" title="Clear">✕</button>
            </div>
            <span id="qcount-${qid}" class="comment-search-count">${answers.length.toLocaleString()} responses</span>
          </div>
          <div id="qcards-${qid}">${cardsHtml(answers)}</div>
        </div>
      </div>`;
  });

  container.innerHTML = sections.join('');
}

// ── Filter state ──────────────────────────────────────────────────────────────
let activeFilters = {};  // {varId: rawValue string, or null=all}

function applyFilters() {
  D.filterVars.forEach(v => {
    const sel = document.getElementById('filter-' + v);
    activeFilters[v] = sel && sel.value !== '' ? sel.value : null;
  });
  const filtered = D.respondents.filter(r => {
    return D.filterVars.every(v => {
      if (!activeFilters[v]) return true;
      return r.f[v] === activeFilters[v];
    });
  });

  // Update status
  const nActive = Object.values(activeFilters).filter(Boolean).length;
  const badge_html = nActive > 0
    ? `<span class="filter-active-count">${nActive}</span>` : '';
  document.getElementById('filter-btn-label').innerHTML = `🔍 Filters${badge_html}`;
  document.getElementById('filter-status').textContent =
    `${filtered.length.toLocaleString()} of ${D.meta.nRespondents.toLocaleString()} respondents`;

  // Recompute & re-render
  const stats = computeStats(filtered);
  renderCards(stats, filtered.length);
  renderRanking(stats, D.meta.topN);
  renderGrid(stats);
  renderTopBottom(stats);
  renderHeatmap(stats);
  renderSentimentOverview(filtered);
  renderComments(filtered);
}

function resetFilters() {
  D.filterVars.forEach(v => {
    const sel = document.getElementById('filter-' + v);
    if (sel) sel.value = '';
  });
  applyFilters();
}

// ── Build filter UI ───────────────────────────────────────────────────────────
function buildFilterUI() {
  const bar = document.getElementById('filter-bar-controls');
  D.filterVars.forEach(v => {
    const opts = D.filterOptions[v] || [];
    const lbl  = D.filterLabels[v] || v;
    const grp  = document.createElement('div');
    grp.className = 'filter-group';
    grp.innerHTML = `<label for="filter-${esc(v)}">${esc(lbl)}</label>
      <select id="filter-${esc(v)}" onchange="applyFilters()">
        <option value="">All</option>
        ${opts.map(([raw,label]) => `<option value="${esc(raw)}">${esc(label)}</option>`).join('')}
      </select>`;
    bar.appendChild(grp);
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (!D || !D.respondents) return;
  buildFilterUI();
  applyFilters();  // initial render with all respondents
});
"""

# ── HTML assembly ─────────────────────────────────────────────────────────────

no_score_msg = "" if score_vars else '<p style="color:#888;font-style:italic;padding:16px 0">No score variables detected in this dataset.</p>'

html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{h(title)}</title>
  <style>{CSS}</style>
</head>
<body>
<div class="app-shell">

  <!-- ── Sidebar ─────────────────────────────────────────────────────────── -->
  <nav class="sidebar">
    <div class="sidebar-brand">
      <span class="brand-name">Indsight</span>
      <span class="brand-sub">By Ramboll</span>
    </div>
    <div class="nav-section">
      <a class="nav-item" href="#sec-cards" onclick="navClick(this)">
        <span class="nav-icon">&#9632;</span><span class="nav-label">Overview</span>
      </a>
      <a class="nav-item" href="#panel-ranking" onclick="navClick(this)">
        <span class="nav-icon">&#9776;</span><span class="nav-label">Score Ranking</span>
      </a>
      <a class="nav-item" href="#panel-grid" onclick="navClick(this)">
        <span class="nav-icon">&#9635;</span><span class="nav-label">Question Breakdown</span>
      </a>
      <a class="nav-item" href="#panel-topbottom" onclick="navClick(this)">
        <span class="nav-icon">&#8645;</span><span class="nav-label">Top &amp; Bottom 5</span>
      </a>
      <a class="nav-item" href="#panel-heatmap" onclick="navClick(this)">
        <span class="nav-icon">&#9638;</span><span class="nav-label">Score Distribution</span>
      </a>
      <a class="nav-item" href="#panel-sentiment" onclick="navClick(this)">
        <span class="nav-icon">&#9685;</span><span class="nav-label">Sentiment</span>
      </a>
      <a class="nav-item" href="#panel-comments" onclick="navClick(this)">
        <span class="nav-icon">&#9998;</span><span class="nav-label">Open-ended Responses</span>
      </a>
    </div>
  </nav>

  <!-- ── Main area ───────────────────────────────────────────────────────── -->
  <div class="main-area">

    <header class="top-header">
      <span class="header-title">{h(title)}</span>
    </header>

    <div class="content-area" id="content-area">
      <div class="content-inner">

        <div class="page-heading">
          <h1>Analysis</h1>
          <p class="meta">Generated {generated} &nbsp;·&nbsp; Source: {h(path_str)}</p>
        </div>

        <!-- Filter bar -->
        <div class="filter-bar">
          <span class="filter-title" id="filter-btn-label">Filters</span>
          <div id="filter-bar-controls" style="display:contents"></div>
          <div class="filter-actions">
            <button class="btn-reset" onclick="resetFilters()">Reset</button>
            <span class="filter-status" id="filter-status">Loading…</span>
          </div>
        </div>

        <!-- Summary cards (JS-rendered, no panel wrapper) -->
        <div id="sec-cards" class="section"></div>

        <!-- Score ranking -->
        <div class="panel" id="panel-ranking">
          <div class="panel-header">
            <span class="panel-title">Score Ranking</span>
            <span class="panel-subtitle">normalised 0–100, ±1 SD shown</span>
          </div>
          <div class="panel-body">
            <div id="sec-ranking" class="section">{no_score_msg}</div>
          </div>
        </div>

        <!-- Question Breakdown -->
        <div class="panel" id="panel-grid">
          <div class="panel-header">
            <span class="panel-title">Question Breakdown</span>
          </div>
          <div class="panel-body">
            <div id="sec-grid" class="section">{no_score_msg}</div>
          </div>
        </div>

        <!-- Top / Bottom 5 -->
        <div class="panel" id="panel-topbottom">
          <div class="panel-header">
            <span class="panel-title">Top 5 &amp; Bottom 5</span>
          </div>
          <div class="panel-body">
            <div id="sec-topbottom" class="section">{no_score_msg}</div>
          </div>
        </div>

        <!-- Score Distribution Heatmap -->
        <div class="panel" id="panel-heatmap">
          <div class="panel-header">
            <span class="panel-title">Score Distribution Heatmap</span>
            <span class="panel-subtitle">% of respondents per bucket</span>
          </div>
          <div class="panel-body">
            <div id="sec-heatmap" class="section">{no_score_msg}</div>
          </div>
        </div>

        <!-- Sentiment Overview -->
        <div class="panel" id="panel-sentiment">
          <div class="panel-header">
            <span class="panel-title">Sentiment Overview</span>
            <span class="panel-subtitle">per open-ended question</span>
          </div>
          <div class="panel-body">
            <div id="sec-sentiment-overview" class="section"></div>
          </div>
        </div>

        <!-- Open-ended Responses -->
        <div class="panel" id="panel-comments">
          <div class="panel-header">
            <span class="panel-title" id="sec-comments-heading">Open-ended Responses</span>
          </div>
          <div class="panel-body">
            <div id="sec-comments" class="section"></div>
          </div>
        </div>

        <footer>Survey Indsight · Generated by report.py · {generated}</footer>
      </div>
    </div>
  </div>

</div>

<script>window.SURVEY_DATA = {data_json};</script>
<script>
// ── Sidebar nav helpers ───────────────────────────────────────────────────────
function navClick(el) {{
  event.preventDefault();
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  el.classList.add('active');
  var target = document.querySelector(el.getAttribute('href'));
  if (target) {{
    var ca = document.getElementById('content-area');
    ca.scrollTo({{ top: target.offsetTop - 20, behavior: 'smooth' }});
  }}
}}
(function() {{
  var anchors = ['sec-cards','panel-ranking','panel-grid','panel-topbottom','panel-heatmap','panel-sentiment','panel-comments'];
  var navLinks = Array.from(document.querySelectorAll('.nav-item'));
  var ca = document.getElementById('content-area');
  if (!ca || !navLinks.length) return;
  navLinks[0].classList.add('active');
  ca.addEventListener('scroll', function() {{
    var scrollTop = ca.scrollTop + 80;
    var active = 0;
    anchors.forEach(function(id, i) {{
      var el = document.getElementById(id);
      if (el && el.offsetTop <= scrollTop) active = i;
    }});
    navLinks.forEach(function(n, i) {{ n.classList.toggle('active', i === active); }});
  }});
}})();
</script>
<script>{JS}</script>
</body>
</html>"""

out_path.write_text(html_content, encoding="utf-8")
print(f"✅ Report saved to: {out_path}")
print(f"   Filter by language, score etc. directly in the browser")
print(f"   File → Print → Save as PDF to export")
