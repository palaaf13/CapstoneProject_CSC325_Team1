"""Course rating form validation."""

import pytest

from apps.ratings.forms import CourseRatingForm


def test_course_rating_form_accepts_all_rating_axes_and_semester():
    form = CourseRatingForm(
        {
            "difficulty": "4",
            "workload": "3",
            "usefulness": "5",
            "semester": "Fall 2026",
        }
    )

    assert form.is_valid()
    assert form.cleaned_data == {
        "difficulty": 4,
        "workload": 3,
        "usefulness": 5,
        "semester": "Fall 2026",
    }


@pytest.mark.parametrize(
    "field, value",
    [("difficulty", "0"), ("workload", "6"), ("usefulness", "2.5")],
)
def test_course_rating_form_rejects_scores_outside_one_to_five(field, value):
    data = {
        "difficulty": "4",
        "workload": "3",
        "usefulness": "5",
        "semester": "Fall 2026",
    }
    data[field] = value
    form = CourseRatingForm(data)

    assert not form.is_valid()
    assert field in form.errors


@pytest.mark.parametrize("semester", ["", "   ", "x" * 33])
def test_course_rating_form_requires_a_valid_semester(semester):
    form = CourseRatingForm(
        {
            "difficulty": "4",
            "workload": "3",
            "usefulness": "5",
            "semester": semester,
        }
    )

    assert not form.is_valid()
    assert "semester" in form.errors
