# LLM Analysis Instructions

Used internally by the skill when the user requests AI summaries.
The LLM should:

1. Run `python3 tools/analyze_comments.py --dataset <path>` and read all output
2. For **each question** in the output, perform the analysis below
3. Write the result to `analysis.json` in the project root
4. Then run `python3 tools/report.py` to generate the final report

## Analysis per question

For each question produce:

**summary** — 3–5 neutral sentences covering the main themes and tone of the responses.

**themes** — 5–8 recurring themes as short noun phrases (e.g. "Work-life balance",
"Leadership visibility"). Cover the full range; keep them mutually exclusive.

**answers** — for every answer assign:
- `category`: exact string from your theme list (best single match)
- `sentiment`: integer 1–5
  - 1 = Very negative
  - 2 = Negative  
  - 3 = Neutral / mixed
  - 4 = Positive
  - 5 = Very positive
  Sentiment is relative to the survey question topic.

Answers may be in any language. Interpret sentiment correctly regardless of language.
Theme names should be in English.

## Output format — write exactly this to `analysis.json`

```json
{
  "generated": "YYYY-MM-DD HH:MM",
  "dataset": "datasets/filename.xlsx",
  "questions": {
    "komm_1": {
      "label": "Har du kommentarer til Trivsel?",
      "n": 518,
      "summary": "Respondents generally report a positive atmosphere...",
      "themes": ["Work environment", "Stress", "Leadership", "Team spirit", "Work-life balance"],
      "answers": [
        {"text": "Arbejdsmiljøet er rigtig godt.", "category": "Work environment", "sentiment": 5},
        {"text": "For meget stress.", "category": "Stress", "sentiment": 1}
      ]
    }
  }
}
```
