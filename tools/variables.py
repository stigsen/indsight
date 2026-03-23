#!/usr/bin/env python3
"""List all survey variables (questions) with their names and descriptions."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, is_score_var

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--dataset", help="Path to a specific XML dataset file")
parser.add_argument("--scores-only", action="store_true", help="Only show score variables (s_*)")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables = data["variables"]
respondents = data["respondents"]

if args.scores_only:
    variables = {k: v for k, v in variables.items() if is_score_var(k)}

print(f"Dataset: {data['path']}")
print(f"Respondents: {len(respondents)}   Variables: {len(variables)}\n")
print(f"{'Variable':<15} Description")
print("─" * 65)
for name, desc in variables.items():
    print(f"{name:<15} {desc}")
