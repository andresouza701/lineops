from typing import cast
from rest_framework.test import APIClient
from rest_framework import status
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from django.utils import timezone
from django.http.response import HttpResponseBase
from datetime import timedelta


class AuthenticationTests(TestCase):

    def test_authentication_required(self):
        client = APIClient()
        response = cast(HttpResponseBase, client.get('/api/phonelines/'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authentication_with_token(self):
        # Create a user and obtain a token
        user = User.objects.create_user(
            username='testuser', password='testpass')
        token = Token.objects.create(user=user)

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        response = cast(HttpResponseBase, client.get('/api/phonelines/'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_authentication_with_invalid_token(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token ' + 'invalidtoken')
        response = cast(HttpResponseBase, client.get('/api/phonelines/'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authentication_with_expired_token(self):
        # Create a user and obtain a token
        user = User.objects.create_user(
            username='testuser', password='testpass')
        token = Token.objects.create(user=user)

        # Simulate token expiration
        token.created = timezone.now() - timedelta(days=30)
        token.save()

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        response = cast(HttpResponseBase, client.get('/api/phonelines/'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authentication_with_no_token(self):
        client = APIClient()
        response = cast(HttpResponseBase, client.get('/api/phonelines/'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
