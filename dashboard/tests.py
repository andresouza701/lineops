import re
from datetime import datetime, time, timedelta

from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from core.services.daily_indicator_service import DailyIndicatorService
from employees.models import Employee, EmployeeHistory
from telecom.models import PhoneLine, PhoneLineHistory, SIMcard
from users.models import SystemUser

from . import views as dashboard_views
from .forms import DailyIndicatorForm
from .models import DashboardDailySnapshot, DailyUserAction


class DashboardDailyIndicatorsTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
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

    def _create_supervisor_scoped_pending_action_dataset(self):
        supervisor = SystemUser.objects.create_user(
            email="supervisor.pending@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        employee = Employee.objects.create(
            full_name="Scoped Pending User",
            corporate_email=supervisor.email,
            employee_id="Carteira X",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        sim_card = SIMcard.objects.create(
            iccid="8900000000000001999",
            carrier="CarrierScoped",
            status=SIMcard.Status.AVAILABLE,
        )
        phone_line = PhoneLine.objects.create(
            phone_number="+5511999991999",
            sim_card=sim_card,
            status=PhoneLine.Status.ALLOCATED,
        )
        allocation = LineAllocation.objects.create(
            employee=employee,
            phone_line=phone_line,
            allocated_by=self.user,
            is_active=True,
        )
        action = DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=employee,
            allocation=allocation,
            supervisor=supervisor,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            note="Aguardando triagem",
            created_by=supervisor,
            updated_by=supervisor,
            is_resolved=False,
        )
        return {
            "supervisor": supervisor,
            "employee": employee,
            "allocation": allocation,
            "action": action,
        }

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

    def test_daily_indicator_form_sorts_supervisor_and_portfolio_choices(self):
        form_b2c = DailyIndicatorForm(initial={"segment": "B2C"})

        self.assertEqual(
            [label for _value, label in form_b2c.fields["supervisor"].choices],
            ["Selecione", "Alex", "Camila", "Leonardo"],
        )
        self.assertEqual(
            [label for _value, label in form_b2c.fields["portfolio"].choices],
            ["Selecione", "Ambiental", "Natura", "Opera", "Valid", "ViaSat"],
        )

    def test_daily_indicator_entry_view_context_sorts_json_choice_lists(self):
        request = self.factory.get(reverse("daily_indicator_entry"))
        request.user = self.user

        response = dashboard_views.daily_indicator_entry(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertLess(
            content.index('"Alex"'),
            content.index('"Camila"'),
        )
        self.assertLess(
            content.index('"Camila"'),
            content.index('"Leonardo"'),
        )
        self.assertLess(
            content.index('"Ambiental"'),
            content.index('"Natura"'),
        )
        self.assertLess(
            content.index('"Opera"'),
            content.index('"Valid"'),
        )
        self.assertLess(
            content.index('"Valid"'),
            content.index('"ViaSat"'),
        )

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

    def test_dashboard_historical_rows_refresh_legacy_snapshot_version(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        created_at = timezone.make_aware(datetime.combine(yesterday, time(8, 0)))

        employee = Employee.objects.create(
            full_name="Legacy Snapshot User",
            corporate_email="legacy-snapshot@corp.com",
            employee_id="Natura",
            teams="B2C Squad",
            status=Employee.Status.ACTIVE,
        )
        Employee.all_objects.filter(pk=employee.pk).update(
            created_at=created_at,
            updated_at=created_at,
        )

        sim = SIMcard.objects.create(
            iccid="8900000000000004556",
            carrier="CarrierLegacy",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number="+5511999994556",
            sim_card=sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        PhoneLine.all_objects.filter(pk=line.pk).update(
            created_at=created_at,
            updated_at=created_at,
        )

        first_alloc = LineAllocation.objects.create(
            employee=employee,
            phone_line=line,
            allocated_by=self.user,
            is_active=True,
        )
        LineAllocation.objects.filter(pk=first_alloc.pk).update(
            allocated_at=timezone.make_aware(datetime.combine(yesterday, time(9, 0))),
            released_at=timezone.make_aware(datetime.combine(yesterday, time(10, 0))),
            is_active=False,
        )

        second_alloc = LineAllocation.objects.create(
            employee=employee,
            phone_line=line,
            allocated_by=self.user,
            is_active=True,
        )
        LineAllocation.objects.filter(pk=second_alloc.pk).update(
            allocated_at=timezone.make_aware(datetime.combine(yesterday, time(11, 0))),
        )

        DashboardDailySnapshot.objects.create(
            date=yesterday,
            people_logged_in=0,
            percentage_without_whatsapp=0,
            b2b_without_whatsapp=0,
            b2c_without_whatsapp=0,
            numbers_available=0,
            numbers_delivered=0,
            numbers_reconnected=0,
            numbers_new=0,
            total_uncovered_day=0,
            calculation_version=1,
        )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        refreshed_snapshot = DashboardDailySnapshot.objects.get(date=yesterday)
        self.assertEqual(
            refreshed_snapshot.calculation_version,
            dashboard_views.CURRENT_DASHBOARD_SNAPSHOT_VERSION,
        )
        self.assertEqual(refreshed_snapshot.numbers_reconnected, 1)

        historical_row = next(
            item
            for item in response.context["indicadores_diarios"]
            if item["data"] == yesterday
        )
        self.assertEqual(historical_row["reconectados"], 1)

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

    def test_daily_user_action_board_shows_pending_as_action_option(self):
        response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pendência")
        self.assertContains(response, 'value="pending"', html=False)

    def test_daily_user_action_board_allows_marking_pending_action(self):
        response = self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": self.employee_b2c.id,
                "action_type": DailyUserAction.ActionType.PENDING,
                "note": "Aguardando validacao",
            },
        )
        self.assertEqual(response.status_code, 302)

        action = DailyUserAction.objects.get(
            day=timezone.localdate(),
            employee=self.employee_b2c,
        )
        self.assertEqual(action.action_type, DailyUserAction.ActionType.PENDING)
        self.assertEqual(action.note, "Aguardando validacao")

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

    def test_daily_user_action_board_filters_rows_by_user_name(self):
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
        self.employee_b2c.line_status = Employee.LineStatus.RESTRICTED
        self.employee_b2c.save(update_fields=["line_status"])

        response = self.client.get(
            reverse("daily_user_action_board"),
            {"user": "B2B"},
        )

        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["employee"].id, self.employee_b2b.id)
        self.assertContains(response, "B2B User")
        self.assertNotContains(response, "B2C User")

    def test_daily_user_action_board_filters_rows_by_line_number(self):
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
        second_sim = SIMcard.objects.create(
            iccid="8900000000000001003",
            carrier="CarrierX",
        )
        second_line = PhoneLine.objects.create(
            phone_number="+5511999999011",
            sim_card=second_sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        second_allocation = LineAllocation.objects.create(
            employee=self.employee_b2b,
            phone_line=second_line,
            allocated_by=self.user,
            is_active=True,
        )
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            allocation=second_allocation,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            supervisor=self.user,
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )

        response = self.client.get(
            reverse("daily_user_action_board"),
            {"line": "9001"},
        )

        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["allocation"].id, self.line_allocation.id)
        self.assertContains(response, "+5511999999001")
        self.assertNotContains(response, "+5511999999011")

    def test_daily_user_action_board_preserves_filters_after_post(self):
        response = self.client.post(
            f"{reverse('daily_user_action_board')}?user=B2B&line=9001",
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": self.employee_b2b.id,
                "allocation_id": str(self.line_allocation.id),
                "action_type": DailyUserAction.ActionType.NEW_NUMBER,
                "note": "Precisa manter o filtro",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("user=B2B", response.url)
        self.assertIn("line=9001", response.url)

    def test_daily_user_action_board_renders_line_detail_modal_trigger(self):
        self.line_allocated.origem = PhoneLine.Origem.SRVMEMU_01
        self.line_allocated.canal = PhoneLine.Canal.WEB
        self.line_allocated.save(update_fields=["origem", "canal"])
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

        response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="lineDetailModal"', html=False)
        self.assertContains(
            response,
            'data-bs-target="#lineDetailModal"',
            count=1,
            html=False,
        )
        self.assertContains(
            response,
            'data-line-number="+5511999999001"',
            html=False,
        )
        self.assertContains(
            response,
            'data-line-iccid="8900000000000001000"',
            html=False,
        )
        self.assertContains(
            response,
            'data-line-origin="SRVMEMU-01"',
            html=False,
        )
        self.assertContains(
            response,
            'data-line-channel="WEB"',
            html=False,
        )
        self.assertContains(
            response,
            'data-line-employee="B2B User"',
            html=False,
        )
        self.assertContains(
            response,
            'data-line-carrier="CarrierX"',
            html=False,
        )
        self.assertContains(
            response,
            'data-line-status="Ativo"',
            html=False,
        )
        self.assertContains(response, "Canal")
        self.assertContains(response, "Usuário")
        self.assertContains(response, "Status")

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

    def test_daily_user_action_board_shows_last_line_status_change_timestamp(self):
        self.client.post(
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

        history = PhoneLineHistory.objects.filter(
            phone_line=self.line_allocated,
            action=PhoneLineHistory.ActionType.STATUS_CHANGED,
        ).first()
        self.assertIsNotNone(history)

        response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Últ. alt. status")
        matching_row = next(
            row
            for row in response.context["rows"]
            if row["employee"].id == self.employee_b2b.id
            and row["allocation"].id == self.line_allocation.id
        )
        self.assertEqual(matching_row["line_status_changed_at"], history.changed_at)
        self.assertContains(
            response,
            timezone.localtime(history.changed_at).strftime("%d/%m/%Y %H:%M"),
        )

    def test_daily_user_action_board_renders_requested_column_order(self):
        response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        expected_headers = [
            "Criticidade",
            "PA",
            "Usuário",
            "Carteira",
            "Resp. Técnico",
            "Últ.alt.status",
            "Linha ativa",
            "Status da linha",
            "Ação",
            "Observação",
        ]

        header_positions = [content.index(f"<th>{header}</th>") for header in expected_headers]
        self.assertEqual(header_positions, sorted(header_positions))

    def test_daily_user_action_board_shows_admin_verifier_for_non_admin_roles(self):
        dataset = self._create_supervisor_scoped_pending_action_dataset()

        response = self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": dataset["employee"].id,
                "allocation_id": str(dataset["allocation"].id),
                "line_status": LineAllocation.LineStatus.RESTRICTED,
                "action_type": dataset["action"].action_type,
                "note": dataset["action"].note,
            },
        )

        self.assertEqual(response.status_code, 302)

        self.client.force_login(dataset["supervisor"])
        board_response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(board_response.status_code, 200)
        self.assertContains(board_response, "Resp. Técnico")
        self.assertContains(board_response, self.user.email)
        self.assertNotContains(board_response, dataset["supervisor"].email)

    def test_daily_user_action_board_allows_admin_filter_by_technical_responsible(self):
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=self.employee_b2b,
            allocation=self.line_allocation,
            supervisor=self.user,
            action_type=DailyUserAction.ActionType.NEW_NUMBER,
            note="Primeira triagem",
            created_by=self.user,
            updated_by=self.user,
            is_resolved=False,
        )
        self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": self.employee_b2b.id,
                "allocation_id": str(self.line_allocation.id),
                "line_status": LineAllocation.LineStatus.RESTRICTED,
                "action_type": DailyUserAction.ActionType.NEW_NUMBER,
                "note": "Primeira triagem",
            },
        )

        other_admin = SystemUser.objects.create_user(
            email="technical.admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        employee = Employee.objects.create(
            full_name="Second Pending User",
            corporate_email="second.pending@test.com",
            employee_id="Carteira Y",
            teams="Curitiba",
            status=Employee.Status.ACTIVE,
        )
        sim_card = SIMcard.objects.create(
            iccid="8900000000000001777",
            carrier="CarrierTwo",
            status=SIMcard.Status.AVAILABLE,
        )
        phone_line = PhoneLine.objects.create(
            phone_number="+5511999991777",
            sim_card=sim_card,
            status=PhoneLine.Status.ALLOCATED,
        )
        allocation = LineAllocation.objects.create(
            employee=employee,
            phone_line=phone_line,
            allocated_by=other_admin,
            is_active=True,
        )
        DailyUserAction.objects.create(
            day=timezone.localdate(),
            employee=employee,
            allocation=allocation,
            supervisor=other_admin,
            action_type=DailyUserAction.ActionType.RECONNECT_WHATSAPP,
            note="Segunda triagem",
            created_by=other_admin,
            updated_by=other_admin,
            is_resolved=False,
        )

        self.client.force_login(other_admin)
        self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": employee.id,
                "allocation_id": str(allocation.id),
                "line_status": LineAllocation.LineStatus.RESTRICTED,
                "action_type": DailyUserAction.ActionType.RECONNECT_WHATSAPP,
                "note": "Segunda triagem",
            },
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("daily_user_action_board"),
            {"technical": self.user.email},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="technical"', html=False)
        self.assertContains(response, self.employee_b2b.full_name)
        self.assertNotContains(response, employee.full_name)
        self.assertEqual(len(response.context["rows"]), 1)
        self.assertEqual(response.context["rows"][0]["employee"].id, self.employee_b2b.id)

    def test_daily_user_action_board_hides_admin_verifier_without_admin_history(self):
        dataset = self._create_supervisor_scoped_pending_action_dataset()

        self.client.force_login(dataset["supervisor"])
        response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resp. Técnico")
        self.assertNotContains(response, self.user.email)

    def test_daily_user_action_board_hides_technical_filter_for_non_admin_roles(self):
        dataset = self._create_supervisor_scoped_pending_action_dataset()

        self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": dataset["employee"].id,
                "allocation_id": str(dataset["allocation"].id),
                "line_status": LineAllocation.LineStatus.RESTRICTED,
                "action_type": dataset["action"].action_type,
                "note": dataset["action"].note,
            },
        )

        self.client.force_login(dataset["supervisor"])
        response = self.client.get(
            reverse("daily_user_action_board"),
            {"technical": self.user.email},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="technical"', html=False)
        self.assertContains(response, dataset["employee"].full_name)
        self.assertEqual(len(response.context["rows"]), 1)

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

        history = EmployeeHistory.objects.filter(
            employee=self.employee_b2c,
            action=EmployeeHistory.ActionType.STATUS_CHANGED,
        ).first()
        self.assertIsNotNone(history)

        board_response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(board_response.status_code, 200)
        matching_row = next(
            row
            for row in board_response.context["rows"]
            if row["employee"].id == self.employee_b2c.id
        )
        self.assertEqual(matching_row["line_status_changed_at"], history.changed_at)
        self.assertContains(
            board_response,
            timezone.localtime(history.changed_at).strftime("%d/%m/%Y %H:%M"),
        )

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

    def _create_scoped_dashboard_dataset(self):
        unmanaged_without_line = Employee.objects.create(
            full_name="Usuario Sem Escopo",
            corporate_email=self.other_supervisor.email,
            manager_email="outro.gerente@test.com",
            employee_id="Natura",
            teams="Araquari",
            status=Employee.Status.ACTIVE,
        )
        available_sim = SIMcard.objects.create(
            iccid="8900000000000003010",
            carrier="CarrierScope",
            status=SIMcard.Status.AVAILABLE,
        )
        available_line = PhoneLine.objects.create(
            phone_number="+5511999993010",
            sim_card=available_sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        managed_sim = SIMcard.objects.create(
            iccid="8900000000000003011",
            carrier="CarrierScope",
            status=SIMcard.Status.AVAILABLE,
        )
        managed_line = PhoneLine.objects.create(
            phone_number="+5511999993011",
            sim_card=managed_sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        managed_allocation = LineAllocation.objects.create(
            employee=self.managed_employee,
            phone_line=managed_line,
            allocated_by=self.supervisor,
            is_active=True,
        )
        unmanaged_sim = SIMcard.objects.create(
            iccid="8900000000000003012",
            carrier="CarrierScope",
            status=SIMcard.Status.AVAILABLE,
        )
        unmanaged_line = PhoneLine.objects.create(
            phone_number="+5511999993012",
            sim_card=unmanaged_sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        LineAllocation.objects.create(
            employee=self.unmanaged_employee,
            phone_line=unmanaged_line,
            allocated_by=self.other_supervisor,
            is_active=True,
        )
        return {
            "available_line": available_line,
            "managed_line": managed_line,
            "managed_allocation": managed_allocation,
            "unmanaged_line": unmanaged_line,
            "unmanaged_without_line": unmanaged_without_line,
        }

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

    def test_manager_action_board_renders_line_detail_trigger_for_visible_line(self):
        sim = SIMcard.objects.create(
            iccid="8900000000000003003",
            carrier="CarrierZ",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number="+5511999993003",
            sim_card=sim,
            status=PhoneLine.Status.ALLOCATED,
            origem=PhoneLine.Origem.APARELHO,
            canal=PhoneLine.Canal.MYLOOP,
        )
        LineAllocation.objects.create(
            employee=self.managed_employee,
            phone_line=line,
            allocated_by=self.supervisor,
            is_active=True,
        )

        response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'data-line-number="+5511999993003"',
            html=False,
        )
        self.assertContains(
            response,
            'data-line-iccid="8900000000000003003"',
            html=False,
        )
        self.assertContains(
            response,
            'data-line-origin="APARELHO"',
            html=False,
        )
        self.assertContains(
            response,
            'data-line-channel="MyLoop"',
            html=False,
        )
        self.assertContains(
            response,
            'data-line-employee="Usuario Vinculado"',
            html=False,
        )

    def test_manager_dashboard_main_scopes_employee_metrics_and_keeps_inventory_global(
        self,
    ):
        self._create_scoped_dashboard_dataset()

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        latest = response.context["indicadores_diarios"][-1]
        self.assertEqual(latest["pessoas_logadas"], 1)
        self.assertEqual(latest["perc_sem_whats"], 0)
        self.assertEqual(latest["total_descoberto_dia"], 0)
        self.assertEqual(latest["numeros_entregues"], 1)
        self.assertEqual(latest["numeros_disponiveis"], 1)
        self.assertEqual(latest["novos"], 3)

    def test_manager_live_dashboard_payload_scopes_employee_metrics(self):
        self._create_scoped_dashboard_dataset()

        response = self.client.get(reverse("daily_indicators_live"), {"period": 7})

        self.assertEqual(response.status_code, 200)
        latest = response.json()["rows"][-1]
        self.assertEqual(latest["pessoas_logadas"], 1)
        self.assertEqual(latest["total_descoberto_dia"], 0)
        self.assertEqual(latest["numeros_entregues"], 1)
        self.assertEqual(latest["numeros_disponiveis"], 1)

    def test_manager_day_breakdown_scopes_users_and_keeps_inventory_global(self):
        dataset = self._create_scoped_dashboard_dataset()
        today_iso = timezone.localdate().strftime("%Y-%m-%d")

        response = self.client.get(
            reverse("daily_indicator_day_breakdown", kwargs={"day": today_iso})
        )

        self.assertEqual(response.status_code, 200)
        indicator = response.context["indicator"]
        self.assertEqual(indicator["pessoas_logadas"], 1)
        self.assertEqual(indicator["numeros_entregues"], 1)
        self.assertEqual(indicator["numeros_disponiveis"], 1)
        self.assertEqual(len(indicator["users"]), 1)
        self.assertEqual(len(indicator["users_with_line"]), 1)
        self.assertEqual(len(indicator["users_without_line"]), 0)
        self.assertEqual(
            indicator["delivered_numbers"][0]["numero"],
            dataset["managed_line"].phone_number,
        )
        self.assertContains(response, "Usuario Vinculado")
        self.assertNotContains(response, "Usuario Nao Vinculado")
        self.assertNotContains(response, "Usuario Sem Escopo")
        self.assertContains(response, dataset["available_line"].phone_number)

    def test_supervisor_dashboard_main_scopes_employee_metrics_and_keeps_inventory_global(
        self,
    ):
        self._create_scoped_dashboard_dataset()
        self.client.force_login(self.supervisor)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        latest = response.context["indicadores_diarios"][-1]
        self.assertEqual(latest["pessoas_logadas"], 1)
        self.assertEqual(latest["total_descoberto_dia"], 0)
        self.assertEqual(latest["numeros_entregues"], 1)
        self.assertEqual(latest["numeros_disponiveis"], 1)


class BackofficeScopeTests(TestCase):
    def setUp(self):
        self.manager = SystemUser.objects.create_user(
            email="gerente.backoffice@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        self.supervisor = SystemUser.objects.create_user(
            email="super.backoffice@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
            manager_email="gerente.backoffice@test.com",
        )
        self.backoffice = SystemUser.objects.create_user(
            email="backoffice.scope@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email="super.backoffice@test.com",
        )
        self.other_supervisor = SystemUser.objects.create_user(
            email="super.outro.backoffice@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.managed_employee = Employee.objects.create(
            full_name="Negociador do Supervisor",
            corporate_email=self.supervisor.email,
            employee_id="Ambiental",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.unmanaged_employee = Employee.objects.create(
            full_name="Negociador de Outro Supervisor",
            corporate_email=self.other_supervisor.email,
            employee_id="Natura",
            teams="Araquari",
            status=Employee.Status.ACTIVE,
        )

    def _create_scoped_dashboard_dataset(self):
        unmanaged_without_line = Employee.objects.create(
            full_name="Usuario Sem Escopo",
            corporate_email=self.other_supervisor.email,
            employee_id="Natura",
            teams="Araquari",
            status=Employee.Status.ACTIVE,
        )
        available_sim = SIMcard.objects.create(
            iccid="8900000000000004010",
            carrier="CarrierBackoffice",
            status=SIMcard.Status.AVAILABLE,
        )
        available_line = PhoneLine.objects.create(
            phone_number="+5511999994010",
            sim_card=available_sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        managed_sim = SIMcard.objects.create(
            iccid="8900000000000004011",
            carrier="CarrierBackoffice",
            status=SIMcard.Status.AVAILABLE,
        )
        managed_line = PhoneLine.objects.create(
            phone_number="+5511999994011",
            sim_card=managed_sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        LineAllocation.objects.create(
            employee=self.managed_employee,
            phone_line=managed_line,
            allocated_by=self.supervisor,
            is_active=True,
        )
        unmanaged_sim = SIMcard.objects.create(
            iccid="8900000000000004012",
            carrier="CarrierBackoffice",
            status=SIMcard.Status.AVAILABLE,
        )
        unmanaged_line = PhoneLine.objects.create(
            phone_number="+5511999994012",
            sim_card=unmanaged_sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        LineAllocation.objects.create(
            employee=self.unmanaged_employee,
            phone_line=unmanaged_line,
            allocated_by=self.other_supervisor,
            is_active=True,
        )
        return {
            "available_line": available_line,
            "managed_line": managed_line,
            "unmanaged_line": unmanaged_line,
            "unmanaged_without_line": unmanaged_without_line,
        }

    def test_backoffice_action_board_only_shows_employees_from_linked_supervisor(self):
        self.client.force_login(self.backoffice)

        response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Negociador do Supervisor")
        self.assertNotContains(response, "Negociador de Outro Supervisor")

    def test_backoffice_action_is_saved_under_linked_supervisor_scope(self):
        self.client.force_login(self.backoffice)

        response = self.client.post(
            reverse("daily_user_action_board"),
            data={
                "day": timezone.localdate().isoformat(),
                "employee_id": self.managed_employee.id,
                "action_type": DailyUserAction.ActionType.NEW_NUMBER,
                "note": "Aguardando linha",
            },
        )

        self.assertEqual(response.status_code, 302)
        action = DailyUserAction.objects.get(
            day=timezone.localdate(),
            employee=self.managed_employee,
        )
        self.assertEqual(action.supervisor, self.supervisor)
        self.assertEqual(action.created_by, self.backoffice)
        self.assertEqual(action.updated_by, self.backoffice)

        self.client.force_login(self.manager)
        manager_response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(manager_response.status_code, 200)
        row = next(
            item
            for item in manager_response.context["supervisor_dashboards"][0]["rows"]
            if item["portfolio"] == "Ambiental"
        )
        self.assertEqual(row["new_number_count"], 1)

    def test_backoffice_dashboard_main_scopes_employee_metrics_like_supervisor(self):
        self._create_scoped_dashboard_dataset()
        self.client.force_login(self.backoffice)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        latest = response.context["indicadores_diarios"][-1]
        self.assertEqual(latest["pessoas_logadas"], 1)
        self.assertEqual(latest["total_descoberto_dia"], 0)
        self.assertEqual(latest["numeros_entregues"], 1)
        self.assertEqual(latest["numeros_disponiveis"], 1)
