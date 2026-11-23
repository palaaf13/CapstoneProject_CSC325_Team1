"""
The evaluation suite's own tests: the golden data is well formed, the checks
catch what they claim to, and the gate fails when the model breaks or is
biased. Everything uses a fake Rambo; no API calls, no seeded database.
"""

import json
import re

import pytest

from apps.assistant.rambo import RamboAnswer, RamboResult, Source
from evals import checks, run
from evals.checks import Known

GOLDEN = run.load_jsonl(run.GOLDEN)
PAIRS = run.load_jsonl(run.PAIRS)


def result(text, *, evidence=(), tools=("search_courses",), sources=(), links_removed=0):
    return RamboResult(
        answer=RamboAnswer(
            text=text,
            tools_used=tuple(tools),
            sources=tuple(Source(u, u) for u in sources),
            links_removed=links_removed,
        ),
        evidence=tuple(evidence),
    )


def oracle_text(expected):
    return (
        "Here is what I found: " + "; ".join(g[0] for g in expected.get("must_mention", [])) + "."
    )


KNOWN = Known(
    course_codes={
        f"{a} {b}"
        for case in GOLDEN + [{"expected": p["expected"]} for p in PAIRS]
        for a, b in checks.COURSE_CODE.findall(oracle_text(case["expected"]))
    }
    | {"BCS 109", "CSC 325"},
    club_names={"Cybersecurity Club", "Supporting Women in Computing"},
    professor_last_names={"abramowitz", "abbas"},
    link_exists=lambda url: url in {"/courses/BCS-109/", "/parking/"},
)


def oracle(question, history):
    """A perfect fake Rambo: every expected fact, grounded, never biased."""
    case = next((c for c in GOLDEN if c["question"] == question), None)
    expected = (
        case["expected"]
        if case
        else next(p["expected"] for p in PAIRS if question in (p["a"], p["b"]))
    )
    text = oracle_text(expected)
    sources = ["https://www.farmingdale.edu/x/"] if expected.get("needs_fsc_link") else []
    return result(text, evidence=[text], sources=sources)


# -- the data ----------------------------------------------------------------
def test_golden_set_has_at_least_15_well_formed_cases():
    assert len(GOLDEN) >= 15
    assert len({c["id"] for c in GOLDEN}) == len(GOLDEN)
    for case in GOLDEN:
        assert case["question"].strip(), case["id"]
        expected = case["expected"]
        assert expected["must_mention"], case["id"]
        # The expected answer must not itself trip the case's forbidden list.
        text = oracle_text(expected)
        assert not any(checks.contains(text, t) for t in expected.get("forbidden", [])), case["id"]


def test_counterfactual_pairs_differ_only_in_who_is_asking():
    assert len(PAIRS) >= 5
    for pair in PAIRS:
        a, b = pair["a"].split(), pair["b"].split()
        assert pair["a"] != pair["b"]
        # Same question: at most a name (and "woman"/"man") differs.
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
def test_covered_uses_word_boundaries_for_short_terms():
    assert checks.covered("Bring your ID card.", [["ID"], ["free"]]) == [True, False]
    assert checks.covered("Good idea", [["ID"]]) == [False]


def test_hallucination_check_flags_invented_facts():
    known = Known({"BCS 109"}, set(), {"abbas"}, lambda url: url == "/courses/BCS-109/")
    clean = result(
        "BCS 109 is 3 credits. Tickets are $35. [BCS 109](/courses/BCS-109/)",
        evidence=['{"code": "BCS 109", "credits": 3}', "Most violations $35"],
    )
    assert checks.hallucination_problems(clean, [], known) == []

    made_up = result(
        "Take CSC 999 with Professor Smith. Tickets are $50, call 934-555-0199 after 6:30. "
        "[CSC 999](/courses/CSC-999/)",
        evidence=["Most violations $35"],
        links_removed=1,
    )
    problems = checks.hallucination_problems(made_up, ["$50"], known)
    for expected in (
        "says '$50'",
        "course CSC 999 does not exist",
        "professor 'Professor Smith' is not in the directory",
        "link /courses/CSC-999/ leads nowhere",
        "tried to link 1 page(s) outside RamHub/FSC",
        "amount $50 is in nothing Rambo looked up",
        "phone number 934-555-0199 is in nothing Rambo looked up",
        "time 6:30 is in nothing Rambo looked up",
    ):
        assert expected in problems


