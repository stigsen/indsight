#!/usr/bin/env python3
"""
Generate a self-contained HTML report with embedded SVG charts.
Open the output file in any browser and use File → Print → Save as PDF.

Usage:
  python3 tools/report.py                          # auto-detect dataset
  python3 tools/report.py --dataset datasets/d.xlsx
  python3 tools/report.py --out my_report.html
  python3 tools/report.py --title "Q1 2026 Survey"
"""

import argparse
import html
import sys
import statistics
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, get_norm_vals, normalize_score

# ── CLI ───────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--dataset", help="Path to dataset file (.xml or .xlsx)")
parser.add_argument("--out", help="Output HTML file (default: report.html in project root)")
parser.add_argument("--title", help="Custom report title")
parser.add_argument("--top", type=int, default=20, help="Max questions to include in ranking chart")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables = data["variables"]
labels = data["labels"]
respondents = data["respondents"]
var_meta = data["var_meta"]
score_vars = data["score_vars"]
path_str = data["path"]

out_path = Path(args.out) if args.out else Path(__file__).parent.parent / "report.html"
title = args.title or f"Survey Report — {Path(path_str).name}"
generated = datetime.now().strftime("%Y-%m-%d %H:%M")

# ── Colour helpers ────────────────────────────────────────────────────────────

def score_colour(pct: float) -> str:
    """Interpolate red→amber→green for a 0-100 score."""
    pct = max(0.0, min(100.0, pct))
    if pct < 50:
        r, g = 220, int(pct / 50 * 180)
    else:
        r, g = int((1 - (pct - 50) / 50) * 180), 170
    return f"rgb({r},{g},60)"


def score_bg(pct: float) -> str:
    """Light pastel background for score badge."""
    pct = max(0.0, min(100.0, pct))
    if pct >= 75:   return "#d4edda"
    if pct >= 50:   return "#fff3cd"
    return "#f8d7da"


def score_fg(pct: float) -> str:
    if pct >= 75:   return "#155724"
    if pct >= 50:   return "#856404"
    return "#721c24"

# ── SVG builders ──────────────────────────────────────────────────────────────

def svg_hbar_chart(items: list[dict], width=680, row_h=38, bar_area=340,
                   label_w=220, val_w=60) -> str:
    """
    Horizontal bar chart.
    items: [{label, value (0-100), n, sd}]
    """
    height = row_h * len(items) + 20
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'style="font-family:\'Segoe UI\',Arial,sans-serif;font-size:12px;">']

    # Grid lines at 25, 50, 75, 100
    bar_x = label_w + 10
    for pct in (25, 50, 75, 100):
        x = bar_x + pct / 100 * bar_area
        colour = "#ddd" if pct < 100 else "#bbb"
        parts.append(f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{height}" '
                     f'stroke="{colour}" stroke-width="1"/>')
        parts.append(f'<text x="{x:.1f}" y="{height-2}" text-anchor="middle" '
                     f'fill="#aaa" font-size="10">{pct}</text>')

    for i, item in enumerate(items):
        y = i * row_h
        val = item.get("value") or 0
        bar_w = val / 100 * bar_area
        col = score_colour(val)
        lbl = html.escape(item["label"][:38] + ("…" if len(item["label"]) > 38 else ""))
        n = item.get("n", "")
        sd = item.get("sd", None)

        # Row background (alternating)
        if i % 2 == 0:
            parts.append(f'<rect x="0" y="{y}" width="{width}" height="{row_h}" fill="#fafafa"/>')

        # Label
        parts.append(f'<text x="{label_w - 6}" y="{y + row_h//2 + 4}" '
                     f'text-anchor="end" fill="#333" font-size="11">{lbl}</text>')

        # Bar
        parts.append(f'<rect x="{bar_x}" y="{y + 8}" width="{bar_w:.1f}" height="{row_h - 16}" '
                     f'fill="{col}" rx="3"/>')

        # Std dev tick
        if sd is not None:
            sd_x = bar_x + (val + sd) / 100 * bar_area
            sd_x2 = bar_x + max(0, (val - sd)) / 100 * bar_area
            mid_y = y + row_h // 2
            parts.append(f'<line x1="{sd_x2:.1f}" y1="{mid_y}" x2="{sd_x:.1f}" y2="{mid_y}" '
                         f'stroke="#555" stroke-width="1" opacity="0.5"/>')
            parts.append(f'<line x1="{sd_x:.1f}" y1="{y+10}" x2="{sd_x:.1f}" y2="{y+row_h-10}" '
                         f'stroke="#555" stroke-width="1.5" opacity="0.5"/>')

        # Value label
        val_x = bar_x + bar_w + 6
        parts.append(f'<text x="{val_x:.1f}" y="{y + row_h//2 + 4}" '
                     f'fill="#333" font-size="11" font-weight="600">{val:.1f}</text>')

        # n label
        n_x = bar_x + bar_area + 8
        parts.append(f'<text x="{n_x}" y="{y + row_h//2 + 4}" fill="#888" font-size="10">n={n}</text>')

    parts.append("</svg>")
    return "\n".join(parts)


