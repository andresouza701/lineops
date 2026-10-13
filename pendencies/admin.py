from django.contrib import admin
from django.utils.html import format_html

from telecom.seal_indicator import render_seal_indicator_html

from .models import AllocationPendency


@admin.register(AllocationPendency)
class AllocationPendencyAdmin(admin.ModelAdmin):
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
