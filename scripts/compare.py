#!/usr/bin/env python3
"""Side-by-side comparison of two respondents (scores normalised to 0–100)."""

import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, normalize_score

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--email1", required=True)
parser.add_argument("--email2", required=True)
parser.add_argument("--dataset")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables, labels, respondents = data["variables"], data["labels"], data["respondents"]
var_meta, score_vars = data["var_meta"], data["score_vars"]
text_vars = [v for v in variables if var_meta.get(v, {}).get("type") == "text"
             and not v.startswith("statoverall")]

def find(frag):
    q = frag.lower()
    m = [r for r in respondents if (r.get("email") or "").lower().find(q) != -1]
    if not m: sys.exit(f"Respondent not found: {frag}")
    if len(m) > 1: print(f"⚠️  Multiple matches, using {m[0].get('email')}", file=sys.stderr)
    return m[0]

r1, r2 = find(args.email1), find(args.email2)

print(f"Comparing  R1: {r1.get('email')}  ↔  R2: {r2.get('email')}\n")
print(f"{'Variable':<18} {'R1':>6} {'R2':>6} {'Δ':>6}   Description")
print("─" * 72)
for v in score_vars:
    vtype = var_meta.get(v, {}).get("type", "other")
    def norm(r):
        raw = r.get(v)
        if raw is None or raw == "": return None
        try: return normalize_score(float(raw), vtype)
        except: return None
    n1, n2 = norm(r1), norm(r2)
    if n1 is None and n2 is None: continue
    d = round(n2 - n1) if n1 is not None and n2 is not None else None
    d_str = (f"+{d}" if d and d > 0 else str(d)) if d is not None else "?"
    marker = " ◀" if d is not None and abs(d) >= 15 else ""
    s1 = f"{n1:.0f}" if n1 is not None else "—"
    s2 = f"{n2:.0f}" if n2 is not None else "—"
    print(f"{v:<18} {s1:>6} {s2:>6} {d_str:>6}   {variables.get(v, v)}{marker}")
print()
for tv in text_vars:
    for r, label in [(r1, "R1"), (r2, "R2")]:
        val = r.get(tv)
        if val: print(f"💬 {label} [{variables.get(tv,tv)}]: {val}")
