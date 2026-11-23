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
        "linked_pages_readable",
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
        "phone number 934-420-9999 is on no page Rambo linked",
        "email registrar@farmingdale.edu is on no page Rambo linked",
        "year 1946 is on no page Rambo linked",
        "amount $75 is on no page Rambo linked",
    ):
        assert expected in problems


def test_specifics_are_checked_against_the_pages_rambo_linked():
    url = "https://www.farmingdale.edu/registrar/index.shtml"
    page = '<p>Call 934-420-2776 or <a href="mailto:regoffice@farmingdale.edu">email us</a>.</p>'
    r = result(
        f"Call 934-420-2776 or email regoffice@farmingdale.edu. [Registrar]({url})", sources=()
    )
    assert checks.hallucination_problems(r, [], pages={url: page}) == []

    wrong = result(f"Call 934-420-9999. [Registrar]({url})", sources=())
    assert checks.hallucination_problems(wrong, [], pages={url: page}) == [
        "phone number 934-420-9999 is on no page Rambo linked"
    ]


def test_a_phone_number_is_not_also_read_as_a_year():
    """The first real run flagged the "2000" in 934-420-2000 as an invented year."""
    url = "https://www.farmingdale.edu/contact/"
    r = result(f"The main line is 934-420-2000. [Contact]({url})", sources=())
    assert checks.hallucination_problems(r, [], pages={url: "934-420-2000"}) == []


def test_details_behind_an_unreadable_page_are_unverified_not_hallucinated():
    pdf = "https://www.farmingdale.edu/residence-life/guide-2025-2026.pdf"
    r = result(f"A permit is $30. [Handbook]({pdf})", sources=())
    problems, unverified = checks.unsupported_specifics(r, pages={pdf: None})
    assert problems == [] and unverified == ["amount $30 (a linked page couldn't be read)"]
    # A page that was never fetched is not an excuse.
    assert checks.unsupported_specifics(r, pages={})[0] == ["amount $30 is on no page Rambo linked"]
    # The year in the link address itself counts as evidence.
    assert checks.unsupported_specifics(
        result(f"See the 2025 handbook. [Handbook]({pdf})", sources=()), pages={pdf: None}
    ) == ([], [])


def test_the_run_fails_if_farmingdale_edu_cannot_be_read():
    def linking(question, history):
        good = oracle(question, history)
        return result(
            good.answer.text + " [FSC](https://www.farmingdale.edu/x/)", evidence=good.evidence
        )

    report = run.run_suite(
        linking, model="fake", prompt_version="rambo_v2", runs=1, workers=2,
        fetch_pages=lambda urls: dict.fromkeys(urls),
    )  # fmt: skip
    assert report.metrics["linked_pages_readable"] == 0.0
    assert "linked_pages_readable" in report.failures


def test_the_runner_fetches_each_linked_page_once(tmp_path):
    fetched = []

    def fake_fetch(urls):
        urls = sorted(set(urls))
        fetched.extend(urls)
        return dict.fromkeys(urls, "page")

    def linking(question, history):
        good = oracle(question, history)
        text = good.answer.text + " [FSC](https://www.farmingdale.edu/x/)"
        return result(text, evidence=good.evidence)

    report = run.run_suite(
        linking, model="fake", prompt_version="rambo_v2", runs=1, workers=2,
        fetch_pages=fake_fetch,
    )  # fmt: skip
    assert fetched == ["https://www.farmingdale.edu/x/"]
    assert report.pages == {"linked": 1, "readable": 1}


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
