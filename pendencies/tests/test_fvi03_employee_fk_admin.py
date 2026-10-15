"""
FVI-03 - Testes RED do campo FK `employee` em AllocationPendencyAdmin
(requisito 4 do checklist desta etapa, parte Pendencias).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
(FVI-02 F17; fechamento "FK employee no Admin"). Node IDs FT21-FT24
derivados nesta etapa (FVI-03).

AllocationPendencyAdmin.formfield_for_foreignkey (F17) so trata
OPERATIONAL_RESPONSIBLE_FK_FIELDS = ("technical_responsible",) e
HISTORICAL_AUTHOR_FK_FIELDS = ("updated_by",); o campo "employee" usa o
<select> padrao (Employee.objects.all(), todos os status). Este arquivo
testa SOMENTE a nova restricao sobre "employee" -- nao duplica os testes
ja existentes de technical_responsible (UVI-06c/06d, ja cobertos em
pendencies/tests/test_uvi06c_responsible_token_value.py e
test_uvi06_responsible_vs_author.py).
"""

from django.contrib.admin import helpers
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from allocations.models import LineAllocation
from employees.models import Employee
from employees.visibility import INACTIVE_EMPLOYEE_LABEL
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser
from users.visibility import KEEP_CURRENT_LABEL, KEEP_CURRENT_TOKEN

from ..models import AllocationPendency


def _grant_full_pendencies_perms(user):
    perms = Permission.objects.filter(content_type__app_label="pendencies")
    user.user_permissions.set(perms)
    user.is_staff = True
    user.save(update_fields=["is_staff"])


class PendencyEmployeeFkAdminTestBase(TestCase):
    def setUp(self):
        self.viewer = SystemUser.objects.create_user(
            email="viewer.fvi03.pend.fk@test.com",
            password="StrongPass123",
            role=SystemUser.Role.SUPER,
        )
        _grant_full_pendencies_perms(self.viewer)

        self.admin_viewer = SystemUser.objects.create_user(
            email="admin.fvi03.pend.fk@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        _grant_full_pendencies_perms(self.admin_viewer)

        self.active_employee = Employee.objects.create(
            full_name="Funcionario Ativo Pend Fk",
            corporate_email="supervisor.fvi03.pend.fk@test.com",
            employee_id="EMP-FVI03-PFK-A",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.ACTIVE,
        )
        self.inactive_unlinked_employee = Employee.objects.create(
            full_name="Funcionario Inativo Pend Sem Vinculo",
            corporate_email="supervisor.fvi03.pend.fk@test.com",
            employee_id="EMP-FVI03-PFK-IU",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.INACTIVE,
        )
        self.inactive_linked_employee = Employee.objects.create(
            full_name="Funcionario Inativo Pend Com Vinculo",
            corporate_email="supervisor.fvi03.pend.fk@test.com",
            employee_id="EMP-FVI03-PFK-IL",
            teams=Employee.UnitChoices.JOINVILLE,
            status=Employee.Status.INACTIVE,
        )

        self.pendency = AllocationPendency.objects.create(
            employee=self.inactive_linked_employee,
            allocation=None,
            action=AllocationPendency.ActionType.NO_ACTION,
        )

    def _add_url(self):
        return reverse("admin:pendencies_allocationpendency_add")

    def _change_url(self):
        return reverse(
            "admin:pendencies_allocationpendency_change", args=[self.pendency.pk]
        )

    def _base_post_payload(self, **overrides):
        payload = {
            "employee": str(self.inactive_linked_employee.pk),
            "allocation": "",
            "action": AllocationPendency.ActionType.NO_ACTION,
            "observation": "",
            "technical_responsible": "",
            "last_submitted_action": "",
            "updated_by": "",
        }
        payload.update(overrides)
        return payload


class FT21_NewChoiceExcludesUnlinkedInactiveEmployee(
    PendencyEmployeeFkAdminTestBase
):
    """FT21: no formulario de CRIACAO de AllocationPendency, funcionario
    inativo sem vinculo nao deve estar entre as opcoes de "employee"
    para viewer restrito; ADMIN preserva visibilidade total."""

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

    def test_admin_viewer_add_form_still_offers_inactive_unlinked_employee(self):
        self.client.force_login(self.admin_viewer)
        response = self.client.get(self._add_url())

        self.assertEqual(response.status_code, 200)
        queryset_pks = set(
            response.context["adminform"]
            .form.fields["employee"]
            .queryset.values_list("pk", flat=True)
        )
        self.assertIn(self.inactive_unlinked_employee.pk, queryset_pks)


class FT22_PersistedInactiveLinkUsesNeutralKeepCurrentToken(
    PendencyEmployeeFkAdminTestBase
):
    """FT22: vinculo JA persistido oculto deve ser representado pelo
    marcador neutro __keep_current__, nunca pela identidade real nas
    choices."""

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


class FT23_PostKeepCurrentTokenPreservesPersistedLink(
    PendencyEmployeeFkAdminTestBase
):
    """FT23: POST reenviando __keep_current__ preserva o vinculo
    persistido, resolvido no servidor."""

    def test_restricted_viewer_post_keep_current_token_preserves_employee(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._change_url(),
            self._base_post_payload(employee=KEEP_CURRENT_TOKEN),
        )

        self.pendency.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.pendency.employee_id, self.inactive_linked_employee.pk)


