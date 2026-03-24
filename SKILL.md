---
name: indsight
description: Analyse SurveyXact survey exports (.xlsx or .xml) and generate interactive HTML reports. Use when asked to analyse, report on, summarise, or explore survey data. Produces charts, score rankings, distribution heatmaps, sentiment analysis, and grouped open-ended responses. Supports interactive browser-side filtering by respondent attributes.
---

# Survey Indsight

Analyse survey datasets exported from SurveyXact (`.xml` or `.xlsx`).
Handles any dataset automatically — Likert 1–5, slider 0–100, binary yes/no, and open-ended text — normalising all numeric scores to a common **0–100 scale** for easy comparison.

## How to run this skill

When a user asks for a report or analysis, **always ask first**:

> "Do you want AI summaries of the open-ended responses? This includes a summary, themes, and sentiment scoring (1–5) per answer. It takes a moment but makes the comments section much more useful."

- **Yes** → Run `analyze_comments.py` to read all text answers, perform the full analysis described in [references/summary_prompt.md](references/summary_prompt.md), write `datasets/<name>_analysis.json`, then run `report.py`.
- **No** → Run `report.py` directly. The report is still fully functional — just without AI-enriched comments.

```bash
# Step 1 (if summaries requested): read all text data
python3 scripts/analyze_comments.py --dataset datasets/myfile.xlsx

# Step 2: generate the HTML report (auto-loads <name>_analysis.json if present)
python3 scripts/report.py --dataset datasets/myfile.xlsx --title "My Survey"
```

Output files are placed alongside the dataset:
- `datasets/myfile.html` — the interactive report
- `datasets/myfile_analysis.json` — AI analysis (if generated)

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

## Scripts

| Script | Purpose |
|---|---|
| `scripts/report.py` | Full interactive HTML report with SVG charts + browser-side filters |
| `scripts/analyze_comments.py` | Dump text answers for LLM analysis |
| `scripts/_loader.py` | Shared dataset loader (used by all scripts) |
| `scripts/variables.py` | List all variables with types and mean scores |
| `scripts/summary.py` | Stats table (mean, median, SD) |
| `scripts/graph.py` | ASCII distribution bar charts |
| `scripts/query.py` | Filter and inspect individual respondents |
| `scripts/priorities.py` | Rank topics by average score |

## Adding More Datasets

Drop `.xml` or `.xlsx` files into `datasets/`. Use `--dataset` to target a specific file.
