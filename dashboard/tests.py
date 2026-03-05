import re

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser

from .forms import DailyIndicatorForm
from .models import DailyUserAction


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
            employee_id="Alimentos",
            teams="B2B Squad",
            status=Employee.Status.ACTIVE,
        )
        self.employee_b2c = Employee.objects.create(
            full_name="B2C User",
            corporate_email="b2c@corp.com",
            employee_id="Natura",
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
            "Acoes",
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
            r"<td>\d+</td>\s*"
            r"<td>.*?Ver detalhes.*?</td>"
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
        if payload["rows"]:
            self.assertIn("detail_url", payload["rows"][0])

    def test_dashboard_splits_sem_whats_by_b2b_and_b2c_portfolios(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        latest = response.context["indicadores_diarios"][-1]
        self.assertEqual(latest["b2b_sem_whats"], 0)
        self.assertEqual(latest["b2c_sem_whats"], 1)

    def test_dashboard_ignores_inactive_users_in_sem_linha_and_descoberto(self):
        Employee.objects.create(
            full_name="Inactive User",
            corporate_email="inactive@corp.com",
            employee_id="Natura",
            teams="B2C Squad",
            status=Employee.Status.INACTIVE,
        )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        latest = response.context["indicadores_diarios"][-1]
        self.assertEqual(latest["b2c_sem_whats"], 1)
        self.assertEqual(latest["total_descoberto_dia"], 1)

    def test_dashboard_daily_row_contains_day_detail_link(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        today_iso = timezone.localdate().strftime("%Y-%m-%d")
        expected_link = reverse(
            "daily_indicator_day_breakdown", kwargs={"day": today_iso}
        )
        self.assertContains(response, expected_link)

    def test_dashboard_exception_cards_show_pending_action_counts(self):
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
        )
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2c,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        cards = response.context["exception_cards"]
        pending_new_number = next(
            card for card in cards if card["title"] == "Pendêcia - Número Novo"
        )
        pending_reconnect = next(
            card for card in cards if card["title"] == "Pendêcia - Reconexão Whats"
        )
        self.assertEqual(pending_new_number["value"], 1)
        self.assertEqual(pending_reconnect["value"], 1)

    def test_daily_indicator_day_breakdown_shows_user_details(self):
        today_iso = timezone.localdate().strftime("%Y-%m-%d")
        response = self.client.get(
            reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "B2B User")
        self.assertContains(response, "B2C User")
        self.assertContains(response, "+5511999999001")
        self.assertContains(response, "+5511999999002")
        self.assertContains(response, "Números disponíveis")
        self.assertContains(response, "Números entregues")
        self.assertContains(response, "Números reconectados")
        self.assertContains(response, "Números novos")
        self.assertContains(response, "Usuarios logados")
        self.assertContains(response, "Usuarios com linha")
        self.assertContains(response, "Usuarios sem linha")

    def test_daily_user_action_board_allows_marking_action(self):
        response = self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": self.employee_b2c.id,
                "action_type": DailyUserAction.ActionType.NEW_NUMBER,
                "note": "Sem linha para iniciar contato",
            },
        )
        self.assertEqual(response.status_code, 302)

        action = DailyUserAction.objects.get(
            day=timezone.localdate(),
            employee=self.employee_b2c,
        )
        self.assertEqual(action.action_type, DailyUserAction.ActionType.NEW_NUMBER)
        self.assertEqual(action.note, "Sem linha para iniciar contato")

    def test_daily_user_action_board_removes_action_when_blank(self):
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2c,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": self.employee_b2c.id,
                "action_type": "",
                "note": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        # Verificar que a ação foi marcada como resolvida em vez de deletada
        action = DailyUserAction.objects.filter(
            day=timezone.localdate(),
            employee=self.employee_b2c,
        ).first()
        self.assertIsNotNone(action)
        self.assertTrue(action.is_resolved)

    def test_daily_user_action_board_blank_action_does_not_create_new_row(self):
        response = self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": self.employee_b2c.id,
                "action_type": "",
                "note": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            DailyUserAction.objects.filter(
                day=timezone.localdate(),
                employee=self.employee_b2c,
            ).exists()
        )

    def test_daily_user_action_board_filters_actions_by_selected_day(self):
        today = timezone.localdate()
        yesterday = today - timezone.timedelta(days=1)

        DailyUserAction.objects.create(
            day=yesterday,
            employee=self.employee_b2c,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.get(
            reverse("daily_user_action_board"),
            {"day": today.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["action_counts"]["new_number"], 0)
        self.assertEqual(response.context["action_counts"]["reconnect_whatsapp"], 0)
