# Survey Indsight Skill

## Purpose
Analyse survey datasets exported from SurveyXact (`.xml` or `.xlsx`).
Handles any dataset automatically — Likert 1–5, slider 0–100, binary yes/no, and open-ended text — normalising all numeric scores to a common **0–100 scale** for easy comparison.

## How to run this skill

When a user asks for a report or analysis, **always ask first**:

> "Do you want AI summaries of the open-ended responses? This includes a summary, themes, and sentiment scoring (1–5) per answer. It takes a moment but makes the comments section much more useful."

- **Yes** → Run `analyze_comments.py` to read all text answers, perform the full analysis described in `tools/summary_prompt.md`, write `analysis.json`, then run `report.py`. The report will include AI summaries, theme filter chips, and sentiment filters per question.
- **No** → Run `report.py` directly. The report is still fully functional — just without AI-enriched comments.

```bash
# Step 1 (if summaries requested): read all text data
python3 tools/analyze_comments.py --dataset datasets/myfile.xlsx

# Step 2: generate the HTML report (auto-loads analysis.json if present)
python3 tools/report.py --dataset datasets/myfile.xlsx --title "My Survey" --out report.html
```

The report opens in any browser. Use **File → Print → Save as PDF** to export.

---

## Dataset Format
SurveyXact exports an Excel-XML or OOXML file with sheets:
- **Variables** — variable names → human-readable descriptions
- **Labels** — score values → label text (e.g. `4` → "Meget vigtigt!")
- **Dataset** — one row per respondent

### Auto-detected variable types
| Type | Detection rule | Normalisation |
|---|---|---|
| `score_1_5` | Values ⊆ {1–6}, max ≤ 6 | (v-1)/4 × 100 |
| `score_0_100` | Slider values or max > 10 | as-is |
| `score_1_10` | Values ⊆ {1–10} | (v-1)/9 × 100 |
| `binary` | Values ⊆ {0,1} or {1,2} | × 100 |
| `text` | Any non-numeric content | — |
| `status` | `statoverall_*` columns | — |
| `email` | Column named `email` | — |

## Tools

| Tool | Script | Purpose |
|---|---|---|
| Variables | `tools/variables.py` | List all variables with types and mean scores |
| Summary | `tools/summary.py` | Stats table (mean, median, SD) — normalised 0–100 |
| Graph | `tools/graph.py` | ASCII distribution bar charts |
| Query | `tools/query.py` | Filter and inspect individual respondents |
| Outliers | `tools/outliers.py` | Z-score outlier detection |
| Priorities | `tools/priorities.py` | Rank topics by average score |
| Compare | `tools/compare.py` | Side-by-side comparison of two respondents |
| **Report** | **`tools/report.py`** | **Full HTML report with SVG charts + interactive filters** |
| **Analyze** | **`tools/analyze_comments.py`** | **Dump text answers for LLM analysis → `analysis.json`** |

## Usage

```bash
# Explore the dataset
python3 tools/variables.py
python3 tools/variables.py --dataset datasets/myfile.xlsx

# Statistics
python3 tools/summary.py
python3 tools/summary.py --variable s_3

# Visual distribution charts (ASCII)
python3 tools/graph.py

# Query respondents
python3 tools/query.py --email someone@company.com
python3 tools/query.py --variable s_1 --min 80   # normalised score ≥ 80/100

# Outlier detection
python3 tools/outliers.py

# Priority ranking
python3 tools/priorities.py --top 10 --bottom 10

# HTML report (open in browser → Print → Save as PDF)
python3 tools/report.py
python3 tools/report.py --dataset datasets/myfile.xlsx --title "Q1 Survey" --out report.html

# Dump comments for LLM analysis
python3 tools/analyze_comments.py
python3 tools/analyze_comments.py --question komm_1   # single question
```

## Adding More Datasets
Drop `.xml` or `.xlsx` files into `datasets/`. Tools auto-pick the first one found,
or use `--dataset` to target a specific file.
