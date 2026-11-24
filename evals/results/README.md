# Evaluation results

`python -m evals.run` writes `latest.md` (the report) and `latest.json` (every
answer Rambo gave, per run, with the problems found) here. CI writes the same
report to the Eval job's summary page. See README > Evaluation suite.

`history/` keeps earlier reports worth remembering, such as the first real run of
the AI review summary we replaced with Rambo.
