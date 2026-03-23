#!/usr/bin/env python3
"""
Detect outlier respondents using z-scores.

Flags anyone whose score on a question deviates significantly from
the group average. Also detects straight-liners (same score on all questions).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, is_score_var, numeric_vals, stats

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--z", type=float, default=1.5, dest="z_threshold",
                    help="Z-score threshold to flag a response as unusual (default: 1.5)")
parser.add_argument("--variable", "-v", help="Focus on a single variable instead of all")
parser.add_argument("--dataset", help="Path to a specific XML dataset file")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables = data["variables"]
respondents = data["respondents"]

score_vars = ([args.variable] if args.variable else [v for v in variables if is_score_var(v)])
if args.variable and args.variable not in variables:
    sys.exit(f"Unknown variable: {args.variable}")

# Pre-compute per-variable stats
var_stats = {}
for v in score_vars:
    vals = numeric_vals(respondents, v)
    var_stats[v] = stats(vals)

# Evaluate each respondent
results = []
for r in respondents:
    email = r.get("email") or "(no email)"
    flags = []
    all_scores = []

    for v in score_vars:
        try:
            score = int(r.get(v) or "")
        except (ValueError, TypeError):
            continue
        if score == 6:
            continue
        all_scores.append(score)

        s = var_stats[v]
        if s["n"] >= 2 and s["sd"] and s["sd"] > 0:
            z = abs((score - s["mean"]) / s["sd"])
            if z >= args.z_threshold:
                direction = "HIGH ↑" if score > s["mean"] else "LOW ↓"
                flags.append({
                    "v": v,
                    "score": score,
                    "z": round(z, 2),
                    "direction": direction,
                    "desc": variables.get(v, v),
                    "group_mean": round(s["mean"], 2),
                })

    unique = set(all_scores)
    is_straight = len(all_scores) >= 3 and len(unique) == 1

    if flags or is_straight:
        results.append({"email": email, "flags": flags, "is_straight": is_straight, "all_scores": all_scores})

if not results:
    print(f"✅ No outliers found at z-threshold={args.z_threshold}. All responses look normal.")
    sys.exit(0)

print(f"🔍 Outlier Detection  (z-threshold: {args.z_threshold})")
print("─" * 65)
print()

for o in results:
    print(f"👤 {o['email']}")
    if o["is_straight"]:
        score_val = o["all_scores"][0]
        print(f"  ⚠️  Straight-liner — every score = {score_val}")
    for f in o["flags"]:
        print(
            f"  ⚠️  {f['v']:<6}  score={f['score']}  z={f['z']}  {f['direction']}  "
            f"(group avg {f['group_mean']})  {f['desc']}"
        )
    print()
