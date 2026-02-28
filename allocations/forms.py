from django import forms

from allocations.models import LineAllocation
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard


class AllocationForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(
            is_deleted=False, status=Employee.Status.ACTIVE
        ),
        label="Funcionario",
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class CombinedRegistrationForm(forms.Form):
    full_name = forms.CharField(label="Nome", max_length=255)
    corporate_email = forms.ChoiceField(
        label="Supervisor",
        choices=[],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    employee_id = forms.ChoiceField(
        label="Carteira",
        choices=[
            ("Alimentos", "Alimentos"),
            ("Andina", "Andina"),
            ("BackOffice", "BackOffice"),
            ("BAT", "BAT"),
            ("Chilli Beans", "Chilli Beans"),
            ("Femsa", "Femsa"),
            ("Heineki", "Heineki"),
            ("Industria", "Industria"),
            ("Manual Dellys", "Manual Dellys"),
            ("MV - Martins", "MV - Martins"),
            ("MV - Pepsico Repique", "MV - Pepsico Repique"),
            ("MV - Pepsico", "MV - Pepsico"),
            ("MV - Transportes", "MV - Transportes"),
            ("MV - Acoes", "MV - Acoes"),
            ("MV - Mix", "MV - Mix"),
            ("MV - Dellys", "MV - Dellys"),
            ("MV - Potencial", "MV - Potencial"),
            ("MV - Represado", "MV - Represado"),
            ("Pepsico", "Pepsico"),
            ("Pesquisa", "Pesquisa"),
            ("Sascar", "Sascar"),
            ("Souza", "Souza"),
            ("Tabacos", "Tabacos"),
            ("Textil", "Textil"),
        ],
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

        super_users = SystemUser.objects.filter(role=SystemUser.Role.SUPER)
        supervisor_choices = [(user.email, user.email) for user in super_users]
        if supervisor_choices:
            self.fields["corporate_email"].choices = supervisor_choices
        else:
            self.fields["corporate_email"] = forms.CharField(
                label="Supervisor",
                max_length=255,
                widget=forms.TextInput(attrs={"class": "form-control"}),
            )

        for name in ["full_name", "phone_number", "iccid", "carrier"]:
            self.fields[name].widget.attrs.setdefault("class", "form-control")
        self.fields["status"].widget.attrs.setdefault("class", "form-select")
        self.fields["line_action"].widget.attrs.setdefault("class", "form-check-input")

    def clean_iccid(self):
        iccid = self.cleaned_data["iccid"]
        if (
            self.cleaned_data.get("line_action") == "new"
            and iccid
            and SIMcard.objects.filter(iccid=iccid, is_deleted=False).exists()
        ):
            raise forms.ValidationError("ICCID ja cadastrado.")
        return iccid

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"]
        if (
            self.cleaned_data.get("line_action") == "new"
            and phone
            and PhoneLine.objects.filter(phone_number=phone, is_deleted=False).exists()
        ):
            raise forms.ValidationError("Linha ja cadastrada.")
        return phone

    def clean(self):  # noqa: PLR0912
        cleaned = super().clean()
        action = cleaned.get("line_action")

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
        label="Funcionario",
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
        super().__init__(*args, **kwargs)
        for name in ["phone_number", "iccid", "carrier"]:
            self.fields[name].widget.attrs.setdefault("class", "form-control")
        self.fields["employee"].widget.attrs.setdefault("class", "form-select")
        self.fields["phone_line"].widget.attrs.setdefault("class", "form-select")
        self.fields["line_action"].widget.attrs.setdefault("class", "form-check-input")
        self.fields["phone_line_status"].queryset = PhoneLine.objects.filter(
            is_deleted=False
        ).order_by("phone_number")

    def clean_iccid(self):
        iccid = self.cleaned_data["iccid"]
        if (
            self.cleaned_data.get("line_action") == "new"
            and iccid
            and SIMcard.objects.filter(iccid=iccid, is_deleted=False).exists()
        ):
            raise forms.ValidationError("ICCID ja cadastrado.")
        return iccid

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"]
        if (
            self.cleaned_data.get("line_action") == "new"
            and phone
            and PhoneLine.objects.filter(phone_number=phone, is_deleted=False).exists()
        ):
            raise forms.ValidationError("Linha ja cadastrada.")
        return phone

    def clean(self):  # noqa: PLR0912
        cleaned = super().clean()
        action = cleaned.get("line_action")

        if action == "new":
            for field in ["phone_number", "iccid", "carrier"]:
                if not cleaned.get(field):
                    self.add_error(field, "Campo obrigatorio.")
            cleaned["phone_line"] = None
            cleaned["status_line"] = ""
            cleaned["phone_line_status"] = None
        elif action == "existing":
            if not cleaned.get("employee"):
                self.add_error("employee", "Selecione o usuário.")
            if not cleaned.get("phone_line"):
                self.add_error("phone_line", "Selecione uma linha disponivel.")
            elif cleaned["phone_line"].status != PhoneLine.Status.AVAILABLE:
                self.add_error("phone_line", "A linha selecionada nao esta disponivel.")

            cleaned["phone_number"] = cleaned.get("phone_number") or ""
            cleaned["iccid"] = cleaned.get("iccid") or ""
            cleaned["carrier"] = cleaned.get("carrier") or ""
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
                        else "usuário desconhecido"
                    )
                    self.add_error(
                        "status_line",
                        (
                            f"Libere a linha primeiro e tente novamente!"
                            f"Status atual: {phone_line.status}. "
                            f"Usuário vinculado: {employee_name}. "
                        ),
                    )
                if (
                    not has_active_allocation
                    and status_line == PhoneLine.Status.ALLOCATED
                ):
                    self.add_error(
                        "status_line",
                        "Use o vínculo com usuário para deixar ALLOCATED.",
                    )

            cleaned["phone_number"] = cleaned.get("phone_number") or ""
            cleaned["iccid"] = cleaned.get("iccid") or ""
            cleaned["carrier"] = cleaned.get("carrier") or ""
            cleaned["phone_line"] = None
            cleaned["employee"] = None

        return cleaned
