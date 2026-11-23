"""
The evaluation suite's own tests: the golden data is well formed, the checks
catch what they claim to, and the gate fails when Rambo breaks, invents
details, or treats students differently. Everything uses a fake Rambo; no API
calls.
"""

import json
import re

import pytest

from apps.assistant.rambo import MAX_QUESTION_CHARS, RamboAnswer, RamboResult, Source
from evals import checks, run

GOLDEN = run.load_jsonl(run.GOLDEN)
PAIRS = run.load_jsonl(run.PAIRS)
FSC = "https://www.farmingdale.edu/x/"


def result(text, *, evidence=(), sources=(FSC,), links_removed=0):
    return RamboResult(
        answer=RamboAnswer(
            text=text,
            tools_used=("web_search",),
            sources=tuple(Source(u, u) for u in sources),
            links_removed=links_removed,
        ),
        evidence=tuple(evidence),
    )


def oracle_text(expected):
    return (
        "Here is what farmingdale.edu says: "
        + "; ".join(g[0] for g in expected.get("must_mention", []))
        + "."
    )


def oracle(question, history):
    """A perfect fake Rambo: every expected fact, each backed by a citation."""
    case = next((c for c in GOLDEN if c["question"] == question), None)
    expected = (
        case["expected"]
        if case
        else next(p["expected"] for p in PAIRS if question in (p["a"], p["b"]))
    )
    text = oracle_text(expected)
    return result(text, evidence=[text])


# -- the data ----------------------------------------------------------------
def test_golden_set_has_at_least_15_well_formed_cases():
    assert len(GOLDEN) >= 15
    assert len({c["id"] for c in GOLDEN}) == len(GOLDEN)
    for case in GOLDEN:
        assert 0 < len(case["question"]) <= MAX_QUESTION_CHARS, case["id"]
        expected = case["expected"]
        assert expected["must_mention"], case["id"]
        # The expected answer must not trip its own case's forbidden list.
        text = oracle_text(expected)
        assert not any(checks.contains(text, t) for t in expected.get("forbidden", [])), case["id"]
        if expected.get("needs_fsc_link"):
            # Every factual answer was checked on a farmingdale.edu page.
            assert case["source"].startswith("https://www.farmingdale.edu/"), case["id"]


def test_counterfactual_pairs_differ_only_in_who_is_asking():
    assert len(PAIRS) >= 5
    for pair in PAIRS:
        a, b = pair["a"].split(), pair["b"].split()
        assert pair["a"] != pair["b"]
        assert sum(x != y for x, y in zip(a, b, strict=False)) <= 2, pair["id"]


def test_thresholds_cover_every_metric():
    assert set(run.load_thresholds()) == {
        "valid_answer_rate",
        "fact_accuracy",
        "hallucination_free_rate",
        "consistency_rate",
        "counterfactual_parity",
    }


# -- the checks --------------------------------------------------------------
def test_contains_matches_whole_words():
    assert checks.contains("FSC plays in NCAA Division III.", "Division III")
    assert not checks.contains("FSC plays in NCAA Division III.", "Division II")
    assert not checks.contains("a great program", "Ram")
    assert checks.contains("Go Rams!", "Rams")


def test_hallucination_check_flags_unbacked_specifics():
    cited = ["University Police: 934-420-2111", "founded in 1912", "regoffice@farmingdale.edu"]
    clean = result(
        "Call (934) 420-2111. FSC was founded in 1912. Email regoffice@farmingdale.edu.",
        evidence=cited,
    )
    assert checks.hallucination_problems(clean, ["Hubert Keen"]) == []

    made_up = result(
        "Call 934-420-9999 or email registrar@farmingdale.edu. Founded in 1946. "
        "The fee is $75. Ask Hubert Keen.",
        evidence=cited,
        links_removed=1,
    )
    problems = checks.hallucination_problems(made_up, ["Hubert Keen"])
    for expected in (
        "says 'Hubert Keen'",
        "tried to link 1 page(s) off farmingdale.edu",
        "phone number 934-420-9999 is in no cited source",
        "email registrar@farmingdale.edu is in no cited source",
        "year 1946 is in no cited source",
        "amount $75 is in no cited source",
    ):
        assert expected in problems


def test_earlier_turns_count_as_evidence_for_follow_ups():
    r = result("They're in Laffin Hall, Room 225, since 2020.", evidence=[])
    assert checks.hallucination_problems(r, [], "Built in 2020.") == []


def test_fsc_source_from_a_citation_or_a_link():
    assert checks.has_fsc_source(result("x"))
    assert checks.has_fsc_source(result("[Registrar](https://www.farmingdale.edu/r/)", sources=()))
    assert not checks.has_fsc_source(result("Ask the registrar.", sources=()))


def test_same_judgement_compares_facts_and_sourcing():
    expected = {"must_mention": [["Parchment"]]}
    a = result("Order through Parchment.")
    assert checks.same_judgement(a, result("Use Parchment online."), expected)[0]
    assert not checks.same_judgement(a, result("Ask the registrar."), expected)[0]
    assert not checks.same_judgement(a, result("Use Parchment.", sources=()), expected)[0]
    assert not checks.same_judgement(a, RamboResult(fallback_reason="timeout"), expected)[0]


# -- the runner and its gate -------------------------------------------------
def test_suite_passes_with_a_perfect_rambo(tmp_path):
    report = run.run_suite(oracle, model="fake", prompt_version="rambo_v2", runs=2, workers=2)
    assert report.passed, (report.metrics, report.cases)
    assert all(value == 1.0 for value in report.metrics.values())
    markdown = run.write_results(report, tmp_path)
    assert "**PASSED**" in markdown
    assert json.loads((tmp_path / "latest.json").read_text())["passed"] is True


def test_suite_fails_the_gate_when_rambo_breaks(tmp_path):
    report = run.run_suite(
        lambda *_: RamboResult(fallback_reason="timeout"), model="fake",
        prompt_version="rambo_v2", runs=2, workers=2,
    )  # fmt: skip
    assert not report.passed
    assert {"valid_answer_rate", "fact_accuracy"} <= set(report.failures)
    assert "FAILED" in run.write_results(report, tmp_path)


def test_suite_catches_a_biased_rambo():
    some_names = re.compile(r"\b(Emily|Jamal|Maria|Aisha|woman|Chinedu)\b")

    def biased(question, history):
        if some_names.search(question):
            return result("I'm not sure, try asking someone on campus.")
        return oracle(question, history)

    report = run.run_suite(biased, model="fake", prompt_version="rambo_v2", runs=1, workers=2)
    assert report.metrics["counterfactual_parity"] == 0.0
    assert "counterfactual_parity" in report.failures


def test_suite_catches_a_hallucinating_rambo():
    def liar(question, history):
        good = oracle(question, history)
        return result(good.answer.text + " Call 934-555-0100.", evidence=good.evidence)

    report = run.run_suite(liar, model="fake", prompt_version="rambo_v2", runs=1, workers=2)
    assert report.metrics["hallucination_free_rate"] == 0.0
    assert "hallucination_free_rate" in report.failures


def test_main_refuses_to_run_without_a_key(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert run.main([]) == 2
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().out


@pytest.mark.parametrize("case", GOLDEN, ids=lambda c: c["id"])
def test_forbidden_answers_are_not_in_the_expected_ones(case):
    expected = case["expected"]
    for group in expected["must_mention"]:
        for word in group:
            assert word not in expected.get("forbidden", []), case["id"]
