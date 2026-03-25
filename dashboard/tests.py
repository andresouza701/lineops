import re
from datetime import datetime, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from core.services.allocation_service import AllocationService
from core.services.daily_indicator_service import DailyIndicatorService
from employees.models import Employee
from telecom.models import PhoneLine, PhoneLineHistory, SIMcard
from users.models import SystemUser
from whatsapp.choices import MeowInstanceHealthStatus, WhatsAppSessionStatus
from whatsapp.models import MeowInstance, WhatsAppSession

from .forms import DailyIndicatorForm
from .models import DailyUserAction, DashboardDailySnapshot


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

        self.line_allocation = LineAllocation.objects.create(
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
            "Números Disponíveis",
            "Números Entregues",
            "Reconectados",
            "Novos",
            "Total Descoberto DIA",
            "Ações",
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

    def test_operator_cannot_access_sensitive_dashboard_views(self):
        operator = SystemUser.objects.create_user(
            email="operator.dashboard@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )
        self.client.force_login(operator)

        today_iso = timezone.localdate().strftime("%Y-%m-%d")
        urls = [
            reverse("daily_user_action_board"),
            reverse("daily_indicators_live"),
            reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso}),
            reverse("daily_indicator_management"),
        ]

        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)

    def test_dashboard_splits_sem_whats_by_b2b_and_b2c_portfolios(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        latest = response.context["indicadores_diarios"][-1]
        self.assertEqual(latest["b2b_sem_whats"], 0)
        self.assertEqual(latest["b2c_sem_whats"], 1)

    def test_dashboard_counts_only_available_lines_as_available(self):
        sim_3 = SIMcard.objects.create(iccid="8900000000000001002", carrier="CarrierX")
        PhoneLine.objects.create(
            phone_number="+5511999999003",
            sim_card=sim_3,
            status=PhoneLine.Status.SUSPENDED,
        )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        latest = response.context["indicadores_diarios"][-1]
        self.assertEqual(response.context["available_lines"], 1)
        self.assertEqual(latest["numeros_disponiveis"], 1)

    def test_daily_indicator_form_rejects_people_logged_in_above_limit(self):
        form = DailyIndicatorForm(
            data={
                "segment": "B2C",
                "supervisor": "Camila",
                "portfolio": "Natura",
                "people_logged_in": 5001,
                "date": timezone.localdate().isoformat(),
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "Valor deve estar entre 0 e 5000.",
            form.errors["people_logged_in"],
        )

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

    def test_dashboard_shows_snapshot_report_export_filter(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("dashboard_daily_snapshot_report"))
        self.assertContains(response, 'name="date"', html=False)
        self.assertContains(response, "Exportar relatório")
        self.assertContains(response, 'data-no-loading="true"', html=False)

    def test_dashboard_snapshot_report_exports_csv_for_selected_day(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        DashboardDailySnapshot.objects.create(
            date=yesterday,
            people_logged_in=44,
            percentage_without_whatsapp=2.27,
            b2b_without_whatsapp=0,
            b2c_without_whatsapp=1,
            numbers_available=2,
            numbers_delivered=23,
            numbers_reconnected=1,
            numbers_new=31,
            total_uncovered_day=1,
        )

        response = self.client.get(
            reverse("dashboard_daily_snapshot_report"),
            {"date": yesterday.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("snapshot_diario_", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        content = response.content.decode("utf-8-sig")
        self.assertIn("Data,Pessoas Logadas,% sem Whats", content)
        self.assertIn("44,2.27,0,1,2,23,1,31,1", content)

    def test_dashboard_historical_rows_use_preserved_snapshot(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        created_at = timezone.make_aware(datetime.combine(yesterday, time(8, 0)))

        employee = Employee.objects.create(
            full_name="Snapshot User",
            corporate_email="snapshot@corp.com",
            employee_id="Natura",
            teams="B2C Squad",
            status=Employee.Status.ACTIVE,
        )
        Employee.all_objects.filter(pk=employee.pk).update(
            created_at=created_at,
            updated_at=created_at,
        )

        sim = SIMcard.objects.create(
            iccid="8900000000000004555",
            carrier="CarrierSnapshot",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number="+5511999994555",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        PhoneLine.all_objects.filter(pk=line.pk).update(
            created_at=created_at,
            updated_at=created_at,
        )

        first_response = self.client.get(reverse("dashboard"))
        self.assertEqual(first_response.status_code, 200)

        snapshot = DashboardDailySnapshot.objects.get(date=yesterday)
        self.assertEqual(snapshot.people_logged_in, 1)
        self.assertEqual(snapshot.b2c_without_whatsapp, 1)
        self.assertEqual(snapshot.numbers_available, 1)

        employee.delete()
        sim.delete()

        second_response = self.client.get(reverse("dashboard"))
        self.assertEqual(second_response.status_code, 200)

        historical_row = next(
            item
            for item in second_response.context["indicadores_diarios"]
            if item["data"] == yesterday
        )
        self.assertEqual(historical_row["pessoas_logadas"], 1)
        self.assertEqual(historical_row["b2c_sem_whats"], 1)
        self.assertEqual(historical_row["numeros_disponiveis"], 1)

    def test_dashboard_exception_cards_show_pending_action_counts(self):
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            allocation=self.line_allocation,
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

    def test_dashboard_shows_whatsapp_pending_summary_section(self):
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            allocation=self.line_allocation,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            note="Validar QR da linha",
            is_resolved=False,
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        summary = response.context["whatsapp_pending_summary"]
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["reconnect_whatsapp"], 1)
        self.assertContains(response, "Fila WhatsApp")
        self.assertContains(response, self.employee_b2b.full_name)
        self.assertContains(response, self.line_allocated.phone_number)
        self.assertContains(response, "Validar QR da linha")
        self.assertContains(
            response,
            reverse("telecom:phoneline_detail", args=[self.line_allocated.pk]),
        )

    def test_dashboard_counts_pending_new_number_from_allocation_flow(self):
        employee = Employee.objects.create(
            full_name="Flow User",
            corporate_email="flow@corp.com",
            employee_id="Unilever",
            teams="B2C Squad",
            status=Employee.Status.ACTIVE,
        )
        sim = SIMcard.objects.create(iccid="8900000000000001666", carrier="CarrierX")
        line = PhoneLine.objects.create(
            phone_number="+5511999999666",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )

        with self.captureOnCommitCallbacks(execute=True):
            allocation = AllocationService.allocate_line(
                employee=employee,
                phone_line=line,
                allocated_by=self.user,
            )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pending_actions_count"], 1)

        cards = response.context["exception_cards"]
        pending_new_number = next(
            card for card in cards if card["title"] == "PendÃªcia - NÃºmero Novo"
        )
        self.assertEqual(pending_new_number["value"], 1)

        action = DailyUserAction.objects.get(
            employee=employee,
            allocation=allocation,
            is_resolved=False,
        )
        self.assertEqual(action.action_type, DailyUserAction.ActionType.NEW_NUMBER)

    def test_dashboard_clears_pending_count_after_release_flow_resolves_action(self):
        employee = Employee.objects.create(
            full_name="Release Flow User",
            corporate_email="release@corp.com",
            employee_id="Nestle",
            teams="B2C Squad",
            status=Employee.Status.ACTIVE,
        )
        sim = SIMcard.objects.create(iccid="8900000000000001667", carrier="CarrierX")
        line = PhoneLine.objects.create(
            phone_number="+5511999999667",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )

        with self.captureOnCommitCallbacks(execute=True):
            allocation = AllocationService.allocate_line(
                employee=employee,
                phone_line=line,
                allocated_by=self.user,
            )

        with self.captureOnCommitCallbacks(execute=True):
            AllocationService.release_line(allocation=allocation, released_by=self.user)

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pending_actions_count"], 0)

        action = DailyUserAction.objects.get(employee=employee, allocation=allocation)
        self.assertTrue(action.is_resolved)

    def test_dashboard_exception_cards_do_not_double_count_old_open_actions(self):
        today = timezone.localdate()
        yesterday = today - timezone.timedelta(days=1)

        DailyUserAction.objects.create(
            day=yesterday,
            employee=self.employee_b2b,
            allocation=self.line_allocation,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )
        DailyUserAction.objects.create(
            day=today,
            employee=self.employee_b2b,
            allocation=self.line_allocation,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        cards = response.context["exception_cards"]
        pending_new_number = next(
            card for card in cards if card["title"] == "Pendêcia - Número Novo"
        )
        self.assertEqual(pending_new_number["value"], 1)

    def test_dashboard_exception_cards_ignore_inactive_users(self):
        inactive_employee = Employee.objects.create(
            full_name="Inactive User",
            corporate_email="inactive@corp.com",
            employee_id="Unilever",
            teams="Joinville",
            status=Employee.Status.INACTIVE,
        )
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=inactive_employee,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        cards = response.context["exception_cards"]
        pending_new_number = next(
            card for card in cards if card["title"] == "Pendêcia - Número Novo"
        )
        self.assertEqual(pending_new_number["value"], 0)

    def test_dashboard_counts_real_reconnections_for_same_employee_only(self):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)

        previous_allocated_at = timezone.make_aware(
            datetime.combine(yesterday, time(10, 0))
        )
        released_at = timezone.make_aware(datetime.combine(today, time(9, 0)))
        reconnected_at = timezone.make_aware(datetime.combine(today, time(11, 0)))

        LineAllocation.objects.filter(pk=self.line_allocation.pk).update(
            allocated_at=previous_allocated_at,
            released_at=released_at,
            is_active=False,
        )

        reconnected_allocation = LineAllocation.objects.create(
            employee=self.employee_b2b,
            phone_line=self.line_allocated,
            allocated_by=self.user,
            is_active=True,
        )
        LineAllocation.objects.filter(pk=reconnected_allocation.pk).update(
            allocated_at=reconnected_at
        )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        latest = response.context["indicadores_diarios"][-1]
        self.assertEqual(latest["reconectados"], 1)
        self.assertEqual(DailyIndicatorService.calculate_reconnected_numbers(today), 1)

        cards = response.context["exception_cards"]
        reconnected_card = next(
            card for card in cards if card["title"] == "Reconectados hoje"
        )
        self.assertEqual(reconnected_card["value"], 1)

    def test_dashboard_does_not_count_line_transfer_as_reconnection(self):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)

        previous_allocated_at = timezone.make_aware(
            datetime.combine(yesterday, time(10, 0))
        )
        released_at = timezone.make_aware(datetime.combine(today, time(9, 0)))
        transferred_at = timezone.make_aware(datetime.combine(today, time(11, 0)))

        LineAllocation.objects.filter(pk=self.line_allocation.pk).update(
            allocated_at=previous_allocated_at,
            released_at=released_at,
            is_active=False,
        )

        transferred_allocation = LineAllocation.objects.create(
            employee=self.employee_b2c,
            phone_line=self.line_allocated,
            allocated_by=self.user,
            is_active=True,
        )
        LineAllocation.objects.filter(pk=transferred_allocation.pk).update(
            allocated_at=transferred_at
        )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        latest = response.context["indicadores_diarios"][-1]
        self.assertEqual(latest["reconectados"], 0)
        self.assertEqual(DailyIndicatorService.calculate_reconnected_numbers(today), 0)

        cards = response.context["exception_cards"]
        reconnected_card = next(
            card for card in cards if card["title"] == "Reconectados hoje"
        )
        self.assertEqual(reconnected_card["value"], 0)

    def test_dashboard_reconnected_exception_card_does_not_include_open_reconnect_actions(
        self,
    ):
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            allocation=self.line_allocation,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        latest = response.context["indicadores_diarios"][-1]
        self.assertEqual(latest["reconectados"], 0)

        cards = response.context["exception_cards"]
        reconnected_card = next(
            card for card in cards if card["title"] == "Reconectados hoje"
        )
        self.assertEqual(reconnected_card["value"], 0)

    def test_dashboard_reconnected_exception_card_includes_admin_resolved_reconnect_actions(
        self,
    ):
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            allocation=self.line_allocation,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )

        response = self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": self.employee_b2b.id,
                "allocation_id": str(self.line_allocation.id),
                "action_type": "",
                "note": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.get(reverse("dashboard"))
        latest = response.context["indicadores_diarios"][-1]
        self.assertEqual(latest["reconectados"], 1)

        cards = response.context["exception_cards"]
        reconnected_card = next(
            card for card in cards if card["title"] == "Reconectados hoje"
        )
        self.assertEqual(reconnected_card["value"], 1)

    def test_dashboard_reconnected_exception_card_ignores_non_admin_resolution(self):
        supervisor_user = SystemUser.objects.create_user(
            email="super.reconnect@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            allocation=self.line_allocation,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            supervisor=supervisor_user,
            created_by=supervisor_user,
            updated_by=supervisor_user,
            is_resolved=True,
        )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        cards = response.context["exception_cards"]
        reconnected_card = next(
            card for card in cards if card["title"] == "Reconectados hoje"
        )
        self.assertEqual(reconnected_card["value"], 0)

    def test_dashboard_reconnected_exception_card_sums_actual_and_admin_resolved_counts(
        self,
    ):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)

        previous_allocated_at = timezone.make_aware(
            datetime.combine(yesterday, time(10, 0))
        )
        released_at = timezone.make_aware(datetime.combine(today, time(9, 0)))
        reconnected_at = timezone.make_aware(datetime.combine(today, time(11, 0)))

        LineAllocation.objects.filter(pk=self.line_allocation.pk).update(
            allocated_at=previous_allocated_at,
            released_at=released_at,
            is_active=False,
        )

        reconnected_allocation = LineAllocation.objects.create(
            employee=self.employee_b2b,
            phone_line=self.line_allocated,
            allocated_by=self.user,
            is_active=True,
        )
        LineAllocation.objects.filter(pk=reconnected_allocation.pk).update(
            allocated_at=reconnected_at
        )

        DailyUserAction.objects.create(
            day=today,
            employee=self.employee_b2b,
            allocation=reconnected_allocation,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )

        response = self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": today.isoformat(),
                "employee_id": self.employee_b2b.id,
                "allocation_id": str(reconnected_allocation.id),
                "action_type": "",
                "note": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.get(reverse("dashboard"))
        latest = response.context["indicadores_diarios"][-1]
        self.assertEqual(latest["reconectados"], 2)

        cards = response.context["exception_cards"]
        reconnected_card = next(
            card for card in cards if card["title"] == "Reconectados hoje"
        )
        self.assertEqual(reconnected_card["value"], 2)

    def test_dashboard_reconnected_exception_card_counts_single_line_fallback_resolution(self):
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            allocation=None,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )

        response = self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": self.employee_b2b.id,
                "allocation_id": str(self.line_allocation.id),
                "action_type": "",
                "note": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        action = DailyUserAction.objects.get(
            employee=self.employee_b2b,
            allocation__isnull=True,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
        )
        self.assertTrue(action.is_resolved)

        dashboard_response = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)
        latest = dashboard_response.context["indicadores_diarios"][-1]
        self.assertEqual(latest["reconectados"], 1)
        cards = dashboard_response.context["exception_cards"]
        reconnected_card = next(
            card for card in cards if card["title"] == "Reconectados hoje"
        )
        self.assertEqual(reconnected_card["value"], 1)

    def test_dashboard_reconnected_exception_card_ignores_old_action_resolved_today(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        DailyUserAction.objects.create(
            day=yesterday,
            employee=self.employee_b2b,
            allocation=self.line_allocation,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )

        response = self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": self.employee_b2b.id,
                "allocation_id": str(self.line_allocation.id),
                "action_type": "",
                "note": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        dashboard_response = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)
        cards = dashboard_response.context["exception_cards"]
        reconnected_card = next(
            card for card in cards if card["title"] == "Reconectados hoje"
        )
        self.assertEqual(reconnected_card["value"], 0)

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
        self.assertContains(response, "Usuários logados")
        self.assertContains(response, "Usuários com linha")
        self.assertContains(response, "Usuários sem linha")

    def test_daily_indicator_day_breakdown_shows_admin_resolved_reconnect_number(self):
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            allocation=self.line_allocation,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )

        response = self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": self.employee_b2b.id,
                "allocation_id": str(self.line_allocation.id),
                "action_type": "",
                "note": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        today_iso = timezone.localdate().strftime("%Y-%m-%d")
        breakdown_response = self.client.get(
            reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso})
        )

        self.assertEqual(breakdown_response.status_code, 200)
        indicator = breakdown_response.context["indicator"]
        self.assertEqual(indicator["reconectados"], 1)
        self.assertEqual(len(indicator["reconnected_numbers"]), 1)
        self.assertEqual(
            indicator["reconnected_numbers"][0]["numero"],
            self.line_allocated.phone_number,
        )
        self.assertContains(breakdown_response, self.line_allocated.phone_number)

    def test_daily_indicator_history_preserves_numbers_after_later_simcard_delete(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        created_at = timezone.make_aware(datetime.combine(yesterday, time(8, 0)))
        allocated_at = timezone.make_aware(datetime.combine(yesterday, time(10, 0)))

        sim = SIMcard.objects.create(
            iccid="8900000000000001999",
            carrier="CarrierHistory",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number="+5511999999333",
            sim_card=sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        PhoneLine.all_objects.filter(pk=line.pk).update(
            created_at=created_at,
            updated_at=created_at,
        )

        allocation = LineAllocation.objects.create(
            employee=self.employee_b2b,
            phone_line=line,
            allocated_by=self.user,
            is_active=True,
        )
        LineAllocation.objects.filter(pk=allocation.pk).update(allocated_at=allocated_at)

        SIMcard.objects.filter(pk=sim.pk).delete()

        self.assertEqual(DailyIndicatorService.calculate_delivered_numbers(yesterday), 1)
        self.assertEqual(DailyIndicatorService.calculate_new_numbers(yesterday), 1)

        response = self.client.get(
            reverse(
                "daily_indicator_day_breakdown",
                kwargs={"day": yesterday.strftime("%Y-%m-%d")},
            )
        )

        self.assertEqual(response.status_code, 200)
        indicator = response.context["indicator"]
        self.assertEqual(indicator["numeros_entregues"], 1)
        self.assertEqual(indicator["novos"], 1)
        self.assertEqual(indicator["delivered_numbers"][0]["numero"], line.phone_number)
        self.assertIn(line.phone_number, indicator["new_numbers"])

    def test_daily_indicator_day_breakdown_hides_line_with_soft_deleted_simcard(self):
        self.line_available.sim_card.delete()

        today_iso = timezone.localdate().strftime("%Y-%m-%d")
        response = self.client.get(
            reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso})
        )

        self.assertEqual(response.status_code, 200)
        indicator = response.context["indicator"]
        self.assertEqual(indicator["numeros_disponiveis"], 0)
        self.assertEqual(indicator["total_descoberto_dia"], 1)
        self.assertEqual(len(indicator["available_numbers"]), 0)
        self.assertEqual(len(indicator["users_with_line"]), 1)
        self.assertEqual(len(indicator["users_without_line"]), 1)
        self.assertNotContains(response, self.line_available.phone_number)

    def test_daily_indicator_history_preserves_employee_deleted_after_day(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        created_at = timezone.make_aware(datetime.combine(yesterday, time(8, 0)))

        employee = Employee.objects.create(
            full_name="Deleted B2C User",
            corporate_email="deleted@corp.com",
            employee_id="Natura",
            teams="B2C Squad",
            status=Employee.Status.ACTIVE,
        )
        Employee.all_objects.filter(pk=employee.pk).update(
            created_at=created_at,
            updated_at=created_at,
        )

        employee.delete()

        response = self.client.get(
            reverse(
                "daily_indicator_day_breakdown",
                kwargs={"day": yesterday.strftime("%Y-%m-%d")},
            )
        )

        self.assertEqual(response.status_code, 200)
        indicator = response.context["indicator"]
        self.assertEqual(indicator["pessoas_logadas"], 1)
        self.assertEqual(indicator["b2c_sem_whats"], 1)
        self.assertEqual(indicator["total_descoberto_dia"], 1)
        self.assertEqual(len(indicator["users_without_line"]), 1)
        self.assertContains(response, "Deleted B2C User")

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

    def test_daily_user_action_board_shows_unresolved_action_from_previous_day(self):
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

        # Ao acessar o dia atual, a ação de ontem ainda deve aparecer
        response = self.client.get(
            reverse("daily_user_action_board"),
            {"day": today.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        # A ação não-resolvida de ontem deve aparecer no dia atual
        self.assertEqual(response.context["action_counts"]["new_number"], 1)
        self.assertEqual(response.context["action_counts"]["reconnect_whatsapp"], 0)

    def test_daily_user_action_board_shows_all_pending_actions(self):
        today = timezone.localdate()
        tomorrow = today + timezone.timedelta(days=1)

        DailyUserAction.objects.create(
            day=tomorrow,
            employee=self.employee_b2c,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
        )

        # "Ações do dia" agora mostra TODAS as ações não-resolvidas,
        # inclusive as de amanhã (não há calendário)
        response = self.client.get(
            reverse("daily_user_action_board"),
        )

        self.assertEqual(response.status_code, 200)
        # Ações futuras DEVEM aparecer agora
        self.assertEqual(response.context["action_counts"]["new_number"], 1)
        self.assertEqual(response.context["action_counts"]["reconnect_whatsapp"], 0)

    def test_daily_user_action_board_keeps_action_visible_when_simcard_line_is_hidden(self):
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            allocation=self.line_allocation,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )
        self.line_allocated.sim_card.delete()

        response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["action_counts"]["new_number"], 1)
        rows = response.context["rows"]
        matching_rows = [
            row for row in rows if row["employee"].id == self.employee_b2b.id
        ]
        self.assertEqual(len(matching_rows), 1)
        self.assertIsNone(matching_rows[0]["allocation"])
        self.assertEqual(
            matching_rows[0]["action"].action_type,
            DailyUserAction.ActionType.NEW_NUMBER,
        )

    def test_daily_user_action_board_logs_line_status_change_in_history(self):
        response = self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": self.employee_b2b.id,
                "allocation_id": str(self.line_allocation.id),
                "line_status": LineAllocation.LineStatus.RESTRICTED,
                "action_type": "",
                "note": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        history = PhoneLineHistory.objects.filter(
            phone_line=self.line_allocated,
            action=PhoneLineHistory.ActionType.STATUS_CHANGED,
        ).first()
        self.assertIsNotNone(history)
        self.assertIn("Status da linha", history.old_value or "")
        self.assertIn("Status da linha", history.new_value or "")

    def test_daily_user_action_board_updates_employee_line_status_without_allocation(
        self,
    ):
        response = self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": self.employee_b2c.id,
                "allocation_id": "",
                "line_status": Employee.LineStatus.RESTRICTED,
                "action_type": "",
                "note": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.employee_b2c.refresh_from_db()
        self.assertEqual(self.employee_b2c.line_status, Employee.LineStatus.RESTRICTED)

    def test_daily_user_action_board_logs_daily_action_change_in_history(self):
        response = self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": self.employee_b2b.id,
                "allocation_id": str(self.line_allocation.id),
                "line_status": self.line_allocation.line_status,
                "action_type": DailyUserAction.ActionType.NEW_NUMBER,
                "note": "Sem acesso ao Whats",
            },
        )

        self.assertEqual(response.status_code, 302)

        history = PhoneLineHistory.objects.filter(
            phone_line=self.line_allocated,
            action=PhoneLineHistory.ActionType.DAILY_ACTION_CHANGED,
        ).first()
        self.assertIsNotNone(history)
        self.assertIn("Atualizar acao", history.new_value or "")

    def test_admin_does_not_see_active_line_without_action(self):
        admin_user = SystemUser.objects.create_user(
            email="admin.test@test.com",
            password="AdminPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(admin_user)

        DailyUserAction.objects.filter(
            employee=self.employee_b2b, allocation=self.line_allocation
        ).update(is_resolved=True)

        response = self.client.get(
            reverse("daily_user_action_board"),
            {"day": timezone.localdate().isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]

        b2b_rows = [
            row
            for row in rows
            if row["employee"].id == self.employee_b2b.id
            and row["allocation"].id == self.line_allocation.id
        ]
        self.assertEqual(
            len(b2b_rows), 0, "Admin should not see Active line without action"
        )

    def test_admin_sees_active_line_with_action(self):
        admin_user = SystemUser.objects.create_user(
            email="admin.test2@test.com",
            password="AdminPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(admin_user)

        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            allocation=self.line_allocation,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=admin_user,
            created_by=admin_user,
            updated_by=admin_user,
            is_resolved=False,
        )

        response = self.client.get(
            reverse("daily_user_action_board"),
            {"day": timezone.localdate().isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]

        b2b_rows = [
            row
            for row in rows
            if row["employee"].id == self.employee_b2b.id
            and row["allocation"].id == self.line_allocation.id
        ]
        self.assertGreater(len(b2b_rows), 0, "Admin should see Active line with action")

    def test_admin_hides_employee_without_line_when_status_is_active_and_no_action(
        self,
    ):
        admin_user = SystemUser.objects.create_user(
            email="admin.test3@test.com",
            password="AdminPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]

        b2c_rows = [row for row in rows if row["employee"].id == self.employee_b2c.id]
        self.assertEqual(
            len(b2c_rows),
            0,
            (
                "Admin should not see employee without line when status is "
                "Active and no action"
            ),
        )

    def test_admin_sees_employee_without_line_when_status_is_not_active(self):
        admin_user = SystemUser.objects.create_user(
            email="admin.test4@test.com",
            password="AdminPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(admin_user)
        self.employee_b2c.line_status = Employee.LineStatus.RESTRICTED
        self.employee_b2c.save(update_fields=["line_status"])

        response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]

        b2c_rows = [row for row in rows if row["employee"].id == self.employee_b2c.id]
        self.assertEqual(len(b2c_rows), 1)
        self.assertFalse(b2c_rows[0]["has_line"])
        self.assertIsNone(b2c_rows[0]["action"])

    def test_pending_badge_ignores_action_with_mismatched_allocation_employee(self):
        other_employee = Employee.objects.create(
            full_name="Other User",
            corporate_email="other@corp.com",
            employee_id="Outras",
            teams="B2B Squad",
            status=Employee.Status.ACTIVE,
        )
        other_sim = SIMcard.objects.create(
            iccid="8900000000000002001", carrier="CarrierX"
        )
        other_line = PhoneLine.objects.create(
            phone_number="+5511999999010",
            sim_card=other_sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        other_allocation = LineAllocation.objects.create(
            employee=other_employee,
            phone_line=other_line,
            allocated_by=self.user,
            is_active=True,
        )

        # Estado inconsistente possível após remanejamento de linha:
        # ação ainda aponta para alocação que não pertence ao employee da ação.
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            allocation=other_allocation,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pending_actions_count"], 0)

    def test_pending_badge_deduplicates_multiple_days_same_action_key(self):
        today = timezone.localdate()
        yesterday = today - timezone.timedelta(days=1)

        DailyUserAction.objects.create(
            day=yesterday,
            employee=self.employee_b2b,
            allocation=self.line_allocation,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )
        DailyUserAction.objects.create(
            day=today,
            employee=self.employee_b2b,
            allocation=self.line_allocation,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pending_actions_count"], 1)

    def test_pending_badge_ignores_no_allocation_action_when_employee_has_line(self):
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            allocation=None,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )

        board_response = self.client.get(reverse("daily_user_action_board"))
        self.assertEqual(board_response.status_code, 200)
        self.assertEqual(board_response.context["action_counts"]["new_number"], 0)

        dashboard_response = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(dashboard_response.context["pending_actions_count"], 0)

    def test_reconnect_whatsapp_without_allocation_counts_for_employee_with_single_line_v2(
        self,
    ):
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            allocation=None,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )

        board_response = self.client.get(reverse("daily_user_action_board"))
        self.assertEqual(board_response.status_code, 200)
        self.assertEqual(board_response.context["action_counts"]["new_number"], 0)
        self.assertEqual(
            board_response.context["action_counts"]["reconnect_whatsapp"], 1
        )

        dashboard_response = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(dashboard_response.context["pending_actions_count"], 1)

        cards = dashboard_response.context["exception_cards"]
        pending_reconnect = next(
            card
            for card in cards
            if "Reconex" in card["title"]
            and card["action_url"] == reverse("daily_user_action_board")
        )
        self.assertEqual(pending_reconnect["value"], 1)

    def test_admin_keeps_employee_visible_when_allocation_removed_with_pending_action(
        self,
    ):
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            allocation=self.line_allocation,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )

        self.line_allocation.is_active = False
        self.line_allocation.released_at = timezone.now() + timedelta(seconds=1)
        self.line_allocation.released_by = self.user
        self.line_allocation.save(
            update_fields=["is_active", "released_at", "released_by"]
        )

        response = self.client.get(reverse("daily_user_action_board"))
        self.assertEqual(response.status_code, 200)

        rows = response.context["rows"]
        b2b_rows = [row for row in rows if row["employee"].id == self.employee_b2b.id]

        self.assertEqual(len(b2b_rows), 1)
        self.assertFalse(b2b_rows[0]["has_line"])
        self.assertIsNotNone(b2b_rows[0]["action"])
        self.assertEqual(
            b2b_rows[0]["action"].action_type,
            DailyUserAction.ActionType.RECONNECT_WHATSAPP,
        )

    def test_dashboard_counts_pending_new_number_from_allocation_flow(self):
        employee = Employee.objects.create(
            full_name="Flow User",
            corporate_email="flow@corp.com",
            employee_id="Unilever",
            teams="B2C Squad",
            status=Employee.Status.ACTIVE,
        )
        sim = SIMcard.objects.create(iccid="8900000000000001666", carrier="CarrierX")
        line = PhoneLine.objects.create(
            phone_number="+5511999999666",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )

        with self.captureOnCommitCallbacks(execute=True):
            allocation = AllocationService.allocate_line(
                employee=employee,
                phone_line=line,
                allocated_by=self.user,
            )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pending_actions_count"], 1)

        cards = response.context["exception_cards"]
        pending_new_number = next(
            card
            for card in cards
            if card["action_url"] == reverse("daily_user_action_board")
            and "novo" in card["description"].lower()
        )
        self.assertEqual(pending_new_number["value"], 1)

        action = DailyUserAction.objects.get(
            employee=employee,
            allocation=allocation,
            is_resolved=False,
        )
        self.assertEqual(action.action_type, DailyUserAction.ActionType.NEW_NUMBER)


class DashboardMeowOperationalSummaryTests(TestCase):
    def setUp(self):
        self.admin_user = SystemUser.objects.create_user(
            email="dashboard-meow-admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.manager_user = SystemUser.objects.create_user(
            email="dashboard-meow-manager@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )

        self.healthy_meow = MeowInstance.objects.create(
            name="Healthy Meow",
            base_url="http://healthy-meow.local",
            health_status=MeowInstanceHealthStatus.HEALTHY,
        )
        self.degraded_meow = MeowInstance.objects.create(
            name="Degraded Meow",
            base_url="http://degraded-meow.local",
            health_status=MeowInstanceHealthStatus.DEGRADED,
        )
        self.unavailable_meow = MeowInstance.objects.create(
            name="Unavailable Meow",
            base_url="http://unavailable-meow.local",
            health_status=MeowInstanceHealthStatus.UNAVAILABLE,
        )

        self._create_session(
            "+5511999993101",
            self.healthy_meow,
            WhatsAppSessionStatus.CONNECTED,
        )
        self._create_session(
            "+5511999993102",
            self.degraded_meow,
            WhatsAppSessionStatus.ERROR,
        )
        self._create_session(
            "+5511999993103",
            self.unavailable_meow,
            WhatsAppSessionStatus.PENDING_RECONNECT,
        )

    def _create_session(self, phone_number, meow_instance, status):
        sim = SIMcard.objects.create(
            iccid=f"8900000000000{phone_number[-6:]}",
            carrier="CarrierX",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number=phone_number,
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        return WhatsAppSession.objects.create(
            line=line,
            meow_instance=meow_instance,
            session_id=f"session_{phone_number}",
            status=status,
        )

    def test_dashboard_exposes_meow_operational_summary_for_admin(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        summary = response.context["meow_operational_summary"]
        self.assertEqual(summary["total_instances"], 3)
        self.assertEqual(summary["healthy_instances"], 1)
        self.assertEqual(summary["degraded_instances"], 1)
        self.assertEqual(summary["unavailable_instances"], 1)
        self.assertEqual(summary["connected_sessions"], 1)
        self.assertEqual(summary["pending_sessions"], 1)
        self.assertEqual(summary["degraded_sessions"], 1)
        self.assertContains(response, "Operacao Meow")
        self.assertContains(response, "Instancias saudaveis")
        self.assertContains(response, "Sessoes degradadas")

    def test_dashboard_hides_meow_operational_summary_for_manager(self):
        self.client.force_login(self.manager_user)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context.get("meow_operational_summary"))
        self.assertNotContains(response, "Operacao Meow")


class ManagerScopeTests(TestCase):
    def setUp(self):
        self.manager = SystemUser.objects.create_user(
            email="gerente.scope@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        self.supervisor = SystemUser.objects.create_user(
            email="super.scope@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
            manager_email="gerente.scope@test.com",
        )
        self.other_supervisor = SystemUser.objects.create_user(
            email="super.outro@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.client.force_login(self.manager)

        self.managed_employee = Employee.objects.create(
            full_name="Usuario Vinculado",
            corporate_email=self.supervisor.email,
            employee_id="Ambiental",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.unmanaged_employee = Employee.objects.create(
            full_name="Usuario Nao Vinculado",
            corporate_email=self.other_supervisor.email,
            manager_email="outro.gerente@test.com",
            employee_id="Natura",
            teams="Araquari",
            status=Employee.Status.ACTIVE,
        )

    def test_manager_dashboard_groups_pending_actions_by_supervisor_and_portfolio(self):
        sim = SIMcard.objects.create(
            iccid="8900000000000003001",
            carrier="CarrierZ",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number="+5511999993001",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        LineAllocation.objects.create(
            employee=self.managed_employee,
            phone_line=line,
            allocated_by=self.supervisor,
            is_active=True,
        )
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.managed_employee,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            supervisor=self.supervisor,
            created_by=self.supervisor,
            updated_by=self.supervisor,
            is_resolved=False,
        )
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.managed_employee,
            allocation=None,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=self.supervisor,
            created_by=self.supervisor,
            updated_by=self.supervisor,
            is_resolved=False,
        )
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.unmanaged_employee,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=self.other_supervisor,
            created_by=self.other_supervisor,
            updated_by=self.other_supervisor,
            is_resolved=False,
        )

        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Supervisor super.scope@test.com")
        self.assertContains(response, "Ambiental")
        self.assertContains(response, "Operador logado")
        self.assertContains(response, "Operador com linha")
        self.assertContains(response, "Operador sem linha")
        self.assertNotContains(response, "Supervisor super.outro@test.com")
        self.assertNotContains(response, "Usuario Nao Vinculado")

    def test_manager_dashboard_shows_operator_counts_by_portfolio(self):
        Employee.objects.create(
            full_name="Usuario Vinculado 2",
            corporate_email=self.supervisor.email,
            employee_id="Ambiental",
            teams="Joinville",
            status=Employee.Status.INACTIVE,
        )
        sim = SIMcard.objects.create(
            iccid="8900000000000003002",
            carrier="CarrierZ",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number="+5511999993002",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        LineAllocation.objects.create(
            employee=self.managed_employee,
            phone_line=line,
            allocated_by=self.supervisor,
            is_active=True,
        )

        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ambiental")
        row = next(
            item
            for item in response.context["supervisor_dashboards"][0]["rows"]
            if item["portfolio"] == "Ambiental"
        )
        self.assertEqual(row["logged_count"], 1)
        self.assertEqual(row["with_line_count"], 1)
        self.assertEqual(row["without_line_count"], 0)

    def test_manager_dashboard_ignores_inactive_user_in_all_metrics(self):
        self.managed_employee.status = Employee.Status.INACTIVE
        self.managed_employee.save(update_fields=["status"])
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.managed_employee,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=self.supervisor,
            created_by=self.supervisor,
            updated_by=self.supervisor,
            is_resolved=False,
        )

        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        row = next(
            item
            for item in response.context["supervisor_dashboards"][0]["rows"]
            if item["portfolio"] == "Ambiental"
        )
        self.assertEqual(row["logged_count"], 0)
        self.assertEqual(row["with_line_count"], 0)
        self.assertEqual(row["without_line_count"], 0)
        self.assertEqual(row["reconnect_count"], 0)
        self.assertEqual(row["new_number_count"], 0)

    def test_manager_dashboard_shows_supervisor_even_without_employees(self):
        Employee.objects.filter(pk=self.managed_employee.pk).delete()

        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Supervisor super.scope@test.com")
        self.assertContains(
            response,
            "Nenhuma carteira vinculada para este supervisor.",
        )

    def test_manager_dashboard_lists_inactive_employee_portfolios(self):
        self.managed_employee.status = Employee.Status.INACTIVE
        self.managed_employee.save(update_fields=["status"])

        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Supervisor super.scope@test.com")
        self.assertContains(response, "Ambiental")

    def test_manager_action_board_only_shows_employees_from_managed_supervisors(self):
        response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Usuario Vinculado")
        self.assertNotContains(response, "Usuario Nao Vinculado")

    def test_manager_dashboard_counts_reconnect_from_allocation_flow(self):
        previous_employee = Employee.objects.create(
            full_name="Usuario Transferido",
            corporate_email=self.supervisor.email,
            employee_id="Ambiental",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        sim = SIMcard.objects.create(
            iccid="8900000000000003003",
            carrier="CarrierZ",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number="+5511999993003",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )

        with self.captureOnCommitCallbacks(execute=True):
            old_allocation = AllocationService.allocate_line(
                employee=previous_employee,
                phone_line=line,
                allocated_by=self.supervisor,
            )

        with self.captureOnCommitCallbacks(execute=True):
            AllocationService.release_line(
                allocation=old_allocation,
                released_by=self.supervisor,
            )

        with self.captureOnCommitCallbacks(execute=True):
            new_allocation = AllocationService.allocate_line(
                employee=self.managed_employee,
                phone_line=line,
                allocated_by=self.supervisor,
            )

        response = self.client.get(reverse("manager_dashboard"))
        self.assertEqual(response.status_code, 200)

        row = next(
            item
            for item in response.context["supervisor_dashboards"][0]["rows"]
            if item["portfolio"] == "Ambiental"
        )
        self.assertEqual(row["reconnect_count"], 1)

        action = DailyUserAction.objects.get(
            employee=self.managed_employee,
            allocation=new_allocation,
            is_resolved=False,
        )
        self.assertEqual(
            action.action_type,
            DailyUserAction.ActionType.RECONNECT_WHATSAPP,
        )

    def test_dashboard_whatsapp_pending_summary_respects_manager_scope(self):
        managed_sim = SIMcard.objects.create(
            iccid="8900000000000003010",
            carrier="CarrierZ",
            status=SIMcard.Status.AVAILABLE,
        )
        managed_line = PhoneLine.objects.create(
            phone_number="+5511999993010",
            sim_card=managed_sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        unmanaged_sim = SIMcard.objects.create(
            iccid="8900000000000003011",
            carrier="CarrierZ",
            status=SIMcard.Status.AVAILABLE,
        )
        unmanaged_line = PhoneLine.objects.create(
            phone_number="+5511999993011",
            sim_card=unmanaged_sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        managed_allocation = LineAllocation.objects.create(
            employee=self.managed_employee,
            phone_line=managed_line,
            allocated_by=self.supervisor,
            is_active=True,
        )
        unmanaged_allocation = LineAllocation.objects.create(
            employee=self.unmanaged_employee,
            phone_line=unmanaged_line,
            allocated_by=self.other_supervisor,
            is_active=True,
        )
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.managed_employee,
            allocation=managed_allocation,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            supervisor=self.supervisor,
            created_by=self.supervisor,
            updated_by=self.supervisor,
            note="Pendencia do escopo",
            is_resolved=False,
        )
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.unmanaged_employee,
            allocation=unmanaged_allocation,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            supervisor=self.other_supervisor,
            created_by=self.other_supervisor,
            updated_by=self.other_supervisor,
            note="Nao deveria aparecer",
            is_resolved=False,
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        summary = response.context["whatsapp_pending_summary"]
        self.assertEqual(summary["total"], 1)
        self.assertContains(response, "Fila WhatsApp")
        self.assertContains(response, "Usuario Vinculado")
        self.assertContains(response, "Pendencia do escopo")
        self.assertNotContains(response, "Usuario Nao Vinculado")
        self.assertNotContains(response, "Nao deveria aparecer")
