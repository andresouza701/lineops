from django.test import TestCase
from django.urls import reverse

from users.models import SystemUser


class PendencyMetricsViewTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="metrics.view.admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.operator = SystemUser.objects.create_user(
            email="metrics.view.operator@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )

    def test_admin_can_open_metrics_page(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("dashboard_metrics"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/metrics.html")
        self.assertIn("summary", response.context)
        self.assertIn("responsible_rankings", response.context)

    def test_operator_cannot_open_metrics_page(self):
        self.client.force_login(self.operator)

        response = self.client.get(reverse("dashboard_metrics"))

        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_cannot_open_metrics_page(self):
        response = self.client.get(reverse("dashboard_metrics"))

        self.assertEqual(response.status_code, 403)
