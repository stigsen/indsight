#!/usr/bin/env python3
"""List all survey variables with their types and descriptions."""

import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _loader import load

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--dataset", help="Path to a specific dataset file (.xml or .xlsx)")
parser.add_argument("--scores-only", action="store_true", help="Only show score variables")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables = data["variables"]
var_meta = data["var_meta"]
respondents = data["respondents"]

if args.scores_only:
    variables = {k: v for k, v in variables.items() if k in data["score_vars"]}

print(f"Dataset : {data['path']}")
print(f"Respondents: {len(respondents)}   Variables: {len(variables)}\n")
print(f"{'Variable':<18} {'Type':<14} {'Mean/100':>8}  Description")
print("─" * 75)
for name, desc in variables.items():
    m = var_meta.get(name, {})
    vtype = m.get("type", "?")
    mean_str = f"{m['mean']:.1f}" if m.get("mean") is not None else "—"
    print(f"{name:<18} {vtype:<14} {mean_str:>8}  {desc}")
