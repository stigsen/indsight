#!/usr/bin/env python3
"""
Query and inspect individual respondent responses.

Filter by email, variable name, and/or score range.
Returns the full response profile for each matching respondent.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, is_score_var

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--email", "-e", help="Filter by email address (partial match)")
parser.add_argument("--variable", "-v", help="Filter on this variable (combine with --min / --max)")
parser.add_argument("--min", type=int, dest="min_score", help="Minimum score (inclusive)")
parser.add_argument("--max", type=int, dest="max_score", help="Maximum score (inclusive)")
parser.add_argument("--no-comments", action="store_true", help="Suppress free-text comments")
parser.add_argument("--dataset", help="Path to a specific XML dataset file")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables = data["variables"]
labels = data["labels"]
headers = data["headers"]
respondents = data["respondents"]

# Apply filters
filtered = respondents

if args.email:
    q = args.email.lower()
    filtered = [r for r in filtered if (r.get("email") or "").lower().find(q) != -1]

if args.variable:
    if args.variable not in variables:
        sys.exit(f"Unknown variable: {args.variable}")
    def score_filter(r):
        try:
            v = int(r.get(args.variable) or "")
        except (ValueError, TypeError):
            return False
        if args.min_score is not None and v < args.min_score:
            return False
        if args.max_score is not None and v > args.max_score:
            return False
        return True
    filtered = [r for r in filtered if score_filter(r)]

if not filtered:
    print("No respondents match the filter.")
    sys.exit(0)

score_vars = [h for h in headers if is_score_var(h)]
show_comments = not args.no_comments

print(f"{len(filtered)} respondent(s) found\n")
for r in filtered:
    email = r.get("email") or "(no email)"
    print(f"👤 {email}")
    for v in score_vars:
        score = r.get(v)
        if score is None or score == "":
            continue
        lbl = labels.get(v, {}).get(score, "")
        desc = variables.get(v, v)
        print(f"  {v:<6}  {score}  {lbl:<28}  {desc}")
    if show_comments and r.get("s_10"):
        print(f"  💬 {r['s_10']}")
    print()
