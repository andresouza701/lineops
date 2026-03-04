import re

from django.test import TestCase
from django.urls import reverse

from allocations.models import LineAllocation
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

from .forms import DailyIndicatorForm


class DashboardDailyIndicatorsTests(TestCase):
    def setUp(self):
        self.user = SystemUser.objects.create_user(
            email="dashboard@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(self.user)

        self.employee_b2b = Employee.objects.create(
            full_name="B2B User",
            corporate_email="b2b@corp.com",
            employee_id="EMP-B2B",
            teams="B2B Squad",
            status=Employee.Status.ACTIVE,
        )
        self.employee_b2c = Employee.objects.create(
            full_name="B2C User",
            corporate_email="b2c@corp.com",
            employee_id="EMP-B2C",
            teams="B2C Squad",
            status=Employee.Status.ACTIVE,
        )

        sim_1 = SIMcard.objects.create(iccid="8900000000000001000", carrier="CarrierX")
        sim_2 = SIMcard.objects.create(iccid="8900000000000001001", carrier="CarrierX")
        self.line_allocated = PhoneLine.objects.create(
            phone_number="+5511999999001",
            sim_card=sim_1,
            status=PhoneLine.Status.ALLOCATED,
        )
        self.line_available = PhoneLine.objects.create(
            phone_number="+5511999999002",
            sim_card=sim_2,
            status=PhoneLine.Status.AVAILABLE,
        )

        LineAllocation.objects.create(
            employee=self.employee_b2b,
            phone_line=self.line_allocated,
            allocated_by=self.user,
            is_active=True,
        )

    def test_dashboard_shows_required_daily_columns(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        for header in [
            "Data",
            "Pessoas Logadas",
            "% sem Whats",
            "B2B sem Whats",
            "B2C sem Whats",
            "N\u00fameros Dispon\u00edveis",
            "N\u00fameros Entregues",
            "Reconectados",
            "Novos",
            "Total Descoberto DIA",
        ]:
            self.assertContains(response, header)

    def test_dashboard_daily_row_uses_consistent_format(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        # Date in DD/MM/YYYY, percentage with 2 decimals, numeric columns as integers.
        row_pattern = (
            r"<td>\d{2}/\d{2}/\d{4}</td>\s*"
            r"<td>\d+</td>\s*"
            r"<td>\d+[,.]\d{2}%</td>\s*"
            r"<td>\d+</td>\s*"
            r"<td>\d+</td>\s*"
            r"<td>\d+</td>\s*"
            r"<td>\d+</td>\s*"
            r"<td>\d+</td>\s*"
            r"<td>\d+</td>\s*"
            r"<td>\d+</td>"
        )
        self.assertRegex(html, re.compile(row_pattern, re.S))

    def test_daily_indicator_form_renders_segment_choices_in_selects(self):
        form_b2b = DailyIndicatorForm()
        supervisor_html_b2b = str(form_b2b["supervisor"])
        portfolio_html_b2b = str(form_b2b["portfolio"])
        self.assertIn("Alex", supervisor_html_b2b)
        self.assertIn("Alimentos", portfolio_html_b2b)

        form_b2c = DailyIndicatorForm(
            data={
                "segment": "B2C",
                "supervisor": "Camila",
                "portfolio": "Natura",
                "people_logged_in": 1,
                "date": "2026-03-01",
            }
        )
        supervisor_html_b2c = str(form_b2c["supervisor"])
        portfolio_html_b2c = str(form_b2c["portfolio"])
        self.assertIn("Camila", supervisor_html_b2c)
        self.assertIn("Natura", portfolio_html_b2c)

    def test_live_daily_indicators_endpoint_returns_payload(self):
        response = self.client.get(reverse("daily_indicators_live"), {"period": 7})
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["period"], 7)
        self.assertIn("rows", payload)
        self.assertIn("fingerprint", payload)
        self.assertTrue(payload["fingerprint"])
