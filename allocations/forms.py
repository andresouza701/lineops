from django import forms

from employees.models import Employee
from telecom.models import PhoneLine, SIMcard


class AllocationForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(
            is_deleted=False, status=Employee.Status.ACTIVE
        ),
        label="Funcionário",
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class CombinedRegistrationForm(forms.Form):
    full_name = forms.CharField(label="Nome", max_length=255)
    corporate_email = forms.ChoiceField(
        label="Supervisor",
        choices=[],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    employee_id = forms.CharField(label="Carteira", max_length=50)
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
            ("existing", "Vincular linha disponível"),
        ),
        initial="new",
        widget=forms.RadioSelect,
        required=False,
    )

    phone_number = forms.CharField(label="Linha", max_length=20, required=False)
    iccid = forms.CharField(label="ICCID", max_length=22, required=False)
    carrier = forms.CharField(label="Operadora", max_length=100, required=False)

    phone_line = forms.ModelChoiceField(
        queryset=PhoneLine.objects.filter(
            is_deleted=False, status=PhoneLine.Status.AVAILABLE
        ),
        label="Linha disponível",
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
        text_fields = [
            "full_name",
            "employee_id",
            "phone_number",
            "iccid",
            "carrier",
        ]
        for name in text_fields:
            self.fields[name].widget.attrs.setdefault("class", "form-control")
        self.fields["status"].widget.attrs.setdefault("class", "form-select")
        self.fields["line_action"].widget.attrs.setdefault("class", "form-check-input")
        # RadioSelect renders inputs; setting class on widget is enough because
        # Django applies it to each rendered input automatically.

    def clean_corporate_email(self):
        supervisor = self.cleaned_data["corporate_email"]
        return supervisor

    def clean_employee_id(self):
        emp_id = self.cleaned_data["employee_id"]
        if Employee.objects.filter(employee_id=emp_id).exists():
            raise forms.ValidationError("Carteira já cadastrada.")
        return emp_id

    def clean_iccid(self):
        iccid = self.cleaned_data["iccid"]
        if (
            self.cleaned_data.get("line_action") == "new"
            and iccid
            and SIMcard.objects.filter(iccid=iccid, is_deleted=False).exists()
        ):
            raise forms.ValidationError("ICCID já cadastrado.")
        return iccid

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"]
        if (
            self.cleaned_data.get("line_action") == "new"
            and phone
            and PhoneLine.objects.filter(phone_number=phone, is_deleted=False).exists()
        ):
            raise forms.ValidationError("Linha já cadastrada.")
        return phone

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get("line_action")

        if not action:
            cleaned["phone_line"] = None
            cleaned["phone_number"] = cleaned.get("phone_number") or ""
            cleaned["iccid"] = cleaned.get("iccid") or ""
            cleaned["carrier"] = cleaned.get("carrier") or ""
            return cleaned

        if action == "new":
            required_fields = ["phone_number", "iccid", "carrier"]
            for field in required_fields:
                if not cleaned.get(field):
                    self.add_error(field, "Campo obrigatório.")
            cleaned["phone_line"] = None
        elif action == "existing":
            if not cleaned.get("phone_line"):
                self.add_error("phone_line", "Selecione uma linha disponível.")
            cleaned["phone_number"] = cleaned.get("phone_number") or ""
            cleaned["iccid"] = cleaned.get("iccid") or ""
            cleaned["carrier"] = cleaned.get("carrier") or ""

        return cleaned


class TelephonyAssignmentForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(
            is_deleted=False, status=Employee.Status.ACTIVE
        ),
        label="Funcionário",
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
        empty_label="Selecione",
    )

    line_action = forms.ChoiceField(
        label="O que deseja fazer?",
        choices=(
            ("new", "Cadastrar nova linha"),
            ("existing", "Vincular linha disponível"),
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
        label="Linha disponível",
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
        empty_label="Selecione",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        text_fields = ["phone_number", "iccid", "carrier"]
        for name in text_fields:
            self.fields[name].widget.attrs.setdefault("class", "form-control")
        self.fields["line_action"].widget.attrs.setdefault("class", "form-check-input")

    def clean_iccid(self):
        iccid = self.cleaned_data["iccid"]
        if (
            self.cleaned_data.get("line_action") == "new"
            and iccid
            and SIMcard.objects.filter(iccid=iccid, is_deleted=False).exists()
        ):
            raise forms.ValidationError("ICCID já cadastrado.")
        return iccid

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"]
        if (
            self.cleaned_data.get("line_action") == "new"
            and phone
            and PhoneLine.objects.filter(phone_number=phone, is_deleted=False).exists()
        ):
            raise forms.ValidationError("Linha já cadastrada.")
        return phone

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get("line_action")

        if action == "new":
            required_fields = ["phone_number", "iccid", "carrier"]
            for field in required_fields:
                if not cleaned.get(field):
                    self.add_error(field, "Campo obrigatório.")
            cleaned["phone_line"] = None
        elif action == "existing":
            if not cleaned.get("employee"):
                self.add_error("employee", "Selecione o colaborador.")
            if not cleaned.get("phone_line"):
                self.add_error("phone_line", "Selecione uma linha disponível.")
            cleaned["phone_number"] = cleaned.get("phone_number") or ""
            cleaned["iccid"] = cleaned.get("iccid") or ""
            cleaned["carrier"] = cleaned.get("carrier") or ""

        return cleaned
