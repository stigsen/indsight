#!/usr/bin/env python3
"""
Dump all open-ended survey answers grouped by question.
Run this tool, read the output, then write analysis.json following
the instructions in tools/summary_prompt.md.

Usage:
  python3 tools/analyze_comments.py                          # all questions
  python3 tools/analyze_comments.py --dataset datasets/d.xlsx
  python3 tools/analyze_comments.py --question komm_1        # one question only
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _loader import load

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--dataset",  help="Path to dataset file (.xml or .xlsx)")
parser.add_argument("--question", help="Analyse a single question variable (e.g. komm_1)")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables  = data["variables"]
var_meta   = data["var_meta"]
respondents = data["respondents"]

text_vars = [(v, desc) for v, desc in variables.items()
             if var_meta.get(v, {}).get("type") == "text"
             and not v.startswith("statoverall")]

if args.question:
    text_vars = [(v, d) for v, d in text_vars if v == args.question]
    if not text_vars:
        sys.exit(f"❌ Question '{args.question}' not found or is not a text variable.")

print(f"Dataset : {data['path']}")
print(f"Questions: {len(text_vars)}")
print()

for v, label in text_vars:
    answers = [str(r[v]).strip() for r in respondents
               if r.get(v) and str(r.get(v)).strip()]
    print("=" * 70)
    print(f"QUESTION: {v}")
    print(f"LABEL   : {label}")
    print(f"ANSWERS : {len(answers)}")
    print("-" * 70)
    for i, a in enumerate(answers):
        print(f"[{i}] {a}")
    print()
