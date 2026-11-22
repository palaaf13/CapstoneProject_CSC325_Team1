"""Forms for student-submitted ratings."""

from django import forms

from .models import CourseRating


class CourseRatingForm(forms.ModelForm):
    class Meta:
        model = CourseRating
        fields = ["difficulty", "workload", "usefulness", "semester"]
        widgets = {
            "difficulty": forms.Select(choices=[(n, n) for n in range(1, 6)]),
            "workload": forms.Select(choices=[(n, n) for n in range(1, 6)]),
            "usefulness": forms.Select(choices=[(n, n) for n in range(1, 6)]),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "field-input")

    def clean_difficulty(self):
        return self._clean_score("difficulty")

    def clean_workload(self):
        return self._clean_score("workload")

    def clean_usefulness(self):
        return self._clean_score("usefulness")

    def _clean_score(self, name):
        score = self.cleaned_data[name]
        if not 1 <= score <= 5:
            raise forms.ValidationError("Choose a score from 1 to 5.")
        return score

    def clean_semester(self):
        semester = self.cleaned_data["semester"].strip()
        if not semester:
            raise forms.ValidationError("Enter the semester you took this course.")
        return semester
