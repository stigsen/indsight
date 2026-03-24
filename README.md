# Indsight — Survey Analysis Skill

An [Agent Skill](https://agentskills.io) for analysing [SurveyXact](https://www.surveyxact.com) survey exports. Drop in a dataset, ask Claude to generate a report, and get a fully interactive HTML report with charts, filters, and AI-powered comment analysis.

---

## What it does

- **Interactive HTML report** — opens in any browser, no server needed
- **Score rankings & heatmap** — all questions normalised to 0–100 for easy comparison
- **Distribution heatmap** — see where respondents cluster per question at a glance
- **Top 5 / Bottom 5** — instantly spot strongest and weakest areas
- **Live browser filters** — filter by language, department, or any categorical variable; all charts update instantly
- **Grouped open-ended responses** — all answers per question with per-section text search
- **AI comment analysis** *(optional)* — LLM-generated summary, themes, and per-answer sentiment (1–5) for every open-ended question
- **Sentiment overview chart** — stacked bar showing mood distribution across all open-ended questions

## Example report

![Score heatmap and sentiment overview](assets/preview.png)

---

## Quick start

```bash
# Clone the skill
git clone https://github.com/stigsen/indsight.git
cd indsight

# Place your SurveyXact export in datasets/
cp /path/to/my_survey.xlsx datasets/

# Generate a report (Claude will ask about AI summaries)
python3 scripts/report.py --dataset datasets/my_survey.xlsx --title "Q1 2026 Survey"
```

Open `datasets/my_survey.html` in your browser.

---

## Using with Claude

This repo is a standard Agent Skill. Load it in Claude and simply ask:

> *"Make me a report for the dataset in the datasets folder"*

Claude will:
1. Ask if you want AI summaries of open-ended responses
2. If yes — read all comments, generate summaries/themes/sentiment, write `datasets/<name>_analysis.json`
3. Generate `datasets/<name>.html` — the full interactive report

---

## Report sections

| Section | Description |
|---|---|
| **Summary cards** | Respondent count, question count, overall average gauge |
| **Score Ranking** | Horizontal bar chart, all questions sorted by mean ± SD |
| **Question Breakdown** | Per-question distribution bars with mean, median, SD |
| **Top 5 / Bottom 5** | Best and worst performing questions |
| **Score Distribution Heatmap** | Grid: questions × score buckets, colour intensity = % of respondents |
| **Sentiment Overview** | Stacked bar per open-ended question (😟 → 😄) |
| **Open-ended Responses** | Grouped by question; text search, theme chips, sentiment filters |

---

## Dataset format

SurveyXact exports as `.xlsx` or `.xml` with three sheets:

| Sheet | Contents |
|---|---|
| **Variables** | Variable code → human-readable label |
| **Labels** | Score value → label text (e.g. `4` → "Very satisfied") |
| **Dataset** | One row per respondent |

Variable types are auto-detected:

| Type | Values | Normalised to 0–100 |
|---|---|---|
| `score_1_5` | 1–5 (Likert) | `(v-1)/4 × 100` |
| `score_0_100` | 0/25/50/75/100 (slider) | as-is |
| `score_1_10` | 1–10 | `(v-1)/9 × 100` |
| `binary` | 0/1 or 1/2 | `× 100` |
| `text` | Free text | — |

---

## Project structure

```
indsight/
├── SKILL.md              # Agent Skill definition (metadata + instructions)
├── scripts/              # Python scripts
│   ├── report.py         # Main report generator
│   ├── analyze_comments.py  # Dumps text answers for LLM analysis
│   ├── _loader.py        # Shared dataset loader
│   ├── variables.py      # List variables with types and scores
│   ├── summary.py        # Stats table (mean, median, SD)
│   ├── graph.py          # ASCII distribution charts
│   ├── query.py          # Filter and inspect respondents
│   └── priorities.py     # Rank topics by score
├── references/
│   └── summary_prompt.md # LLM instructions for comment analysis
└── datasets/             # ← gitignored; place your exports here
```

---

## Requirements

```bash
pip install openpyxl
```

Python 3.9+ · No other dependencies for report generation.

---

## License

MIT
