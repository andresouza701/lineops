from django.db import IntegrityError
from django.test import SimpleTestCase

from core.integrity import (
    DUPLICATE_EMPLOYEE_NAME_CONSTRAINT,
    DUPLICATE_PHONE_NUMBER_CONSTRAINT,
    integrity_error_matches,
    is_duplicate_employee_name_error,
    is_duplicate_phone_number_error,
)


class _CauseWithDiag(Exception):
    def __init__(self, message: str, constraint_name: str | None = None) -> None:
        super().__init__(message)
        if constraint_name is not None:
            self.diag = type("_Diag", (), {"constraint_name": constraint_name})()


class IntegrityErrorMatcherTest(SimpleTestCase):
    def test_matches_when_constraint_is_in_exception_message(self) -> None:
        exc = IntegrityError(
            "duplicate key value violates unique constraint "
            f'"{DUPLICATE_EMPLOYEE_NAME_CONSTRAINT}"'
        )

        self.assertTrue(
            integrity_error_matches(
                exc,
                constraint_name=DUPLICATE_EMPLOYEE_NAME_CONSTRAINT,
            )
        )

    def test_matches_when_field_is_in_exception_message(self) -> None:
        exc = IntegrityError("duplicate value for field phone_number")

        self.assertTrue(
            integrity_error_matches(
                exc,
                constraint_name=DUPLICATE_PHONE_NUMBER_CONSTRAINT,
                field_name="phone_number",
            )
        )

    def test_matches_when_constraint_is_in_cause(self) -> None:
        cause = _CauseWithDiag(
            f'constraint "{DUPLICATE_PHONE_NUMBER_CONSTRAINT}" violation'
        )
        try:
            raise IntegrityError("integrity issue") from cause
        except IntegrityError as exc:
            self.assertTrue(
                integrity_error_matches(
                    exc,
                    constraint_name=DUPLICATE_PHONE_NUMBER_CONSTRAINT,
                )
            )

    def test_matches_when_constraint_name_is_in_cause_diag(self) -> None:
        cause = _CauseWithDiag(
            "db failure",
            constraint_name=DUPLICATE_EMPLOYEE_NAME_CONSTRAINT,
        )
        try:
            raise IntegrityError("integrity issue") from cause
        except IntegrityError as exc:
            self.assertTrue(
                integrity_error_matches(
                    exc,
                    constraint_name=DUPLICATE_EMPLOYEE_NAME_CONSTRAINT,
                )
            )

    def test_returns_false_when_error_does_not_match(self) -> None:
        exc = IntegrityError("some other integrity issue")

        self.assertFalse(
            integrity_error_matches(
                exc,
                constraint_name=DUPLICATE_PHONE_NUMBER_CONSTRAINT,
                field_name="phone_number",
            )
        )

    def test_duplicate_helper_for_employee_name(self) -> None:
        exc = IntegrityError(
            "duplicate key value violates unique constraint "
            f'"{DUPLICATE_EMPLOYEE_NAME_CONSTRAINT}"'
        )

        self.assertTrue(is_duplicate_employee_name_error(exc))

    def test_duplicate_helper_for_phone_number(self) -> None:
        exc = IntegrityError(
            "duplicate key value violates unique constraint "
            f'"{DUPLICATE_PHONE_NUMBER_CONSTRAINT}"'
        )

        self.assertTrue(is_duplicate_phone_number_error(exc))
