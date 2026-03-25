#!/usr/bin/env python3
"""
List all available dataset files in the datasets/ folder.
Run this to discover which files are available before generating a report.

Usage:
  python3 scripts/list_datasets.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _loader import list_datasets

files = list_datasets(cwd=Path(__file__).parent.parent)

if not files:
    print("No datasets found in datasets/.")
else:
    print(f"Found {len(files)} dataset(s) in datasets/:\n")
    for i, f in enumerate(files, 1):
        size_kb = f.stat().st_size // 1024
        print(f"  [{i}] {f.name}  ({size_kb} KB)")

print("\n  You can also provide a path to any .xlsx or .xml file outside this folder.")
print("  Example: /home/user/downloads/my_survey.xlsx")
