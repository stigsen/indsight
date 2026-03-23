#!/usr/bin/env python3
"""
Statistical summary of survey scores.

Shows mean, median, mode, std dev and N per question.
Score 6 (N/A) is excluded from all calculations.
Use --variable for a detailed single-question breakdown with bar chart.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, is_score_var, numeric_vals, stats, distribution, bar_chart

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--variable", "-v", help="Focus on a single variable (e.g. s_27)")
parser.add_argument("--sort", choices=["mean", "median", "name"], default="mean",
                    help="Sort order for overview table (default: mean descending)")
parser.add_argument("--dataset", help="Path to a specific XML dataset file")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables = data["variables"]
labels = data["labels"]
respondents = data["respondents"]

score_vars = [v for v in variables if is_score_var(v)]
if args.variable:
    if args.variable not in variables:
        sys.exit(f"Unknown variable: {args.variable}")
    score_vars = [args.variable]

rows = []
for v in score_vars:
    vals = numeric_vals(respondents, v)
    if not vals:
        continue
    s = stats(vals)
    s["v"] = v
    s["desc"] = variables[v]
    rows.append(s)

if not rows:
    sys.exit("No data found.")

# Sort
if args.sort == "mean":
    rows.sort(key=lambda r: -(r["mean"] or 0))
elif args.sort == "median":
    rows.sort(key=lambda r: -(r["median"] or 0))
else:
    rows.sort(key=lambda r: r["v"])

# ── Single variable: detailed view ──────────────────────────────────────────
if args.variable and len(rows) == 1:
    r = rows[0]
    all_vals = numeric_vals(respondents, args.variable, exclude_na=False)
    valid_vals = [v for v in all_vals if v != 6]
    na_count = len(all_vals) - len(valid_vals)

    print(f"📋 {r['desc']}")
    print("─" * 58)
    print(f"  Mean    : {r['mean']:.2f}")
    print(f"  Median  : {r['median']}")
    print(f"  Mode    : {r['mode']}")
    print(f"  Std Dev : {r['sd']:.2f}")
    print(f"  N       : {r['n']} valid,  {na_count} N/A")
    print()
    print(bar_chart(r["desc"], distribution(valid_vals), labels.get(args.variable, {}), r["n"]))
    sys.exit(0)

# ── Overview table ───────────────────────────────────────────────────────────
print(f"Survey Summary — {len(respondents)} respondents  (sorted by {args.sort})\n")
print(f"{'Var':<8} {'Mean':>6} {'Med':>5} {'Mode':>5} {'SD':>5} {'N':>5}  Description")
print("─" * 80)
for r in rows:
    print(
        f"{r['v']:<8} {r['mean']:>6.2f} {r['median']:>5} {str(r['mode']):>5} "
        f"{r['sd']:>5.2f} {r['n']:>5}  {r['desc']}"
    )
