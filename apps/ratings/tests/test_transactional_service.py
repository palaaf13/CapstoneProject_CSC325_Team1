from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError
from pymongo.errors import DuplicateKeyError, OperationFailure

from apps.ratings import services


class FakeSession:
    def __init__(self, behavior=None):
        self.behavior = behavior
        self.with_transaction = Mock(side_effect=self._with_transaction)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def _with_transaction(self, callback):
        if self.behavior is not None:
            return self.behavior(callback, self)
        return callback(self)


def setup_service(monkeypatch, *, create_side_effect=None, ratings=None, session_behavior=None):
    session = FakeSession(session_behavior)
    client = SimpleNamespace(start_session=Mock(return_value=session))
    connection = SimpleNamespace(
        session=None,
        in_atomic_block=False,
        in_atomic_block_mongo=False,
        ensure_connection=Mock(),
        connection=client,
        run_on_commit=[],
    )
    monkeypatch.setattr(services, "connections", {"default": connection})

    course = Mock()
    course.pk = "course-id"
    fresh_course = Mock()
    course_manager = Mock()
    course_manager.using.return_value.get.return_value = fresh_course
    monkeypatch.setattr(services.Course, "objects", course_manager)

    rating = Mock()
    course_ratings = (
        [
            {"difficulty": 4, "workload": 3, "usefulness": 5},
        ]
        if ratings is None
        else ratings
    )
    rating_manager = Mock()
    rating_manager.using.return_value.create.return_value = rating
    rating_manager.using.return_value.filter.return_value.values.return_value = course_ratings
    if create_side_effect is not None:
        rating_manager.using.return_value.create.side_effect = create_side_effect
    monkeypatch.setattr(services.CourseRating, "objects", rating_manager)

    summary = {"avg_difficulty": 4.0, "avg_workload": 3.0, "avg_usefulness": 5.0, "count": 1}
    summary_factory = Mock(return_value=summary)
    monkeypatch.setattr(services, "CourseRatingSummary", summary_factory)
    monkeypatch.setattr(services, "_clean_course_rating_semester", Mock(return_value="Fall 2026"))

    user = Mock()
    user.pk = "user-id"
    kwargs = {
        "user": user,
        "course": course,
        "difficulty": 4,
        "workload": 3,
        "usefulness": 5,
        "semester": "Fall 2026",
    }
    return (
        kwargs,
        connection,
        client,
        session,
        course_manager,
        fresh_course,
        rating_manager,
        rating,
        summary_factory,
    )


def test_transactional_submission_runs_all_database_work_in_callback(monkeypatch):
    (
        kwargs,
        connection,
        client,
        session,
        course_manager,
        fresh_course,
        rating_manager,
        rating,
        summary_factory,
    ) = setup_service(monkeypatch)

    result = services.submit_course_rating_transactional(**kwargs)

    assert result is rating
    connection.ensure_connection.assert_called_once_with()
    client.start_session.assert_called_once_with()
    session.with_transaction.assert_called_once()
    course_manager.using.return_value.get.assert_called_once_with(pk="course-id")
    rating_manager.using.return_value.create.assert_called_once_with(
        user_id="user-id",
        course_id="course-id",
        difficulty=4,
        workload=3,
        usefulness=5,
        semester="Fall 2026",
    )
    rating_manager.using.return_value.filter.assert_called_once_with(course_id="course-id")
    fresh_course.save.assert_called_once_with(using="default", update_fields=["rating_summary"])
    assert connection.session is None
    assert connection.run_on_commit == []
    summary_factory.assert_called_once_with(
        avg_difficulty=4.0, avg_workload=3.0, avg_usefulness=5.0, count=1
    )


