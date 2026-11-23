"""Forms for rating a course or a professor. Views never read request.POST directly."""

from datetime import date

from django import forms

from .models import MAX_COMMENT_LENGTH

SCORE_CHOICES = [(n, str(n)) for n in range(1, 6)]
YEARS_BACK = 4


def recent_semesters(today: date | None = None) -> list[str]:
    """The current term and the ones before it, newest first: "Fall 2026", "Summer 2026", ..."""
    today = today or date.today()
    if today.month >= 9:
        term_index = 2
    elif today.month >= 6:
        term_index = 1
    else:
        term_index = 0
    terms = ("Spring", "Summer", "Fall")
    year = today.year
    semesters = []
    while year > today.year - YEARS_BACK:
        semesters.append(f"{terms[term_index]} {year}")
        term_index -= 1
        if term_index < 0:
            term_index = 2
            year -= 1
    return semesters


def score_field(label: str, low: str, high: str) -> forms.TypedChoiceField:
    return forms.TypedChoiceField(
        label=label,
        choices=SCORE_CHOICES,
        coerce=int,
        widget=forms.RadioSelect,
        help_text=f"1 = {low}, 5 = {high}",
        error_messages={"required": f"Pick a {label.lower()} score from 1 to 5."},
    )


class RatingFormBase(forms.Form):
    semester = forms.ChoiceField(label="When you took it")
    comment = forms.CharField(
        label="Advice for the next student",
        required=False,
        max_length=MAX_COMMENT_LENGTH,
        strip=True,
        widget=forms.Textarea(attrs={"rows": 5}),
        help_text="What should someone know before they sign up? Stick to what you experienced.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(s, s) for s in recent_semesters()]
        # Keep an older saved semester selectable when a student edits their rating.
        current = self.initial.get("semester")
        if current and current not in dict(choices):
            choices.append((current, current))
        self.fields["semester"].choices = [("", "Choose a semester"), *choices]

    @property
    def score_fields(self):
        return [self[name] for name in self.SCORE_FIELDS]


class CourseRatingForm(RatingFormBase):
    SCORE_FIELDS = ("difficulty", "workload", "usefulness")

    difficulty = score_field("Difficulty", "easy", "very hard")
    workload = score_field("Workload", "light", "heavy")
    usefulness = score_field("Usefulness", "not useful", "very useful")

    field_order = ["difficulty", "workload", "usefulness", "semester", "comment"]


class ProfessorRatingForm(RatingFormBase):
    SCORE_FIELDS = ("clarity", "helpfulness", "fairness")

    clarity = score_field("Clarity", "hard to follow", "very clear")
    helpfulness = score_field("Helpfulness", "not helpful", "very helpful")
    fairness = score_field("Fairness", "unfair grading", "very fair")
    course = forms.ChoiceField(label="Which course", required=False)

    field_order = ["clarity", "helpfulness", "fairness", "course", "semester", "comment"]

    def __init__(self, *args, courses=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.courses = {str(course.pk): course for course in courses}
        if not self.courses:
            # Most professors have no course assignments until schedule data
            # arrives (RH-21). A dropdown with nothing to pick is noise.
            del self.fields["course"]
            return
        self.fields["course"].choices = [
            ("", "Not listed / prefer not to say"),
            *((pk, f"{c.code} {c.title}") for pk, c in self.courses.items()),
        ]

    def clean_course(self):
        """The chosen Course, or None. Only courses this professor teaches are offered."""
        return self.courses.get(self.cleaned_data.get("course") or "")
