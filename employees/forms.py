from django import forms
from django.apps import apps

from core.constants import B2B_PORTFOLIOS, B2C_PORTFOLIOS
from core.normalization import normalize_email_address, normalize_full_name
from users.visibility import (
    KEEP_CURRENT_LABEL,
    KEEP_CURRENT_TOKEN,
    NO_ACTIVE_ACCOUNTS_LABEL,
    viewer_is_exempt,
    visible_accounts_queryset,
)

from .models import Employee

def sort_choice_pairs(choices):
    return sorted(list(dict.fromkeys(choices)), key=lambda item: str(item[1]))


ALL_PORTFOLIOS = sort_choice_pairs(B2B_PORTFOLIOS + B2C_PORTFOLIOS)


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "full_name",
            "email",
            "corporate_email",
            "manager_email",
            "employee_id",
            "teams",
            "status",
            "pa",
        ]
        widgets = {
            "pa": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Opcional"}
            )
        }

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")
        instance = self.instance
        if instance and instance.pk and status == Employee.Status.INACTIVE:
            line_allocation_model = apps.get_model("allocations", "LineAllocation")
            has_active_line = line_allocation_model.objects.filter(
                employee=instance, is_active=True
            ).exists()
            if has_active_line:
                raise forms.ValidationError(
                    "Nao e permitido inativar um usuario que possui "
                    "linha vinculada ativa."
                )

        cleaned_data["supervisor_email"] = cleaned_data.get("corporate_email")
        cleaned_data["portfolio"] = cleaned_data.get("employee_id")
        return cleaned_data

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
        return self._clean_account_field(
            "corporate_email", "Selecione um supervisor valido."
        )

    def clean_manager_email(self):
        return self._clean_account_field(
            "manager_email", "Selecione um gerente valido."
        )

    def _clean_account_field(self, field_name, error_message):
        raw_value = normalize_email_address(self.cleaned_data.get(field_name))
        state = self._account_field_state[field_name]

        if raw_value == KEEP_CURRENT_TOKEN:
            if state["keep_current_allowed"]:
                return state["persisted_email"]
            raise forms.ValidationError(error_message)

        if state["total_count"] == 0:
            # Nenhuma conta desse role existe no banco: comportamento legado
            # preservado (campo texto livre, sem conta correspondente).
            return raw_value

        if raw_value not in state["allowed_emails"]:
            raise forms.ValidationError(error_message)
        return raw_value

    def _configure_account_field(self, field_name, role_filter):
        """UVI-04: centraliza a regra de visibilidade (users.visibility) para
        os seletores corporate_email/manager_email. Viewer vem da request
        (nunca do POST); ausencia de viewer e tratada como o caso restrito.

        Resolve tres estados distintos (contrato UVI-02, item 9):
        - total_count == 0: nenhuma conta desse role existe -- fallback de
          texto livre legado preservado (nao e um caso de visibilidade).
        - ha conta(s) visivel(eis): <select> com essas opcoes (+ marcador
          "Manter vínculo atual" quando o valor persistido for uma conta
          oculta para este viewer).
        - ha conta(s) mas nenhuma visivel: <select> sem opcao real
          atribuivel (so o marcador, se aplicavel), nunca texto livre.
        """
        from users.models import SystemUser

        all_accounts = SystemUser.objects.filter(role__in=role_filter)
        total_count = all_accounts.count()
        visible_emails = sorted(
            {
                normalize_email_address(email)
                for email in visible_accounts_queryset(
                    self._viewer, all_accounts
                ).values_list("email", flat=True)
            }
        )

        persisted_email = None
        if self.instance and self.instance.pk:
            persisted_email = normalize_email_address(
                getattr(self.instance, field_name, None)
            ) or None

        keep_current_allowed = bool(
            persisted_email
            and not viewer_is_exempt(self._viewer)
            and all_accounts.filter(
                email__iexact=persisted_email, is_active=False
            ).exists()
        )

        self._account_field_state[field_name] = {
            "total_count": total_count,
            "allowed_emails": visible_emails,
            "keep_current_allowed": keep_current_allowed,
            "persisted_email": persisted_email,
        }

        original_required = self.fields[field_name].required
        if total_count == 0:
            # Nenhuma conta desse role existe: campo de texto livre legado
            # preservado. Troca o TIPO do campo (nao so o widget) --
            # permanecer com o EmailField gerado pelo ModelForm rejeitaria
            # o marcador/valores nao-email nos outros ramos abaixo.
            self.fields[field_name] = forms.CharField(
                required=original_required,
                widget=forms.TextInput(attrs={"class": "form-control"}),
            )
            return

        choices = [(email, email) for email in visible_emails]
        if keep_current_allowed:
            choices = [(KEEP_CURRENT_TOKEN, KEEP_CURRENT_LABEL)] + choices
            self.initial[field_name] = KEEP_CURRENT_TOKEN
        elif not choices:
            choices = [("", NO_ACTIVE_ACCOUNTS_LABEL)]

        self.fields[field_name] = forms.ChoiceField(
            required=True,
            choices=choices,
            widget=forms.Select(attrs={"class": "form-select"}),
            # ChoiceField.default_error_messages["invalid_choice"] inclui
            # "%(value)s" -- interpola o valor FORJADO (ex.: o e-mail da
            # conta oculta) de volta na mensagem de erro renderizada,
            # vazando a identidade mesmo sem aparecer como <option>
            # (achado real na regressao desta etapa). Mensagem generica
            # sem interpolacao do valor submetido.
            error_messages={"invalid_choice": "Selecione uma opcao valida."},
        )

    def __init__(self, *args, can_edit_full_name=True, viewer=None, **kwargs):
        self._viewer = viewer
        super().__init__(*args, **kwargs)

        if not self.initial.get("status"):
            self.initial["status"] = Employee.Status.ACTIVE

        from users.models import SystemUser

        self._account_field_state = {}
        self._configure_account_field(
            field_name="corporate_email",
            role_filter=list(SystemUser.SUPERVISOR_ROLES),
        )
        self._configure_account_field(
            field_name="manager_email",
            role_filter=[SystemUser.Role.GERENTE],
        )

        self.fields["employee_id"] = forms.ChoiceField(
            label="Carteira",
            choices=ALL_PORTFOLIOS,
            widget=forms.Select(attrs={"class": "form-select"}),
            initial=self.instance.employee_id if self.instance else None,
            required=True,
        )

        unidade_choices = [
            (Employee.UnitChoices.JOINVILLE, "Joinville"),
            (Employee.UnitChoices.ARAQUARI, "Araquari"),
        ]
        self.fields["teams"] = forms.ChoiceField(
            label="Unidade",
            choices=unidade_choices,
            widget=forms.Select(attrs={"class": "form-select"}),
            initial=self.instance.teams if self.instance else None,
            required=True,
        )

        self.fields["full_name"].widget.attrs.setdefault("class", "form-control")
        if self.instance and self.instance.pk and not can_edit_full_name:
            self.fields["full_name"].disabled = True
        self.fields["email"].required = False
        self.fields["email"].widget.attrs.setdefault("class", "form-control")
        self.fields["status"].widget.attrs.setdefault("class", "form-select")
        self.fields["pa"].required = False
        self.fields["pa"].widget.attrs.setdefault("class", "form-control")
