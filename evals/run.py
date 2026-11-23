"""
Run the review-summary evaluation suite against the real API:

    python -m evals.run

Needs ANTHROPIC_API_KEY. Calls the same code the site does
(apps.assistant.summarizer.summarize_reviews), scores the results with
evals/checks.py, writes evals/results/latest.json and latest.md, and exits 1
if any metric is below its threshold in evals/thresholds.json. CI runs this as
the Eval stage on every pull request into main.

One run is 60 API calls to Claude Haiku 5.5 and costs about two cents.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from apps.assistant import summarizer
from apps.assistant.summarizer import SummaryResult

from . import checks

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "review_summary" / "golden.jsonl"
PAIRS = HERE / "review_summary" / "counterfactual_pairs.jsonl"
THRESHOLDS = HERE / "thresholds.json"
RESULTS = HERE / "results"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_thresholds() -> dict[str, float]:
    data = json.loads(THRESHOLDS.read_text())
    return {k: float(v) for k, v in data.items() if not k.startswith("_")}


@dataclass
class Report:
    model: str
    prompt_version: str
    runs: int
    metrics: dict[str, float] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    cases: list[dict] = field(default_factory=list)
    pairs: list[dict] = field(default_factory=list)
    served_by: list[str] = field(default_factory=list)
    tokens: dict[str, int] = field(default_factory=dict)

    @property
    def failures(self) -> list[str]:
        return [
            name
            for name, minimum in self.thresholds.items()
            if self.metrics.get(name, 0.0) < minimum
        ]

    @property
    def passed(self) -> bool:
        return not self.failures


Summarize = Callable[[str, list[str]], SummaryResult]


def _rate(values: list[bool]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def run_suite(summarize: Summarize, *, model: str, runs: int = 3, workers: int = 8) -> Report:
    """Run every golden case `runs` times and every counterfactual pair once, then score."""
    golden, pairs = load_jsonl(GOLDEN), load_jsonl(PAIRS)

    jobs = [(c["subject"], c["reviews"]) for c in golden for _ in range(runs)]
    jobs += [(p[side]["subject"], p[side]["reviews"]) for p in pairs for side in ("a", "b")]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda job: summarize(*job), jobs))

    report = Report(
        model=model,
        prompt_version=summarizer.PROMPT_VERSION,
        runs=runs,
        thresholds=load_thresholds(),
    )
    report.served_by = sorted({r.summary.model for r in results if r.ok and r.summary.model})
    report.tokens = {
        "input": sum(r.usage.get("input_tokens", 0) for r in results),
        "output": sum(r.usage.get("output_tokens", 0) for r in results),
    }

    valid, tone_ok, themes_ok, clean, consistent = [], [], [], [], []
    for i, case in enumerate(golden):
        attempts = results[i * runs : (i + 1) * runs]
        expected = case["expected"]
        first = attempts[0]
        row = {"id": case["id"], "runs": []}
        for attempt in attempts:
            valid.append(attempt.ok)
            if attempt.ok:
                s = attempt.summary
                coverage = checks.covered_themes(s, expected["themes"])
                problems = checks.hallucination_problems(
                    s, case["reviews"], expected.get("forbidden", [])
                )
                row["runs"].append(
                    {
                        "tone": s.tone,
                        "themes": coverage,
                        "hallucinations": problems,
                        "summary": s.to_dict(),
                    }
                )
                clean.append(not problems)
            else:
                row["runs"].append({"fallback": attempt.fallback_reason})
                clean.append(False)

        # Accuracy is scored on the first run; the repeats are for consistency.
        if first.ok:
            tone_ok.append(first.summary.tone == expected["tone"])
            themes_ok.append(all(checks.covered_themes(first.summary, expected["themes"])))
        else:
            tone_ok.append(False)
            themes_ok.append(False)
        row["tone_ok"], row["themes_ok"] = tone_ok[-1], themes_ok[-1]

        if all(a.ok for a in attempts):
            verdicts = [
                checks.same_judgement(first.summary, a.summary, expected["themes"])
                for a in attempts[1:]
            ]
            row["consistent"] = all(ok for ok, _ in verdicts)
            row["inconsistency"] = "; ".join(why for ok, why in verdicts if not ok)
        else:
            row["consistent"] = False
            row["inconsistency"] = "a run fell back"
        consistent.append(row["consistent"])
        report.cases.append(row)

    parity = []
    offset = len(golden) * runs
    for j, pair in enumerate(pairs):
        a, b = results[offset + 2 * j], results[offset + 2 * j + 1]
        if a.ok and b.ok:
            same, why = checks.same_judgement(a.summary, b.summary, pair["expected"]["themes"])
        else:
            same, why = False, f"fallback: {a.fallback_reason or b.fallback_reason}"
        parity.append(same)
        report.pairs.append(
            {
                "id": pair["id"],
                "same": same,
                "why": why,
                "a": a.summary.to_dict() if a.ok else {"fallback": a.fallback_reason},
                "b": b.summary.to_dict() if b.ok else {"fallback": b.fallback_reason},
            }
        )

    report.metrics = {
        "valid_output_rate": _rate(valid),
        "tone_accuracy": _rate(tone_ok),
        "theme_coverage": _rate(themes_ok),
        "hallucination_free_rate": _rate(clean),
        "consistency_rate": _rate(consistent),
        "counterfactual_parity": _rate(parity),
    }
    return report


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def to_markdown(report: Report, *, when: str, sha: str) -> str:
    verdict = "PASSED" if report.passed else f"FAILED ({', '.join(report.failures)})"
    lines = [
        "# Review summary evaluation",
        "",
        f"**{verdict}** · model `{report.model}` (served by "
        f"{', '.join(f'`{m}`' for m in report.served_by) or 'n/a'}) · prompt "
        f"`{report.prompt_version}` · commit `{sha}` · {when}",
        "",
        "| Check | Result | Threshold | |",
        "| --- | --- | --- | --- |",
    ]
    for name, minimum in report.thresholds.items():
        value = report.metrics.get(name, 0.0)
        lines.append(
            f"| {name} | {value:.0%} | {minimum:.0%} | {'pass' if value >= minimum else '**FAIL**'} |"
        )
    lines += [
        "",
        f"{len(report.cases)} golden cases × {report.runs} runs, {len(report.pairs)} counterfactual "
        f"pairs. Tokens: {report.tokens.get('input', 0):,} in, {report.tokens.get('output', 0):,} out.",
        "",
        "## Golden cases",
        "",
        "| Case | Tone | Themes | Consistent | Hallucination problems |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report.cases:
        problems = sorted({p for run in row["runs"] for p in run.get("hallucinations", [])})
        fallbacks = [run["fallback"] for run in row["runs"] if "fallback" in run]
        if fallbacks:
            problems.append(f"fallback: {', '.join(fallbacks)}")
        tone = row["runs"][0].get("tone", "-")
        lines.append(
            f"| {row['id']} | {tone} {'✓' if row['tone_ok'] else '✗'} | "
            f"{'✓' if row['themes_ok'] else '✗'} | {'✓' if row['consistent'] else '✗ ' + row['inconsistency']} | "
            f"{'; '.join(problems) or '-'} |"
        )
    lines += [
        "",
        "## Counterfactual pairs (bias)",
        "",
        "| Pair | Same judgement | Difference |",
        "| --- | --- | --- |",
    ]
    for pair in report.pairs:
        lines.append(f"| {pair['id']} | {'✓' if pair['same'] else '✗'} | {pair['why'] or '-'} |")
    return "\n".join(lines) + "\n"


def write_results(report: Report, out: Path) -> str:
    out.mkdir(parents=True, exist_ok=True)
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    sha = _git_sha()
    data = {
        "passed": report.passed,
        "failures": report.failures,
        "when": when,
        "commit": sha,
        "model": report.model,
        "served_by": report.served_by,
        "prompt_version": report.prompt_version,
        "runs": report.runs,
        "metrics": report.metrics,
        "thresholds": report.thresholds,
        "tokens": report.tokens,
        "cases": report.cases,
        "pairs": report.pairs,
    }
    (out / "latest.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    markdown = to_markdown(report, when=when, sha=sha)
    (out / "latest.md").write_text(markdown)
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(markdown)
    return markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument(
        "--model", default=os.environ.get("AI_SUMMARY_MODEL", summarizer.DEFAULT_MODEL)
    )
    parser.add_argument("--runs", type=int, default=3, help="repeats per golden case (consistency)")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path, default=RESULTS)
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set. The eval calls the real API; see README > Evaluation suite."
        )
        return 2

    import anthropic

    client = anthropic.Anthropic(max_retries=4, timeout=60)

    def summarize(subject: str, reviews: list[str]) -> SummaryResult:
        return summarizer.summarize_reviews(subject, reviews, client=client, model=args.model)

    report = run_suite(summarize, model=args.model, runs=args.runs, workers=args.workers)
    print(write_results(report, args.out))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
