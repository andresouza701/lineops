from django import forms
from django.contrib import admin
from django.contrib.admin import helpers
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext

from core.current_user import get_current_user
from employees.visibility import (
    EmployeeLinkedDisplayProxy,
    apply_keep_current_to_employee_formfield,
    masked_employee_label,
    resolve_employee_fk_keep_current,
    wrap_admin_form_with_employee_keep_current,
)
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

    list_select_related = ("employee", "phone_line")
    list_filter = ("is_active", "allocated_at")
    search_fields = ("employee__full_name", "phone_line__phone_number")

    def has_delete_permission(self, request, obj=None):
        return False

    def get_list_display(self, request):
        """FVI-06 (fechamento do achado 1 da conferencia corretiva de
        FVI-05): a coluna "employee" da changelist nao pode expor a
        identidade de um funcionario inativo a um viewer restrito --
        mesma inconsistencia ja corrigida no <select> do campo (FVI-04),
        agora tambem na apresentacao somente-leitura. Projecao por
        linha via closure (sem consulta adicional: ``obj.employee`` ja
        vem carregado por ``list_select_related``, apenas o atributo
        ``status`` em memoria decide o rotulo)."""
        viewer = request.user

        def employee_display(obj):
            return masked_employee_label(viewer, obj.employee)

        employee_display.short_description = "Employee"
        employee_display.admin_order_field = "employee"

        return (
            employee_display,
            "phone_line_display",
            "allocated_at",
            "released_at",
            "is_active",
        )

    def render_change_form(
        self, request, context, add=False, change=False, form_url="", obj=None
    ):
        """FVI-06: quando o vinculo "employee" persistido deste registro
        esta oculto para o viewer (``_masked_employee_pk``), sobrescreve
        ``subtitle`` (usado no <title> da pagina pelo admin/base_site.html)
        e ``original`` (usado no ultimo segmento do breadcrumb pelo
        change_form.html, via ``str(original)``) para a mesma
        representacao mascarada -- cobre GET normal e redisplay apos
        POST invalido (ambos passam por este hook). Nao mutamos o obj
        persistido nem seu __str__; apenas o CONTEXTO desta resposta.

        FVI-06b (correcao de regressao): ``original`` tambem e consumido
        por ``original.pk`` nos templates instalados do Django
        (``change_form_object_tools.html`` -- link "Historico";
        ``submit_line.html`` -- link "Apagar"), nao apenas por
        ``str(original)`` no breadcrumb. Atribuir uma STRING simples
        quebrava esses dois links (``href=""``, pk ausente numa string).
        ``EmployeeLinkedDisplayProxy`` (mesmo mecanismo ja usado em
        ``response_change``) preserva ``obj`` real -- e portanto `.pk` --
        delegando tudo exceto ``__str__``."""
        if obj is not None and self._masked_employee_pk(request) is not None:
            masked_text = self._masked_str(request.user, obj)
            context["subtitle"] = masked_text
            context["original"] = EmployeeLinkedDisplayProxy(obj, masked_text)
        return super().render_change_form(
            request, context, add=add, change=change, form_url=form_url, obj=obj
        )

    def response_change(self, request, obj):
        """FVI-06: a mensagem de sucesso pos-save ("The line allocation
        ... was changed successfully.") serializa ``str(obj)`` -- mesma
        identidade que o <select> ja mascara. Envolve ``obj`` num proxy
        transparente (``EmployeeLinkedDisplayProxy``) apenas para esta
        chamada, sem alterar o objeto persistido nem o LogEntry de
        historico (que e construido antes deste hook, com o __str__
        real, preservando auditoria)."""
        if self._masked_employee_pk(request) is not None:
            obj = EmployeeLinkedDisplayProxy(obj, self._masked_str(request.user, obj))
        return super().response_change(request, obj)

    def action_checkbox(self, obj):
        """FVI-06: o checkbox de acao em lote da changelist (coluna
        automatica inserida por ``get_changelist_instance``) tambem
        serializa ``str(obj)`` no atributo ``aria-label`` -- vazamento
        de acessibilidade/DOM-source, nao visivel no texto renderizado,
        mas presente no HTML. Este hook publico de ModelAdmin NAO
        recebe ``request`` (assinatura ``(self, obj)``, chamado por
        ``lookup_field`` sem contexto de requisicao); usa o thread-local
        ``get_current_user`` ja estabelecido pelo projeto
        (``core.middleware.CurrentUserMiddleware``, sem introduzir novo
        mecanismo) para obter o viewer, sem mutar ``self``/estado
        compartilhado do ModelAdmin."""
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
        return f"{masked_employee_label(viewer, obj.employee)} - {obj.phone_line}"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "employee":
            return self._employee_field(db_field, request, **kwargs)
        if db_field.name in AUTHOR_FK_FIELDS:
            kwargs["queryset"] = self._visible_author_queryset(
                request, db_field.name
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        """FVI-04: mesmo padrao ja usado por AllocationPendencyAdmin para
        technical_responsible -- quando o vinculo persistido de
        "employee" esta oculto para o viewer, o initial precisa do
        marcador neutro (o PK real nao esta mais entre as choices)."""
        form_class = super().get_form(request, obj, **kwargs)
        masked_id = self._masked_employee_pk(request)
        return wrap_admin_form_with_employee_keep_current(form_class, masked_id)

    def _employee_field(self, db_field, request, **kwargs):
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
        persisted_id = self._persisted_fk_id(request, field_name)
        if persisted_id:
            visible = visible | base.filter(pk=persisted_id)
        return visible.distinct()

    def _persisted_fk_id(self, request, field_name):
        object_id = request.resolver_match.kwargs.get("object_id") if request.resolver_match else None
        if not object_id:
            return None
        return (
            LineAllocation.objects.filter(pk=object_id)
            .values_list(field_name, flat=True)
            .first()
        )

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
