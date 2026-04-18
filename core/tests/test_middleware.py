from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from core.current_user import get_current_user
from core.middleware import CurrentUserMiddleware


class CurrentUserMiddlewareTest(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_middleware_returns_response_and_clears_current_user(self) -> None:
        def ok_response(_request):
            return HttpResponse("ok")

        request = self.factory.get("/")
        request.user = AnonymousUser()

        middleware = CurrentUserMiddleware(ok_response)
        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode("utf-8"), "ok")
        self.assertIsNone(get_current_user())

    def test_integrity_errors_are_re_raised(self) -> None:
        def failing_response(_request):
            raise IntegrityError("some other integrity issue")

        request = self.factory.post("/employees/create/")
        request.user = AnonymousUser()

        middleware = CurrentUserMiddleware(failing_response)

        with self.assertRaises(IntegrityError):
            middleware(request)

        self.assertIsNone(get_current_user())
