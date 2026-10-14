from django import forms
from django.contrib import admin
from django.utils.html import format_html

from telecom.origin_restriction import is_origin_blocked_for_opening, origin_open_block_reason
from telecom.seal_indicator import render_seal_indicator_html

from .models import AllocationPendency


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

    list_display = (
        "employee",
        "allocation_display",
        "action",
        "technical_responsible",
        "pendency_submitted_at",
        "resolved_at",
        "updated_at",
    )
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
