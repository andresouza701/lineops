from django import forms
from django.contrib import admin
from django.http import Http404

from core.normalization import normalize_email_address, normalize_full_name
from users.models import SystemUser
from users.visibility import (
    KEEP_CURRENT_LABEL,
    KEEP_CURRENT_TOKEN,
    KeepCurrentInvalidContext,
    account_is_hidden_for_viewer,
    account_text_field_initial,
    mask_inactive_email,
    redisplay_value_for_rejected_submission,
    resolve_account_text_field_post,
    resolve_all_inactive_emails_casefold,
)

from .models import Employee
from .visibility import visible_employees_queryset


def _persisted_text_field_value(form, field_name):
    if form.instance and form.instance.pk:
        return (
            normalize_email_address(getattr(form.instance, field_name, None)) or None
        )
    return None


def _guard_redisplay_of_hidden_value(field, viewer, persisted_email):
    """UVI-06c/UVI-06d (correcao): um valor FORJADO no POST que resolva
    para conta oculta nao pode ser ecoado de volta no <input
    value="..."> apos a rejeicao -- ver docstring equivalente em
    users/admin.py (mesmo mecanismo, bound_data so afeta representacao,
    nunca a validacao). O token so e usado quando HA, NESTE campo, um
    vinculo persistido tambem oculto (``persisted_email``); sem isso a
    representacao e vazia (achado UVI-06d)."""
    original_bound_data = field.bound_data

    def bound_data(data, initial, _orig=original_bound_data, _viewer=viewer, _persisted=persisted_email):
        override = redisplay_value_for_rejected_submission(_viewer, data, _persisted)
        if override is not None:
            return override
        return _orig(data, initial)

    field.bound_data = bound_data


class EmployeeAdminForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = "__all__"

    def __init__(self, *args, viewer=None, **kwargs):
        self._viewer = viewer
        super().__init__(*args, **kwargs)
        self._apply_keep_current_text_field("corporate_email")
        self._apply_keep_current_text_field("manager_email")

    def _apply_keep_current_text_field(self, field_name):
        """UVI-06 (correcao): quando o valor persistido deste campo esta
        oculto para o viewer, troca o TIPO do campo (EmailField ->
        CharField) -- mesmo padrao de EmployeeForm._configure_account_field
        e de users/admin.py -- para o marcador __keep_current__ passar
        pela validacao de formato de e-mail sem ser rejeitado antes de
        clean_<campo> rodar. ``initial`` passa a ser o token, nunca o
        e-mail real."""
        persisted = _persisted_text_field_value(self, field_name)
        initial = account_text_field_initial(self._viewer, persisted)
        if initial == KEEP_CURRENT_TOKEN:
            original_required = self.fields[field_name].required
            self.fields[field_name] = forms.CharField(
                required=original_required,
                widget=forms.TextInput(attrs={"class": "vTextField"}),
                help_text=KEEP_CURRENT_LABEL,
            )
            self.initial[field_name] = KEEP_CURRENT_TOKEN
        _guard_redisplay_of_hidden_value(self.fields[field_name], self._viewer, persisted)

    def clean_full_name(self):
        full_name = normalize_full_name(self.cleaned_data.get("full_name"))
        if not full_name:
            return full_name

        if Employee.has_active_full_name_conflict(
            full_name,
            exclude_id=self.instance.pk if self.instance and self.instance.pk else None,
        ):
            raise forms.ValidationError(
                "Ja existe um usuario cadastrado com este nome."
            )

        return full_name

    def clean_email(self):
        email = normalize_email_address(self.cleaned_data.get("email"))
        if not email:
            return None

        if Employee.has_active_email_conflict(
            email,
            exclude_id=self.instance.pk if self.instance and self.instance.pk else None,
        ):
            raise forms.ValidationError(
                "Ja existe um negociador cadastrado com este email."
            )

        return email

    def clean_corporate_email(self):
        return self._resolve_account_text_field("corporate_email") or ""

    def clean_manager_email(self):
        return self._resolve_account_text_field("manager_email")

    def _resolve_account_text_field(self, field_name):
        """UVI-04 (U07) + UVI-06 (correcao): EmployeeAdminForm e um caminho
        alternativo de associacao via texto livre (sem <select>). Resolve
        o marcador __keep_current__ a partir do valor persistido no banco
        (``self.instance`` ainda nao mutado nesta fase de ``clean()``),
        preserva o vinculo JA persistido (mesmo que a conta esteja
        inativa -- nao e uma NOVA associacao), e rejeita apontar para uma
        conta oculta diferente da atual."""
        raw_value = normalize_email_address(
            self.cleaned_data.get(field_name)
        ) or None
        persisted = _persisted_text_field_value(self, field_name)
        try:
            value = resolve_account_text_field_post(self._viewer, raw_value, persisted)
        except KeepCurrentInvalidContext:
            raise forms.ValidationError("Selecione uma conta ativa.")
        if value == persisted:
            return value
        if value and account_is_hidden_for_viewer(self._viewer, value):
            raise forms.ValidationError("Selecione uma conta ativa.")
        return value


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    form = EmployeeAdminForm

    search_fields = ("full_name", "email", "corporate_email", "employee_id", "teams")
    list_filter = ("status", "is_deleted", "teams")
    ordering = ("full_name",)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = request.user.scope_employee_queryset(queryset)
        return visible_employees_queryset(request.user, queryset)

    def _get_obj_does_not_exist_redirect(self, request, opts, object_id):
        """FVI-04 (mesmo hook generico de ModelAdmin ja comprovado em
        SystemUserAdmin, UVI-04): change/delete/history convergem aqui
        quando o objeto nao esta no queryset filtrado -- 404 generico,
        indistinguivel de ID inexistente, em vez do redirecionamento
        padrao do Django Admin."""
        raise Http404("Pagina nao encontrada.")

    def get_list_display(self, request):
        """UVI-06 (correcao): corporate_email na changelist nao pode expor
        identidade de conta inativa a viewer restrito. Projecao em lote
        (uma consulta por requisicao, capturada por closure -- nunca
        atribuida a self, nunca por linha/N+1). ADMIN/DEV veem a
        identidade real (set vazio, sem mascaramento)."""
        viewer = request.user
        inactive_emails = resolve_all_inactive_emails_casefold(viewer)

        def corporate_email_display(obj):
            return mask_inactive_email(obj.corporate_email, inactive_emails)

        corporate_email_display.short_description = "Supervisor"

        return (
            "full_name",
            "email",
            corporate_email_display,
            "employee_id",
            "teams",
            "status",
            "is_deleted",
            "created_at",
            "updated_at",
        )

    def get_form(self, request, obj=None, **kwargs):
        """UVI-04: injeta o viewer (request.user) no EmployeeAdminForm sem
        alterar a assinatura publica de ModelAdmin.get_form -- padrao usual
        do Django Admin para passar contexto de request a um ModelForm."""
        form_class = super().get_form(request, obj, **kwargs)
        viewer = request.user

        class ViewerBoundEmployeeAdminForm(form_class):
            def __init__(form_self, *args, **form_kwargs):
                form_kwargs.setdefault("viewer", viewer)
                super().__init__(*args, **form_kwargs)

        return ViewerBoundEmployeeAdminForm

    def get_deleted_objects(self, objs, request):
        deleted_objects = [str(obj) for obj in objs]
        model_count = {self.model._meta.verbose_name: len(deleted_objects)}
        perms_needed = set()
        protected = []
        return deleted_objects, model_count, perms_needed, protected

    def delete_model(self, request, obj):
        obj.delete()

    def delete_queryset(self, request, queryset):
        queryset.delete()
