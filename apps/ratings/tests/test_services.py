import pytest

from apps.ratings.services import calculate_average, validate_rating_score


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
