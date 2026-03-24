#!/usr/bin/env python3
"""ASCII bar charts of score distributions (normalised 0–100)."""

import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, get_norm_vals, distribution_norm, bar_chart

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--variables", "-v", nargs="+", metavar="VAR")
parser.add_argument("--dataset")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables, labels, respondents = data["variables"], data["labels"], data["respondents"]
var_meta, score_vars = data["var_meta"], data["score_vars"]

if not score_vars:
    print("ℹ️  No numeric score variables found in this dataset.")
    sys.exit(0)

to_graph = args.variables if args.variables else score_vars
bucket_labels = {i: f"{i*20}–{(i+1)*20 if i<4 else 100}%" for i in range(5)}

for v in to_graph:
    if v not in variables:
        print(f"⚠️  Unknown variable: {v}", file=sys.stderr); continue
    norm_vals = get_norm_vals(respondents, v, var_meta)
    if not norm_vals: continue
    dist = distribution_norm(norm_vals)
    print(bar_chart(variables[v], dist, bucket_labels, len(norm_vals)))
    print()