def svg_dist_chart(norm_vals: list, label_map: dict, var_type: str,
                   width=260, height=140) -> str:
    """Small distribution bar chart for a single question."""
    if not norm_vals:
        return ""

    # Build buckets based on variable type
    if var_type == "score_1_5":
        # Use original 5 buckets mapped to 0-100
        bucket_edges = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]
        bucket_labels_list = [label_map.get(str(i), f"Score {i}") for i in range(1, 6)]
    elif var_type == "binary":
        bucket_edges = [(0, 50), (50, 101)]
        bucket_labels_list = ["No", "Yes"]
    else:
        bucket_edges = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]
        bucket_labels_list = ["0–20", "20–40", "40–60", "60–80", "80–100"]

    counts = [0] * len(bucket_edges)
    for v in norm_vals:
        for idx, (lo, hi) in enumerate(bucket_edges):
            if lo <= v < hi:
                counts[idx] += 1
                break
        else:
            counts[-1] += 1

    total = len(norm_vals)
    max_count = max(counts) or 1
    n_buckets = len(bucket_edges)
    pad = 30
    chart_w = width - pad
    chart_h = height - 35
    bar_w = chart_w / n_buckets - 4

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'style="font-family:\'Segoe UI\',Arial,sans-serif;font-size:10px;">']

    for i, (count, (lo, _)) in enumerate(zip(counts, bucket_edges)):
        bh = count / max_count * chart_h
        x = pad + i * (bar_w + 4)
        y = chart_h - bh
        mid_score = lo + (bucket_edges[i][1] - lo) / 2
        col = score_colour(mid_score)
        pct = round(count / total * 100)

        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" '
                     f'fill="{col}" rx="2"/>')
        if count > 0:
            parts.append(f'<text x="{x + bar_w/2:.1f}" y="{y - 3:.1f}" '
                         f'text-anchor="middle" fill="#444" font-size="9">{pct}%</text>')

        short_lbl = bucket_labels_list[i] if i < len(bucket_labels_list) else str(lo)
        short_lbl = (short_lbl[:8] + "…") if len(short_lbl) > 9 else short_lbl
        parts.append(f'<text x="{x + bar_w/2:.1f}" y="{height - 5}" '
                     f'text-anchor="middle" fill="#666" font-size="9">{html.escape(short_lbl)}</text>')

    # y-axis label
    parts.append(f'<text x="0" y="{height//2}" transform="rotate(-90,8,{height//2})" '
                 f'text-anchor="middle" fill="#999" font-size="9">count</text>')

    parts.append("</svg>")
    return "\n".join(parts)


