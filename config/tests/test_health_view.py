from django.test import TestCase, override_settings
from django.urls import reverse

from users.models import SystemUser


class HealthCheckViewTests(TestCase):
    def test_health_is_public_when_auth_not_required(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response["Cache-Control"], "no-store")

    @override_settings(HEALTHCHECK_REQUIRE_AUTH=True)
    def test_health_requires_auth_when_enabled(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"status": "forbidden"})
        self.assertEqual(response["Cache-Control"], "no-store")

    @override_settings(HEALTHCHECK_REQUIRE_AUTH=True)
    def test_health_returns_ok_for_authenticated_user(self):
        user = SystemUser.objects.create_user(
            email="health@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response["Cache-Control"], "no-store")
