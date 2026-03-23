#!/usr/bin/env python3
"""Rank survey topics by average score (normalised 0–100). Higher = more positive."""

import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _loader import load

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--top", type=int, default=5)
parser.add_argument("--bottom", type=int, default=5)
parser.add_argument("--all", action="store_true", dest="show_all")
parser.add_argument("--dataset")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables, var_meta, respondents = data["variables"], data["var_meta"], data["respondents"]

ranked = sorted(
    [{"v": v, "desc": variables.get(v, v), **var_meta[v]}
     for v in data["score_vars"] if var_meta[v].get("mean") is not None],
    key=lambda r: -(r["mean"])
)
if not ranked:
    print("ℹ️  No numeric score variables found."); sys.exit(0)

def render(items, title):
    print(title); print("─" * 65)
    for i, r in enumerate(items, 1):
        bar = "█" * round(r["mean"] / 100 * 28)
        print(f"{i:>2}. {bar:<28} {r['mean']:.1f}±{r['sd']:.1f}  (n={r['n']})  {r['desc']}")
    print()

print(f"📊 Survey Scores — {len(respondents)} respondents  (0–100 normalised)\n")
if args.show_all:
    render(ranked, f"All {len(ranked)} variables ranked")
else:
    render(ranked[:args.top], f"Top {args.top} — highest scores")
    render(list(reversed(ranked[-args.bottom:])), f"Bottom {args.bottom} — lowest scores")
