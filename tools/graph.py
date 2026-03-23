#!/usr/bin/env python3
"""
ASCII bar charts showing score distributions.

Generates a bar chart per question so you can visually compare
how the team rated different topics.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, is_score_var, numeric_vals, distribution, bar_chart

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--variables", "-v", nargs="+", metavar="VAR",
                    help="Variable(s) to graph (e.g. s_27 s_28). Default: all score variables.")
parser.add_argument("--include-na", action="store_true",
                    help="Include score 6 (N/A) in the chart.")
parser.add_argument("--dataset", help="Path to a specific XML dataset file")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables = data["variables"]
labels = data["labels"]
respondents = data["respondents"]

exclude_na = not args.include_na
max_score = 6 if args.include_na else 5

vars_to_graph = args.variables if args.variables else [v for v in variables if is_score_var(v)]

for v in vars_to_graph:
    if v not in variables:
        print(f"⚠️  Unknown variable: {v}", file=sys.stderr)
        continue
    vals = numeric_vals(respondents, v, exclude_na=exclude_na)
    if not vals:
        continue
    dist = distribution(vals, min_score=1, max_score=max_score)
    print(bar_chart(variables[v], dist, labels.get(v, {}), len(vals)))
    print()