class FT24_ForgedOtherInactiveEmployeeIsRejected(PendencyEmployeeFkAdminTestBase):
    """FT24: POST forjado associando a outro funcionario inativo sem
    vinculo previo com este registro deve ser recusado."""

    def test_restricted_viewer_post_other_inactive_employee_pk_is_rejected(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._change_url(),
            self._base_post_payload(
                employee=str(self.inactive_unlinked_employee.pk)
            ),
        )

        self.pendency.refresh_from_db()
        self.assertNotEqual(response.status_code, 302)
        self.assertEqual(self.pendency.employee_id, self.inactive_linked_employee.pk)

    def test_restricted_viewer_post_switch_to_active_employee_is_accepted_as_control(
        self,
    ):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._change_url(),
            self._base_post_payload(employee=str(self.active_employee.pk)),
        )

        self.pendency.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.pendency.employee_id, self.active_employee.pk)


class FT36_CreateWithKeepCurrentTokenIsRejected(PendencyEmployeeFkAdminTestBase):
    """FT36 (fechamento da lacuna de cobertura apontada na revisao de
    FVI-04): POST de CRIACAO de AllocationPendency com
    employee="__keep_current__" nao tem vinculo persistido a preservar
    (object_id inexistente -> masked_id sempre None) -- o token nao e
    reconhecido pelo to_python sobrescrito e cai na validacao padrao do
    ModelChoiceField. O probe temporario relatado na revisao anterior so
    cobriu LineAllocationAdmin e foi descartado; este teste permanente
    cobre o mesmo cenario para AllocationPendencyAdmin especificamente,
    sem extrapolar aquele resultado."""

    def test_restricted_viewer_create_with_keep_current_token_is_rejected(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._add_url(),
            self._base_post_payload(employee=KEEP_CURRENT_TOKEN),
        )

        # HTTP 200 sozinho nao comprova rejeicao: o erro precisa estar
        # especificamente no campo employee.
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("employee", form.errors)
        self.assertFalse(form.is_valid())

        # Nenhum registro novo foi criado (nem para o token, nem para
        # nenhum outro employee) -- a rejeicao ocorreu antes de
        # qualquer persistencia.
        self.assertEqual(AllocationPendency.objects.count(), 1)  # so self.pendency

        self.assertNotContains(
            response, self.inactive_unlinked_employee.full_name
        )
        self.assertNotContains(
            response, self.inactive_linked_employee.full_name
        )

    def test_restricted_viewer_create_with_valid_active_employee_is_accepted_as_control(
        self,
    ):
        """Controle positivo: o MESMO fluxo de criacao, com os MESMOS
        demais campos, aceita um funcionario ATIVO -- prova que a
        rejeicao do teste acima e da regra do campo employee, nao de
        fixture/permissao quebrada."""
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._add_url(),
            self._base_post_payload(employee=str(self.active_employee.pk)),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            AllocationPendency.objects.filter(
                employee=self.active_employee, allocation=None
            ).exists()
        )


