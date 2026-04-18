from unittest.mock import patch

from django.test import RequestFactory, TestCase

from core.context_processors import pending_actions_count
from users.models import SystemUser


class PendingActionsContextProcessorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = SystemUser.objects.create_user(
            email="context.admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.supervisor = SystemUser.objects.create_user(
            email="context.super@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )

    @patch("core.context_processors.get_pending_actions_count_for_user", return_value=4)
    def test_admin_context_processor_uses_pending_actions_service(self, count_mock):
        request = self.factory.get("/")
        request.user = self.admin

        context = pending_actions_count(request)

        self.assertEqual(context["pending_actions_count"], 4)
        count_mock.assert_called_once_with(self.admin)

    @patch("core.context_processors.get_pending_actions_count_for_user")
    def test_non_admin_does_not_call_pending_actions_service(self, count_mock):
        request = self.factory.get("/")
        request.user = self.supervisor

        context = pending_actions_count(request)

        self.assertEqual(context["pending_actions_count"], 0)
        count_mock.assert_not_called()
