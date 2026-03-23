#!/usr/bin/env python3
"""Statistical summary of survey scores (all normalised to 0–100)."""

import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, get_norm_vals, stats, distribution_norm, bar_chart

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--variable", "-v")
parser.add_argument("--sort", choices=["mean", "median", "name"], default="mean")
parser.add_argument("--dataset")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables, labels, respondents = data["variables"], data["labels"], data["respondents"]
var_meta, score_vars = data["var_meta"], data["score_vars"]

if not score_vars:
    print("ℹ️  No numeric score variables found in this dataset.")
    sys.exit(0)

target_vars = [args.variable] if args.variable else score_vars
if args.variable and args.variable not in variables:
    sys.exit(f"Unknown variable: {args.variable}")

rows = []
for v in target_vars:
    m = var_meta.get(v, {})
    if m.get("mean") is None:
        continue
    rows.append({"v": v, "desc": variables.get(v, v), **m})

if args.sort == "mean":   rows.sort(key=lambda r: -(r.get("mean") or 0))
elif args.sort == "median": rows.sort(key=lambda r: -(r.get("median") or 0))
else: rows.sort(key=lambda r: r["v"])

if args.variable and len(rows) == 1:
    r = rows[0]
    norm_vals = get_norm_vals(respondents, args.variable, var_meta)
    all_raw = [resp.get(args.variable) for resp in respondents if resp.get(args.variable) not in (None,"")]
    na_count = len(all_raw) - r["n"]
    print(f"📋 {r['desc']}")
    print(f"   Type   : {r['type']}  (raw scale → normalised to 0–100)")
    print("─" * 60)
    print(f"  Mean    : {r['mean']:.1f}/100")
    print(f"  Median  : {r['median']:.1f}/100")
    print(f"  Std Dev : {r['sd']:.1f}")
    print(f"  N       : {r['n']} valid,  {na_count} N/A or empty")
    print()
    lbl = labels.get(args.variable, {})
    dist = distribution_norm(norm_vals)
    bucket_labels = {i: f"{i*20}–{(i+1)*20}%" for i in range(5)}
    print(bar_chart(r["desc"], dist, bucket_labels, r["n"]))
    sys.exit(0)

print(f"Survey Summary — {len(respondents)} respondents  (scores normalised 0–100, sorted by {args.sort})\n")
print(f"{'Var':<18} {'Type':<12} {'Mean':>6} {'Median':>7} {'SD':>6} {'N':>6}  Description")
print("─" * 90)
for r in rows:
    print(f"{r['v']:<18} {r['type']:<12} {r['mean']:>6.1f} {r['median']:>7.1f} {r['sd']:>6.1f} {r['n']:>6}  {r['desc']}")
