from django.contrib import messages
from django.db import IntegrityError
from django.http import HttpResponse

from core.current_user import clear_current_user, set_current_user

DUPLICATE_EMPLOYEE_NAME_CONSTRAINT = "employees_employee_unique_active_full_name_ci"
DUPLICATE_EMPLOYEE_NAME_MESSAGE = "Ja existe um usuario cadastrado com este nome."


def _is_duplicate_employee_name_error(exc: IntegrityError) -> bool:
    if DUPLICATE_EMPLOYEE_NAME_CONSTRAINT in str(exc):
        return True

    cause = getattr(exc, "__cause__", None)
    if not cause:
        return False

    if DUPLICATE_EMPLOYEE_NAME_CONSTRAINT in str(cause):
        return True

    diag = getattr(cause, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    return constraint_name == DUPLICATE_EMPLOYEE_NAME_CONSTRAINT


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_user(getattr(request, "user", None))
        try:
            response = self.get_response(request)
        except IntegrityError as exc:
            if not _is_duplicate_employee_name_error(exc):
                raise

            if hasattr(request, "_messages"):
                messages.error(request, DUPLICATE_EMPLOYEE_NAME_MESSAGE)

            response = HttpResponse(
                DUPLICATE_EMPLOYEE_NAME_MESSAGE,
                status=409,
                content_type="text/plain; charset=utf-8",
            )
        finally:
            clear_current_user()
        return response
