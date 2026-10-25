import pytest

from apps.catalog.models import ProfessorRatingSummary
from apps.ratings.services import (
    calculate_average,
    summarize_course_ratings,
    summarize_professor_ratings,
    validate_rating_score,
)


@pytest.mark.parametrize("score", [1, 2, 3, 4, 5])
def test_valid_rating_scores_are_accepted(score):
    assert validate_rating_score(score) is None


@pytest.mark.parametrize(
    "score",
    [0, 6, -1, 2.5, 4.75, 5.1, True, False, "5", None],
)
def test_invalid_rating_scores_are_rejected(score):
    with pytest.raises(ValueError):
        validate_rating_score(score)


def test_calculate_average_returns_mean_rounded_to_two_decimals():
    assert calculate_average([4, 5, 3]) == 4.0
    assert calculate_average([4, 5]) == 4.5
    assert calculate_average([1, 2, 2]) == 1.67


def test_calculate_average_returns_none_for_no_scores():
    assert calculate_average([]) is None


def test_calculate_average_rejects_invalid_scores():
    with pytest.raises(ValueError):
        calculate_average([4, 6])


def test_calculate_average_rejects_decimal_scores():
    with pytest.raises(ValueError):
        calculate_average([4, 2.5])


def test_summarize_course_ratings():
    summary = summarize_course_ratings(
        [
            {"difficulty": 4, "workload": 3, "usefulness": 5},
            {"difficulty": 2, "workload": 5, "usefulness": 3},
        ]
    )

    assert summary == {
        "avg_difficulty": 3.0,
        "avg_workload": 4.0,
        "avg_usefulness": 4.0,
        "count": 2,
    }


def test_summarize_empty_course_ratings():
    summary = summarize_course_ratings([])

    assert summary == {
        "avg_difficulty": None,
        "avg_workload": None,
        "avg_usefulness": None,
        "count": 0,
    }


def test_summarize_professor_ratings():
    summary = summarize_professor_ratings(
        [
            {"clarity": 5, "helpfulness": 4, "fairness": 5},
            {"clarity": 3, "helpfulness": 4, "fairness": 3},
        ]
    )

    assert summary["avg_clarity"] == 4.0
    assert summary["avg_helpfulness"] == 4.0
    assert summary["avg_fairness"] == 4.0
    assert summary["avg_overall"] == 4.0
    assert summary["count"] == 2
    assert summary["source"] == "ramhub"
    assert summary["rank_score"] == ProfessorRatingSummary.compute_rank_score(4.0, 2)


def test_summarize_empty_professor_ratings():
    summary = summarize_professor_ratings([])

    assert summary["avg_overall"] is None
    assert summary["count"] == 0
    assert summary["source"] == ""
    assert summary["rank_score"] is None
