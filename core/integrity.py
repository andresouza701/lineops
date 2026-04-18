from django.db import IntegrityError

DUPLICATE_EMPLOYEE_NAME_CONSTRAINT = "employees_employee_unique_active_full_name_ci"
DUPLICATE_PHONE_NUMBER_CONSTRAINT = "telecom_phoneline_phone_number_key"


def integrity_error_matches(
    exc: IntegrityError,
    *,
    constraint_name: str,
    field_name: str = "",
) -> bool:
    """Match IntegrityError by constraint name and optional field hint."""

    expected_tokens = tuple(
        token for token in (constraint_name, field_name) if token
    )

    if any(token in str(exc) for token in expected_tokens):
        return True

    cause = getattr(exc, "__cause__", None)
    if not cause:
        return False

    if any(token in str(cause) for token in expected_tokens):
        return True

    diag = getattr(cause, "diag", None)
    return getattr(diag, "constraint_name", None) == constraint_name


def is_duplicate_employee_name_error(exc: IntegrityError) -> bool:
    return integrity_error_matches(
        exc,
        constraint_name=DUPLICATE_EMPLOYEE_NAME_CONSTRAINT,
    )


def is_duplicate_phone_number_error(exc: IntegrityError) -> bool:
    return integrity_error_matches(
        exc,
        constraint_name=DUPLICATE_PHONE_NUMBER_CONSTRAINT,
        field_name="phone_number",
    )