def svg_gauge(value: float, size=100) -> str:
    """Semi-circle gauge for a 0-100 score."""
    import math
    cx, cy, r = size // 2, size // 2 + 10, size // 2 - 10
    angle = (1 - value / 100) * math.pi
    x_end = cx + r * math.cos(angle)
    y_end = cy - r * math.sin(angle)
    col = score_colour(value)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size//2 + 20}" '
             f'style="font-family:\'Segoe UI\',Arial,sans-serif;">']
    # Background arc
    parts.append(f'<path d="M {cx-r} {cy} A {r} {r} 0 0 1 {cx+r} {cy}" '
                 f'fill="none" stroke="#e9e9e9" stroke-width="12" stroke-linecap="round"/>')
    # Value arc
    parts.append(f'<path d="M {cx-r} {cy} A {r} {r} 0 0 1 {x_end:.2f} {y_end:.2f}" '
                 f'fill="none" stroke="{col}" stroke-width="12" stroke-linecap="round"/>')
    # Value text
    parts.append(f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" '
                 f'font-size="16" font-weight="bold" fill="#333">{value:.1f}</text>')
    parts.append(f'<text x="{cx}" y="{cy + 18}" text-anchor="middle" '
                 f'font-size="9" fill="#888">/ 100</text>')
    parts.append("</svg>")
    return "\n".join(parts)


# ── Data preparation ──────────────────────────────────────────────────────────

ranked = sorted(
    [{"v": v, "label": variables.get(v, v), **var_meta[v]}
     for v in score_vars if var_meta[v].get("mean") is not None],
    key=lambda r: -r["mean"]
)

# Overall stats
all_means = [r["mean"] for r in ranked if r.get("mean") is not None]
overall_avg = statistics.mean(all_means) if all_means else 0
n_resp = len(respondents)
n_completed = sum(1 for r in respondents if r.get("statoverall_4") == "1")
completion_pct = n_completed / n_resp * 100 if n_resp else 100

# Text comments
text_vars = [(v, desc) for v, desc in variables.items()
             if var_meta.get(v, {}).get("type") == "text"
             and not v.startswith("statoverall")]
comments = []
for r in respondents:
    for tv, tdesc in text_vars:
        val = r.get(tv)
        if val and str(val).strip():
            comments.append({"email": r.get("email") or "—", "question": tdesc, "text": str(val).strip()})

# Outliers (z > 2.0)
Z_THRESH = 2.0
outlier_rows = []
for r in respondents:
    email = r.get("email") or "(no email)"
    flags = []
    for v in score_vars:
        m = var_meta.get(v, {})
        raw = r.get(v)
        if raw is None or raw == "": continue
        try:
            fv = float(raw)
            if int(fv) in m.get("na_values", set()): continue
            norm = normalize_score(fv, m.get("type", "other"))
        except: continue
        if norm is None: continue
        mean_v, sd_v = m.get("mean"), m.get("sd")
        if mean_v is not None and sd_v and sd_v > 0:
            z = abs((norm - mean_v) / sd_v)
            if z >= Z_THRESH:
                flags.append({"v": v, "desc": variables.get(v, v),
                               "norm": norm, "avg": mean_v, "z": z,
                               "dir": "↑" if norm > mean_v else "↓"})
    if flags:
        outlier_rows.append({"email": email, "flags": flags})

# ── HTML assembly ─────────────────────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px;
       color: #333; background: #f5f6fa; }
.page { max-width: 960px; margin: 0 auto; padding: 24px; background: #fff;
        box-shadow: 0 2px 12px rgba(0,0,0,.08); }