class FT37_CreateWithForgedHiddenInactivePkIsRejected(
    PendencyEmployeeFkAdminTestBase
):
    """FT37: POST de CRIACAO com a PK REAL de um funcionario inativo sem
    vinculo (oculto para o viewer restrito, fora do queryset de escolhas
    por construcao) deve ser recusado."""

    def test_restricted_viewer_create_with_forged_inactive_pk_is_rejected(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._add_url(),
            self._base_post_payload(
                employee=str(self.inactive_unlinked_employee.pk)
            ),
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("employee", form.errors)
        self.assertFalse(form.is_valid())

        self.assertFalse(
            AllocationPendency.objects.filter(
                employee=self.inactive_unlinked_employee
            ).exists()
        )
        self.assertEqual(AllocationPendency.objects.count(), 1)  # so self.pendency

        self.assertNotContains(
            response, self.inactive_unlinked_employee.full_name
        )

    def test_admin_viewer_create_with_same_inactive_pk_is_accepted_as_control(self):
        """Controle positivo: ADMIN (excecao de role) consegue criar com
        a MESMA PK inativa sem vinculo -- prova que a rejeicao do teste
        acima e da regra de visibilidade do viewer restrito, nao de uma
        invalidade generica da PK/payload."""
        self.client.force_login(self.admin_viewer)

        response = self.client.post(
            self._add_url(),
            self._base_post_payload(
                employee=str(self.inactive_unlinked_employee.pk)
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            AllocationPendency.objects.filter(
                employee=self.inactive_unlinked_employee
            ).exists()
        )


class FT38_EditWithKeepCurrentTokenOnVisibleActiveLinkIsRejected(
    PendencyEmployeeFkAdminTestBase
):
    """FT38: POST de EDICAO com employee="__keep_current__" quando o
    vinculo persistido do registro JA e visivel (funcionario ATIVO) deve
    ser recusado -- masked_id e None para vinculo ja visivel, o token
    nao e reconhecido pelo to_python padrao."""

    def setUp(self):
        super().setUp()
        self.active_linked_pendency = AllocationPendency.objects.create(
            employee=self.active_employee,
            allocation=None,
            action=AllocationPendency.ActionType.NO_ACTION,
        )

    def _active_change_url(self):
        return reverse(
            "admin:pendencies_allocationpendency_change",
            args=[self.active_linked_pendency.pk],
        )

    def test_restricted_viewer_edit_active_link_with_keep_current_token_is_rejected(
        self,
    ):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._active_change_url(),
            self._base_post_payload(employee=KEEP_CURRENT_TOKEN),
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("employee", form.errors)
        self.assertFalse(form.is_valid())

        self.active_linked_pendency.refresh_from_db()
        self.assertEqual(
            self.active_linked_pendency.employee_id, self.active_employee.pk
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
            self._base_post_payload(employee=str(self.active_employee.pk)),
        )

        self.assertEqual(response.status_code, 302)
        self.active_linked_pendency.refresh_from_db()
        self.assertEqual(
            self.active_linked_pendency.employee_id, self.active_employee.pk
        )


def _make_allocation_for(employee, suffix):
    sim = SIMcard.objects.create(
        iccid=f"9999000011112222{suffix:04d}",
        carrier="CarrierFvi06Pend",
        status=SIMcard.Status.AVAILABLE,
    )
    phone_line = PhoneLine.objects.create(
        phone_number=f"+5511955550{suffix:04d}",
        sim_card=sim,
        status=PhoneLine.Status.ALLOCATED,
    )
    return LineAllocation.objects.create(
        employee=employee, phone_line=phone_line, is_active=True
    )


class FT43_ChangelistMasksHiddenEmployeeIdentity(PendencyEmployeeFkAdminTestBase):
    """FT43 (FVI-06, fechamento do achado 1 da conferencia corretiva de
    FVI-05): a coluna "employee" (direta) e o funcionario embutido na
    coluna "allocation_display" (via allocation.employee) nao podem
    expor o nome do funcionario inativo vinculado para o viewer
    restrito. ADMIN preserva a identidade real nas duas colunas."""

    def setUp(self):
        super().setUp()
        self.inactive_linked_allocation = _make_allocation_for(
            self.inactive_linked_employee, 1
        )
        self.pendency.allocation = self.inactive_linked_allocation
        self.pendency.save(update_fields=["allocation"])
        self.active_linked_pendency = AllocationPendency.objects.create(
            employee=self.active_employee,
            allocation=_make_allocation_for(self.active_employee, 2),
            action=AllocationPendency.ActionType.NO_ACTION,
        )

    def _changelist_url(self):
        return reverse("admin:pendencies_allocationpendency_changelist")

    def test_restricted_viewer_changelist_hides_inactive_employee_name(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self._changelist_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, self.inactive_linked_employee.full_name
        )
        self.assertContains(response, INACTIVE_EMPLOYEE_LABEL)

    def test_restricted_viewer_action_checkbox_aria_label_is_also_masked(self):
        """O checkbox de acao em lote (coluna automatica inserida pelo
        Django quando ha acoes disponiveis, ex. "Remover selecionados")
        serializa str(obj) no atributo aria-label -- vazamento de
        acessibilidade/DOM-source distinto da coluna visivel, que o
        teste acima nao cobre especificamente."""
        self.client.force_login(self.viewer)
        response = self.client.get(self._changelist_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            f'aria-label="Selecione esse objeto para uma ação - '
            f"{self.inactive_linked_employee.full_name}",
        )
        self.assertContains(
            response,
            f'aria-label="Selecione esse objeto para uma ação - '
            f"{INACTIVE_EMPLOYEE_LABEL}",
        )

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


class FT44_ChangeFormTitleAndBreadcrumbMaskHiddenEmployeeIdentity(
    PendencyEmployeeFkAdminTestBase
):
    """FT44 (FVI-06): GET normal da pagina de edicao -- <title> (via
    context["subtitle"]) e o ultimo segmento do breadcrumb (via
    context["original"]) nao podem conter o nome do funcionario inativo
    vinculado para o viewer restrito. ADMIN preserva a identidade
    real."""

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
        self.assertEqual(response.context["original"].pk, self.pendency.pk)

    def test_admin_viewer_change_form_title_and_breadcrumb_show_real_identity(
        self,
    ):
        self.client.force_login(self.admin_viewer)
        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, self.inactive_linked_employee.full_name
        )


class FT45_InvalidPostRedisplayDoesNotLeakHiddenEmployeeIdentity(
    PendencyEmployeeFkAdminTestBase
):
    """FT45 (FVI-06): redisplay apos POST invalido (erro em campo ALHEIO
    ao employee) nao pode reintroduzir a identidade do funcionario
    inativo vinculado no <title>/breadcrumb."""

    def test_restricted_viewer_invalid_redisplay_keeps_identity_masked(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._change_url(),
            self._base_post_payload(
                employee=KEEP_CURRENT_TOKEN,
                action="action-invalida-fvi06",
            ),
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("action", form.errors)
        self.assertNotContains(
            response, self.inactive_linked_employee.full_name
        )
        self.assertContains(response, INACTIVE_EMPLOYEE_LABEL)


class FT46_SuccessMessageDoesNotLeakHiddenEmployeeIdentity(
    PendencyEmployeeFkAdminTestBase
):
    """FT46 (FVI-06): a mensagem de sucesso exibida apos salvar
    serializa str(obj) -- mesma identidade que o <select> ja mascara.
    Editar um campo ALHEIO ao employee (mantendo __keep_current__) nao
    pode revelar o nome do funcionario inativo vinculado nessa
    mensagem."""

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


class FT48_HistoryAndDeleteLinksSurviveIdentityMasking(PendencyEmployeeFkAdminTestBase):
    """FT48 (FVI-06b, correcao da regressao de navegacao): mesma regressao
    de FT47 (allocations), para AllocationPendencyAdmin.
    render_change_form. Diferente de LineAllocationAdmin
    (has_delete_permission sempre False), AllocationPendencyAdmin nao
    sobrescreve has_delete_permission -- o viewer desta fixture TEM a
    permissao tecnica (_grant_full_pendencies_perms concede todas as
    permissoes do app), entao o link "Apagar" deve estar PRESENTE e
    correto aqui (complementa o caso "ausente" ja coberto em FT47)."""

    def setUp(self):
        super().setUp()
        self.active_linked_pendency = AllocationPendency.objects.create(
            employee=self.active_employee,
            allocation=None,
            action=AllocationPendency.ActionType.NO_ACTION,
        )

    def _history_url(self, pk):
        return reverse("admin:pendencies_allocationpendency_history", args=[pk])

    def _delete_url(self, pk):
        return reverse("admin:pendencies_allocationpendency_delete", args=[pk])

    def test_restricted_viewer_history_link_has_exact_url(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        expected_href = f'href="{self._history_url(self.pendency.pk)}"'
        self.assertContains(response, expected_href)
        self.assertNotContains(response, 'class="historylink" href=""')
        self.assertNotContains(
            response, self.inactive_linked_employee.full_name
        )
        self.assertContains(response, INACTIVE_EMPLOYEE_LABEL)

    def test_restricted_viewer_following_history_link_reaches_correct_record(self):
        self.client.force_login(self.viewer)

        history_response = self.client.get(self._history_url(self.pendency.pk))

        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response.context["object"].pk, self.pendency.pk)

    def test_restricted_viewer_delete_link_has_exact_url_when_permitted(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        expected_href = f'href="{self._delete_url(self.pendency.pk)}"'
        self.assertContains(response, expected_href)
        self.assertNotContains(response, 'class="deletelink" href=""')

    def test_restricted_viewer_following_delete_link_reaches_correct_confirmation_page(
        self,
    ):
        """So navegacao/URL -- nenhuma exclusao e executada (sem POST de
        confirmacao)."""
        self.client.force_login(self.viewer)

        delete_response = self.client.get(self._delete_url(self.pendency.pk))

        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.context["object"].pk, self.pendency.pk)
        self.pendency.refresh_from_db()  # ainda existe: nenhuma exclusao ocorreu

    def test_restricted_viewer_invalid_redisplay_keeps_correct_history_url(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._change_url(),
            self._base_post_payload(
                employee=KEEP_CURRENT_TOKEN, action="action-invalida-fvi06b"
            ),
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("action", form.errors)
        expected_href = f'href="{self._history_url(self.pendency.pk)}"'
        self.assertContains(response, expected_href)

    def test_admin_viewer_history_link_has_exact_url_as_control(self):
        self.client.force_login(self.admin_viewer)
        response = self.client.get(self._change_url())

        self.assertEqual(response.status_code, 200)
        expected_href = f'href="{self._history_url(self.pendency.pk)}"'
        self.assertContains(response, expected_href)

    def test_restricted_viewer_active_employee_history_link_has_exact_url_as_control(
        self,
    ):
        self.client.force_login(self.viewer)
        url = reverse(
            "admin:pendencies_allocationpendency_change",
            args=[self.active_linked_pendency.pk],
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        expected_href = (
            f'href="{self._history_url(self.active_linked_pendency.pk)}"'
        )
        self.assertContains(response, expected_href)


class FT49_AllocationSelectorMasksHiddenEmployeeIdentity(
    PendencyEmployeeFkAdminTestBase
):
    """FT49 (P2-1, revisao FVI 2026-10-15): o <select> do campo
    "allocation" usa o rotulo padrao do ModelChoiceField
    (str(LineAllocation)), que inclui a identidade REAL do funcionario
    mesmo quando oculta pela excecao de FVI-04/06 -- achado registrado
    e NAO corrigido em FVI-06b ("Achado adicional descoberto durante o
    aceite em navegador"). A ELEGIBILIDADE das escolhas (queryset) nao e
    alterada por este teste -- so o ROTULO exibido."""

    def setUp(self):
        super().setUp()
        self.allocation_active = _make_allocation_for(self.active_employee, 20)
        self.allocation_inactive_linked = _make_allocation_for(
            self.inactive_linked_employee, 21
        )
        self.allocation_inactive_unlinked = _make_allocation_for(
            self.inactive_unlinked_employee, 22
        )
        self.pendency.allocation = self.allocation_inactive_linked
        self.pendency.save(update_fields=["allocation"])

    def test_restricted_viewer_can_open_add_form(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self._add_url())
        self.assertEqual(response.status_code, 200)

    def test_restricted_viewer_can_open_change_form(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self._change_url())
        self.assertEqual(response.status_code, 200)

    def test_restricted_viewer_allocation_options_mask_inactive_employee_identity(
        self,
    ):
        self.client.force_login(self.viewer)
        response = self.client.get(self._add_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, self.inactive_linked_employee.full_name
        )
        self.assertNotContains(
            response, self.inactive_unlinked_employee.full_name
        )
        self.assertContains(response, INACTIVE_EMPLOYEE_LABEL)

    def test_restricted_viewer_active_employee_allocation_label_shows_real_name_as_control(
        self,
    ):
        self.client.force_login(self.viewer)
        response = self.client.get(self._add_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.active_employee.full_name)

    def test_admin_viewer_allocation_options_show_real_identity(self):
        self.client.force_login(self.admin_viewer)
        response = self.client.get(self._add_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, self.inactive_linked_employee.full_name
        )
        self.assertContains(
            response, self.inactive_unlinked_employee.full_name
        )

    def test_restricted_viewer_existing_allocation_link_is_preserved_on_valid_post(
        self,
    ):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._change_url(),
            self._base_post_payload(
                employee=KEEP_CURRENT_TOKEN,
                allocation=str(self.allocation_inactive_linked.pk),
            ),
        )

        self.pendency.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.pendency.allocation_id, self.allocation_inactive_linked.pk
        )

    def test_restricted_viewer_invalid_redisplay_keeps_allocation_masking_and_error(
        self,
    ):
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._change_url(),
            self._base_post_payload(
                employee=KEEP_CURRENT_TOKEN,
                allocation=str(self.allocation_inactive_linked.pk),
                action="action-invalida-fvi07",
            ),
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("action", form.errors)
        self.assertNotContains(
            response, self.inactive_linked_employee.full_name
        )
        self.assertContains(response, INACTIVE_EMPLOYEE_LABEL)

    def test_switching_viewer_does_not_leak_masking_state_between_requests(self):
        self.client.force_login(self.viewer)
        restricted_response = self.client.get(self._add_url())
        self.assertNotContains(
            restricted_response, self.inactive_linked_employee.full_name
        )
        self.client.logout()

        self.client.force_login(self.admin_viewer)
        admin_response = self.client.get(self._add_url())
        self.assertContains(
            admin_response, self.inactive_linked_employee.full_name
        )
        self.client.logout()

        self.client.force_login(self.viewer)
        restricted_again = self.client.get(self._add_url())
        self.assertNotContains(
            restricted_again, self.inactive_linked_employee.full_name
        )

    def test_restricted_viewer_post_eligibility_of_new_allocation_choice_is_unchanged(
        self,
    ):
        """Nenhum filtro novo de elegibilidade: uma alocacao de
        funcionario inativo SEM vinculo previo com nenhuma pendencia
        continua uma escolha valida para "allocation" -- a correcao e
        apenas do ROTULO, nao do queryset/autorizacao."""
        self.client.force_login(self.viewer)

        response = self.client.post(
            self._add_url(),
            self._base_post_payload(
                employee=str(self.active_employee.pk),
                allocation=str(self.allocation_inactive_unlinked.pk),
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            AllocationPendency.objects.filter(
                allocation=self.allocation_inactive_unlinked
            ).exists()
        )

    def test_query_count_for_allocation_field_does_not_grow_with_allocation_volume(
        self,
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.client.force_login(self.viewer)

        with CaptureQueriesContext(connection) as baseline:
            self.client.get(self._add_url())
        baseline_count = len(baseline.captured_queries)

        for i in range(20):
            _make_allocation_for(self.active_employee, 100 + i)

        with self.assertNumQueries(baseline_count):
            self.client.get(self._add_url())


class FT50_DeleteConfirmationMasksHiddenEmployeeIdentity(
    PendencyEmployeeFkAdminTestBase
):
    """FT50 (P2-2, revisao FVI 2026-10-15): a confirmacao de exclusao
    (individual e em lote) usa get_deleted_objects/str(obj) diretamente
    (django/contrib/admin/utils.py, vendor), fora de render_change_form
    (ja corrigido em FVI-06/06b) -- achado registrado e NAO corrigido em
    FVI-06b. E fluxo OPERACIONAL (o viewer esta decidindo excluir um
    registro que ja esta autorizado a abrir), nao historico -- a
    classificacao anterior que o tratava como equivalente a pagina de
    historico foi retificada pela revisao."""

    def setUp(self):
        super().setUp()
        self.active_linked_pendency = AllocationPendency.objects.create(
            employee=self.active_employee,
            allocation=None,
            action=AllocationPendency.ActionType.NO_ACTION,
        )

    def _delete_url(self, pk):
        return reverse("admin:pendencies_allocationpendency_delete", args=[pk])

    def _changelist_url(self):
        return reverse("admin:pendencies_allocationpendency_changelist")

    def _batch_delete_payload(self, pks):
        return {
            "action": "delete_selected",
            helpers.ACTION_CHECKBOX_NAME: [str(pk) for pk in pks],
            "index": "0",
        }

    def test_restricted_viewer_individual_delete_confirmation_masks_identity(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self._delete_url(self.pendency.pk))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, self.inactive_linked_employee.full_name
        )
        self.assertContains(response, INACTIVE_EMPLOYEE_LABEL)
        self.assertEqual(response.context["object"].pk, self.pendency.pk)
        self.assertEqual(response.context["perms_lacking"], set())
        self.assertEqual(response.context["protected"], [])
        self.assertTrue(response.context["deleted_objects"])
        self.assertTrue(
            AllocationPendency.objects.filter(pk=self.pendency.pk).exists()
        )

    def test_admin_viewer_individual_delete_confirmation_shows_real_identity(self):
        self.client.force_login(self.admin_viewer)
        response = self.client.get(self._delete_url(self.pendency.pk))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, self.inactive_linked_employee.full_name
        )

    def test_restricted_viewer_active_employee_delete_confirmation_shows_real_name_as_control(
        self,
    ):
        self.client.force_login(self.viewer)
        response = self.client.get(
            self._delete_url(self.active_linked_pendency.pk)
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.active_employee.full_name)

    def test_restricted_viewer_batch_delete_confirmation_masks_identity(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            self._changelist_url(),
            self._batch_delete_payload([self.pendency.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, self.inactive_linked_employee.full_name
        )
        self.assertContains(response, INACTIVE_EMPLOYEE_LABEL)
        self.assertEqual(response.context["perms_lacking"], set())
        self.assertEqual(response.context["protected"], [])
        self.assertTrue(response.context["deletable_objects"])
        self.assertTrue(
            AllocationPendency.objects.filter(pk=self.pendency.pk).exists()
        )

    def test_admin_viewer_batch_delete_confirmation_shows_real_identity(self):
        self.client.force_login(self.admin_viewer)
        response = self.client.post(
            self._changelist_url(),
            self._batch_delete_payload([self.pendency.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, self.inactive_linked_employee.full_name
        )
