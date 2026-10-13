from django.contrib import admin
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from telecom.seal_indicator import seal_indicator_for_phone_line

from .models import LineAllocation


@admin.register(LineAllocation)
class LineAllocationAdmin(admin.ModelAdmin):
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
        "phone_line_display",
        "allocated_at",
        "released_at",
        "is_active",
    )
    list_select_related = ("employee", "phone_line")
    list_filter = ("is_active", "allocated_at")
    search_fields = ("employee__full_name", "phone_line__phone_number")

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Phone line")
    def phone_line_display(self, obj):
        # Mesmo texto do __str__ de PhoneLine (nao alterado: "numero -
        # status"), com o indicador compartilhado de SVI-04 (I27) colado
        # ao NUMERO (ajuste aprovado 2026-10-11: indicador a esquerda do
        # numero, nao no inicio da string composta inteira). Objeto ja
        # carregado via list_select_related: sem consulta adicional por
        # linha.
        indicator_html = mark_safe(
            render_to_string(
                "telecom/_seal_indicator.html",
                {"indicator": seal_indicator_for_phone_line(obj.phone_line)},
            )
        )
        return format_html(
            "{}{} - {}", indicator_html, obj.phone_line.phone_number, obj.phone_line.status
        )
