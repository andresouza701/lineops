from django import forms
from django.contrib import admin
from django.contrib.admin import helpers
from django.contrib.admin.utils import NestedObjects, quote
from django.db import router
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html
from django.utils.text import capfirst
from django.utils.translation import gettext

from core.current_user import get_current_user
from employees.visibility import (
    EmployeeLinkedDisplayProxy,
    apply_keep_current_to_employee_formfield,
    employee_is_visible,
    masked_employee_label,
    resolve_employee_fk_keep_current,
)
from telecom.origin_restriction import is_origin_blocked_for_opening, origin_open_block_reason
from telecom.seal_indicator import render_seal_indicator_html
from users.models import SystemUser
from users.visibility import (
    KEEP_CURRENT_LABEL,
    KEEP_CURRENT_TOKEN,
    mask_inactive_email,
    resolve_all_inactive_emails_casefold,
    visible_accounts_queryset,
)

from .models import AllocationPendency

# UVI-06 (correcao): technical_responsible ("Responsavel Tecnico") e uma
# referencia OPERACIONAL -- quem esta tratando a pendencia agora, campo
# que o contrato trata como seletor/associacao, por isso recebe opcao
# neutra quando o vinculo persistido estiver oculto para o viewer (nao
# expor a identidade real no <option>). updated_by ("Atualizado por") e
# metadado de AUTORIA/historico -- quem alterou o registro por ultimo --
# mesma categoria de allocated_by/released_by em LineAllocationAdmin
# (U13, ja aprovado: novas escolhas obedecem visibilidade, referencia
# historica EXIBIDA permanece, sem mascaramento) -- a excecao historica
# aprovada pelo contrato (UVI-01/02: "Preservar identidades em
# historico, auditoria e relatorios") se aplica a ele: mesmo mecanismo
# de LineAllocationAdmin, nunca o mascaramento neutro de
# technical_responsible.
OPERATIONAL_RESPONSIBLE_FK_FIELDS = ("technical_responsible",)
HISTORICAL_AUTHOR_FK_FIELDS = ("updated_by",)


class AllocationPendencyAdminForm(forms.ModelForm):
    """Decisão 1A (Fechamento 2026-10-13): o Admin não é exceção à regra
    de origem. Compara o `action` persistido ANTES desta requisição
    (self.instance, ainda não mutado pelo ModelForm nesta fase de
    clean() — construct_instance só ocorre depois, em _post_clean())
    com o valor proposto em cleaned_data, para decidir se é uma
    transição de abertura/reabertura.

    A origem avaliada é a da allocation PROPOSTA neste mesmo POST
    (`cleaned_data["allocation"]`), nunca a allocation antiga de
    `self.instance` — conferência corretiva de POR-04: usar a antiga
    ignorava troca simultânea de linha (permitia abrir trocando para uma
    origem bloqueada, e bloqueava indevidamente ao trocar de uma origem
    bloqueada para uma permitida) e, numa criação nova (`self.instance.pk`
    ainda None), nunca avaliava origem alguma."""

    class Meta:
        model = AllocationPendency
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        new_action = cleaned_data.get("action")
        old_action = (
            self.instance.action
            if self.instance.pk
            else AllocationPendency.ActionType.NO_ACTION
        )
        was_no_action = old_action == AllocationPendency.ActionType.NO_ACTION
        will_be_no_action = (
            new_action == AllocationPendency.ActionType.NO_ACTION or not new_action
        )
        if was_no_action and not will_be_no_action:
            proposed_allocation = cleaned_data.get("allocation")
            phone_line = (
                proposed_allocation.phone_line if proposed_allocation else None
            )
            if is_origin_blocked_for_opening(phone_line):
                raise forms.ValidationError(origin_open_block_reason(phone_line))
        return cleaned_data


