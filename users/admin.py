from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.http import Http404

from core.normalization import normalize_email_address

from .models import SystemUser
from .visibility import (
    KEEP_CURRENT_LABEL,
    KEEP_CURRENT_TOKEN,
    KeepCurrentInvalidContext,
    account_is_hidden_for_viewer,
    account_text_field_initial,
    mask_inactive_email,
    redisplay_value_for_rejected_submission,
    resolve_account_text_field_post,
    resolve_all_inactive_emails_casefold,
    visible_accounts_queryset,
)


def _persisted_text_field_value(form, field_name):
    if form.instance and form.instance.pk:
        return (
            normalize_email_address(getattr(form.instance, field_name, None)) or None
        )
    return None


def _apply_keep_current_text_field(form, field_name, viewer):
    """UVI-06 (correcao): quando o valor persistido deste campo esta
    oculto para o viewer, troca o TIPO do campo (EmailField -> CharField)
    -- igual ao padrao ja usado em EmployeeForm._configure_account_field
    -- para o marcador __keep_current__ passar pela validacao de formato
    de e-mail do ModelForm sem ser rejeitado antes de clean_<campo>
    rodar. ``initial`` passa a ser o token, nunca o e-mail real: a
    identidade nunca chega ao HTML renderizado (value="" do input)."""
    persisted = _persisted_text_field_value(form, field_name)
    initial = account_text_field_initial(viewer, persisted)
    if initial == KEEP_CURRENT_TOKEN:
        original_required = form.fields[field_name].required
        form.fields[field_name] = forms.CharField(
            required=original_required,
            widget=forms.TextInput(attrs={"class": "vTextField"}),
            help_text=KEEP_CURRENT_LABEL,
        )
        form.initial[field_name] = KEEP_CURRENT_TOKEN
    _guard_redisplay_of_hidden_value(form.fields[field_name], viewer, persisted)


def _guard_redisplay_of_hidden_value(field, viewer, persisted_email):
    """UVI-06c/UVI-06d (correcao): um valor FORJADO no POST que resolva
    para uma conta oculta nao pode ser ecoado de volta no <input
    value="..."> apos a rejeicao. ``bound_data`` so afeta a
    REPRESENTACAO (``BoundField.value()``) -- a validacao real
    (``_clean_fields``) le ``bf.data`` diretamente e nunca passa por
    aqui, entao a entrada original continua sendo validada e recusada
    normalmente (nao vira manutencao silenciosa nem sucesso). O token
    __keep_current__ so e usado como representacao quando HA, NESTE
    campo, um vinculo persistido tambem oculto (``persisted_email``) --
    sem isso (campo sem vinculo, ou vinculo persistido ATIVO) a
    representacao e vazia (achado real UVI-06d: o token nao pode
    aparecer num campo que nunca foi trocado para CharField, nem
    representar um vinculo que nao existe ou que esta ativo). Valor
    ativo valido submetido continua exibido normalmente quando o erro
    esta em outro campo."""
    original_bound_data = field.bound_data

    def bound_data(data, initial, _orig=original_bound_data, _viewer=viewer, _persisted=persisted_email):
        override = redisplay_value_for_rejected_submission(_viewer, data, _persisted)
        if override is not None:
            return override
        return _orig(data, initial)

    field.bound_data = bound_data


def _validate_account_text_field(form, field_name, viewer):
    """UVI-04 (conferencia corretiva) + UVI-06 (correcao): supervisor_email/
    manager_email sao texto livre no proprio cadastro de SystemUser --
    unico caminho real de edicao (confirmado em UVI-02/03, sem rota de
    auto-edicao de perfil). Resolve o marcador __keep_current__ a partir
    do valor persistido no banco (``form.instance`` ainda nao mutado
    nesta fase de ``clean()``), preserva um vinculo JA persistido (mesmo
    inativo -- nao e nova associacao) e rejeita apontar para uma conta
    DIFERENTE que esteja oculta para o viewer. E-mail sem nenhuma conta
    correspondente mantem tratamento legado (SystemUser.clean() e as
    validacoes de existencia de cada role nao sao alteradas aqui)."""
    persisted = _persisted_text_field_value(form, field_name)
    raw_value = normalize_email_address(form.cleaned_data.get(field_name)) or None
    try:
        value = resolve_account_text_field_post(viewer, raw_value, persisted)
    except KeepCurrentInvalidContext:
        raise forms.ValidationError("Selecione uma conta ativa.")
    if value == persisted:
        return value
    if value and account_is_hidden_for_viewer(viewer, value):
        raise forms.ValidationError("Selecione uma conta ativa.")
    return value


