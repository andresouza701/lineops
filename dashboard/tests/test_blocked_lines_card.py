from django.test import TestCase
from django.urls import reverse

from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class DashboardBlockedLinesCardTest(TestCase):
    def setUp(self):
        self.user = SystemUser.objects.create_user(
            email="dashboard.blocked@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(self.user)

    def test_dashboard_exception_card_counts_suspended_and_cancelled_lines(self):
        suspended_sim = SIMcard.objects.create(
            iccid="8900000000000012997",
            carrier="CarrierBlocked",
            status=SIMcard.Status.BLOCKED,
        )
        cancelled_sim = SIMcard.objects.create(
            iccid="8900000000000012998",
            carrier="CarrierBlocked",
            status=SIMcard.Status.CANCELLED,
        )
        PhoneLine.objects.create(
            phone_number="+5511999912997",
            sim_card=suspended_sim,
            status=PhoneLine.Status.SUSPENDED,
        )
        PhoneLine.objects.create(
            phone_number="+5511999912998",
            sim_card=cancelled_sim,
            status=PhoneLine.Status.CANCELLED,
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        cards = response.context["exception_cards"]
        blocked_lines_card = next(
            card for card in cards if card["title"] == "Linhas bloqueadas"
        )
        self.assertEqual(blocked_lines_card["value"], 2)
