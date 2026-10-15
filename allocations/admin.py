from django.contrib import admin
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from telecom.seal_indicator import seal_indicator_for_phone_line
from users.models import SystemUser
from users.visibility import visible_accounts_queryset

from .models import LineAllocation

AUTHOR_FK_FIELDS = ("allocated_by", "released_by")


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

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name in AUTHOR_FK_FIELDS:
            kwargs["queryset"] = self._visible_author_queryset(
                request, db_field.name
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def _visible_author_queryset(self, request, field_name):
        """UVI-04: novas escolhas de autoria (allocated_by/released_by)
        obedecem visibilidade (SUPER/BACKOFFICE/GERENTE/OPERATOR nao veem
        contas inativas sem vinculo com o registro). O vinculo JA
        persistido no objeto aberto continua disponivel -- preserva
        autoria historica sem exigir que o autor atual esteja ativo
        (contrato: "Manter autor existente nao deve remover FK nem
        impedir edicao alheia")."""
        base = SystemUser.objects.all()
        visible = visible_accounts_queryset(request.user, base)

        object_id = request.resolver_match.kwargs.get("object_id") if request.resolver_match else None
        if object_id:
            persisted_id = (
                LineAllocation.objects.filter(pk=object_id)
                .values_list(field_name, flat=True)
                .first()
            )
            if persisted_id:
                visible = visible | base.filter(pk=persisted_id)
        return visible.distinct()

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
