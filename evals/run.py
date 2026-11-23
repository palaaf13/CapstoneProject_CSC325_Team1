"""
Run Rambo's evaluation suite against the real API:

    python -m evals.run

Needs ANTHROPIC_API_KEY, nothing else: no database. Asks every golden
question three times and every counterfactual pair once, through the same
`rambo.ask` the site uses (Claude Haiku 5.5 searching farmingdale.edu);
scores the answers with evals/checks.py; writes evals/results/latest.md and
latest.json; and exits 1 if any metric is below its threshold in
evals/thresholds.json. CI runs this as the Eval stage on every pull request
into main.

One run is 75 questions, most with a farmingdale.edu web search or two, and
costs roughly $1 to $2.
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

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "rambo" / "golden.jsonl"
PAIRS = HERE / "rambo" / "counterfactual_pairs.jsonl"
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
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def failures(self) -> list[str]:
        return [n for n, minimum in self.thresholds.items() if self.metrics.get(n, 0.0) < minimum]

    @property
    def passed(self) -> bool:
        return not self.failures


# (question, history) -> RamboResult
Ask = Callable[[str, list[dict]], object]


def _rate(values: list[bool]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def _passes_facts(result, expected: dict) -> bool:
    from . import checks

    if not result.ok:
        return False
    text = result.answer.text
    if not all(checks.covered(text, expected.get("must_mention", []))):
        return False
    if len(text) > expected.get("max_chars", 10_000):
        return False
    return not (expected.get("needs_fsc_link") and not checks.has_fsc_source(result))


def run_suite(
    ask: Ask, *, model: str, prompt_version: str, runs: int = 3, workers: int = 6
) -> Report:
    from . import checks

    golden, pairs = load_jsonl(GOLDEN), load_jsonl(PAIRS)
    jobs = [(c["question"], c.get("history", [])) for c in golden for _ in range(runs)]
    jobs += [(p[side], []) for p in pairs for side in ("a", "b")]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda job: ask(*job), jobs))

    report = Report(
        model=model, prompt_version=prompt_version, runs=runs, thresholds=load_thresholds()
    )
    report.served_by = sorted({r.answer.model for r in results if r.ok and r.answer.model})
    report.usage = {
        key: sum(r.usage.get(key, 0) for r in results)
        for key in ("api_calls", "input_tokens", "output_tokens", "web_searches")
    }

    valid, facts, clean, consistent = [], [], [], []
    for i, case in enumerate(golden):
        attempts = results[i * runs : (i + 1) * runs]
        expected = case["expected"]
        row = {"id": case["id"], "question": case["question"], "runs": []}
        for attempt in attempts:
            valid.append(attempt.ok)
            if attempt.ok:
                history = " ".join(turn["answer"] for turn in case.get("history", []))
                problems = checks.hallucination_problems(
                    attempt, expected.get("forbidden", []), history
                )
                clean.append(not problems)
                row["runs"].append(
                    {
                        "answer": attempt.answer.text,
                        "tools": list(attempt.answer.tools_used),
                        "facts": checks.covered(
                            attempt.answer.text, expected.get("must_mention", [])
                        ),
                        "passes": _passes_facts(attempt, expected),
                        "hallucinations": problems,
                    }
                )
            else:
                clean.append(False)
                row["runs"].append({"fallback": attempt.fallback_reason})

        # Accuracy is scored on the first run; the repeats measure consistency.
        row["facts_ok"] = _passes_facts(attempts[0], expected)
        facts.append(row["facts_ok"])
        outcomes = [run.get("passes") for run in row["runs"]]
        coverage = [tuple(run.get("facts", ())) for run in row["runs"]]
        row["consistent"] = (
            all(a.ok for a in attempts) and len(set(outcomes)) == 1 and len(set(coverage)) == 1
        )
        consistent.append(row["consistent"])
        report.cases.append(row)

    parity = []
    offset = len(golden) * runs
    for j, pair in enumerate(pairs):
        a, b = results[offset + 2 * j], results[offset + 2 * j + 1]
        same, why = checks.same_judgement(a, b, pair["expected"])
        parity.append(same)
        report.pairs.append(
            {
                "id": pair["id"],
                "same": same,
                "why": why,
                "a": {
                    "question": pair["a"],
                    "answer": a.answer.text if a.ok else f"fallback: {a.fallback_reason}",
                },
                "b": {
                    "question": pair["b"],
                    "answer": b.answer.text if b.ok else f"fallback: {b.fallback_reason}",
                },
            }
        )

    report.metrics = {
        "valid_answer_rate": _rate(valid),
        "fact_accuracy": _rate(facts),
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


def _cell(text: str, limit: int = 160) -> str:
    text = " ".join(text.split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def to_markdown(report: Report, *, when: str, sha: str) -> str:
    verdict = "PASSED" if report.passed else f"FAILED ({', '.join(report.failures)})"
    served = ", ".join(f"`{m}`" for m in report.served_by) or "n/a"
    u = report.usage
    lines = [
        "# Rambo evaluation",
        "",
        f"**{verdict}** · model `{report.model}` (served by {served}) · prompt "
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
        f"{len(report.cases)} golden questions × {report.runs} runs, {len(report.pairs)} counterfactual pairs. "
        f"{u.get('api_calls', 0)} API calls, {u.get('input_tokens', 0):,} input / "
        f"{u.get('output_tokens', 0):,} output tokens, {u.get('web_searches', 0)} web searches.",
        "",
        "## Golden questions",
        "",
        "| Case | Facts (run 1) | Consistent | Problems | First answer |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report.cases:
        problems = sorted({p for run in row["runs"] for p in run.get("hallucinations", [])})
        problems += [f"fallback: {run['fallback']}" for run in row["runs"] if "fallback" in run]
        first = row["runs"][0].get("answer") or row["runs"][0].get("fallback", "")
        lines.append(
            f"| {row['id']} | {'✓' if row['facts_ok'] else '✗'} | {'✓' if row['consistent'] else '✗'} | "
            f"{_cell('; '.join(problems)) or '-'} | {_cell(first)} |"
        )
    lines += [
        "",
        "## Counterfactual pairs (bias)",
        "",
        "| Pair | Same answer | Difference |",
        "| --- | --- | --- |",
    ]
    for pair in report.pairs:
        lines.append(
            f"| {pair['id']} | {'✓' if pair['same'] else '✗'} | {_cell(pair['why']) or '-'} |"
        )
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
        "usage": report.usage,
        "cases": report.cases,
        "pairs": report.pairs,
    }
    (out / "latest.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    markdown = to_markdown(report, when=when, sha=sha)
    (out / "latest.md").write_text(markdown)
    if summary_file := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(markdown)
    return markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Rambo's evaluation suite against the real API."
    )
    parser.add_argument("--model", default=os.environ.get("RAMBO_MODEL", "claude-haiku-5-5"))
    parser.add_argument(
        "--runs", type=int, default=3, help="repeats per golden question (consistency)"
    )
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--out", type=Path, default=RESULTS)
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set. The eval calls the real API; see README > Evaluation suite."
        )
        return 2

    import anthropic

    from apps.assistant import rambo

    client = anthropic.Anthropic(max_retries=4, timeout=120)

    def ask(question: str, history: list[dict]):
        return rambo.ask(question, client=client, history=history, model=args.model)

    report = run_suite(
        ask, model=args.model, prompt_version=rambo.PROMPT_VERSION,
        runs=args.runs, workers=args.workers,
    )  # fmt: skip
    print(write_results(report, args.out))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
