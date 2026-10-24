"""Database models for student-submitted course and professor ratings."""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.catalog.models import Course, Professor


class CourseRating(models.Model):
    """A student's rating of a course."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_ratings",
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="student_ratings",
    )
    difficulty = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    workload = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    usefulness = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    semester = models.CharField(max_length=32)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "course"],
                name="ratings_course_user_unique",
            ),
        ]

    def __str__(self):
        return f"Rating for {self.course} by {self.user}"


class ProfessorRating(models.Model):
    """A student's rating of a professor."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="professor_ratings",
    )
    professor = models.ForeignKey(
        Professor,
        on_delete=models.CASCADE,
        related_name="student_ratings",
    )
    clarity = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    helpfulness = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    fairness = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="professor_ratings",
    )
    semester = models.CharField(max_length=32)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "professor"],
                name="ratings_professor_user_unique",
            ),
        ]

    def __str__(self):
        return f"Rating for {self.professor} by {self.user}"
