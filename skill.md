# Survey Indsight Skill

## Purpose
This skill helps you analyse survey data exported from SurveyXact (Excel-XML format).
The dataset lives in the `datasets/` folder. All tools are in `tools/`.

## Dataset Format
SurveyXact exports an Excel-XML file with the following sheets:
- **Variables** — maps variable names (e.g. `s_27`) to human-readable descriptions
- **Labels** — maps numeric score values to text labels (e.g. `1` → "Jeg er faktisk ligeglad")
- **Dataset** — one row per respondent, one column per variable
- **Structure** — question metadata (type, sub-type, question text)

### Score scale (Closed/Single questions)
| Score | Meaning |
|-------|---------|
| 1 | Jeg er faktisk ligeglad (Don't care at all) |
| 2 | Ikke så vigtigt for mig (Not that important) |
| 3 | Vigtigt (Important) |
| 4 | Meget vigtigt! (Very important!) |
| 5 | Kan ikke leve uden det! (Can't live without it!) |
| 6 | Ved ikke / ikke relevant (Don't know / N/A) |

**Note:** Score `6` is excluded from statistical calculations (mean, median, etc.) by default.

## Available Tools

| Tool | Script | Purpose |
|------|--------|---------|
| Variables | `tools/variables.py` | List all questions/variables in the dataset |
| Summary | `tools/summary.py` | Statistical summary (mean, median, mode, std dev) |
| Graph | `tools/graph.py` | ASCII bar chart of score distributions |
| Query | `tools/query.py` | Filter and inspect individual respondent responses |
| Outliers | `tools/outliers.py` | Detect statistical outliers and straight-liners |
| Priorities | `tools/priorities.py` | Rank topics by average priority score |
| Compare | `tools/compare.py` | Side-by-side comparison of two respondents |

## Usage

All tools are run from the project root (`/path/to/indsight/`) and auto-discover the dataset in `datasets/`.

```bash
# List all variables
python3 tools/variables.py

# Summary of all questions (sorted by mean)
python3 tools/summary.py

# Summary of one specific question
python3 tools/summary.py --variable s_27

# Sort summary differently
python3 tools/summary.py --sort mean|median|name

# Graph distributions
python3 tools/graph.py
python3 tools/graph.py --variables s_27 s_28 s_33

# Query respondents
python3 tools/query.py --email thoe
python3 tools/query.py --variable s_27 --min 4
python3 tools/query.py --variable s_33 --min 5 --max 5

# Outlier detection
python3 tools/outliers.py
python3 tools/outliers.py --z 2.0
python3 tools/outliers.py --variable s_27

# Priority ranking
python3 tools/priorities.py
python3 tools/priorities.py --top 3 --bottom 3

# Compare two respondents
python3 tools/compare.py --email1 thoe --email2 tmlb
```

## Adding More Datasets
Drop additional `.xml` files into `datasets/`. The tools will pick up the first one found.
To target a specific file, use `--dataset datasets/myfile.xml`.

## Notes
- Free-text comments are stored in variable `s_10`
- `statoverall_*` variables track survey completion status, not priority scores
- All tools print to stdout and exit with code 0 on success, 1 on error
