"""
UVI-03 - Testes RED/GREEN da visibilidade de contas de acesso inativas em
CombinedRegistrationForm e no Admin de LineAllocation (FK de autoria
allocated_by/released_by).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
(UVI-01/UVI-02). Node IDs T04/T07 do checklist derivado em UVI-02.

Revisado na conferencia corretiva (ver secao "UVI-03a" da spec, ponto 3):
a entrega anterior testava CombinedRegistrationForm() isolado e afirmava
RED sem considerar que o UNICO chamador real (RegistrationHubView) e
ADMIN-only, e que o contrato restringe seletores operacionais explicitamente
"aos papeis restritos" (item 6) -- ADMIN preserva visibilidade de contas
inativas por excecao de role (Spec Summary/UVI-01). Testar o form isolado,
sem a rota, apresentava uma politica de contexto inexistente como se fosse
uma violacao alcancavel por papel restrito, o que o ponto 3 pediu para
corrigir. Mantido como GREEN (controle documentado), nao como RED.

O mesmo raciocinio se aplica ao Admin de LineAllocation: o Django Admin em
si nao e role-gated pelo RoleRequiredMixin, apenas por is_staff + permissao
de modelo -- entao testar com um viewer ADMIN nao prova violacao para os
quatro papeis restritos. Este arquivo agora separa explicitamente um
controle ADMIN (GREEN, excecao preservada) de um teste com viewer
genuinamente restrito (RED, sem excecao de role).
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from allocations.forms import CombinedRegistrationForm
from allocations.models import LineAllocation
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class T04_CombinedRegistrationFormAdminOnlyExceptionTest(TestCase):
    """CombinedRegistrationForm e instanciado SOMENTE por
    RegistrationHubView, allowed_roles=[ADMIN] (allocations/views.py).
    ADMIN preserva visibilidade de contas inativas por excecao de role --
    nao ha papel restrito alcancando esta rota hoje. Classificado como
    GREEN (comportamento atual compativel com a excecao), nao como
    violacao. Gap ESTRUTURAL documentado sem assercao de teste: o form nao
    recebe nenhum parametro de viewer/contexto, entao se um dia for
    reutilizado por uma rota de papel restrito (nao e o caso hoje), o
    mesmo vazamento se repetiria sem qualquer mudanca neste arquivo --
    isso e uma nota de risco para UVI-04/05, nao uma falha atual, e por
    isso nao e codificada como RED (nao ha rota real a testar ainda)."""

    def setUp(self):
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.combined.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.active_super = SystemUser.objects.create_user(
            email="super.ativo.combined.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.admin_viewer = SystemUser.objects.create_user(
            email="admin.combined.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(self.admin_viewer)

    def test_registration_hub_is_admin_only_as_control(self):
        """Controle de alcance: confirma que a rota que instancia este
        form e de fato ADMIN-only (nenhum papel restrito a alcanca hoje),
        condicao sob a qual a classificacao GREEN abaixo se sustenta."""
        from allocations.views import RegistrationHubView

        self.assertEqual(
            list(RegistrationHubView.allowed_roles), [SystemUser.Role.ADMIN]
        )

    def test_admin_route_still_offers_inactive_supervisor_as_choice(self):
        """GREEN: consistente com a excecao de role, ADMIN (unico papel
        que usa esta rota) ve e pode selecionar o supervisor inativo --
        isto NAO e apresentado como falha."""
        response = self.client.get(reverse("allocations:allocation_list"))

        self.assertEqual(response.status_code, 200)
        form = response.context["employee_form"]
        rendered_values = [
            value for value, _label in form.fields["corporate_email"].widget.choices
        ]
        self.assertIn(self.inactive_super.email, rendered_values)

    def test_admin_route_still_offers_active_supervisor_as_choice(self):
        """Controle positivo complementar: o ativo tambem continua
        disponivel -- a presenca do inativo nao substituiu a lista."""
        response = self.client.get(reverse("allocations:allocation_list"))

        self.assertEqual(response.status_code, 200)
        form = response.context["employee_form"]
        rendered_values = [
            value for value, _label in form.fields["corporate_email"].widget.choices
        ]
        self.assertIn(self.active_super.email, rendered_values)


class T07_LineAllocationAdminAuthorFkAdminExceptionTest(TestCase):
    """Controle: Django Admin nao e role-gated pelo RoleRequiredMixin
    (apenas is_staff + permissao de modelo). Um viewer ADMIN navegando o
    Admin de LineAllocation preserva visibilidade de contas inativas por
    excecao de role -- GREEN, nao e apresentado como violacao."""

    def setUp(self):
        self.inactive_other_user = SystemUser.objects.create_user(
            email="outro.inativo.linefk.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )
        self.inactive_other_user.is_active = False
        self.inactive_other_user.save(update_fields=["is_active"])

        self.admin_viewer = SystemUser.objects.create_user(
            email="admin.linefk.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
            is_staff=True,
        )
        self.admin_viewer.user_permissions.set(
            Permission.objects.filter(content_type__app_label="allocations")
        )

        self.employee = Employee.objects.create(
            full_name="Funcionario LineFK UVI03",
            corporate_email="super.linefk.uvi03@corp.com",
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.sim_card = SIMcard.objects.create(
            iccid="8900000000000000901",
            carrier="CarrierUvi03",
            status=SIMcard.Status.AVAILABLE,
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number="+551199999901",
            sim_card=self.sim_card,
            status=PhoneLine.Status.ALLOCATED,
        )
        self.allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.phone_line,
            allocated_by=self.admin_viewer,
            is_active=True,
        )
        self.client.force_login(self.admin_viewer)

    def test_admin_change_page_still_offers_unrelated_inactive_user_as_control(self):
        url = reverse("admin:allocations_lineallocation_change", args=[self.allocation.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.inactive_other_user.email)

    def test_change_page_still_preserves_persisted_author_identity(self):
        url = reverse("admin:allocations_lineallocation_change", args=[self.allocation.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.admin_viewer.email)


class T07b_LineAllocationAdminAuthorFkRestrictedStaffViewerTest(TestCase):
    """RED inequivoco: viewer com role restrito (SUPER, sem excecao) mas
    com is_staff + permissoes de modelo suficientes para alcancar a rota
    do Admin de LineAllocation (cenario administrativamente possivel: um
    administrador pode conceder permissao de Django Admin a qualquer
    role). "Novas escolhas" no FK allocated_by devem obedecer visibilidade
    e nao oferecer outra conta inativa sem vinculo com o registro."""

    def setUp(self):
        self.inactive_other_user = SystemUser.objects.create_user(
            email="outro.inativo.linefk.restrito.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )
        self.inactive_other_user.is_active = False
        self.inactive_other_user.save(update_fields=["is_active"])

        self.super_viewer = SystemUser.objects.create_user(
            email="super.staff.linefk.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
            is_staff=True,
        )
        self.super_viewer.user_permissions.set(
            Permission.objects.filter(content_type__app_label="allocations")
        )

        self.employee = Employee.objects.create(
            full_name="Funcionario LineFK Restrito UVI03",
            corporate_email="super.linefk.restrito.uvi03@corp.com",
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.sim_card = SIMcard.objects.create(
            iccid="8900000000000000902",
            carrier="CarrierUvi03b",
            status=SIMcard.Status.AVAILABLE,
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number="+551199999902",
            sim_card=self.sim_card,
            status=PhoneLine.Status.ALLOCATED,
        )
        self.allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.phone_line,
            allocated_by=self.super_viewer,
            is_active=True,
        )
        self.client.force_login(self.super_viewer)

    def test_restricted_staff_can_reach_change_page_as_control(self):
        url = reverse("admin:allocations_lineallocation_change", args=[self.allocation.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

    def test_restricted_staff_change_page_must_not_offer_unrelated_inactive_user(self):
        url = reverse("admin:allocations_lineallocation_change", args=[self.allocation.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_other_user.email)

    def test_restricted_staff_change_page_still_preserves_persisted_author(self):
        """Controle positivo: o vinculo ja persistido (o proprio
        super_viewer como allocated_by) continua presente."""
        url = reverse("admin:allocations_lineallocation_change", args=[self.allocation.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.super_viewer.email)
