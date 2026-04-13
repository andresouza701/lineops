from django import forms

from allocations.models import LineAllocation
from core.constants import B2B_PORTFOLIOS, B2C_PORTFOLIOS
from core.normalization import (
    normalize_carrier_name,
    normalize_email_address,
    normalize_full_name,
)
from core.validation import (
    normalize_iccid,
    normalize_phone_number,
    validate_phone_number_format,
)
from employees.models import Employee
from telecom.models import PhoneLine

def sort_choice_pairs(choices):
    return sorted(list(dict.fromkeys(choices)), key=lambda item: str(item[1]).casefold())


ALL_PORTFOLIOS = sort_choice_pairs(B2B_PORTFOLIOS + B2C_PORTFOLIOS)
OPTIONAL_SELECT_CHOICES = [("", "---------")]


class AllocationForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(
            is_deleted=False, status=Employee.Status.ACTIVE
        ),
        label="Usuário",
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class CombinedRegistrationForm(forms.Form):
    full_name = forms.CharField(label="Nome", max_length=255)
    corporate_email = forms.CharField(
        label="Supervisor",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    manager_email = forms.CharField(
        label="Gerente",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    employee_id = forms.ChoiceField(
        label="Carteira",
        choices=ALL_PORTFOLIOS,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    teams = forms.ChoiceField(
        label="Unidade",
        choices=[
            ("Joinville", "Joinville"),
            ("Araquari", "Araquari"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    status = forms.ChoiceField(
        label="Status", choices=Employee.Status.choices, initial=Employee.Status.ACTIVE
    )

    line_action = forms.ChoiceField(
        label="O que deseja fazer?",
        choices=(
            ("new", "Cadastrar nova linha"),
            ("existing", "Vincular linha disponivel"),
            ("change_status", "Trocar status linha"),
        ),
        initial="new",
        widget=forms.RadioSelect,
        required=False,
    )

    status_line = forms.ChoiceField(
        label="Novo status da linha",
        choices=PhoneLine.Status.choices,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    phone_line_status = forms.ModelChoiceField(
        queryset=PhoneLine.objects.filter(is_deleted=False),
        label="Linha para trocar status",
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
        empty_label="Selecione",
    )

    phone_number = forms.CharField(label="Linha", max_length=20, required=False)
    iccid = forms.CharField(label="ICCID", max_length=22, required=False)
    carrier = forms.CharField(label="Operadora", max_length=100, required=False)
    phone_line = forms.ModelChoiceField(
        queryset=PhoneLine.objects.filter(
            is_deleted=False, status=PhoneLine.Status.AVAILABLE
        ),
        label="Linha disponivel",
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
        empty_label="Selecione",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from users.models import SystemUser

        super_users = SystemUser.objects.filter(role__in=SystemUser.SUPERVISOR_ROLES)
        manager_users = SystemUser.objects.filter(role=SystemUser.Role.GERENTE)
        self.supervisor_emails = sorted(
            [normalize_email_address(user.email) for user in super_users]
        )
        self.manager_emails = sorted(
            [normalize_email_address(user.email) for user in manager_users]
        )
        supervisor_choices = [(email, email) for email in self.supervisor_emails]
        manager_choices = [(email, email) for email in self.manager_emails]
        if supervisor_choices:
            self.fields["corporate_email"].required = True
            self.fields["corporate_email"].widget = forms.Select(
                attrs={"class": "form-select"},
                choices=supervisor_choices,
            )
        if manager_choices:
            self.fields["manager_email"].required = True
            self.fields["manager_email"].widget = forms.Select(
                attrs={"class": "form-select"},
                choices=manager_choices,
            )

        for name in ["full_name", "phone_number", "iccid", "carrier"]:
            self.fields[name].widget.attrs.setdefault("class", "form-control")
        self.fields["status"].widget.attrs.setdefault("class", "form-select")
        self.fields["line_action"].widget.attrs.setdefault("class", "form-check-input")

    def clean_iccid(self):
        iccid = normalize_iccid(self.cleaned_data["iccid"])
        return iccid

    def clean_phone_number(self):
        phone = normalize_phone_number(self.cleaned_data["phone_number"])
        if self.cleaned_data.get("line_action") == "new" and phone:
            validate_phone_number_format(phone)
            if PhoneLine.active_phone_number_conflicts(phone).exists():
                raise forms.ValidationError("Linha ja cadastrada.")
        return phone

    def clean_corporate_email(self):
        corporate_email = normalize_email_address(
            self.cleaned_data.get("corporate_email")
        )
        if self.supervisor_emails and corporate_email not in self.supervisor_emails:
            raise forms.ValidationError("Selecione um supervisor valido!")
        return corporate_email

    def clean_manager_email(self):
        manager_email = normalize_email_address(self.cleaned_data.get("manager_email"))
        if self.manager_emails and manager_email not in self.manager_emails:
            raise forms.ValidationError("Selecione um gerente valido!")
        return manager_email

    def clean_full_name(self):
        full_name = normalize_full_name(self.cleaned_data.get("full_name"))
        if not full_name:
            return full_name

        if Employee.has_active_full_name_conflict(full_name):
            raise forms.ValidationError(
                "Ja existe um usuario cadastrado com este nome."
            )

        return full_name

    def clean_carrier(self):
        return normalize_carrier_name(self.cleaned_data.get("carrier"))

    def clean(self):  # noqa: PLR0912
        cleaned = super().clean()
        action = cleaned.get("line_action")

        # Semantic aliases used by services without breaking current field names.
        cleaned["supervisor_email"] = cleaned.get("corporate_email")
        cleaned["portfolio"] = cleaned.get("employee_id")

        if not action:
            return cleaned

        if action == "new":
            for field in ["phone_number", "iccid", "carrier"]:
                if not cleaned.get(field):
                    self.add_error(field, "Campo obrigatorio.")
        elif action == "existing":
            if not cleaned.get("phone_line"):
                self.add_error("phone_line", "Selecione uma linha disponivel.")
        elif action == "change_status":
            if not cleaned.get("phone_line_status"):
                self.add_error("phone_line_status", "Selecione a linha.")
            if not cleaned.get("status_line"):
                self.add_error("status_line", "Selecione o novo status.")

        return cleaned


class TelephonyAssignmentForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(
            is_deleted=False, status=Employee.Status.ACTIVE
        ),
        label="Usuário",
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
        empty_label="Selecione",
    )
    line_action = forms.ChoiceField(
        label="O que deseja fazer?",
        choices=(
            ("new", "Cadastrar nova linha"),
            ("existing", "Vincular linha disponivel"),
            ("change_status", "Trocar status linha"),
        ),
        initial="new",
        widget=forms.RadioSelect,
    )
    phone_number = forms.CharField(label="Linha", max_length=20, required=False)
    iccid = forms.CharField(label="ICCID", max_length=22, required=False)
    carrier = forms.CharField(label="Operadora", max_length=100, required=False)
    origem = forms.ChoiceField(
        label="Origem",
        choices=OPTIONAL_SELECT_CHOICES + list(PhoneLine.Origem.choices),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    canal = forms.ChoiceField(
        label="Canal",
        choices=OPTIONAL_SELECT_CHOICES + list(PhoneLine.Canal.choices),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    phone_line = forms.ModelChoiceField(
        queryset=PhoneLine.objects.filter(
            is_deleted=False, status=PhoneLine.Status.AVAILABLE
        ),
        label="Linha disponivel",
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
        empty_label="Selecione",
    )
    status_line = forms.ChoiceField(
        label="Novo status da linha",
        choices=PhoneLine.Status.choices,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    phone_line_status = forms.ModelChoiceField(
        queryset=PhoneLine.objects.filter(is_deleted=False),
        label="Linha para trocar status",
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
        empty_label="Selecione",
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        for name in ["phone_number", "iccid", "carrier"]:
            self.fields[name].widget.attrs.setdefault("class", "form-control")
        self.fields["origem"].widget.attrs.setdefault("class", "form-select")
        self.fields["canal"].widget.attrs.setdefault("class", "form-select")
        self.fields["employee"].widget.attrs.setdefault("class", "form-select")
        self.fields["phone_line"].widget.attrs.setdefault("class", "form-select")
        self.fields["line_action"].widget.attrs.setdefault("class", "form-check-input")
        visible_lines = PhoneLine.visible_to_user(
            self.user,
            PhoneLine.objects.filter(is_deleted=False).order_by("phone_number"),
        )
        self.fields["phone_line"].queryset = visible_lines.filter(
            status=PhoneLine.Status.AVAILABLE
        )
        self.fields["phone_line_status"].queryset = visible_lines

    def clean_iccid(self):
        iccid = normalize_iccid(self.cleaned_data["iccid"])
        return iccid

    def clean_phone_number(self):
        phone = normalize_phone_number(self.cleaned_data["phone_number"])
        if self.cleaned_data.get("line_action") == "new" and phone:
            validate_phone_number_format(phone)
            if PhoneLine.active_phone_number_conflicts(phone).exists():
                raise forms.ValidationError("Linha ja cadastrada!")
        return phone

    def clean_carrier(self):
        return normalize_carrier_name(self.cleaned_data.get("carrier"))

    def clean(self):  # noqa: PLR0912
        cleaned = super().clean()
        action = cleaned.get("line_action")

        if action == "new":
            for field in ["phone_number", "iccid", "carrier", "origem"]:
                if not cleaned.get(field):
                    self.add_error(field, "Campo obrigatorio!")
            cleaned["phone_line"] = None
            cleaned["status_line"] = ""
            cleaned["phone_line_status"] = None
        elif action == "existing":
            if not cleaned.get("employee"):
                self.add_error("employee", "Selecione o usuario.")
            if not cleaned.get("phone_line"):
                self.add_error("phone_line", "Selecione uma linha disponivel.")
            elif cleaned["phone_line"].status != PhoneLine.Status.AVAILABLE:
                self.add_error("phone_line", "A linha selecionada nao esta disponivel.")

            cleaned["phone_number"] = cleaned.get("phone_number") or ""
            cleaned["iccid"] = cleaned.get("iccid") or ""
            cleaned["carrier"] = cleaned.get("carrier") or ""
            cleaned["origem"] = cleaned.get("origem") or ""
            cleaned["canal"] = cleaned.get("canal") or ""
            cleaned["status_line"] = ""
            cleaned["phone_line_status"] = None
        elif action == "change_status":
            phone_line = cleaned.get("phone_line_status")
            status_line = cleaned.get("status_line")

            if not phone_line:
                self.add_error("phone_line_status", "Selecione a linha.")
            if not status_line:
                self.add_error("status_line", "Selecione o novo status.")

            if phone_line and status_line:
                active_allocation = (
                    LineAllocation.objects.filter(phone_line=phone_line, is_active=True)
                    .select_related("employee")
                    .first()
                )
                has_active_allocation = active_allocation is not None
                if has_active_allocation and status_line != PhoneLine.Status.ALLOCATED:
                    employee_name = (
                        active_allocation.employee.full_name
                        if active_allocation.employee_id
                        else "Usuario desconhecido!"
                    )
                    self.add_error(
                        "status_line",
                        (
                            "Libere a linha primeiro e tente novamente!"
                            f"Status atual: {phone_line.status}. "
                            f"Usuario vinculado: {employee_name}. "
                        ),
                    )
                if (
                    not has_active_allocation
                    and status_line == PhoneLine.Status.ALLOCATED
                ):
                    self.add_error(
                        "status_line",
                        "Use o vinculo com usuario para deixar ALLOCATED.",
                    )

            cleaned["phone_number"] = cleaned.get("phone_number") or ""
            cleaned["iccid"] = cleaned.get("iccid") or ""
            cleaned["carrier"] = cleaned.get("carrier") or ""
            cleaned["origem"] = cleaned.get("origem") or ""
            cleaned["canal"] = cleaned.get("canal") or ""
            cleaned["phone_line"] = None
            cleaned["employee"] = None

        return cleaned