@admin.register(AllocationPendency)
class AllocationPendencyAdmin(admin.ModelAdmin):
    form = AllocationPendencyAdminForm

    class Media:
        # SVI-07 (checagem final): so o CSS ESCOPADO do indicador — o
        # arquivo inteiro (static/css/styles.css) vazava regras globais
        # para os controles nativos do Admin (achado real, ver
        # docs/superpowers/evidence/SVI-07/admin_css_check/). Sem este
        # arquivo, o indicador fica no DOM mas sem forma/cor/foco (ver
        # telecom/test_seal_indicator_admin_styles_svi07.py).
        css = {"all": ("css/seal_indicator.css",)}

    # SVI-07 (correcao do N+1 confirmado na revisao final do diff):
    # "employee" (list_display) e FK direta neste model. Antes desta
    # feature, o Admin resolvia 1 query total (select_related()
    # automatico do Django quando list_select_related nao e declarado —
    # ver ChangeList.apply_select_related/has_related_field_in_list_
    # display). Ao declarar list_select_related explicitamente para
    # cobrir allocation/allocation__phone_line/allocation__employee (selo
    # compartilhado), essa automacao foi DESLIGADA e "employee" ficou de
    # fora — 1 query extra por linha desde entao, nao antes da feature.
    # Corrigido incluindo "employee" na mesma lista explicita.
    list_select_related = (
        "employee",
        "allocation",
        "allocation__phone_line",
        "allocation__employee",
    )
    list_filter = ("action",)
    search_fields = ("employee__full_name",)

    def get_list_display(self, request):
        """UVI-06 (correcao): technical_responsible na changelist nao pode
        expor identidade de conta inativa a viewer restrito (campo
        operacional, mesma excecao ADMIN/DEV das demais colunas
        mascaradas). updated_by nao esta em list_display, inalterado.
        Projecao em lote (uma consulta por requisicao, capturada por
        closure -- nunca atribuida a self, nunca por linha/N+1 novo: o
        acesso a obj.technical_responsible ja ocorria na coluna padrao)."""
        viewer = request.user
        inactive_emails = resolve_all_inactive_emails_casefold(viewer)

        def technical_responsible_display(obj):
            responsible = obj.technical_responsible
            if responsible is None:
                return self.get_empty_value_display()
            return mask_inactive_email(responsible.email, inactive_emails)

        technical_responsible_display.short_description = "Responsável Técnico"

        # FVI-06 (fechamento do achado 1 da conferencia corretiva de
        # FVI-05): "employee" (coluna direta) e o funcionario embutido em
        # "allocation_display" (via obj.allocation.employee) nao podem
        # expor a identidade de um funcionario inativo a um viewer
        # restrito -- mesma inconsistencia ja corrigida no <select> do
        # campo (FVI-04), agora tambem na apresentacao somente-leitura.
        # Sem consulta adicional: ambos os objetos ja vem carregados por
        # list_select_related, apenas o atributo status em memoria
        # decide o rotulo.
        def employee_display(obj):
            return masked_employee_label(viewer, obj.employee)

        employee_display.short_description = "Employee"
        employee_display.admin_order_field = "employee"

        return (
            employee_display,
            "allocation_display",
            "action",
            technical_responsible_display,
            "pendency_submitted_at",
            "resolved_at",
            "updated_at",
        )

    def get_form(self, request, obj=None, **kwargs):
        """UVI-06c (correcao): quando technical_responsible esta mascarado
        (vinculo persistido oculto para o viewer), model_to_dict(instance)
        preencheria form.initial com o PK REAL -- isto faria o <select>
        nao marcar nenhuma option como selected (a option real foi
        removida do queryset em _technical_responsible_field) e, pior,
        um POST sem alteracao do cliente reenviaria aquele PK oculto
        diretamente. initial precisa ser sobrescrito para o token, mesmo
        padrao ja usado em SystemUserAdmin/EmployeeAdminForm para os
        campos de texto livre."""
        form_class = super().get_form(request, obj, **kwargs)
        masked_fields = {}
        if self._masked_technical_responsible_pk(request) is not None:
            masked_fields["technical_responsible"] = KEEP_CURRENT_TOKEN
        if self._masked_employee_pk(request) is not None:
            masked_fields["employee"] = KEEP_CURRENT_TOKEN

        if not masked_fields:
            return form_class

        class AllocationPendencyAdminFormWithKeepCurrent(form_class):
            def __init__(form_self, *args, **init_kwargs):
                super().__init__(*args, **init_kwargs)
                form_self.initial.update(masked_fields)

        return AllocationPendencyAdminFormWithKeepCurrent

    def _masked_technical_responsible_pk(self, request):
        viewer = request.user
        persisted_id = self._persisted_fk_id(request, "technical_responsible")
        if not persisted_id:
            return None
        visible = visible_accounts_queryset(viewer, SystemUser.objects.all())
        if visible.filter(pk=persisted_id).exists():
            return None
        return persisted_id

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "employee":
            return self._employee_field(db_field, request, **kwargs)
        if db_field.name == "allocation":
            return self._allocation_field(db_field, request, **kwargs)
        if db_field.name in OPERATIONAL_RESPONSIBLE_FK_FIELDS:
            return self._technical_responsible_field(db_field, request, **kwargs)
        if db_field.name in HISTORICAL_AUTHOR_FK_FIELDS:
            kwargs["queryset"] = self._visible_historical_author_queryset(
                request, db_field.name
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def _allocation_field(self, db_field, request, **kwargs):
        """P2-1 (achado confirmado na revisao de FVI-06b, registrado e NAO
        corrigido naquela etapa -- "Achado adicional descoberto durante o
        aceite em navegador"): o <select> de "allocation" usava o rotulo
        padrao do ModelChoiceField (str(LineAllocation)), que inclui a
        identidade REAL do funcionario mesmo quando oculta pela excecao de
        FVI-04/06 -- unico FK de employee sem tratamento equivalente. A
        ELEGIBILIDADE das escolhas (queryset) NAO e alterada por esta
        correcao -- contrato nao define uma regra de elegibilidade
        diferente da ja existente, e o mascaramento autorizado pode
        avancar independentemente dela (decisao registrada na spec).
        Troca apenas o ROTULO exibido via label_from_instance, preservando
        o phone_line (necessario para distinguir alocacoes do mesmo
        rotulo mascarado). select_related evita N+1 ao montar as
        <option> (cada rotulo acessa allocation.employee/phone_line)."""
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if formfield is not None and formfield.queryset is not None:
            viewer = request.user
            formfield.queryset = formfield.queryset.select_related(
                "employee", "phone_line"
            )
            formfield.label_from_instance = (
                lambda obj: self._masked_allocation_label(viewer, obj)
            )
        return formfield

    def _masked_allocation_label(self, viewer, allocation):
        return (
            f"{masked_employee_label(viewer, allocation.employee)} - "
            f"{allocation.phone_line}"
        )

    def _employee_field(self, db_field, request, **kwargs):
        """FVI-04: mesmo mecanismo ja aprovado para technical_responsible
        -- opcao sintetica __keep_current__ quando o vinculo persistido
        esta oculto para o viewer, sem reincluir identidade oculta nas
        choices."""
        persisted_id = self._persisted_fk_id(request, "employee")
        visible, masked_id = resolve_employee_fk_keep_current(
            request.user, persisted_id
        )
        kwargs["queryset"] = visible.distinct()
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        return apply_keep_current_to_employee_formfield(formfield, masked_id)

    def _masked_employee_pk(self, request):
        persisted_id = self._persisted_fk_id(request, "employee")
        _, masked_id = resolve_employee_fk_keep_current(request.user, persisted_id)
        return masked_id

    def _visible_historical_author_queryset(self, request, field_name):
        """UVI-06 (correcao): updated_by e autoria historica (U13/U14),
        mesmo mecanismo de LineAllocationAdmin._visible_author_queryset --
        novas escolhas filtradas por visibilidade, vinculo JA persistido
        reincluido e EXIBIDO com a identidade real (sem mascaramento: a
        excecao historica preserva autoria, nao oculta conta operacional,
        contrato U13 ja aprovado, aplicado aqui pela mesma razao)."""
        base = SystemUser.objects.all()
        visible = visible_accounts_queryset(request.user, base)
        persisted_id = self._persisted_fk_id(request, field_name)
        if persisted_id:
            visible = visible | base.filter(pk=persisted_id)
        return visible.distinct()

    def _persisted_fk_id(self, request, field_name):
        object_id = (
            request.resolver_match.kwargs.get("object_id")
            if request.resolver_match
            else None
        )
        if not object_id:
            return None
        return (
            AllocationPendency.objects.filter(pk=object_id)
            .values_list(field_name, flat=True)
            .first()
        )

    def _technical_responsible_field(self, db_field, request, **kwargs):
        """UVI-06c (correcao): technical_responsible e referencia
        operacional (quem esta tratando a pendencia). Novas escolhas
        continuam filtradas por visibilidade (visible_accounts_queryset).
        Achado real de UVI-06: a entrega anterior reincluia o pk oculto
        no queryset e so trocava o ROTULO (label_from_instance) -- o
        <option value="..."> continuava carregando o PK REAL da conta
        oculta (``<option value="1" selected>Manter vinculo atual
        </option>``), violando "token __keep_current__, sem transportar
        o ID da conta oculta como opcao". Corrigido: o pk oculto NUNCA
        entra no queryset/choices; quando o vinculo persistido esta
        oculto, uma opcao SINTETICA (valor literal KEEP_CURRENT_TOKEN,
        rotulo KEEP_CURRENT_LABEL) e adicionada, e ``to_python`` resolve
        esse token para o SystemUser realmente persistido NESTE registro
        (relido do banco a cada requisicao via ``object_id`` da URL,
        nunca de pk enviado pelo cliente) -- o token nunca chega a FK
        persistida, que recebe sempre o objeto real resolvido no
        servidor. POST com pk de outro inativo (fora do queryset e
        diferente do token) continua recusado pelo ModelChoiceField
        padrao, sem qualquer reinclusao de identidade oculta."""
        viewer = request.user
        base = SystemUser.objects.all()
        visible = visible_accounts_queryset(viewer, base)
        masked_pk = self._masked_technical_responsible_pk(request)
        kwargs["queryset"] = visible.distinct()
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if masked_pk is not None and formfield is not None:
            formfield.choices = [
                (KEEP_CURRENT_TOKEN, KEEP_CURRENT_LABEL)
            ] + list(formfield.choices)
            original_to_python = formfield.to_python

            def to_python(value, _orig=original_to_python, _pk=masked_pk):
                if value == KEEP_CURRENT_TOKEN:
                    return SystemUser.objects.filter(pk=_pk).first()
                return _orig(value)

            formfield.to_python = to_python
        return formfield

    @admin.display(description="Allocation")
    def allocation_display(self, obj):
        """FVI-06: metodo vinculado (nao closure) de propósito --
        preserva a assinatura ``(self, obj)`` ja exercitada diretamente
        por teste permanente pre-existente
        (test_seal_indicator_admin_nullable_allocation_svi07.py,
        ``admin_instance.allocation_display(pendency)`` sem request).
        Usa o mesmo thread-local ``get_current_user`` de
        ``action_checkbox`` para obter o viewer sem exigir request na
        assinatura publica deste hook do ModelAdmin."""
        return self._masked_allocation_display(get_current_user(), obj)

    def _masked_allocation_display(self, viewer, obj):
        # Telefone indireto via LineAllocation.__str__ (I28, nao alterado
        # -- este metodo so compoe a APRESENTACAO da coluna, nunca o
        # __str__ do model) + indicador compartilhado de SVI-04. Objeto
        # ja carregado via list_select_related: sem consulta adicional
        # por linha. SVI-07 (revisao final do diff): AllocationPendency.
        # allocation admite null (pendencia de funcionario sem linha) —
        # sem guarda, obj.allocation.phone_line levantava AttributeError.
        # Ausencia usa o mesmo "-" padrao do proprio Admin
        # (get_empty_value_display), nao um telefone/selo inventado.
        if obj.allocation is None:
            return self.get_empty_value_display()
        # Mesmo texto do __str__ de LineAllocation (nao alterado:
        # "funcionario - numero - status"), com o indicador colado ao
        # NUMERO (ajuste aprovado 2026-10-11), nao ao inicio da string
        # composta inteira (que comecaria pelo funcionario). FVI-06:
        # funcionario trocado por masked_employee_label -- rotulo neutro
        # quando obj.allocation.employee esta oculto para o viewer.
        phone_line = obj.allocation.phone_line
        return format_html(
            "{} - {}{} - {}",
            masked_employee_label(viewer, obj.allocation.employee),
            render_seal_indicator_html(phone_line),
            phone_line.phone_number,
            phone_line.status,
        )

    def render_change_form(
        self, request, context, add=False, change=False, form_url="", obj=None
    ):
        """FVI-06: mesmo hook/raciocinio de LineAllocationAdmin -- quando
        o vinculo "employee" persistido deste registro esta oculto para
        o viewer, sobrescreve ``subtitle`` (<title>) e ``original``
        (ultimo segmento do breadcrumb) para a representacao mascarada,
        cobrindo GET normal e redisplay apos POST invalido.

        FVI-06b (correcao de regressao): mesmo achado de
        LineAllocationAdmin -- ``original.pk`` e consumido pelos links
        "Historico"/"Apagar" dos templates instalados do Django; uma
        STRING simples quebrava os dois (``href=""``).
        ``EmployeeLinkedDisplayProxy`` preserva `obj` real (e `.pk`),
        trocando somente ``__str__``."""
        if obj is not None and self._masked_employee_pk(request) is not None:
            masked_text = self._masked_str(request.user, obj)
            context["subtitle"] = masked_text
            context["original"] = EmployeeLinkedDisplayProxy(obj, masked_text)
        return super().render_change_form(
            request, context, add=add, change=change, form_url=form_url, obj=obj
        )

    def response_change(self, request, obj):
        """FVI-06: mesmo hook de LineAllocationAdmin -- a mensagem de
        sucesso pos-save serializa ``str(obj)``; envolve ``obj`` num
        proxy transparente apenas para esta chamada, sem alterar o
        objeto persistido nem o LogEntry de historico (construido antes
        deste hook, com o __str__ real, preservando auditoria)."""
        if self._masked_employee_pk(request) is not None:
            obj = EmployeeLinkedDisplayProxy(obj, self._masked_str(request.user, obj))
        return super().response_change(request, obj)

    def action_checkbox(self, obj):
        """FVI-06: mesmo hook/raciocinio de LineAllocationAdmin -- o
        checkbox de acao em lote tambem serializa ``str(obj)`` no
        ``aria-label``. Sem ``request`` na assinatura; usa o
        thread-local ``get_current_user`` ja estabelecido pelo projeto
        (``core.middleware.CurrentUserMiddleware``)."""
        checkbox = forms.CheckboxInput(
            {
                "class": "action-select",
                "aria-label": format_html(
                    gettext("Select this object for an action - {}"),
                    self._masked_str(get_current_user(), obj),
                ),
            },
            lambda value: False,
        )
        return checkbox.render(helpers.ACTION_CHECKBOX_NAME, str(obj.pk))

    def _masked_str(self, viewer, obj):
        allocation_info = (
            obj.allocation.phone_line.phone_number
            if obj.allocation and obj.allocation.phone_line_id
            else "sem linha"
        )
        return (
            f"{masked_employee_label(viewer, obj.employee)} / "
            f"{allocation_info} — {obj.get_action_display()}"
        )

    def render_delete_form(self, request, context):
        """P2-2 (achado confirmado na revisao de FVI-06b, registrado e NAO
        corrigido naquela etapa): delete_view usa context["object"] para
        o breadcrumb (object.pk no link "change", str(object) truncado) e
        para o texto de confirmacao (escaped_object=object), vendor
        admin/delete_confirmation.html -- fora de render_change_form (ja
        corrigido em FVI-06/06b: aquele hook so cobre change_form, nunca
        delete_confirmation). E fluxo OPERACIONAL (o viewer ja esta
        autorizado a abrir este registro), nao historico -- retificacao
        da classificacao anterior. Mesmo mecanismo de render_change_form:
        EmployeeLinkedDisplayProxy preserva o obj real (.pk, usado pelo
        link de breadcrumb), troca somente __str__."""
        obj = context.get("object")
        if obj is not None and not employee_is_visible(request.user, obj.employee):
            context["object"] = EmployeeLinkedDisplayProxy(
                obj, self._masked_str(request.user, obj)
            )
        return super().render_delete_form(request, context)

    def get_deleted_objects(self, objs, request):
        """P2-2: get_deleted_objects (vendor,
        django/contrib/admin/utils.py:123) e a acao delete_selected
        (vendor, django/contrib/admin/actions.py:19) compoem a lista
        "Objetos" da confirmacao de exclusao (individual E em lote) via
        "%s: %s" % (verbose_name, obj) / format_html(..., obj) -- ambos
        chamam str(obj) diretamente, mesmo vazamento de render_delete_form
        acima, porem na ESTRUTURA de colecao/autorizacao, nao no contexto
        simples. Separa projecao visual de colecao: reutiliza
        NestedObjects (Collector real do Django, inalterado -- a mesma
        verificacao de has_delete_permission por objeto, protected e
        model_count), substituindo somente a STRING exibida por objeto
        (via self._masked_str, mesmo helper de action_checkbox/
        response_change/render_delete_form) quando o objeto e uma
        AllocationPendency com vinculo employee oculto para o viewer --
        nunca remove objeto da lista, nunca altera pk/URL/permissao.
        PendencyObservationNotification aponta para AllocationPendency
        com on_delete=CASCADE: a colecao pode aninhar notificacoes.
        Para outros tipos, o format_callback preserva str(obj), como
        no Django original, sem omitir objetos ou alterar a cascata."""
        objs = list(objs)
        if not objs:
            return [], {}, set(), []
        viewer = request.user
        using = router.db_for_write(objs[0]._meta.model)
        collector = NestedObjects(using=using, origin=objs)
        collector.collect(objs)
        perms_needed = set()
        admin_site = self.admin_site

        def format_callback(obj):
            model = obj.__class__
            opts = obj._meta
            display = (
                self._masked_str(viewer, obj)
                if isinstance(obj, AllocationPendency)
                else str(obj)
            )
            no_edit_link = "%s: %s" % (capfirst(opts.verbose_name), display)
            if admin_site.is_registered(model):
                if not admin_site.get_model_admin(model).has_delete_permission(
                    request, obj
                ):
                    perms_needed.add(opts.verbose_name)
                try:
                    admin_url = reverse(
                        "%s:%s_%s_change"
                        % (admin_site.name, opts.app_label, opts.model_name),
                        None,
                        (quote(obj.pk),),
                    )
                except NoReverseMatch:
                    return no_edit_link
                return format_html(
                    '{}: <a href="{}">{}</a>',
                    capfirst(opts.verbose_name),
                    admin_url,
                    display,
                )
            return no_edit_link

        to_delete = collector.nested(format_callback)
        protected = [format_callback(obj) for obj in collector.protected]
        model_count = {
            model._meta.verbose_name_plural: len(model_objs)
            for model, model_objs in collector.model_objs.items()
        }
        return to_delete, model_count, perms_needed, protected

    readonly_fields = (
        "created_at",
        "updated_at",
        "last_action_changed_at",
        "pendency_submitted_at",
        "resolved_at",
    )
