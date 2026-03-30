from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(
    ALLOWED_HOSTS=["qa.lineops.local", "testserver"],
    CSRF_TRUSTED_ORIGINS=[],
)
class CsrfProxyHeaderTests(TestCase):
    def _get_csrf_token(self, host: str):
        client = Client(enforce_csrf_checks=True)
        response = client.get(reverse("login"), secure=True, HTTP_HOST=host)

        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", client.cookies)

        return client.cookies["csrftoken"].value, client

    def test_secure_post_is_rejected_when_proxy_strips_non_default_port(self):
        token, client = self._get_csrf_token("qa.lineops.local")

        response = client.post(
            reverse("logout"),
            {"csrfmiddlewaretoken": token},
            secure=True,
            HTTP_HOST="qa.lineops.local",
            HTTP_REFERER="https://qa.lineops.local:18443/accounts/logout/",
        )

        self.assertEqual(response.status_code, 403)

    def test_secure_post_passes_when_host_header_preserves_public_port(self):
        token, client = self._get_csrf_token("qa.lineops.local:18443")

        response = client.post(
            reverse("logout"),
            {"csrfmiddlewaretoken": token},
            secure=True,
            HTTP_HOST="qa.lineops.local:18443",
            HTTP_REFERER="https://qa.lineops.local:18443/accounts/logout/",
        )

        self.assertEqual(response.status_code, 302)
