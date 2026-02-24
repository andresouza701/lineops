from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from users.models import SystemUser


class PermissionByRoleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "StrongPass123"
        self.admin = SystemUser.objects.create_user(
            email="admin.role@test.com",
            password=self.password,
            role=SystemUser.Role.ADMIN,
        )
        self.operator = SystemUser.objects.create_user(
            email="operator.role@test.com",
            password=self.password,
            role=SystemUser.Role.OPERATOR,
        )

    def _access_token(self, email, password):
        response = self.client.post(
            "/api/token/",
            {"email": email, "password": password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.json()["access"]

    def test_admin_can_access_admin_only_endpoint(self):
        token = self._access_token(self.admin.email, self.password)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.get("/api/admin-only/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_operator_cannot_access_admin_only_endpoint(self):
        token = self._access_token(self.operator.email, self.password)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.get("/api/admin-only/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