@admin.register(SystemUser)
class SystemUserAdmin(UserAdmin):
    model = SystemUser
    ordering = ("email",)
    list_filter = ("role", "is_staff", "is_active")
    # Defeito pre-existente (achado na conferencia corretiva de UVI-03,
    # nao relacionado a visibilidade de inatividade): UserAdmin.search_fields
    # herdado inclui "username", campo que SystemUser nao possui
    # (username = None) -- qualquer busca (?q=) levantava FieldError para
    # QUALQUER usuario. Sobrescrito com o campo real do cadastro.
    search_fields = ("email",)

    def get_queryset(self, request):
        """UVI-04: ADMIN/DEV preservam visibilidade integral (excecao de
        role, nao de is_staff/is_superuser); os demais quatro papeis nao
        veem contas inativas em changelist, busca, contagem, paginacao,
        popup ou acoes em lote -- todos consomem este mesmo queryset."""
        queryset = super().get_queryset(request)
        return visible_accounts_queryset(request.user, queryset)

    def get_form(self, request, obj=None, **kwargs):
        """UVI-04 (conferencia corretiva) + UVI-06 (correcao): injeta o
        viewer (request.user) no form real do Admin (padrao usual do
        Django Admin para propagar contexto de request a um ModelForm,
        mesmo mecanismo de EmployeeAdmin.get_form) para validar
        supervisor_email/manager_email sem alterar SystemUser.clean() nem
        consumidores fora do Admin. __init__ aplica a representacao
        neutra em GET quando o vinculo persistido estiver oculto para o
        viewer -- a identidade real nunca chega ao HTML renderizado."""
        form_class = super().get_form(request, obj, **kwargs)
        viewer = request.user

        class SystemUserAdminFormWithVisibility(form_class):
            def __init__(form_self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                _apply_keep_current_text_field(form_self, "supervisor_email", viewer)
                _apply_keep_current_text_field(form_self, "manager_email", viewer)

            def clean_supervisor_email(form_self):
                return _validate_account_text_field(
                    form_self, "supervisor_email", viewer
                )

            def clean_manager_email(form_self):
                return _validate_account_text_field(
                    form_self, "manager_email", viewer
                )

        return SystemUserAdminFormWithVisibility

    def get_list_display(self, request):
        """UVI-06 (correcao): manager_email/supervisor_email na changelist
        nao podem expor identidade de conta inativa a viewer restrito.
        Projecao em lote (uma consulta por requisicao, via
        resolve_all_inactive_emails_casefold, capturada por closure --
        nunca atribuida a self, nunca por linha/N+1). ADMIN/DEV veem a
        identidade real (set vazio, sem mascaramento)."""
        viewer = request.user
        inactive_emails = resolve_all_inactive_emails_casefold(viewer)

        def manager_email_display(obj):
            return mask_inactive_email(obj.manager_email, inactive_emails)

        manager_email_display.short_description = "Gerente vinculado"

        def supervisor_email_display(obj):
            return mask_inactive_email(obj.supervisor_email, inactive_emails)

        supervisor_email_display.short_description = "Supervisor vinculado"

        return (
            "email",
            "role",
            manager_email_display,
            supervisor_email_display,
            "is_staff",
            "is_active",
        )

    def _get_obj_does_not_exist_redirect(self, request, opts, object_id):
        """UVI-04 (contrato UVI-02): o Django Admin padrao redireciona
        (302) para o index quando o objeto nao e encontrado no queryset
        filtrado -- change/delete/history usam este hook. O contrato exige
        404 generico (sem identidade) para objeto oculto por visibilidade,
        indistinguivel de um ID inexistente. Unico ponto de sobrescrita
        necessario: os tres caminhos citados convergem para este hook
        (confirmado por leitura do Django 5.2.11 instalado)."""
        raise Http404("Pagina nao encontrada.")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_staff",
                    "is_active",
                    "role",
                    "manager_email",
                    "supervisor_email",
                    "is_superuser",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login",)}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "role",
                    "manager_email",
                    "supervisor_email",
                ),
            },
        ),
    )
