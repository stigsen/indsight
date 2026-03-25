#!/usr/bin/env python3
"""Dump all respondent data as a structured, LLM-readable table.

Used by the skill's Query mode: Claude reads this output, then answers
any free-form question about the dataset (filters, cross-tabs, rankings,
spotting funny/unusual answers, etc.)

Usage:
  python3 scripts/dump_respondents.py
  python3 scripts/dump_respondents.py --dataset datasets/myfile.xlsx
  python3 scripts/dump_respondents.py --max 200          # cap rows (large datasets)
  python3 scripts/dump_respondents.py --format json      # machine-readable JSON
"""

import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _loader import load, normalize_score

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--dataset", "-d")
parser.add_argument("--format", choices=["table", "json"], default="table",
                    help="Output format (default: table)")
parser.add_argument("--max", type=int, default=0,
                    help="Maximum number of respondents to dump (0 = all)")
args = parser.parse_args()

data = load(path=args.dataset, cwd=Path(__file__).parent.parent)
variables  = data["variables"]   # var_name → description
labels     = data["labels"]      # var_name → {raw_val → label text}
respondents = data["respondents"]
var_meta   = data["var_meta"]
score_vars = data["score_vars"]

# All ordered columns (scores first, then text, skip status internals)
text_vars = [v for v in variables
             if var_meta.get(v, {}).get("type") == "text"
             and not v.startswith("statoverall")]
has_email  = any("email" in r for r in respondents[:5])
all_vars   = score_vars + text_vars

rows = respondents[:args.max] if args.max else respondents

# ── JSON output ────────────────────────────────────────────────────────────────
if args.format == "json":
    out = []
    for i, r in enumerate(rows, 1):
        rec = {"#": i}
        if has_email:
            rec["email"] = r.get("email", "")
        for v in all_vars:
            raw = r.get(v)
            if raw is None or raw == "":
                continue
            vtype = var_meta.get(v, {}).get("type", "other")
            desc  = variables.get(v, v)
            if vtype == "text":
                rec[desc or v] = raw
            else:
                try:
                    norm = normalize_score(float(raw), vtype)
                    norm_str = f"{norm:.0f}/100" if norm is not None else raw
                except (ValueError, TypeError):
                    norm_str = raw
                lbl = labels.get(v, {}).get(str(raw), "")
                rec[desc or v] = {"raw": raw, "score": norm_str, "label": lbl}
        out.append(rec)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0)

# ── Table output ───────────────────────────────────────────────────────────────
# Header block: explain all columns
print("=" * 70)
print(f"DATASET DUMP  —  {len(rows)} respondents  ({len(all_vars)} variables)")
print("=" * 70)
print("\nVARIABLE LEGEND")
print("-" * 70)
for v in all_vars:
    desc  = variables.get(v, "")
    vtype = var_meta.get(v, {}).get("type", "")
    lmap  = labels.get(v, {})
    lbl_str = "  [" + ", ".join(f"{k}={lv}" for k, lv in sorted(lmap.items())) + "]" if lmap else ""
    print(f"  {v:<20} ({vtype}){('  '+desc) if desc else ''}{lbl_str}")

print("\n" + "=" * 70)
print("RESPONDENTS")
print("=" * 70)

for i, r in enumerate(rows, 1):
    email = r.get("email", "")
    header = f"#{i}"
    if email:
        header += f"  {email}"
    print(f"\n{header}")
    print("-" * 50)

    for v in score_vars:
        raw = r.get(v)
        if raw is None or raw == "":
            continue
        vtype = var_meta.get(v, {}).get("type", "other")
        desc  = variables.get(v, v)
        try:
            norm = normalize_score(float(raw), vtype)
            norm_str = f"{norm:>5.0f}/100" if norm is not None else f"{raw:>9}"
        except (ValueError, TypeError):
            norm_str = f"{str(raw):>9}"
        lbl = labels.get(v, {}).get(str(raw), "")
        lbl_part = f"  [{lbl}]" if lbl else ""
        desc_part = f"  {desc}" if desc else ""
        print(f"  {v:<20} {norm_str}{lbl_part}{desc_part}")

    for v in text_vars:
        val = r.get(v)
        if not val:
            continue
        desc = variables.get(v, v)
        label_line = f"  [{desc}]" if desc else f"  [{v}]"
        print(f"  💬{label_line}")
        print(f"     {val}")

print(f"\n{'=' * 70}")
print(f"END OF DUMP  —  {len(rows)} respondents shown")
if args.max and len(respondents) > args.max:
    print(f"⚠️  Dataset has {len(respondents)} respondents total; use --max 0 to dump all.")
print("=" * 70)