def test_transient_retry_repeats_only_orm_work_without_external_hooks(monkeypatch):
    attempts = {"count": 0}

    def create_once_failing(**kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            cause = OperationFailure(
                "transient",
                details={"errorLabels": ["TransientTransactionError"]},
            )
            raise DatabaseError("wrapped query error") from cause
        return Mock(name="rating")

    def retry_transient(callback, session):
        try:
            return callback(session)
        except OperationFailure as error:
            if error.has_error_label("TransientTransactionError"):
                return callback(session)
            raise

    (kwargs, connection, _, session, _, _, rating_manager, _, _) = setup_service(
        monkeypatch,
        create_side_effect=create_once_failing,
        session_behavior=retry_transient,
    )

    services.submit_course_rating_transactional(**kwargs)

    assert attempts["count"] == 2
    assert session.with_transaction.call_count == 1
    assert rating_manager.using.return_value.create.call_count == 2
    assert connection.session is None
    # No on-commit or other external work is registered from a retryable callback.
    assert connection.run_on_commit == []


def test_unknown_commit_result_is_not_resubmitted_by_service(monkeypatch):
    attempts = {"callbacks": 0}
    unknown = OperationFailure(
        "unknown commit",
        details={"errorLabels": ["UnknownTransactionCommitResult"]},
    )

    def unresolved_commit(callback, session):
        callback(session)
        attempts["callbacks"] += 1
        raise unknown

    (kwargs, connection, _, session, _, _, rating_manager, _, _) = setup_service(
        monkeypatch, session_behavior=unresolved_commit
    )

    with pytest.raises(OperationFailure) as error:
        services.submit_course_rating_transactional(**kwargs)

    assert error.value.has_error_label("UnknownTransactionCommitResult")
    assert attempts["callbacks"] == 1
    assert session.with_transaction.call_count == 1
    assert rating_manager.using.return_value.create.call_count == 1
    assert connection.session is None


def test_duplicate_key_is_translated_and_not_retried(monkeypatch):
    duplicate = DuplicateKeyError(
        "duplicate",
        code=11000,
        details={"keyPattern": {"user_id": 1, "course_id": 1}},
    )
    wrapped_duplicate = IntegrityError("wrapped duplicate")
    wrapped_duplicate.__cause__ = duplicate
    (kwargs, connection, _, session, _, _, rating_manager, _, _) = setup_service(
        monkeypatch,
        create_side_effect=wrapped_duplicate,
    )

    with pytest.raises(services.CourseRatingAlreadyExists):
        services.submit_course_rating_transactional(**kwargs)

    session.with_transaction.assert_called_once()
    rating_manager.using.return_value.create.assert_called_once()
    assert connection.session is None


def test_validation_happens_before_connection_or_transaction(monkeypatch):
    (kwargs, connection, client, _, _, _, _, _, _) = setup_service(monkeypatch)
    kwargs["difficulty"] = True

    with pytest.raises(ValueError, match="whole numbers from 1 to 5"):
        services.submit_course_rating_transactional(**kwargs)

    connection.ensure_connection.assert_not_called()
    client.start_session.assert_not_called()


@pytest.mark.parametrize("field", ["difficulty", "workload", "usefulness"])
@pytest.mark.parametrize("score", [0, 6, -1, 2.5, True, "4", None])
def test_all_invalid_score_types_and_values_fail_before_transaction(monkeypatch, field, score):
    (kwargs, connection, client, _, _, _, _, _, _) = setup_service(monkeypatch)
    kwargs[field] = score

    with pytest.raises(ValueError, match="whole numbers from 1 to 5"):
        services.submit_course_rating_transactional(**kwargs)

    connection.ensure_connection.assert_not_called()
    client.start_session.assert_not_called()


def test_nested_transaction_is_rejected_before_starting_session(monkeypatch):
    (kwargs, connection, client, _, _, _, _, _, _) = setup_service(monkeypatch)
    connection.in_atomic_block_mongo = True

    with pytest.raises(RuntimeError, match="cannot be nested"):
        services.submit_course_rating_transactional(**kwargs)

    client.start_session.assert_not_called()


def test_session_is_attached_during_orm_operations_and_restored(monkeypatch):
    (kwargs, connection, _, session, course_manager, fresh_course, rating_manager, _, _) = (
        setup_service(monkeypatch)
    )
    observed = []

    def observe(label):
        assert connection.session is session
        observed.append(label)

    def get_course(*, pk):
        observe("course_get")
        assert pk == "course-id"
        return fresh_course

    def create_rating(**values):
        observe("rating_create")
        return Mock(name="rating")

    def filter_ratings(**values):
        observe("ratings_filter")
        return rating_manager.using.return_value.filter.return_value

    def values(*fields):
        observe("ratings_values")
        return [{"difficulty": 4, "workload": 3, "usefulness": 5}]

    def save_course(*, using, update_fields):
        observe("course_save")

    course_manager.using.return_value.get.side_effect = get_course
    rating_manager.using.return_value.create.side_effect = create_rating
    rating_manager.using.return_value.filter.side_effect = filter_ratings
    rating_manager.using.return_value.filter.return_value.values.side_effect = values
    fresh_course.save.side_effect = save_course

    services.submit_course_rating_transactional(**kwargs)

    assert observed == [
        "course_get",
        "rating_create",
        "ratings_filter",
        "ratings_values",
        "course_save",
    ]
    assert connection.session is None


def test_unrelated_duplicate_key_is_not_classified_as_course_rating_duplicate(monkeypatch):
    duplicate = DuplicateKeyError(
        "duplicate",
        code=11000,
        details={
            "indexName": "ratings_course_user_unique",
            "keyPattern": {"username": 1},
        },
    )
    wrapped_duplicate = IntegrityError("wrapped duplicate")
    wrapped_duplicate.__cause__ = duplicate
    (kwargs, _, _, session, _, _, rating_manager, _, _) = setup_service(
        monkeypatch,
        create_side_effect=wrapped_duplicate,
    )

    with pytest.raises(IntegrityError) as error:
        services.submit_course_rating_transactional(**kwargs)

    assert error.value is wrapped_duplicate
    assert not isinstance(error.value, services.CourseRatingAlreadyExists)
    session.with_transaction.assert_called_once()
    rating_manager.using.return_value.create.assert_called_once()


def test_invalid_semester_is_rejected_before_session_creation(monkeypatch):
    (kwargs, connection, client, _, _, _, _, _, _) = setup_service(monkeypatch)
    monkeypatch.setattr(
        services,
        "_clean_course_rating_semester",
        Mock(side_effect=ValidationError("invalid semester")),
    )

    with pytest.raises(ValidationError, match="invalid semester"):
        services.submit_course_rating_transactional(**kwargs)

    connection.ensure_connection.assert_not_called()
    client.start_session.assert_not_called()
