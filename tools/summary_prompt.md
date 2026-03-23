# Comment Analysis Prompt

When the user asks to analyse open-ended responses, use `analyze_comments.py`
to read all text answers, then produce `analysis.json` in the format below.

## Your task

For each question:
1. **Summary** — write 3–5 neutral sentences summarising what respondents say overall.
2. **Themes** — identify 5–8 recurring themes (short noun phrases, e.g. "Work-life balance",
   "Leadership communication"). Cover the full response range.
3. **Per-answer enrichment** — for every answer assign:
   - `category`: the single best-matching theme (exact string from your theme list)
   - `sentiment`: integer 1–5
     - 1 = Very negative
     - 2 = Negative
     - 3 = Neutral / mixed
     - 4 = Positive
     - 5 = Very positive
     Sentiment is relative to the question (a complaint = 1–2, a compliment = 4–5).

Answers may be in any language (Danish, English, German, etc.) — always interpret
sentiment correctly regardless of language.

## Output format

Write the result to `analysis.json` (in the project root) in this exact structure:

```json
{
  "generated": "YYYY-MM-DD HH:MM",
  "dataset": "datasets/filename.xlsx",
  "questions": {
    "komm_1": {
      "label": "Har du kommentarer til Trivsel?",
      "n": 518,
      "summary": "Respondents generally report...",
      "themes": ["Work environment", "Stress", "Leadership", "Team spirit", "Work-life balance"],
      "answers": [
        {"text": "Arbejdsmiljøet er rigtig godt.", "category": "Work environment", "sentiment": 5},
        {"text": "For meget stress.", "category": "Stress", "sentiment": 1}
      ]
    },
    "komm_2": { ... }
  }
}
```

`report.py` will auto-load `analysis.json` and show summaries, theme filter
buttons and sentiment filters inside each open-ended section.
