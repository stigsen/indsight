#!/usr/bin/env python3
"""
Generate a self-contained HTML report with embedded SVG charts and interactive filtering.
Open the output file in any browser — use the filter bar to slice by language, answer, etc.
Use File → Print → Save as PDF to export.

Usage:
  python3 tools/report.py                          # auto-detect dataset
  python3 tools/report.py --dataset datasets/d.xlsx
  python3 tools/report.py --out my_report.html
  python3 tools/report.py --title "Q1 2026 Survey"
  python3 tools/report.py --top 30
"""

import argparse
import html
import json
import sys
import statistics
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, normalize_score

# ── CLI ───────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--dataset", help="Path to dataset file (.xml or .xlsx)")
parser.add_argument("--out", help="Output HTML file (default: report.html in project root)")
parser.add_argument("--title", help="Custom report title")
parser.add_argument("--top", type=int, default=35, help="Max questions to include in ranking chart")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables  = data["variables"]
labels     = data["labels"]
respondents = data["respondents"]
var_meta   = data["var_meta"]
score_vars = data["score_vars"]
path_str   = data["path"]

out_path  = Path(args.out) if args.out else Path(__file__).parent.parent / "report.html"
title     = args.title or f"Survey Report — {Path(path_str).name}"
generated = datetime.now().strftime("%Y-%m-%d %H:%M")

h = lambda s: html.escape(str(s))

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
}

data_json = json.dumps(survey_data, ensure_ascii=False, separators=(",", ":"))

# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; color: #333; background: #f5f6fa; }
.page { max-width: 980px; margin: 0 auto; padding: 24px; background: #fff; box-shadow: 0 2px 12px rgba(0,0,0,.08); }
h1 { font-size: 24px; font-weight: 700; color: #1a1a2e; margin-bottom: 4px; }
h2 { font-size: 17px; font-weight: 600; color: #1a1a2e; margin: 32px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #4361ee; }
h3 { font-size: 13px; font-weight: 600; color: #555; margin-bottom: 6px; }
.meta { color: #888; font-size: 12px; margin-bottom: 16px; }
.cards { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 8px; }
.card { background: #fff; border: 1px solid #e0e0e0; border-radius: 10px; padding: 16px 20px;
        flex: 1; min-width: 140px; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,.05); }
.card .big { font-size: 32px; font-weight: 700; line-height: 1.1; }
.card .lbl { font-size: 11px; color: #888; margin-top: 4px; }
.badge { display:inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }
.section { margin-bottom: 32px; }
.chart-wrap { overflow-x: auto; }
.question-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px,1fr)); gap: 16px; }
.q-card { background: #fafafa; border: 1px solid #e8e8e8; border-radius: 8px; padding: 12px; }
.q-card .q-title { font-size: 11px; color: #555; margin-bottom: 8px; line-height: 1.3; min-height: 28px; }
.q-card .q-stats { display:flex; gap:8px; font-size:11px; color:#888; margin-top:6px; }
.q-card .q-mean { font-size:14px; font-weight:700; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { background: #f0f2ff; text-align: left; padding: 7px 10px; font-weight: 600; color: #444; border-bottom: 2px solid #dde; }
td { padding: 6px 10px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }
tr:hover td { background: #f8f9ff; }
.comment-card { background: #fff; border-left: 3px solid #4361ee; padding: 8px 12px;
                margin-bottom: 6px; border-radius: 0 6px 6px 0; font-size: 12px; line-height: 1.5; }

/* ── Comment sections (grouped by question) ─────────────────────────────── */
.comment-section {
  margin-bottom: 28px; border: 1px solid #e8e8f0; border-radius: 10px; overflow: hidden;
}
.comment-section-header {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  background: #f0f2ff; padding: 12px 16px; cursor: pointer; user-select: none;
}
.comment-section-header:hover { background: #e6e9fc; }
.comment-q-title {
  font-size: 13px; font-weight: 600; color: #1a1a2e; margin: 0; flex: 1;
}
.comment-q-count {
  font-size: 11px; color: #4361ee; font-weight: 600; white-space: nowrap;
}
.comment-q-toggle { font-size: 12px; color: #4361ee; margin-left: 8px; }
.comment-section-body { padding: 12px 16px; }

/* ── Comment search bar ──────────────────────────────────────────────────── */
.comment-search-bar {
  display: flex; align-items: center; gap: 12px; margin-bottom: 12px;
  flex-wrap: wrap;
}
.comment-search-wrap {
  display: flex; align-items: center; gap: 6px;
  background: #f8f9ff; border: 1px solid #c8cef7; border-radius: 8px;
  padding: 6px 12px; flex: 1; min-width: 220px;
}
.comment-search-wrap:focus-within {
  border-color: #4361ee; box-shadow: 0 0 0 2px rgba(67,97,238,.15);
}
.search-icon { font-size: 13px; opacity: .6; }
#comment-search-clear {
  background: none; border: none; cursor: pointer; color: #999;
  font-size: 14px; padding: 0 2px; line-height: 1;
}
#comment-search-clear:hover { color: #333; }
.comment-search-count {
  font-size: 11px; color: #888; white-space: nowrap;
}
.flag-high { color: #c0392b; font-weight: 600; }
.flag-low  { color: #2980b9; font-weight: 600; }
.type-tag  { font-size: 10px; background: #eef2ff; color: #4361ee; padding: 1px 6px; border-radius: 8px; margin-left: 6px; }
footer { text-align:center; font-size:11px; color:#bbb; margin-top:40px; }

/* ── Filter bar ──────────────────────────────────────────────────────────── */
.filter-bar {
  background: #f0f2ff;
  border: 1px solid #c8cef7;
  border-radius: 10px;
  padding: 12px 16px;
  margin-bottom: 24px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.filter-bar .filter-title {
  font-size: 12px; font-weight: 600; color: #4361ee; white-space: nowrap;
}
.filter-group {
  display: flex; flex-direction: column; gap: 3px; min-width: 140px;
}
.filter-group label {
  font-size: 10px; color: #666; font-weight: 600; text-transform: uppercase; letter-spacing: .4px;
}
.filter-group select {
  font-size: 12px; padding: 4px 8px; border: 1px solid #c8cef7; border-radius: 6px;
  background: #fff; color: #333; cursor: pointer;
  appearance: none; -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%234361ee'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 8px center; padding-right: 22px;
}
.filter-group select:focus { outline: 2px solid #4361ee; outline-offset: 1px; }
.filter-actions { display: flex; align-items: flex-end; gap: 8px; margin-top: 2px; }
.btn-reset {
  font-size: 12px; padding: 5px 14px; background: #4361ee; color: #fff;
  border: none; border-radius: 6px; cursor: pointer; font-weight: 600; white-space: nowrap;
}
.btn-reset:hover { background: #3451d1; }
.filter-status {
  font-size: 11px; color: #555; background: #fff; padding: 4px 10px;
  border-radius: 12px; border: 1px solid #c8cef7; white-space: nowrap;
}
.filter-active-count {
  display: inline-block; background: #4361ee; color: #fff; border-radius: 10px;
  font-size: 10px; font-weight: 700; padding: 1px 6px; margin-left: 4px; vertical-align: middle;
}
.no-data { color: #888; font-style: italic; padding: 16px 0; }

/* ── Outlier cards ───────────────────────────────────────────────────────── */
.outlier-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px,1fr)); gap: 14px; }
.outlier-card {
  background: #fff; border: 1px solid #e0e0e0; border-radius: 10px;
  overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.05);
}
.outlier-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; background: #f8f9ff; border-bottom: 1px solid #e8e8f0;
}
.outlier-id { font-size: 12px; font-weight: 600; color: #333; word-break: break-all; }
.outlier-count {
  font-size: 11px; font-weight: 700; background: #4361ee; color: #fff;
  padding: 2px 9px; border-radius: 10px; white-space: nowrap; margin-left: 8px; flex-shrink: 0;
}
.outlier-flag {
  display: grid; grid-template-columns: 26px 1fr auto; align-items: center;
  gap: 8px; padding: 8px 14px; border-bottom: 1px solid #f4f4f4; font-size: 12px;
}
.outlier-flag:last-child { border-bottom: none; }
.dir-badge {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 50%; font-size: 13px;
  font-weight: 700; flex-shrink: 0;
}
.dir-high { background: #fde8e8; color: #c0392b; }
.dir-low  { background: #e8f0fd; color: #2361b8; }
.flag-label { color: #333; line-height: 1.3; }
.flag-label .var-code { font-size: 10px; color: #aaa; margin-left: 4px; font-family: monospace; }
.flag-scores { text-align: right; white-space: nowrap; }
.flag-their { font-weight: 700; font-size: 13px; }
.flag-avg   { font-size: 10px; color: #888; margin-top: 1px; }
.flag-bar-wrap { grid-column: 1 / -1; padding: 0 0 4px 34px; }
.flag-bar-track {
  height: 6px; background: #eee; border-radius: 3px; position: relative; overflow: visible;
}
.flag-bar-fill { height: 100%; border-radius: 3px; }
.flag-bar-avg-marker {
  position: absolute; top: -3px; width: 2px; height: 12px;
  background: #555; border-radius: 1px; transform: translateX(-50%);
}
.z-pill {
  display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 8px;
  background: #f0f0f0; color: #555; cursor: help; margin-left: 4px;
  border-bottom: 1px dashed #bbb;
}
.outlier-more { padding: 8px 14px; font-size: 11px; color: #888; font-style: italic; }

@media print {
  .filter-bar { display: none !important; }
  body { background: #fff; }
  .page { box-shadow: none; padding: 0; }
  h2 { page-break-after: avoid; }
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

function renderOutliers(filtered, stats) {
  const Z_THRESH = 2.0;
  // Only flag continuous scale variables — skip categorical/binary/filter vars
  const filterVarSet = new Set(D.filterVars);
  const outlierVars = D.scoreVars.filter((v, vi) =>
    !filterVarSet.has(v) &&
    D.varTypes[v] !== 'binary' &&
    D.varTypes[v] !== 'text'
  );
  const outlierVarIdxMap = {};
  outlierVars.forEach(v => { outlierVarIdxMap[v] = D.scoreVars.indexOf(v); });

  const outliers = [];
  filtered.forEach((r, ri) => {
    const flags = [];
    outlierVars.forEach(v => {
      const vi = outlierVarIdxMap[v];
      const s = stats[v];
      if (!s || s.mean===null || !s.sd || s.sd===0) return;
      const raw = r.s[vi];
      const n = normScore(raw, D.varTypes[v], D.naValues[v]);
      if (n===null) return;
      const z = Math.abs((n - s.mean) / s.sd);
      if (z >= Z_THRESH)
        flags.push({v, label: D.varLabels[v]||v, norm:n, avg:s.mean, z, dir: n>s.mean?'↑':'↓'});
    });
    if (flags.length) {
      // Sort flags by z-score descending so most extreme come first
      flags.sort((a,b)=>b.z-a.z);
      outliers.push({idx: ri+1, flags});
    }
  });

  if (!outliers.length) {
    document.getElementById('sec-outliers').innerHTML =
      `<p style="color:#888;font-style:italic">No significant outliers found (z-threshold: ${Z_THRESH}).</p>`;
    return;
  }

  const zTooltip = 'Z-score: how many standard deviations this answer is from the group average. ' +
    'A value of 2 or more means the answer is unusually high or low compared to other respondents.';

  const cards = outliers.slice(0,40).map(o => {
    const countLabel = `${o.flags.length} unusual answer${o.flags.length>1?'s':''}`;

    const flagRows = o.flags.slice(0,8).map(f => {
      const isHigh  = f.dir === '↑';
      const dirCls  = isHigh ? 'dir-high' : 'dir-low';
      const dirSymbol = isHigh ? '▲' : '▼';
      const dirLabel  = isHigh ? 'Above avg' : 'Below avg';
      const their = f.norm.toFixed(0);
      const avg   = f.avg.toFixed(0);
      const diff  = Math.abs(f.norm - f.avg).toFixed(0);
      const fillPct  = Math.min(f.norm, 100);
      const avgPct   = Math.min(f.avg, 100);
      const fillCol  = scoreColour(f.norm);
      const shortLbl = f.label.length > 70 ? f.label.slice(0,70)+'…' : f.label;

      return `
        <div class="outlier-flag">
          <span class="dir-badge ${dirCls}" title="${dirLabel}">${dirSymbol}</span>
          <div class="flag-label">
            ${esc(shortLbl)}
            <span class="var-code">(${esc(f.v)})</span>
          </div>
          <div class="flag-scores">
            <div class="flag-their" style="color:${scoreColour(f.norm)}">${their}<span style="font-size:10px;color:#aaa">/100</span></div>
            <div class="flag-avg">avg ${avg} &nbsp; Δ${diff}</div>
            <span class="z-pill" title="${esc(zTooltip)}">z = ${f.z.toFixed(1)}</span>
          </div>
        </div>
        <div class="flag-bar-wrap">
          <div class="flag-bar-track">
            <div class="flag-bar-fill" style="width:${fillPct}%;background:${fillCol}"></div>
            <div class="flag-bar-avg-marker" style="left:${avgPct}%" title="Group average: ${avg}"></div>
          </div>
        </div>`;
    }).join('');

    const moreFlags = o.flags.length > 8
      ? `<div class="outlier-more">+ ${o.flags.length-8} more flagged questions</div>` : '';

    return `<div class="outlier-card">
      <div class="outlier-header">
        <span class="outlier-id">👤 Respondent #${o.idx}</span>
        <span class="outlier-count">${countLabel}</span>
      </div>
      ${flagRows}${moreFlags}
    </div>`;
  });

  const more = outliers.length > 40
    ? `<p style="color:#888;font-size:11px;margin-top:12px">… and ${outliers.length-40} more outlier respondents not shown</p>` : '';

  document.getElementById('sec-outliers').innerHTML =
    `<p style="font-size:11px;color:#888;margin-bottom:12px">
      Respondents whose answers deviate significantly from the group (z ≥ ${Z_THRESH}).
      The <strong>bar</strong> shows their score (coloured fill); the <strong>vertical line</strong> marks the group average.
      <span class="z-pill" title="${esc(zTooltip)}" style="cursor:help">What is z-score? ℹ</span>
    </p>
    <div class="outlier-grid">${cards.join('')}</div>${more}`;
}

function renderComments(filtered) {
  // Group answers by question ID, preserving original question order
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

  // Store answers globally for per-question search
  window._qAnswers = {};
  qids.forEach(q => { window._qAnswers[q] = byQid[q]; });

  function cardsHtml(answers) {
    if (!answers.length) return '<p class="no-data">No responses match your search.</p>';
    return answers.map(txt => `<div class="comment-card">${esc(txt)}</div>`).join('');
  }

  // Per-question search (debounced)
  const timers = {};
  window.filterQComments = function(qid, query) {
    clearTimeout(timers[qid]);
    timers[qid] = setTimeout(() => {
      const q = query.trim().toLowerCase();
      const all = window._qAnswers[qid] || [];
      const matched = q ? all.filter(t => t.toLowerCase().includes(q)) : all;
      const el = document.getElementById('qcards-' + qid);
      const ct = document.getElementById('qcount-' + qid);
      if (el) el.innerHTML = cardsHtml(matched);
      if (ct) ct.textContent = q
        ? `${matched.length.toLocaleString()} of ${all.length.toLocaleString()} match`
        : `${all.length.toLocaleString()} responses`;
    }, 150);
  };

  window.clearQSearch = function(qid) {
    const inp = document.getElementById('qsearch-' + qid);
    if (inp) { inp.value = ''; window.filterQComments(qid, ''); }
  };

  // Toggle collapse/expand per section
  window.toggleQSection = function(qid) {
    const body = document.getElementById('qbody-' + qid);
    const tog  = document.getElementById('qtog-' + qid);
    if (!body) return;
    const hidden = body.style.display === 'none';
    body.style.display = hidden ? '' : 'none';
    if (tog) tog.textContent = hidden ? '▲' : '▼';
  };

  const sections = qids.map(qid => {
    const label   = D.textVars[qid] || qid;
    const answers = byQid[qid];
    return `
      <div class="comment-section">
        <div class="comment-section-header" onclick="toggleQSection('${qid}')">
          <h3 class="comment-q-title">${esc(label)}</h3>
          <span class="comment-q-count">${answers.length.toLocaleString()} responses</span>
          <span class="comment-q-toggle" id="qtog-${qid}">▲</span>
        </div>
        <div class="comment-section-body" id="qbody-${qid}">
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
  renderOutliers(filtered, stats);
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
<div class="page">
  <h1>{h(title)}</h1>
  <p class="meta">Generated {generated} &nbsp;·&nbsp; Source: {h(path_str)}</p>

  <!-- Filter bar -->
  <div class="filter-bar">
    <span class="filter-title" id="filter-btn-label">🔍 Filters</span>
    <div id="filter-bar-controls" style="display:contents"></div>
    <div class="filter-actions">
      <button class="btn-reset" onclick="resetFilters()">Reset</button>
      <span class="filter-status" id="filter-status">Loading…</span>
    </div>
  </div>

  <!-- Summary cards (JS-rendered) -->
  <div id="sec-cards" class="section"></div>

  <!-- Score ranking -->
  <h2>Score Ranking <span style="font-weight:400;font-size:13px;color:#888">(normalised 0–100, ±1 SD shown)</span></h2>
  <div id="sec-ranking" class="section">{no_score_msg}</div>

  <!-- Per-question grid -->
  <h2>Question Breakdown</h2>
  <div id="sec-grid" class="section">{no_score_msg}</div>

  <!-- Top / Bottom 5 -->
  <h2>Top 5 &amp; Bottom 5</h2>
  <div id="sec-topbottom" class="section">{no_score_msg}</div>

  <!-- Outliers -->
  <h2>Outliers <span style="font-weight:400;font-size:13px;color:#888">(z ≥ 2.0)</span></h2>
  <div id="sec-outliers" class="section"></div>

  <!-- Comments -->
  <h2 id="sec-comments-heading">Open-ended Responses</h2>
  <div id="sec-comments" class="section"></div>

  <footer>Survey Indsight · Generated by report.py · {generated}</footer>
</div>

<script>window.SURVEY_DATA = {data_json};</script>
<script>{JS}</script>
</body>
</html>"""

out_path.write_text(html_content, encoding="utf-8")
print(f"✅ Report saved to: {out_path}")
print(f"   Filter by language, score etc. directly in the browser")
print(f"   File → Print → Save as PDF to export")