def test_codes_named_in_evidence_are_not_hallucinations():
    """A prerequisite can name a course that isn't in the current catalog."""
    known = Known(set(), set(), set(), lambda url: True)
    r = result("You need CSC 111.", evidence=["prerequisites: CSC 111"])
    assert checks.hallucination_problems(r, [], known) == []


def test_web_answers_need_an_fsc_source_instead_of_number_checks():
    r = result(
        "Transcripts cost $10.", tools=["web_search"], sources=["https://www.farmingdale.edu/t/"]
    )
    assert checks.hallucination_problems(r, [], KNOWN) == []
    assert checks.has_fsc_source(r)
    assert not checks.has_fsc_source(result("Ask the registrar.", tools=["web_search"]))


def test_same_judgement_compares_facts_and_suggestions():
    expected = {"must_mention": [["CareerConnect"]]}
    a = result("Use CareerConnect. Try [Cybersecurity Club](/clubs/cyber/).")
    b = result("Check CareerConnect and the [Cybersecurity Club](/clubs/cyber/).")
    assert checks.same_judgement(a, b, expected, KNOWN)[0]
    assert not checks.same_judgement(a, result("Ask around."), expected, KNOWN)[0]
    other = result("Use CareerConnect. Try Supporting Women in Computing.")
    assert not checks.same_judgement(a, other, expected, KNOWN)[0]
    assert not checks.same_judgement(a, RamboResult(fallback_reason="timeout"), expected, KNOWN)[0]


# -- the runner and its gate -------------------------------------------------
def test_suite_passes_with_a_perfect_rambo(tmp_path):
    report = run.run_suite(
        oracle, KNOWN, model="fake", prompt_version="rambo_v1", runs=2, workers=2
    )
    assert report.passed, (report.metrics, report.cases)
    assert all(value == 1.0 for value in report.metrics.values())
    markdown = run.write_results(report, tmp_path)
    assert "**PASSED**" in markdown
    assert json.loads((tmp_path / "latest.json").read_text())["passed"] is True


def test_suite_fails_the_gate_when_rambo_breaks(tmp_path):
    report = run.run_suite(
        lambda *_: RamboResult(fallback_reason="timeout"), KNOWN, model="fake",
        prompt_version="rambo_v1", runs=2, workers=2,
    )  # fmt: skip
    assert not report.passed
    assert {"valid_answer_rate", "fact_accuracy"} <= set(report.failures)
    assert "FAILED" in run.write_results(report, tmp_path)


def test_suite_catches_a_biased_rambo():
    women = re.compile(r"\b(Emily|Maria|Aisha|woman|Jamal|Chinedu)\b")

    def biased(question, history):
        if women.search(question):
            return result("Try Supporting Women in Computing.")
        return oracle(question, history)

    report = run.run_suite(
        biased, KNOWN, model="fake", prompt_version="rambo_v1", runs=1, workers=2
    )
    assert "counterfactual_parity" in report.failures


def test_suite_catches_a_hallucinating_rambo():
    def liar(question, history):
        good = oracle(question, history)
        return result(good.answer.text + " Parking tickets are $500.", evidence=good.evidence)

    report = run.run_suite(liar, KNOWN, model="fake", prompt_version="rambo_v1", runs=1, workers=2)
    assert report.metrics["hallucination_free_rate"] == 0.0
    assert "hallucination_free_rate" in report.failures


def test_main_refuses_to_run_without_a_key(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert run.main([]) == 2
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().out


@pytest.mark.parametrize("case", GOLDEN, ids=lambda c: c["id"])
def test_each_question_is_short_enough_for_rambo(case):
    from apps.assistant.rambo import MAX_QUESTION_CHARS

    assert len(case["question"]) <= MAX_QUESTION_CHARS
