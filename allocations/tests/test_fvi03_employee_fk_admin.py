"""
FVI-03 - Testes RED do campo FK `employee` em LineAllocationAdmin
(requisito 4 do checklist desta etapa, parte Alocacoes).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
(FVI-02 F16; fechamento "FK employee no Admin"). Node IDs FT16-FT20
derivados nesta etapa (FVI-03).

LineAllocationAdmin.formfield_for_foreignkey hoje (F16) so trata
AUTHOR_FK_FIELDS = ("allocated_by", "released_by"); o campo "employee"
usa o <select> padrao do ModelForm (Employee.objects.all(), todos os
status). O contrato aprovado (fechamento 2026-10-15) exige: NOVA escolha
de funcionario inativo sem vinculo bloqueada; vinculo JA persistido
inativo representado pelo marcador neutro "__keep_current__"
(KEEP_CURRENT_TOKEN/KEEP_CURRENT_LABEL, ja definidos em
users/visibility.py), sem nome/identificador oculto nas choices.
ADMIN/DEV preservam a identidade real sem restricao.
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from employees.models import Employee
from employees.visibility import INACTIVE_EMPLOYEE_LABEL
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser
from users.visibility import KEEP_CURRENT_LABEL, KEEP_CURRENT_TOKEN

from ..models import LineAllocation


def _grant_full_allocations_perms(user):
    perms = Permission.objects.filter(content_type__app_label="allocations")
    user.user_permissions.set(perms)
    user.is_staff = True
    user.save(update_fields=["is_staff"])


class LineAllocationEmployeeFkAdminTestBase(TestCase):
    def setUp(self):
        self.viewer = SystemUser.objects.create_user(
            email="viewer.fvi03.alloc.fk@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        _grant_full_allocations_perms(self.viewer)

        self.admin_viewer = SystemUser.objects.create_user(
            email="admin.fvi03.alloc.fk@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        _grant_full_allocations_perms(self.admin_viewer)

        self.active_employee = Employee.objects.create(
            full_name="Funcionario Ativo Fk",
            corporate_email="supervisor.fvi03.alloc.fk@test.com",
            employee_id="EMP-FVI03-FK-A",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.inactive_unlinked_employee = Employee.objects.create(
            full_name="Funcionario Inativo Sem Vinculo",
            corporate_email="supervisor.fvi03.alloc.fk@test.com",
            employee_id="EMP-FVI03-FK-IU",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.INACTIVE,
        )
        self.inactive_linked_employee = Employee.objects.create(
            full_name="Funcionario Inativo Com Vinculo",
            corporate_email="supervisor.fvi03.alloc.fk@test.com",
            employee_id="EMP-FVI03-FK-IL",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.INACTIVE,
        )

        sim = SIMcard.objects.create(
            iccid="11112222333344445555",
            carrier="CarrierFvi03",
            status=SIMcard.Status.AVAILABLE,
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number="+5511988887777",
            sim_card=sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        self.allocation = LineAllocation.objects.create(
            employee=self.inactive_linked_employee,
            phone_line=self.phone_line,
            is_active=True,
        )

    def _add_url(self):
        return reverse("admin:allocations_lineallocation_add")

    def _change_url(self):
        return reverse(
            "admin:allocations_lineallocation_change", args=[self.allocation.pk]
        )

    def _base_post_payload(self, **overrides):
        payload = {
            "employee": str(self.inactive_linked_employee.pk),
            "phone_line": str(self.phone_line.pk),
            "is_active": "on",
            "line_status": LineAllocation.LineStatus.ACTIVE,
            "released_at_0": "",
            "released_at_1": "",
            "allocated_by": "",
            "released_by": "",
        }
        payload.update(overrides)
        return payload

    def _make_phone_line(self, suffix):
        """Linha extra isolada por teste, para criacao/edicao nao
        colidirem com self.phone_line (ja usada por self.allocation)."""
        sim = SIMcard.objects.create(
            iccid=f"7777000011112222{suffix:04d}",
            carrier="CarrierFvi04Probe",
            status=SIMcard.Status.AVAILABLE,
        )
        return PhoneLine.objects.create(
            phone_number=f"+5511966660{suffix:04d}",
            sim_card=sim,
            status=PhoneLine.Status.ALLOCATED,
        )


class FT16_NewChoiceExcludesUnlinkedInactiveEmployee(
    LineAllocationEmployeeFkAdminTestBase
):
    """FT16: no formulario de CRIACAO, funcionario inativo sem vinculo
    nao deve estar entre as opcoes de "employee" para viewer restrito;
    funcionario ativo continua disponivel; ADMIN ve tudo."""

    def test_restricted_viewer_add_form_excludes_unlinked_inactive_employee(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self._add_url())

        self.assertEqual(response.status_code, 200)
        queryset_pks = set(
            response.context["adminform"]
            .form.fields["employee"]
            .queryset.values_list("pk", flat=True)
        )
        self.assertNotIn(self.inactive_unlinked_employee.pk, queryset_pks)

    def test_restricted_viewer_add_form_still_offers_active_employee_as_control(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self._add_url())

        self.assertEqual(response.status_code, 200)
        queryset_pks = set(
            response.context["adminform"]
            .form.fields["employee"]
            .queryset.values_list("pk", flat=True)
        )
        self.assertIn(self.active_employee.pk, queryset_pks)

    def test_admin_viewer_add_form_still_offers_inactive_unlinked_employee(self):
        """Controle positivo: ADMIN/DEV preservam identidade real sem
        restricao, mesmo sem vinculo preexistente."""
        self.client.force_login(self.admin_viewer)
        response = self.client.get(self._add_url())

        self.assertEqual(response.status_code, 200)
        queryset_pks = set(
            response.context["adminform"]
            .form.fields["employee"]
            .queryset.values_list("pk", flat=True)
        )
        self.assertIn(self.inactive_unlinked_employee.pk, queryset_pks)


class FT17_PersistedInactiveLinkUsesNeutralKeepCurrentToken(
    LineAllocationEmployeeFkAdminTestBase
):
    """FT17: quando o vinculo JA persistido esta oculto para o viewer, a
    tela de edicao deve representar esse vinculo pelo marcador neutro
    __keep_current__ (initial do campo), nao pelo PK/identidade real."""

    def test_restricted_viewer_change_form_initial_is_keep_current_token(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertEqual(form.initial.get("employee"), KEEP_CURRENT_TOKEN)

    def test_restricted_viewer_change_form_offers_keep_current_label_option(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, KEEP_CURRENT_LABEL)

    def test_admin_viewer_change_form_initial_is_real_pk_as_control(self):
        self.client.force_login(self.admin_viewer)
        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertEqual(
            form.initial.get("employee"), self.inactive_linked_employee.pk
        )


class FT18_PostKeepCurrentTokenPreservesPersistedLink(
    LineAllocationEmployeeFkAdminTestBase
):
    """FT18: POST reenviando o marcador __keep_current__ deve preservar
    o vinculo real persistido (resolvido no servidor), nao ser rejeitado
    como PK invalida nem alterar o funcionario vinculado."""

    def test_restricted_viewer_post_keep_current_token_preserves_employee(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._change_url(),
            self._base_post_payload(employee=KEEP_CURRENT_TOKEN),
        )

        self.allocation.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.allocation.employee_id, self.inactive_linked_employee.pk)


class FT19_ForgedOtherInactiveEmployeeIsRejected(
    LineAllocationEmployeeFkAdminTestBase
):
    """FT19: POST forjado associando a um OUTRO funcionario inativo
    (sem vinculo previo com esta allocation) deve ser recusado; o
    vinculo persistido permanece inalterado."""

    def test_restricted_viewer_post_other_inactive_employee_pk_is_rejected(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._change_url(),
            self._base_post_payload(
                employee=str(self.inactive_unlinked_employee.pk)
            ),
        )

        self.allocation.refresh_from_db()
        self.assertNotEqual(response.status_code, 302)
        self.assertEqual(self.allocation.employee_id, self.inactive_linked_employee.pk)


class FT20_SwitchingToActiveEmployeeIsAccepted(
    LineAllocationEmployeeFkAdminTestBase
):
    """FT20: POST trocando o vinculo para um funcionario ATIVO deve ser
    aceito normalmente, mesmo com o vinculo anterior oculto."""

    def test_restricted_viewer_post_switch_to_active_employee_is_accepted(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._change_url(),
            self._base_post_payload(employee=str(self.active_employee.pk)),
        )

        self.allocation.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.allocation.employee_id, self.active_employee.pk)


class FT33_CreateWithKeepCurrentTokenIsRejected(
    LineAllocationEmployeeFkAdminTestBase
):
    """FT33 (fechamento da lacuna de cobertura apontada na revisao de
    FVI-04): POST de CRIACAO com employee="__keep_current__" nao tem
    vinculo persistido a preservar (object_id inexistente -> masked_id
    sempre None em resolve_employee_fk_keep_current) -- o token nao e
    reconhecido pelo to_python sobrescrito e cai na validacao padrao do
    ModelChoiceField, que rejeita a string como PK. Substitui o probe
    temporario relatado na revisao anterior (que so cobriu
    LineAllocationAdmin de forma descartavel, nunca persistido no
    repositorio) por um teste permanente equivalente."""

    def test_restricted_viewer_create_with_keep_current_token_is_rejected(self):
        new_line = self._make_phone_line(1)
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._add_url(),
            self._base_post_payload(
                employee=KEEP_CURRENT_TOKEN, phone_line=str(new_line.pk)
            ),
        )

        # HTTP 200 sozinho nao comprova rejeicao: o formulario precisa
        # ter voltado com erro especificamente no campo employee, nao em
        # outro campo (o que indicaria fixture/payload invalido, nao a
        # regra sob teste).
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("employee", form.errors)
        self.assertFalse(form.is_valid())

        # Nenhuma LineAllocation foi criada para esta linha (nem para
        # nenhum outro employee) -- a rejeicao ocorreu antes de qualquer
        # persistencia, nao apenas na resposta HTTP.
        self.assertFalse(LineAllocation.objects.filter(phone_line=new_line).exists())

        # Redisplay nao pode reintroduzir identidade oculta: nao ha
        # vinculo persistido nesta criacao, entao nenhum nome de
        # funcionario inativo deveria aparecer na pagina de erro.
        self.assertNotContains(
            response, self.inactive_unlinked_employee.full_name
        )
        self.assertNotContains(
            response, self.inactive_linked_employee.full_name
        )

    def test_restricted_viewer_create_with_valid_active_employee_is_accepted_as_control(
        self,
    ):
        """Controle positivo desta classe: o MESMO fluxo de criacao, com
        os MESMOS demais campos, aceita um funcionario ATIVO -- prova
        que a rejeicao do teste acima nao e causada por fixture/permissao
        quebrada, e sim pela regra do campo employee especificamente."""
        new_line = self._make_phone_line(2)
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._add_url(),
            self._base_post_payload(
                employee=str(self.active_employee.pk), phone_line=str(new_line.pk)
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            LineAllocation.objects.filter(
                phone_line=new_line, employee=self.active_employee
            ).exists()
        )


class FT34_CreateWithForgedHiddenInactivePkIsRejected(
    LineAllocationEmployeeFkAdminTestBase
):
    """FT34: POST de CRIACAO com a PK REAL de um funcionario inativo sem
    vinculo (oculto para o viewer restrito, fora do queryset de escolhas
    por construcao) deve ser recusado -- a PK forjada nao esta entre as
    choices do ModelChoiceField, mesmo sendo um valor real e existente no
    banco."""

    def test_restricted_viewer_create_with_forged_inactive_pk_is_rejected(self):
        new_line = self._make_phone_line(3)
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._add_url(),
            self._base_post_payload(
                employee=str(self.inactive_unlinked_employee.pk),
                phone_line=str(new_line.pk),
            ),
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("employee", form.errors)
        self.assertFalse(form.is_valid())

        self.assertFalse(
            LineAllocation.objects.filter(
                employee=self.inactive_unlinked_employee
            ).exists()
        )
        self.assertFalse(LineAllocation.objects.filter(phone_line=new_line).exists())

        # Nome do funcionario oculto forjado nao pode aparecer na pagina
        # de erro (nem como opcao selecionada, nem em texto solto).
        self.assertNotContains(
            response, self.inactive_unlinked_employee.full_name
        )

    def test_admin_viewer_create_with_same_inactive_pk_is_accepted_as_control(self):
        """Controle positivo: ADMIN (excecao de role) consegue criar com
        a MESMA PK inativa sem vinculo -- prova que a rejeicao do teste
        acima e da regra de visibilidade do viewer restrito, nao de uma
        invalidade generica da PK/payload."""
        new_line = self._make_phone_line(4)
        self.client.force_login(self.admin_viewer)

        response = self.client.post(
            self._add_url(),
            self._base_post_payload(
                employee=str(self.inactive_unlinked_employee.pk),
                phone_line=str(new_line.pk),
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            LineAllocation.objects.filter(
                phone_line=new_line, employee=self.inactive_unlinked_employee
            ).exists()
        )


class FT35_EditWithKeepCurrentTokenOnVisibleActiveLinkIsRejected(
    LineAllocationEmployeeFkAdminTestBase
):
    """FT35: POST de EDICAO com employee="__keep_current__" quando o
    vinculo persistido do registro JA e visivel (funcionario ATIVO) deve
    ser recusado -- resolve_employee_fk_keep_current so marca masked_id
    quando o vinculo persistido esta OCULTO; para vinculo ja visivel,
    masked_id e None, o to_python nao e sobrescrito, e o token cai na
    validacao padrao do ModelChoiceField (nao e uma PK valida)."""

    def setUp(self):
        super().setUp()
        self.active_linked_line = self._make_phone_line(5)
        self.active_linked_allocation = LineAllocation.objects.create(
            employee=self.active_employee,
            phone_line=self.active_linked_line,
            is_active=True,
        )

    def _active_change_url(self):
        return reverse(
            "admin:allocations_lineallocation_change",
            args=[self.active_linked_allocation.pk],
        )

    def test_restricted_viewer_edit_active_link_with_keep_current_token_is_rejected(
        self,
    ):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._active_change_url(),
            self._base_post_payload(
                employee=KEEP_CURRENT_TOKEN,
                phone_line=str(self.active_linked_line.pk),
            ),
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("employee", form.errors)
        self.assertFalse(form.is_valid())

        self.active_linked_allocation.refresh_from_db()
        self.assertEqual(
            self.active_linked_allocation.employee_id, self.active_employee.pk
        )
        self.assertEqual(
            self.active_linked_allocation.phone_line_id, self.active_linked_line.pk
        )

    def test_restricted_viewer_edit_active_link_with_real_pk_is_accepted_as_control(
        self,
    ):
        """Controle positivo: o MESMO registro (vinculo ja visivel),
        reenviando a PK REAL (nao o token) do mesmo funcionario ATIVO,
        e aceito normalmente -- prova que a rejeicao do teste acima e
        especifica do token nao reconhecido, nao do registro/fixture."""
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._active_change_url(),
            self._base_post_payload(
                employee=str(self.active_employee.pk),
                phone_line=str(self.active_linked_line.pk),
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.active_linked_allocation.refresh_from_db()
        self.assertEqual(
            self.active_linked_allocation.employee_id, self.active_employee.pk
        )


class FT39_ChangelistMasksHiddenEmployeeIdentity(
    LineAllocationEmployeeFkAdminTestBase
):
    """FT39 (FVI-06, fechamento do achado 1 da conferencia corretiva de
    FVI-05): a coluna "employee" da changelist nao pode expor o nome do
    funcionario inativo vinculado para o viewer restrito -- mesma
    inconsistencia ja corrigida no <select> do campo (FVI-04/FT17), mas
    aqui na apresentacao somente-leitura da listagem."""

    def setUp(self):
        super().setUp()
        self.active_linked_line = self._make_phone_line(10)
        self.active_linked_allocation = LineAllocation.objects.create(
            employee=self.active_employee,
            phone_line=self.active_linked_line,
            is_active=True,
        )

    def _changelist_url(self):
        return reverse("admin:allocations_lineallocation_changelist")

    def test_restricted_viewer_changelist_hides_inactive_employee_name(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self._changelist_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, self.inactive_linked_employee.full_name
        )
        self.assertContains(response, INACTIVE_EMPLOYEE_LABEL)

    def test_restricted_viewer_changelist_still_shows_active_employee_name_as_control(
        self,
    ):
        self.client.force_login(self.viewer)
        response = self.client.get(self._changelist_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.active_employee.full_name)

    def test_admin_viewer_changelist_shows_real_inactive_employee_name(self):
        self.client.force_login(self.admin_viewer)
        response = self.client.get(self._changelist_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, self.inactive_linked_employee.full_name
        )


class FT40_ChangeFormTitleAndBreadcrumbMaskHiddenEmployeeIdentity(
    LineAllocationEmployeeFkAdminTestBase
):
    """FT40 (FVI-06): GET normal da pagina de edicao -- <title> (via
    context["subtitle"]) e o ultimo segmento do breadcrumb (via
    context["original"]) nao podem conter o nome do funcionario inativo
    vinculado para o viewer restrito, mesmo este estando legitimamente
    autorizado a abrir o registro (excecao de coexistencia). ADMIN
    preserva a identidade real."""

    def test_restricted_viewer_change_form_title_and_breadcrumb_are_masked(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, self.inactive_linked_employee.full_name
        )
        self.assertContains(response, INACTIVE_EMPLOYEE_LABEL)
        # FVI-06b: "original" e um EmployeeLinkedDisplayProxy (preserva
        # .pk para os links Historico/Apagar) -- a comparacao textual e
        # via str(), nao identidade/igualdade de objeto.
        self.assertEqual(
            response.context["subtitle"], str(response.context["original"])
        )
        self.assertEqual(response.context["original"].pk, self.allocation.pk)

    def test_admin_viewer_change_form_title_and_breadcrumb_show_real_identity(
        self,
    ):
        self.client.force_login(self.admin_viewer)
        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, self.inactive_linked_employee.full_name
        )


class FT41_InvalidPostRedisplayDoesNotLeakHiddenEmployeeIdentity(
    LineAllocationEmployeeFkAdminTestBase
):
    """FT41 (FVI-06): redisplay apos POST invalido (erro em campo ALHEIO
    ao employee) nao pode reintroduzir a identidade do funcionario
    inativo vinculado no <title>/breadcrumb -- mesmo hook
    (render_change_form) cobre GET normal e este caminho de erro."""

    def test_restricted_viewer_invalid_redisplay_keeps_identity_masked(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._change_url(),
            self._base_post_payload(
                employee=KEEP_CURRENT_TOKEN, phone_line=""
            ),
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("phone_line", form.errors)
        self.assertNotContains(
            response, self.inactive_linked_employee.full_name
        )
        self.assertContains(response, INACTIVE_EMPLOYEE_LABEL)


class FT42_SuccessMessageDoesNotLeakHiddenEmployeeIdentity(
    LineAllocationEmployeeFkAdminTestBase
):
    """FT42 (FVI-06): a mensagem de sucesso exibida apos salvar ("The
    line allocation ... was changed successfully.") serializa str(obj)
    -- mesma identidade que o <select> ja mascara. Editar um campo
    ALHEIO ao employee (mantendo __keep_current__) nao pode revelar o
    nome do funcionario inativo vinculado nessa mensagem."""

    def test_restricted_viewer_success_message_masks_hidden_employee(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._change_url(),
            self._base_post_payload(employee=KEEP_CURRENT_TOKEN),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(messages)
        joined = " ".join(messages)
        self.assertNotIn(self.inactive_linked_employee.full_name, joined)
        self.assertIn(INACTIVE_EMPLOYEE_LABEL, joined)

    def test_admin_viewer_success_message_shows_real_identity(self):
        self.client.force_login(self.admin_viewer)

        response = self.client.post(
            self._change_url(),
            self._base_post_payload(employee=str(self.inactive_linked_employee.pk)),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(messages)
        joined = " ".join(messages)
        self.assertIn(self.inactive_linked_employee.full_name, joined)


class FT47_HistoryAndDeleteLinksSurviveIdentityMasking(
    LineAllocationEmployeeFkAdminTestBase
):
    """FT47 (FVI-06b, correcao da regressao de navegacao): render_change_form
    (FVI-06) sobrescrevia context["original"] com uma STRING mascarada --
    os templates instalados do Django usam original.pk para construir os
    links "Historico"/"Apagar" (admin/change_form_object_tools.html,
    admin/submit_line.html), que silenciosamente viram href="" quando
    original nao tem atributo pk. Esta classe exige a URL EXATA via
    reverse(), nunca apenas presenca de texto/href, e segue o link ate o
    destino real -- 200 sozinho ou "Historico" no texto nao comprova
    navegacao correta."""

    def setUp(self):
        super().setUp()
        self.active_linked_line = self._make_phone_line(20)
        self.active_linked_allocation = LineAllocation.objects.create(
            employee=self.active_employee,
            phone_line=self.active_linked_line,
            is_active=True,
        )

    def _history_url(self, pk):
        return reverse("admin:allocations_lineallocation_history", args=[pk])

    def test_restricted_viewer_history_link_has_exact_url(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        expected_href = f'href="{self._history_url(self.allocation.pk)}"'
        self.assertContains(response, expected_href)
        self.assertNotContains(response, 'class="historylink" href=""')
        # Mascaramento continua intacto nesta mesma pagina (regressao nao
        # pode ser corrigida reabrindo o vazamento de identidade).
        self.assertNotContains(
            response, self.inactive_linked_employee.full_name
        )
        self.assertContains(response, INACTIVE_EMPLOYEE_LABEL)

    def test_restricted_viewer_following_history_link_reaches_correct_record(self):
        self.client.force_login(self.viewer)

        history_response = self.client.get(self._history_url(self.allocation.pk))

        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response.context["object"].pk, self.allocation.pk)

    def test_restricted_viewer_delete_link_absent_when_already_forbidden(self):
        """LineAllocationAdmin.has_delete_permission e sempre False -- o
        link "Apagar" deve continuar AUSENTE (nunca concedemos permissao
        nova so para faze-lo aparecer e provar a URL)."""
        self.client.force_login(self.viewer)
        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="deletelink"')

    def test_restricted_viewer_invalid_redisplay_keeps_correct_history_url(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._change_url(),
            self._base_post_payload(employee=KEEP_CURRENT_TOKEN, phone_line=""),
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("phone_line", form.errors)
        expected_href = f'href="{self._history_url(self.allocation.pk)}"'
        self.assertContains(response, expected_href)

    def test_admin_viewer_history_link_has_exact_url_as_control(self):
        self.client.force_login(self.admin_viewer)
        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        expected_href = f'href="{self._history_url(self.allocation.pk)}"'
        self.assertContains(response, expected_href)

    def test_restricted_viewer_active_employee_history_link_has_exact_url_as_control(
        self,
    ):
        """Controle: registro com funcionario ATIVO (sem mascaramento
        algum) tambem precisa da URL exata -- prova que a correcao nao
        depende do caminho mascarado para funcionar."""
        self.client.force_login(self.viewer)
        url = reverse(
            "admin:allocations_lineallocation_change",
            args=[self.active_linked_allocation.pk],
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        expected_href = (
            f'href="{self._history_url(self.active_linked_allocation.pk)}"'
        )
        self.assertContains(response, expected_href)
