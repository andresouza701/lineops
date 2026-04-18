from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from allocations.models import LineAllocation
from dashboard.services.query_service import get_pending_action_counts_for_user
from employees.models import Employee
from pendencies.models import AllocationPendency
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class DashboardPendingCardsConsistencyTest(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="dashboard.pending.admin@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.supervisor = SystemUser.objects.create_user(
            email="dashboard.pending.super@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.employee = Employee.objects.create(
            full_name="Pending Scoped User",
            corporate_email=self.supervisor.email,
            employee_id="Portfolio Pending",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )

    def _create_active_allocation(self, suffix: str):
        sim = SIMcard.objects.create(
            iccid=f"8900000000000092{suffix}",
            carrier="CarrierPending",
            status=SIMcard.Status.AVAILABLE,
        )
        line = PhoneLine.objects.create(
            phone_number=f"+5511999982{suffix}",
            sim_card=sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        return LineAllocation.objects.create(
            employee=self.employee,
            phone_line=line,
            allocated_by=self.admin,
            is_active=True,
        )

    @staticmethod
    def _exception_card_value(response, title):
        card = next(c for c in response.context["exception_cards"] if c["title"] == title)
        return card["value"]

    def test_dashboard_pending_cards_match_daily_action_board_counts(self):
        allocation = self._create_active_allocation("101")
        AllocationPendency.objects.create(
            employee=self.employee,
            allocation=allocation,
            action=AllocationPendency.ActionType.NEW_NUMBER,
        )
        # Pendência legada sem allocation não deve ser contabilizada enquanto há linha ativa.
        AllocationPendency.objects.create(
            employee=self.employee,
            allocation=None,
            action=AllocationPendency.ActionType.RECONNECT_WHATSAPP,
        )

        self.client.force_login(self.admin)
        dashboard_response = self.client.get(reverse("dashboard"))
        board_response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(board_response.status_code, 200)

        self.assertEqual(
            self._exception_card_value(
                dashboard_response, "Pendencia - Numero Novo"
            ),
            board_response.context["action_counts"]["new_number"],
        )
        self.assertEqual(
            self._exception_card_value(
                dashboard_response, "Pendencia - Reconexao Whats"
            ),
            board_response.context["action_counts"]["reconnect_whatsapp"],
        )
        self.assertEqual(board_response.context["action_counts"]["new_number"], 1)
        self.assertEqual(board_response.context["action_counts"]["reconnect_whatsapp"], 0)

    def test_sidebar_badge_includes_pending_action_type(self):
        """
        O badge da barra lateral deve refletir o valor do card Total,
        que soma new_number + reconnect_whatsapp + pending.
        Antes da correcao, o tipo 'pending' era ignorado pelo context_service.
        """
        allocation = self._create_active_allocation("103")
        AllocationPendency.objects.create(
            employee=self.employee,
            allocation=allocation,
            action=AllocationPendency.ActionType.PENDING,
        )

        self.client.force_login(self.admin)
        dashboard_response = self.client.get(reverse("dashboard"))
        board_response = self.client.get(reverse("daily_user_action_board"))

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(board_response.status_code, 200)

        board_total = board_response.context["action_counts"]["total"]
        badge_count = dashboard_response.context["pending_actions_count"]

        self.assertEqual(board_response.context["action_counts"]["pending"], 1)
        self.assertEqual(board_total, 1)
        self.assertEqual(
            badge_count,
            board_total,
            "O badge da sidebar deve ser igual ao card Total das acoes do dia",
        )

    def test_query_service_excludes_pendencies_from_inactive_allocations(self):
        allocation = self._create_active_allocation("102")
        allocation.is_active = False
        allocation.released_at = timezone.now()
        allocation.save(update_fields=["is_active", "released_at"])

        AllocationPendency.objects.create(
            employee=self.employee,
            allocation=allocation,
            action=AllocationPendency.ActionType.NEW_NUMBER,
        )
        AllocationPendency.objects.create(
            employee=self.employee,
            allocation=None,
            action=AllocationPendency.ActionType.RECONNECT_WHATSAPP,
        )

        counts = get_pending_action_counts_for_user(self.admin)

        self.assertEqual(counts["new_number"], 0)
        self.assertEqual(counts["reconnect_whatsapp"], 1)
