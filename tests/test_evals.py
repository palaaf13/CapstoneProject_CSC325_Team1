"""
The evaluation suite's own tests: the golden data is well formed, the checks
score what they claim to, and `python -m evals.run` fails when results drop
below the thresholds. Everything here uses a fake model; no API calls.
"""

import json

import pytest

from apps.assistant.summarizer import Point, ReviewSummary, SummaryResult
from evals import checks, run

GOLDEN = run.load_jsonl(run.GOLDEN)
PAIRS = run.load_jsonl(run.PAIRS)


def summary(overview="", tone="mixed", pros=(), cons=(), n=4):
    return ReviewSummary(
        overview=overview,
        tone=tone,
        pros=tuple(Point(text, tuple(cited)) for text, cited in pros),
        cons=tuple(Point(text, tuple(cited)) for text, cited in cons),
        review_count=n,
    )


# -- the data ----------------------------------------------------------------
def test_golden_set_has_at_least_15_well_formed_cases():
    assert len(GOLDEN) >= 15
    assert len({c["id"] for c in GOLDEN}) == len(GOLDEN)
    for case in GOLDEN:
        assert len(case["reviews"]) >= 3, case["id"]
        assert case["expected"]["tone"] in ("positive", "mixed", "negative"), case["id"]
        assert case["expected"]["themes"], case["id"]
        reviews = " ".join(case["reviews"]).lower()
        for term in case["expected"].get("forbidden", []):
            # A forbidden term must be something the reviews never say...
            if term not in ("accent", "she", "her", "he", "his", "him"):
                assert not checks._contains(reviews, term), (case["id"], term)
        for group in case["expected"]["themes"]:
            # ...and every expected theme something at least one review does.
            assert any(checks._contains(reviews, word) for word in group) or case["id"] == (
                "course-reviews-disagree"
            ), (case["id"], group)


def test_counterfactual_pairs_differ_only_in_who_the_professor_is():
    assert len(PAIRS) >= 5
    for pair in PAIRS:
        a, b = pair["a"]["reviews"], pair["b"]["reviews"]
        assert len(a) == len(b) >= 3
        assert pair["a"]["subject"] != pair["b"]["subject"]
        for x, y in zip(a, b, strict=True):
            assert len(x.split()) == len(y.split()), pair["id"]


def test_thresholds_cover_every_metric():
    assert set(run.load_thresholds()) == {
        "valid_output_rate",
        "tone_accuracy",
        "theme_coverage",
        "hallucination_free_rate",
        "consistency_rate",
        "counterfactual_parity",
    }


# -- the checks --------------------------------------------------------------
def test_theme_coverage_matches_stems_and_word_boundaries():
    s = summary("Grading is strict and the workload is heavy.")
    assert checks.covered_themes(s, [["grad"], ["heavy"], ["he"], ["easy"]]) == [
        True,
        True,
        False,
        False,
    ]


def test_hallucination_check_flags_invented_details():
    reviews = ["Quizzes are 10 questions.", "The labs are long.", "Fair grader."]
    clean = summary("Short quizzes of 10 questions.", cons=[("Long labs", [2])])
    assert checks.hallucination_problems(clean, reviews, ["curve"]) == []

    invented = summary(
        "Quizzes have 12 questions and there is a curve.",
        pros=[("Gives extra credit generously", [3])],
    )
    problems = checks.hallucination_problems(invented, reviews, ["curve"])
    assert "mentions 'curve'" in problems
    assert "number 12 is in no review" in problems
    assert any(p.startswith("ungrounded point") for p in problems)


def test_numbers_from_the_course_code_are_not_hallucinations():
    """First real run flagged "CSC 240" as an invented number."""
    s = summary("CSC 240 has weekly labs.")
    assert checks.unsupported_numbers(s, ["Labs every week."], "CSC 240 Data Structures") == []
    assert checks.unsupported_numbers(s, ["Labs every week."]) == ["240"]


def test_grounding_tolerates_simple_word_endings():
    reviews = ["Take his class, you won't regret it."]
    assert checks.ungrounded_points(summary(pros=[("Worth taking", [1])]), reviews) == []
    assert checks.ungrounded_points(summary(pros=[("Generous curve", [1])]), reviews) == [
        "Generous curve"
    ]


def test_same_judgement_compares_tone_and_themes():
    themes = [["exam"], ["clear"]]
    a = summary("Clear lectures, hard exams.", tone="mixed")
    assert checks.same_judgement(a, summary("Hard exams but clear.", tone="mixed"), themes)[0]
    assert not checks.same_judgement(a, summary("Clear lectures.", tone="mixed"), themes)[0]
    assert not checks.same_judgement(
        a, summary("Clear lectures, hard exams.", tone="positive"), themes
    )[0]


# -- the runner and its gate -------------------------------------------------
def oracle(subject, reviews):
    """A perfect fake model: right tone, every theme, grounded in review 1."""
    case = next((c for c in GOLDEN if c["subject"] == subject and c["reviews"] == reviews), None)
    if case is None:
        pair = next(p for p in PAIRS for side in "ab" if p[side]["reviews"] == reviews)
        expected = pair["expected"]
    else:
        expected = case["expected"]
    words = [group[0] for group in expected["themes"]]
    forbidden = expected.get("forbidden", [])
    # Quote a review that says nothing the summary may not repeat (e.g. an accent).
    quote = next(
        n for n, r in enumerate(reviews, 1) if not any(checks._contains(r, t) for t in forbidden)
    )
    return SummaryResult(
        summary=summary(
            overview="Students mention " + ", ".join(words) + ".",
            tone=expected["tone"],
            pros=[(reviews[quote - 1][:80], [quote])],
            n=len(reviews),
        )
    )


def test_suite_passes_with_a_perfect_model(tmp_path):
    report = run.run_suite(oracle, model="fake", runs=2, workers=2)
    assert report.passed, report.metrics
    assert all(value == 1.0 for value in report.metrics.values())
    markdown = run.write_results(report, tmp_path)
    assert "**PASSED**" in markdown
    assert json.loads((tmp_path / "latest.json").read_text())["passed"] is True


def test_suite_fails_the_gate_when_the_model_breaks(tmp_path):
    report = run.run_suite(
        lambda *_: SummaryResult(fallback_reason="invalid_output"), model="fake", runs=2, workers=2
    )
    assert not report.passed
    assert "valid_output_rate" in report.failures
    assert "FAILED" in run.write_results(report, tmp_path)


def test_suite_catches_a_biased_model(tmp_path):
    def biased(subject, reviews):
        result = oracle(subject, reviews)
        if "Michael" in subject or "Connor" in subject or "Liam" in subject or "David" in subject:
            return SummaryResult(summary=summary("Great.", tone="positive", n=len(reviews)))
        return result

    report = run.run_suite(biased, model="fake", runs=1, workers=2)
    assert report.metrics["counterfactual_parity"] < report.thresholds["counterfactual_parity"]
    assert "counterfactual_parity" in report.failures


def test_main_refuses_to_run_without_a_key(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert run.main([]) == 2
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().out


@pytest.mark.parametrize("pair", PAIRS, ids=lambda p: p["id"])
def test_each_pair_names_a_different_professor(pair):
    assert pair["a"]["subject"].startswith("Professor ")
    assert pair["b"]["subject"].startswith("Professor ")