h1 { font-size: 24px; font-weight: 700; color: #1a1a2e; margin-bottom: 4px; }
h2 { font-size: 17px; font-weight: 600; color: #1a1a2e; margin: 32px 0 12px;
     padding-bottom: 6px; border-bottom: 2px solid #4361ee; }
h3 { font-size: 13px; font-weight: 600; color: #555; margin-bottom: 6px; }
.meta { color: #888; font-size: 12px; margin-bottom: 24px; }
.cards { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 8px; }
.card { background: #fff; border: 1px solid #e0e0e0; border-radius: 10px;
        padding: 16px 20px; flex: 1; min-width: 140px; text-align: center;
        box-shadow: 0 1px 4px rgba(0,0,0,.05); }
.card .big { font-size: 32px; font-weight: 700; line-height: 1.1; }
.card .lbl { font-size: 11px; color: #888; margin-top: 4px; }
.badge { display:inline-block; padding: 2px 8px; border-radius: 12px;
         font-size: 12px; font-weight: 600; }
.section { margin-bottom: 32px; }
.chart-wrap { overflow-x: auto; }
.question-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px,1fr));
                  gap: 16px; }
.q-card { background: #fafafa; border: 1px solid #e8e8e8; border-radius: 8px;
           padding: 12px; }
.q-card .q-title { font-size: 11px; color: #555; margin-bottom: 8px;
                    line-height: 1.3; min-height: 28px; }
.q-card .q-stats { display:flex; gap:8px; font-size:11px; color:#888;
                    margin-top:6px; }
.q-card .q-mean { font-size:14px; font-weight:700; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { background: #f0f2ff; text-align: left; padding: 7px 10px;
     font-weight: 600; color: #444; border-bottom: 2px solid #dde; }
td { padding: 6px 10px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }
tr:hover td { background: #f8f9ff; }
.comment-card { background: #fff; border-left: 3px solid #4361ee;
                padding: 8px 12px; margin-bottom: 8px; border-radius: 0 6px 6px 0;
                font-size: 12px; }
.comment-meta { font-size: 10px; color: #888; margin-bottom: 4px; }
.flag-high { color: #c0392b; font-weight: 600; }
.flag-low  { color: #2980b9; font-weight: 600; }
.type-tag { font-size: 10px; background: #eef2ff; color: #4361ee;
            padding: 1px 6px; border-radius: 8px; margin-left: 6px; }
footer { text-align:center; font-size:11px; color:#bbb; margin-top:40px; }
@media print {
  body { background: #fff; }
  .page { box-shadow: none; padding: 0; }
  h2 { page-break-after: avoid; }
  .q-card, .comment-card { break-inside: avoid; }
}
"""

def h(s): return html.escape(str(s))

def badge(value):
    bg = score_bg(value)
    fg = score_fg(value)
    return f'<span class="badge" style="background:{bg};color:{fg}">{value:.1f}</span>'

# Build ranking chart data
chart_items = [{"label": r["label"], "value": r["mean"], "n": r["n"], "sd": r["sd"]}
               for r in ranked[:args.top]]

# ── Sections ──────────────────────────────────────────────────────────────────

sections = []

# 1. Summary cards
compl_str = f"{n_completed:,} ({completion_pct:.0f}%)" if n_completed > 0 else f"{n_resp:,}"
cards_html = f"""
<div class="cards">
  <div class="card">
    <div class="big" style="color:#4361ee">{n_resp:,}</div>
    <div class="lbl">Respondents</div>
  </div>
  <div class="card">
    <div class="big" style="color:#4361ee">{len(score_vars)}</div>
    <div class="lbl">Score questions</div>
  </div>
  <div class="card">
    <div class="big">{svg_gauge(overall_avg, 100)}</div>
    <div class="lbl">Overall avg (0–100)</div>
  </div>
  <div class="card">
    <div class="big" style="color:#4361ee">{len(text_vars)}</div>
    <div class="lbl">Open-ended questions</div>
  </div>
  <div class="card">
    <div class="big" style="color:#4361ee">{len(comments)}</div>
    <div class="lbl">Comments received</div>
  </div>
</div>"""
sections.append(cards_html)

# 2. Score ranking chart
if ranked:
    chart_svg = svg_hbar_chart(chart_items)
    top_label = f"Top {args.top}" if len(ranked) > args.top else "All"
    sections.append(f"""
<h2>Score Ranking <span style="font-weight:400;font-size:13px;color:#888">(normalised 0–100, ±1 SD shown)</span></h2>
<div class="chart-wrap">{chart_svg}</div>""")

# 3. Per-question detail grid
if ranked:
    cards_grid = []
    for r in ranked:
        v = r["v"]
        norm_vals = get_norm_vals(respondents, v, var_meta)
        lbl = labels.get(v, {})
        dist_svg = svg_dist_chart(norm_vals, lbl, r["type"])
        type_tag = f'<span class="type-tag">{r["type"]}</span>'
        na_count = len([resp for resp in respondents
                        if resp.get(v) is None or resp.get(v) == ""
                        or int(float(resp[v])) in r.get("na_values", set())
                        if resp.get(v) is not None])
        cards_grid.append(f"""
<div class="q-card">
  <div class="q-title">{h(r['label'])}{type_tag}</div>
  <div style="display:flex;align-items:flex-end;gap:10px">
    {dist_svg}
    <div>
      <div class="q-mean">{badge(r['mean'])}</div>
      <div class="q-stats">
        <span>±{r['sd']:.1f} SD</span>
        <span>n={r['n']:,}</span>
      </div>
      <div class="q-stats" style="margin-top:4px">
        <span>med {r['median']:.0f}</span>
      </div>
    </div>
  </div>
</div>""")
    sections.append(f"""
<h2>Question Breakdown</h2>
<div class="question-grid">{''.join(cards_grid)}</div>""")

# 4. Top / Bottom table
if len(ranked) >= 4:
    top5 = ranked[:5]
    bot5 = list(reversed(ranked[-5:]))
    def tb_row(r, rank, kind):
        colour = "#155724" if kind == "top" else "#721c24"
        return f"""<tr>
          <td style="color:{colour};font-weight:600">#{rank}</td>
          <td><code style="font-size:11px">{h(r['v'])}</code></td>
          <td>{h(r['label'])}</td>
          <td style="text-align:center">{badge(r['mean'])}</td>
          <td style="text-align:center;color:#888">±{r['sd']:.1f}</td>
          <td style="text-align:right;color:#888">{r['n']:,}</td>
        </tr>"""
    top_rows = "".join(tb_row(r, i+1, "top") for i, r in enumerate(top5))
    bot_rows = "".join(tb_row(r, len(ranked)-i, "bottom") for i, r in enumerate(bot5))
    hdr = "<tr><th>#</th><th>Var</th><th>Description</th><th>Mean</th><th>SD</th><th>N</th></tr>"
    sections.append(f"""
<h2>Top 5 &amp; Bottom 5</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px">
  <div>
    <h3>🏆 Highest scores</h3>
    <table>{hdr}{top_rows}</table>
  </div>
  <div>
    <h3>⚠️ Lowest scores</h3>
    <table>{hdr}{bot_rows}</table>
  </div>
</div>""")

# 5. Outliers
if outlier_rows:
    out_rows_html = []
    for o in outlier_rows[:50]:  # cap at 50 for readability
        flag_parts = []
        for f in o["flags"]:
            cls = "flag-high" if f["dir"] == "↑" else "flag-low"
            flag_parts.append(
                f'<span class="{cls}">{h(f["v"])} {f["dir"]} {f["norm"]:.0f}'
                f' (z={f["z"]:.1f})</span>'
            )
        out_rows_html.append(f"""<tr>
          <td>{h(o['email'])}</td>
          <td>{len(o['flags'])}</td>
          <td>{" &nbsp; ".join(flag_parts)}</td>
        </tr>""")
    sections.append(f"""
<h2>Outliers <span style="font-weight:400;font-size:13px;color:#888">(z ≥ {Z_THRESH:.1f})</span></h2>
<table>
  <tr><th>Respondent</th><th># Flags</th><th>Flagged questions</th></tr>
  {''.join(out_rows_html)}
</table>""")
else:
    sections.append(f"""
<h2>Outliers</h2>
<p style="color:#888;font-style:italic">No significant outliers found (z-threshold: {Z_THRESH}).</p>""")

# 6. Comments
if comments:
    capped = comments[:100]
    comment_cards = []
    for c in capped:
        comment_cards.append(f"""
<div class="comment-card">
  <div class="comment-meta">👤 {h(c['email'])} &nbsp;·&nbsp; {h(c['question'])}</div>
  {h(c['text'])}
</div>""")
    more = f'<p style="color:#888;font-size:11px;margin-top:8px">... and {len(comments)-100} more</p>' \
           if len(comments) > 100 else ""
    sections.append(f"""
<h2>Open-ended Responses ({len(comments)} total)</h2>
{''.join(comment_cards)}{more}""")

# ── Final HTML ────────────────────────────────────────────────────────────────

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
  {''.join(sections)}
  <footer>Survey Indsight · Generated by report.py · {generated}</footer>
</div>
</body>
</html>"""

out_path.write_text(html_content, encoding="utf-8")
print(f"✅ Report saved to: {out_path}")
print(f"   Open in browser and use File → Print → Save as PDF")
