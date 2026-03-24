#!/usr/bin/env python3
"""Query individual respondent data. Filter by email, variable, and/or score range."""

import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, normalize_score

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--email", "-e")
parser.add_argument("--variable", "-v")
parser.add_argument("--min", type=float, dest="min_score", help="Min normalised score (0-100)")
parser.add_argument("--max", type=float, dest="max_score", help="Max normalised score (0-100)")
parser.add_argument("--no-comments", action="store_true")
parser.add_argument("--dataset")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables, labels, headers = data["variables"], data["labels"], data["headers"]
respondents, var_meta, score_vars = data["respondents"], data["var_meta"], data["score_vars"]

text_vars = [v for v in variables if var_meta.get(v, {}).get("type") == "text"
             and not v.startswith("statoverall")]

filtered = respondents
if args.email:
    q = args.email.lower()
    filtered = [r for r in filtered if (r.get("email") or "").lower().find(q) != -1]

if args.variable:
    if args.variable not in variables:
        sys.exit(f"Unknown variable: {args.variable}")
    vtype = var_meta.get(args.variable, {}).get("type", "other")
    def score_ok(r):
        raw = r.get(args.variable)
        if raw is None or raw == "": return False
        try:
            n = normalize_score(float(raw), vtype)
            if n is None: return False
            if args.min_score is not None and n < args.min_score: return False
            if args.max_score is not None and n > args.max_score: return False
            return True
        except (ValueError, TypeError): return False
    filtered = [r for r in filtered if score_ok(r)]

if not filtered:
    print("No respondents match the filter."); sys.exit(0)

show_comments = not args.no_comments
print(f"{len(filtered)} respondent(s) found\n")

for r in filtered:
    email = r.get("email") or "(no email)"
    print(f"👤 {email}")
    for v in score_vars:
        raw = r.get(v)
        if raw is None or raw == "": continue
        vtype = var_meta.get(v, {}).get("type", "other")
        try:
            n = normalize_score(float(raw), vtype)
            norm_str = f"→ {n:.0f}/100" if n is not None else ""
        except: norm_str = ""
        lbl = labels.get(v, {}).get(str(raw), "")
        desc = variables.get(v, v)
        print(f"  {v:<18} {str(raw):<5} {norm_str:<10} {lbl:<28} {desc}")
    if show_comments:
        for tv in text_vars:
            val = r.get(tv)
            if val: print(f"  💬 [{variables.get(tv, tv)}] {val}")
    print()
