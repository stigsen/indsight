#!/usr/bin/env python3
"""Detect outlier respondents using z-scores on normalised (0–100) scores."""

import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, normalize_score

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--z", type=float, default=1.5, dest="z_threshold")
parser.add_argument("--variable", "-v")
parser.add_argument("--dataset")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables, respondents = data["variables"], data["respondents"]
var_meta, score_vars = data["var_meta"], data["score_vars"]

if not score_vars:
    print("ℹ️  No numeric score variables found in this dataset."); sys.exit(0)

check_vars = [args.variable] if args.variable else score_vars
if args.variable and args.variable not in variables:
    sys.exit(f"Unknown variable: {args.variable}")

outliers = []
for r in respondents:
    email = r.get("email") or "(no email)"
    flags, all_norm = [], []
    for v in check_vars:
        raw = r.get(v)
        if raw is None or raw == "": continue
        m = var_meta.get(v, {})
        vtype = m.get("type", "other")
        if int(float(raw)) in m.get("na_values", set()): continue
        try:
            norm = normalize_score(float(raw), vtype)
        except: continue
        if norm is None: continue
        all_norm.append(norm)
        mean_v, sd_v = m.get("mean"), m.get("sd")
        if mean_v is not None and sd_v and sd_v > 0:
            z = abs((norm - mean_v) / sd_v)
            if z >= args.z_threshold:
                flags.append({"v": v, "raw": raw, "norm": norm, "z": z,
                               "dir": "HIGH ↑" if norm > mean_v else "LOW ↓",
                               "avg": mean_v, "desc": variables.get(v, v)})
    unique = set(round(x) for x in all_norm)
    is_straight = len(all_norm) >= 3 and len(unique) == 1
    if flags or is_straight:
        outliers.append({"email": email, "flags": flags, "is_straight": is_straight, "all_norm": all_norm})

if not outliers:
    print(f"✅ No outliers at z-threshold={args.z_threshold}."); sys.exit(0)

print(f"🔍 Outlier Detection  (z-threshold: {args.z_threshold})")
print("─" * 68)
for o in outliers:
    print(f"\n👤 {o['email']}")
    if o["is_straight"]:
        print(f"  ⚠️  Straight-liner — all scores ≈ {o['all_norm'][0]:.0f}/100")
    for f in o["flags"]:
        print(f"  ⚠️  {f['v']:<18} raw={f['raw']}  norm={f['norm']:.0f}  z={f['z']:.2f}  "
              f"{f['dir']}  (avg {f['avg']:.1f})  {f['desc']}")
