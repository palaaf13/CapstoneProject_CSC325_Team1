from django import forms

from .rambo import MAX_QUESTION_CHARS


class QuestionForm(forms.Form):
    question = forms.CharField(
        max_length=MAX_QUESTION_CHARS,
        strip=True,
        error_messages={
            "required": "Type a question first.",
            "max_length": f"Keep it under {MAX_QUESTION_CHARS} characters.",
        },
    )
