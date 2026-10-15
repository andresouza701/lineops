"""UVI-04 - Complemento de cobertura solicitado antes da implementacao
correspondente (fluxo contrato -> testes -> RED real -> implementacao ->
validacao): marcador __keep_current__ (fronteira de backend), T11
(desativacao entre GET e POST) e T12 (custo de consulta + isolamento entre
viewers). Node IDs do checklist UVI-02/UVI-03.

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md

Escopo explicitamente de BACKEND (UVI-04): o marcador em si, sua
resolucao no servidor a partir do objeto persistido, e a rejeicao de
POST forjado. O rotulo HTML/neutralizacao visual completa do marcador
(contrato item 7, "nome exato e transporte... antes dos testes" de UI)
e reserva de UVI-05 -- aqui validamos apenas o valor submetido/aceito, nao
a renderizacao visual do <option> (os testes de T08/T08b em
test_uvi03_inactive_account_visibility.py ja cobrem a mascara de
template, ainda RED, fora do escopo desta etapa)."""

from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

from employees.forms import EmployeeForm
from employees.models import Employee
from users.models import SystemUser
from users.visibility import KEEP_CURRENT_TOKEN, NO_ACTIVE_ACCOUNTS_LABEL


class KeepCurrentTokenFixture(TestCase):
    def setUp(self):
        self.inactive_super = SystemUser.objects.create_user(
            email="super.inativo.keepcurrent.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.inactive_super.is_active = False
        self.inactive_super.save(update_fields=["is_active"])

        self.active_super = SystemUser.objects.create_user(
            email="super.ativo.keepcurrent.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.backoffice = SystemUser.objects.create_user(
            email="backoffice.keepcurrent.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.inactive_super.email,
        )
        self.employee = Employee.objects.create(
            full_name="Funcionario KeepCurrent UVI04",
            corporate_email=self.inactive_super.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )

    def _valid_payload(self, corporate_email):
        return {
            "full_name": "Funcionario KeepCurrent UVI04",
            "email": "",
            "corporate_email": corporate_email,
            "manager_email": "",
            "employee_id": "Alimentos",
            "teams": "Joinville",
            "status": Employee.Status.ACTIVE,
            "pa": "",
        }


class KeepCurrentTokenFormUnitTests(KeepCurrentTokenFixture):
    """Nivel de unidade (form isolado, viewer restrito explicito)."""

    def test_token_is_offered_when_persisted_link_is_hidden_for_viewer(self):
        form = EmployeeForm(instance=self.employee, viewer=self.backoffice)
        values = [v for v, _l in form.fields["corporate_email"].widget.choices]
        self.assertIn(KEEP_CURRENT_TOKEN, values)
        self.assertNotIn(self.inactive_super.email, values)

    def test_token_is_not_offered_for_exempt_viewer(self):
        """ADMIN/DEV preservam visibilidade -- nao precisam do marcador,
        pois a identidade real continua nas opcoes."""
        admin_viewer = SystemUser.objects.create_user(
            email="admin.keepcurrent.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        form = EmployeeForm(instance=self.employee, viewer=admin_viewer)
        values = [v for v, _l in form.fields["corporate_email"].widget.choices]
        self.assertNotIn(KEEP_CURRENT_TOKEN, values)
        self.assertIn(self.inactive_super.email, values)

    def test_submitting_token_keeps_persisted_hidden_link(self):
        form = EmployeeForm(
            data=self._valid_payload(KEEP_CURRENT_TOKEN),
            instance=self.employee,
            viewer=self.backoffice,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["corporate_email"], self.inactive_super.email
        )

    def test_switching_to_active_account_still_works_instead_of_token(self):
        """Controle positivo: o marcador nao e a UNICA opcao valida --
        trocar explicitamente por um ativo continua funcionando."""
        form = EmployeeForm(
            data=self._valid_payload(self.active_super.email),
            instance=self.employee,
            viewer=self.backoffice,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["corporate_email"], self.active_super.email)

    def test_token_is_rejected_on_creation_with_no_persisted_instance(self):
        """Rejeitar criacao/forja: sem instancia persistida, nao ha vinculo
        algum a "manter" -- o marcador nao pode ser usado para criar um
        funcionario novo."""
        form = EmployeeForm(
            data=self._valid_payload(KEEP_CURRENT_TOKEN), viewer=self.backoffice
        )
        self.assertFalse(form.is_valid())
        self.assertIn("corporate_email", form.errors)

    def test_token_is_rejected_when_persisted_link_is_not_hidden(self):
        """Marcador fora do contexto permitido: a instancia existe, mas o
        vinculo persistido JA e uma conta ativa (nada para "manter" que
        esteja oculto) -- o marcador nao e uma forma alternativa de
        selecionar/confirmar um valor ja ativo."""
        active_employee = Employee.objects.create(
            full_name="Funcionario KeepCurrent Ativo UVI04",
            corporate_email=self.active_super.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        form = EmployeeForm(
            data=self._valid_payload(KEEP_CURRENT_TOKEN),
            instance=active_employee,
            viewer=self.backoffice,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("corporate_email", form.errors)

    def test_token_cannot_be_used_to_point_to_a_different_hidden_inactive_account(self):
        """Rejeitar "outro inativo": o marcador resolve EXCLUSIVAMENTE o
        vinculo persistido deste funcionario -- nao pode ser usado como um
        atalho generico para qualquer conta inativa. Simulado forcando o
        formulario a resolver o marcador contra uma instancia cujo vinculo
        persistido e uma SEGUNDA conta inativa diferente: o valor
        resolvido deve ser exatamente a persistida, nunca uma terceira."""
        other_inactive = SystemUser.objects.create_user(
            email="super.inativo2.keepcurrent.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        other_inactive.is_active = False
        other_inactive.save(update_fields=["is_active"])

        form = EmployeeForm(
            data=self._valid_payload(KEEP_CURRENT_TOKEN),
            instance=self.employee,
            viewer=self.backoffice,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["corporate_email"], self.inactive_super.email
        )
        self.assertNotEqual(form.cleaned_data["corporate_email"], other_inactive.email)

    def test_zero_visible_accounts_state_blocks_new_hidden_assignment_without_keep_current(
        self,
    ):
        """Contrato item 9 generalizado: quando ha contas do role mas
        NENHUMA visivel para o viewer e nao ha vinculo persistido oculto a
        preservar (criacao nova), o campo nao pode virar um bypass -- nem
        texto livre, nem selecao do unico inativo existente."""
        from django import forms as djforms

        # Desativa tambem o unico supervisor ativo do fixture: cenario
        # real de "ha contas, mas nenhuma visivel" (nao "zero contas no
        # banco", que preserva o fallback legado -- ver T06c).
        self.active_super.is_active = False
        self.active_super.save(update_fields=["is_active"])

        form = EmployeeForm(data=self._valid_payload(self.inactive_super.email), viewer=self.backoffice)
        self.assertIsInstance(form.fields["corporate_email"].widget, djforms.Select)
        choice_labels = dict(form.fields["corporate_email"].widget.choices)
        self.assertIn(NO_ACTIVE_ACCOUNTS_LABEL, choice_labels.values())
        self.assertFalse(form.is_valid())
        self.assertIn("corporate_email", form.errors)


class T05b_KeepCurrentRealRouteTests(KeepCurrentTokenFixture):
    """Mesmo mecanismo pela rota HTTP real (EmployeeUpdateView), viewer
    restrito (BACKOFFICE), reforcando T05b de test_uvi03_inactive_account_
    visibility.py com o marcador especificamente."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.backoffice)

    def test_get_edit_page_offers_keep_current_marker_not_the_real_identity(self):
        response = self.client.get(
            reverse("employees:employee_update", args=[self.employee.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.inactive_super.email)
        self.assertContains(response, KEEP_CURRENT_TOKEN)

    def test_posting_keep_current_marker_preserves_persisted_link_in_db(self):
        response = self.client.post(
            reverse("employees:employee_update", args=[self.employee.pk]),
            self._valid_payload(KEEP_CURRENT_TOKEN),
        )
        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.corporate_email, self.inactive_super.email)

    def test_error_in_unrelated_field_preserves_keep_current_choice_on_redisplay(self):
        """"Preservar escolha apos erro alheio": erro em employee_id (nao
        corporate_email) redisplay o formulario com o MARCADOR ainda
        selecionavel (nao a identidade real, nem um valor vazio/primeira
        opcao)."""
        payload = self._valid_payload(KEEP_CURRENT_TOKEN)
        payload["employee_id"] = "Carteira-Invalida-UVI04"

        response = self.client.post(
            reverse("employees:employee_update", args=[self.employee.pk]), payload
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("employee_id"))
        self.assertNotContains(response, self.inactive_super.email)
        self.assertContains(response, KEEP_CURRENT_TOKEN)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.corporate_email, self.inactive_super.email)


class T11_DeactivationBetweenGetAndPostTest(TestCase):
    """T11: conta ativa no GET, desativada antes do POST. A nova
    associacao (nao um keep_current de vinculo ja persistido) deve ser
    bloqueada no servidor -- cada requisicao reavalia o estado atual do
    banco, nao o que foi mostrado no GET anterior."""

    def setUp(self):
        self.soon_to_be_inactive = SystemUser.objects.create_user(
            email="super.race.t11.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.other_active = SystemUser.objects.create_user(
            email="super.outro.race.t11.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        self.backoffice = SystemUser.objects.create_user(
            email="backoffice.race.t11.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email=self.other_active.email,
        )
        self.employee = Employee.objects.create(
            full_name="Funcionario T11 UVI04",
            corporate_email=self.other_active.email,
            employee_id="Alimentos",
            teams="Joinville",
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.backoffice)

    def test_get_shows_the_account_as_active_choice(self):
        response = self.client.get(
            reverse("employees:employee_update", args=[self.employee.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.soon_to_be_inactive.email)

    def test_post_after_deactivation_rejects_new_association_and_preserves_db(self):
        # GET ja comprovado acima (choices incluiam a conta ainda ativa).
        self.soon_to_be_inactive.is_active = False
        self.soon_to_be_inactive.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("employees:employee_update", args=[self.employee.pk]),
            {
                "full_name": "Funcionario T11 UVI04",
                "email": "",
                "corporate_email": self.soon_to_be_inactive.email,
                "manager_email": "",
                "employee_id": "Alimentos",
                "teams": "Joinville",
                "status": Employee.Status.ACTIVE,
                "pa": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("corporate_email"))
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.corporate_email, self.other_active.email)


class T12_QueryCostAndViewerIsolationTest(TestCase):
    """T12: custo de consulta nao cresce linearmente com o numero de
    contas (mesma contagem de queries para 2 ou 20 supervisores) e
    isolamento entre viewers (nenhum estado compartilhado entre
    instancias de formulario sucessivas na mesma requisicao/processo)."""

    def _create_supervisors(self, count, *, inactive=0, batch="a"):
        for index in range(count):
            user = SystemUser.objects.create_user(
                email=f"super.cost.t12.{batch}.{index}.uvi04@test.com",
                password="StrongPass123",
                role=SystemUser.Role.SUPER,
            )
            if index < inactive:
                user.is_active = False
                user.save(update_fields=["is_active"])

    def test_form_init_query_count_is_constant_regardless_of_row_count(self):
        self._create_supervisors(2, inactive=0, batch="small")
        with CaptureQueriesContext(connection) as small_ctx:
            EmployeeForm()
        small_count = len(small_ctx.captured_queries)

        self._create_supervisors(20, inactive=10, batch="large")
        with CaptureQueriesContext(connection) as large_ctx:
            EmployeeForm()
        large_count = len(large_ctx.captured_queries)

        self.assertEqual(
            small_count,
            large_count,
            "custo de consulta do formulario nao pode crescer com o "
            "numero de contas (sem N+1 por conta)",
        )

    def test_distinct_viewers_produce_distinct_isolated_choices_in_sequence(self):
        inactive_super = SystemUser.objects.create_user(
            email="super.inativo.isolamento.t12.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        inactive_super.is_active = False
        inactive_super.save(update_fields=["is_active"])

        admin_viewer = SystemUser.objects.create_user(
            email="admin.isolamento.t12.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        restricted_viewer = SystemUser.objects.create_user(
            email="backoffice.isolamento.t12.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.BACKOFFICE,
        )

        restricted_form = EmployeeForm(viewer=restricted_viewer)
        admin_form = EmployeeForm(viewer=admin_viewer)
        restricted_form_again = EmployeeForm(viewer=restricted_viewer)

        restricted_values = [
            v for v, _l in restricted_form.fields["corporate_email"].widget.choices
        ]
        admin_values = [
            v for v, _l in admin_form.fields["corporate_email"].widget.choices
        ]
        restricted_values_again = [
            v for v, _l in restricted_form_again.fields["corporate_email"].widget.choices
        ]

        self.assertNotIn(inactive_super.email, restricted_values)
        self.assertIn(inactive_super.email, admin_values)
        self.assertEqual(
            restricted_values,
            restricted_values_again,
            "duas instancias com o MESMO viewer devem produzir o mesmo "
            "resultado -- sem cache global contaminando entre requests",
        )
