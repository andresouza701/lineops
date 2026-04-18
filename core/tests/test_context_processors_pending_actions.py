from unittest.mock import patch

from django.test import RequestFactory, TestCase

from core.context_processors import pending_actions_count
from users.models import SystemUser

MOCK_COUNTS = {"new_number": 2, "reconnect_whatsapp": 1, "pending": 1}


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

    @patch(
        "core.context_processors.get_pending_action_counts_cached",
        return_value=MOCK_COUNTS,
    )
    def test_admin_context_processor_uses_pending_actions_service(self, cache_mock):
        request = self.factory.get("/")
        request.user = self.admin

        context = pending_actions_count(request)

        self.assertEqual(context["pending_actions_count"], 4)
        cache_mock.assert_called_once_with(request)

    @patch("core.context_processors.get_pending_action_counts_cached")
    def test_non_admin_does_not_call_pending_actions_service(self, cache_mock):
        request = self.factory.get("/")
        request.user = self.supervisor

        context = pending_actions_count(request)

        self.assertEqual(context["pending_actions_count"], 0)
        cache_mock.assert_not_called()

    @patch(
        "core.context_processors.get_pending_action_counts_cached",
        return_value=MOCK_COUNTS,
    )
    def test_admin_context_processor_caches_result_per_request(self, cache_mock):
        """
        Chamadas multiplas ao context processor no mesmo request devem
        consumir o mesmo cache por request. O mock retorna o dict cacheado
        sem re-executar a query.
        """
        request = self.factory.get("/")
        request.user = self.admin

        context1 = pending_actions_count(request)
        context2 = pending_actions_count(request)

        self.assertEqual(context1["pending_actions_count"], 4)
        self.assertEqual(context2["pending_actions_count"], 4)
