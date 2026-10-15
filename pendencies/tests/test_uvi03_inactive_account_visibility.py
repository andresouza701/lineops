"""
UVI-03 - Testes RED/GREEN da visibilidade de contas de acesso inativas no
Admin de AllocationPendency (FK technical_responsible/updated_by) e
controle positivo de notificacoes (pendencies/services.py, U18).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
(UVI-01/UVI-02). Node IDs T07/T13 do checklist derivado em UVI-02.

pendencies/admin.py::AllocationPendencyAdmin nao declara fieldsets nem
raw_id_fields/autocomplete_fields para technical_responsible/updated_by
(confirmado por introspecao em UVI-02, U14/U22): o formulario padrao do
ModelAdmin renderiza um <select> com TODAS as SystemUser, inclusive
inativas. pendencies/services.py ja filtra is_active=True nos
destinatarios de notificacao (U18) -- GREEN, controle preexistente que
nao deve regredir.

Revisado na conferencia corretiva (ver secao "UVI-03a" da spec, ponto 3):
o Django Admin nao e role-gated pelo RoleRequiredMixin (so por is_staff +
permissao de modelo). Testar com viewer ADMIN nao prova violacao para os
quatro papeis restritos, pois ADMIN preserva visibilidade de contas
inativas por excecao de role. A classe T07 original foi dividida em um
controle ADMIN (GREEN, excecao preservada) e um teste com viewer
genuinamente restrito (T07b, RED sem excecao).
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from employees.models import Employee
from pendencies.models import AllocationPendency
from pendencies.services import notify_observation_change
from users.models import SystemUser


class T07_AllocationPendencyAdminFkAdminExceptionTest(TestCase):
    """Controle: viewer ADMIN preserva visibilidade de contas inativas por
    excecao de role -- GREEN, nao e apresentado como violacao."""

    def setUp(self):
        self.inactive_other_user = SystemUser.objects.create_user(
            email="outro.inativo.pendfk.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )
        self.inactive_other_user.is_active = False
        self.inactive_other_user.save(update_fields=["is_active"])

        self.admin_viewer = SystemUser.objects.create_user(
            email="admin.pendfk.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
            is_staff=True,
        )
        self.admin_viewer.user_permissions.set(
            Permission.objects.filter(content_type__app_label="pendencies")
        )

        self.employee = Employee.objects.create(
            full_name="Funcionario PendFK UVI03",
            corporate_email="super.pendfk.uvi03@corp.com",
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=None,
            technical_responsible=self.admin_viewer,
        )
        self.client.force_login(self.admin_viewer)

    def test_admin_change_page_still_offers_unrelated_inactive_user_as_control(self):
        url = reverse(
            "admin:pendencies_allocationpendency_change", args=[self.pendency.pk]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.inactive_other_user.email)

    def test_change_page_still_preserves_persisted_technical_responsible(self):
        """Controle positivo: o vinculo ja persistido (technical_responsible
        atual) continua presente no formulario."""
        url = reverse(
            "admin:pendencies_allocationpendency_change", args=[self.pendency.pk]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.admin_viewer.email)


class T07b_AllocationPendencyAdminFkRestrictedStaffViewerTest(TestCase):
    """RED inequivoco: viewer com role restrito (GERENTE, sem excecao) mas
    com is_staff + permissoes de modelo suficientes para alcancar a rota
    do Admin de AllocationPendency."""

    def setUp(self):
        self.inactive_other_user = SystemUser.objects.create_user(
            email="outro.inativo.pendfk.restrito.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )
        self.inactive_other_user.is_active = False
        self.inactive_other_user.save(update_fields=["is_active"])

        self.manager_viewer = SystemUser.objects.create_user(
            email="gerente.staff.pendfk.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
            is_staff=True,
        )
        self.manager_viewer.user_permissions.set(
            Permission.objects.filter(content_type__app_label="pendencies")
        )

        self.employee = Employee.objects.create(
            full_name="Funcionario PendFK Restrito UVI03",
            corporate_email="super.pendfk.restrito.uvi03@corp.com",
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=None,
            technical_responsible=self.manager_viewer,
        )
        self.client.force_login(self.manager_viewer)

    def test_restricted_staff_can_reach_change_page_as_control(self):
        url = reverse(
            "admin:pendencies_allocationpendency_change", args=[self.pendency.pk]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

    def test_restricted_staff_change_page_must_not_offer_unrelated_inactive_user(self):
        url = reverse(
            "admin:pendencies_allocationpendency_change", args=[self.pendency.pk]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_other_user.email)

    def test_restricted_staff_change_page_still_preserves_persisted_technical_responsible(
        self,
    ):
        url = reverse(
            "admin:pendencies_allocationpendency_change", args=[self.pendency.pk]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.manager_viewer.email)


class T13_NotificationRecipientsAlreadyExcludeInactiveTest(TestCase):
    """GREEN -- controle preexistente (U18): destinatarios de notificacao
    ja sao filtrados por is_active=True antes desta feature."""

    def setUp(self):
        self.admin_sender = SystemUser.objects.create_user(
            email="admin.notif.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.active_super = SystemUser.objects.create_user(
            email="super.ativo.notif.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.notif.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.employee = Employee.objects.create(
            full_name="Funcionario Notif UVI03",
            corporate_email="super.notiffk.uvi03@corp.com",
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.pendency = AllocationPendency.objects.create(
            employee=self.employee, allocation=None
        )

    def test_inactive_role_matching_recipient_does_not_receive_notification(self):
        created_count = notify_observation_change(
            self.pendency, self.admin_sender, "Observacao de teste UVI03"
        )

        recipient_emails = set(
            self.pendency.observation_notifications.values_list(
                "recipient__email", flat=True
            )
        )
        self.assertIn(self.active_super.email, recipient_emails)
        self.assertNotIn(self.inactive_super.email, recipient_emails)
        self.assertEqual(created_count, 1)
