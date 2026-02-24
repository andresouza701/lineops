from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from users.models import SystemUser


class AuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "StrongPass123"
        self.admin = SystemUser.objects.create_user(
            email="admin.auth@test.com",
            password=self.password,
            role=SystemUser.Role.ADMIN,
        )

    def test_authentication_required(self):
        response = self.client.get("/api/admin-only/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authentication_with_valid_jwt(self):
        token_response = self.client.post(
            "/api/token/",
            {"email": self.admin.email, "password": self.password},
            format="json",
        )
        self.assertEqual(token_response.status_code, status.HTTP_200_OK)
        access_token = token_response.json()["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = self.client.get("/api/admin-only/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_authentication_with_invalid_token(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalidtoken")
        response = self.client.get("/api/admin-only/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authentication_with_invalid_credentials(self):
        response = self.client.post(
            "/api/token/",
            {"email": self.admin.email, "password": "wrong-password"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
