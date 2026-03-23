#!/usr/bin/env python3
"""
Side-by-side comparison of two respondents.

Shows each question with both scores and the difference (R2 − R1).
Useful for understanding how two people's priorities differ.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, is_score_var

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--email1", required=True, help="Email (or partial) of first respondent")
parser.add_argument("--email2", required=True, help="Email (or partial) of second respondent")
parser.add_argument("--dataset", help="Path to a specific XML dataset file")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables = data["variables"]
labels = data["labels"]
respondents = data["respondents"]

def find_respondent(email_fragment):
    q = email_fragment.lower()
    matches = [r for r in respondents if (r.get("email") or "").lower().find(q) != -1]
    if not matches:
        sys.exit(f"Respondent not found: {email_fragment}")
    if len(matches) > 1:
        print(f"⚠️  Multiple matches for '{email_fragment}': {[r.get('email') for r in matches]}", file=sys.stderr)
        print(f"   Using first match: {matches[0].get('email')}", file=sys.stderr)
    return matches[0]

r1 = find_respondent(args.email1)
r2 = find_respondent(args.email2)

score_vars = [v for v in variables if is_score_var(v)]

print(f"Comparing respondents")
print(f"  R1: {r1.get('email')}")
print(f"  R2: {r2.get('email')}")
print()
print(f"{'Var':<8} {'R1':>3} {'R2':>3} {'Δ':>4}   Description")
print("─" * 70)

diffs = []
for v in score_vars:
    try:
        s1 = int(r1.get(v) or "")
    except (ValueError, TypeError):
        s1 = None
    try:
        s2 = int(r2.get(v) or "")
    except (ValueError, TypeError):
        s2 = None

    if s1 is None and s2 is None:
        continue

    delta = (s2 - s1) if (s1 is not None and s2 is not None) else None
    delta_str = f"+{delta}" if delta is not None and delta > 0 else str(delta) if delta is not None else "?"
    s1_str = str(s1) if s1 is not None else "-"
    s2_str = str(s2) if s2 is not None else "-"
    diffs.append(abs(delta) if delta is not None else 0)

    # Highlight big differences
    marker = " ◀" if (delta is not None and abs(delta) >= 2) else ""
    print(f"{v:<8} {s1_str:>3} {s2_str:>3} {delta_str:>4}   {variables.get(v, v)}{marker}")

print()
if diffs:
    print(f"Average absolute difference: {sum(diffs)/len(diffs):.2f}")

# Comments
c1, c2 = r1.get("s_10"), r2.get("s_10")
if c1:
    print(f"\n💬 {r1.get('email')}: {c1}")
if c2:
    print(f"\n💬 {r2.get('email')}: {c2}")
