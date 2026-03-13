from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import IntegrityError
from django.test import RequestFactory, TestCase

from core.current_user import get_current_user
from core.middleware import (
    DUPLICATE_EMPLOYEE_NAME_CONSTRAINT,
    DUPLICATE_EMPLOYEE_NAME_MESSAGE,
    CurrentUserMiddleware,
)


class CurrentUserMiddlewareTest(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_duplicate_employee_integrity_error_returns_409(self) -> None:
        def failing_response(_request):
            raise IntegrityError(
                "duplicate key value violates unique constraint "
                f'"{DUPLICATE_EMPLOYEE_NAME_CONSTRAINT}"'
            )

        request = self.factory.post("/employees/create/")
        request.user = AnonymousUser()
        request.session = self.client.session
        request._messages = FallbackStorage(request)

        middleware = CurrentUserMiddleware(failing_response)
        response = middleware(request)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.content.decode("utf-8"), DUPLICATE_EMPLOYEE_NAME_MESSAGE
        )

    def test_other_integrity_errors_are_re_raised(self) -> None:
        def failing_response(_request):
            raise IntegrityError("some other integrity issue")

        request = self.factory.post("/employees/create/")
        request.user = AnonymousUser()

        middleware = CurrentUserMiddleware(failing_response)

        with self.assertRaises(IntegrityError):
            middleware(request)

    def test_current_user_is_cleared_when_exception_happens(self) -> None:
        def failing_response(_request):
            raise IntegrityError(
                "duplicate key value violates unique constraint "
                f'"{DUPLICATE_EMPLOYEE_NAME_CONSTRAINT}"'
            )

        request = self.factory.post("/employees/create/")
        request.user = AnonymousUser()

        middleware = CurrentUserMiddleware(failing_response)
        middleware(request)

        self.assertIsNone(get_current_user())
