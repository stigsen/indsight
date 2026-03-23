#!/usr/bin/env python3
"""
Rank all survey topics by average priority score.

Shows the most- and least-wanted topics with a visual bar chart.
Score 6 (N/A) is excluded. Higher score = higher priority.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, is_score_var, numeric_vals, stats

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--top", type=int, default=5, help="Number of top items to show (default: 5)")
parser.add_argument("--bottom", type=int, default=5, help="Number of bottom items to show (default: 5)")
parser.add_argument("--all", action="store_true", dest="show_all", help="Show all topics ranked")
parser.add_argument("--dataset", help="Path to a specific XML dataset file")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables = data["variables"]
respondents = data["respondents"]

ranked = []
for v in variables:
    if not is_score_var(v):
        continue
    vals = numeric_vals(respondents, v)
    s = stats(vals)
    if s["n"] == 0:
        continue
    ranked.append({"v": v, "desc": variables[v], "mean": s["mean"], "n": s["n"], "sd": s["sd"]})

ranked.sort(key=lambda r: -r["mean"])

def render_list(items, title):
    print(title)
    print("─" * 65)
    for i, r in enumerate(items, 1):
        bar = "█" * round(r["mean"] / 5 * 24)
        print(f"{i:>2}. {bar:<24} {r['mean']:.2f} ±{r['sd']:.2f}  (n={r['n']})  {r['desc']}")
    print()

print(f"🏆 Survey Priorities — {len(respondents)} respondents\n")

if args.show_all:
    render_list(ranked, f"All {len(ranked)} topics ranked")
else:
    render_list(ranked[:args.top], f"Top {args.top} — highest priority")
    render_list(list(reversed(ranked[-args.bottom:])), f"Bottom {args.bottom} — lowest priority")
