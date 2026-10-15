from django import forms
from django.contrib import admin
from django.utils.html import format_html

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

        return (
            "employee",
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
        masked_pk = self._masked_technical_responsible_pk(request)

        if masked_pk is None:
            return form_class

        class AllocationPendencyAdminFormWithKeepCurrent(form_class):
            def __init__(form_self, *args, **init_kwargs):
                super().__init__(*args, **init_kwargs)
                form_self.initial["technical_responsible"] = KEEP_CURRENT_TOKEN

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
        if db_field.name in OPERATIONAL_RESPONSIBLE_FK_FIELDS:
            return self._technical_responsible_field(db_field, request, **kwargs)
        if db_field.name in HISTORICAL_AUTHOR_FK_FIELDS:
            kwargs["queryset"] = self._visible_historical_author_queryset(
                request, db_field.name
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

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
        # Telefone indireto via LineAllocation.__str__ (I28, nao alterado)
        # + indicador compartilhado de SVI-04. Objeto ja carregado via
        # list_select_related: sem consulta adicional por linha.
        # SVI-07 (revisao final do diff): AllocationPendency.allocation
        # admite null (pendencia de funcionario sem linha) — sem guarda,
        # obj.allocation.phone_line levantava AttributeError. Ausencia
        # usa o mesmo "-" padrao do proprio Admin (get_empty_value_
        # display), nao um telefone/selo inventado.
        if obj.allocation is None:
            return self.get_empty_value_display()
        # Mesmo texto do __str__ de LineAllocation (nao alterado:
        # "funcionario - numero - status"), com o indicador colado ao
        # NUMERO (ajuste aprovado 2026-10-11), nao ao inicio da string
        # composta inteira (que comecaria pelo funcionario).
        phone_line = obj.allocation.phone_line
        return format_html(
            "{} - {}{} - {}",
            obj.allocation.employee,
            render_seal_indicator_html(phone_line),
            phone_line.phone_number,
            phone_line.status,
        )
    readonly_fields = (
        "created_at",
        "updated_at",
        "last_action_changed_at",
        "pendency_submitted_at",
        "resolved_at",
    )
