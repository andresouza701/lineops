from django import forms
from django.apps import apps

from core.validation import (
    normalize_iccid,
    normalize_phone_number,
    validate_iccid_format,
    validate_phone_number_format,
)
from employees.models import Employee

from .models import PhoneLine, SIMcard

MAX_ACTIVE_LINES_PER_EMPLOYEE = 2


class SIMcardForm(forms.ModelForm):
    class Meta:
        model = SIMcard
        fields = ["iccid", "carrier"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["iccid"].widget.attrs.setdefault("class", "form-control")
        self.fields["carrier"].widget.attrs.setdefault("class", "form-control")


class SIMcardCreateWithLineForm(SIMcardForm):
    phone_number = forms.CharField(
        label="Linha",
        max_length=20,
        required=True,
        help_text="Numero da linha vinculado ao SIM card.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone_number"].widget.attrs.setdefault("class", "form-control")

    def clean_phone_number(self):
        phone_number = normalize_phone_number(self.cleaned_data.get("phone_number"))
        validate_phone_number_format(phone_number)
        if PhoneLine.objects.filter(
            phone_number=phone_number,
            is_deleted=False,
        ).exists():
            raise forms.ValidationError("Numero de linha ja cadastrado.")
        return phone_number


class PhoneLineForm(forms.ModelForm):
    class Meta:
        model = PhoneLine
        fields = ["phone_number", "sim_card"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        available_simcards = SIMcard.objects.filter(
            is_deleted=False,
            phone_line__isnull=True,
            status=SIMcard.Status.AVAILABLE,
        )

        if self.instance and self.instance.pk and self.instance.sim_card_id:
            available_simcards = (
                available_simcards
                | SIMcard.objects.filter(pk=self.instance.sim_card_id, is_deleted=False)
            ).distinct()

        self.fields["sim_card"].queryset = available_simcards
        self.fields["phone_number"].widget.attrs.setdefault("class", "form-control")
        self.fields["sim_card"].widget.attrs.setdefault("class", "form-select")


class PhoneLineUpdateForm(PhoneLineForm):
    employee = forms.ModelChoiceField(
        label="Usuário vinculado",
        queryset=Employee.objects.none(),
        required=False,
        empty_label="Sem vínculo",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta(PhoneLineForm.Meta):
        fields = ["phone_number", "sim_card", "status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sim_card"].label = "SIM card"
        self.fields["status"].label = "Status"
        self.fields["status"].widget.attrs.setdefault("class", "form-select")

        if self.instance and self.instance.pk:
            # Regra da tela de edição: linha e SIM não podem ser alterados.
            self.fields["phone_number"].disabled = True
            self.fields["sim_card"].disabled = True

        self.fields["employee"].queryset = Employee.objects.filter(
            is_deleted=False,
            status=Employee.Status.ACTIVE,
        ).order_by("full_name")

        if self.instance and self.instance.pk:
            active_allocation = (
                self.instance.allocations.filter(is_active=True)
                .select_related("employee")
                .first()
            )
            if active_allocation:
                self.fields["employee"].initial = active_allocation.employee

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")
        employee = cleaned_data.get("employee")

        if employee and status != PhoneLine.Status.ALLOCATED:
            self.add_error(
                "status",
                "Quando houver usuário vinculado, o status deve ser Alocada.",
            )

        if not employee and status == PhoneLine.Status.ALLOCATED:
            self.add_error(
                "employee",
                "Selecione um usuário para manter a linha como Alocada.",
            )

        if employee and self.instance and self.instance.pk:
            line_allocation_model = apps.get_model("allocations", "LineAllocation")
            employee_active_lines_count = (
                line_allocation_model.objects.filter(
                    employee=employee,
                    is_active=True,
                )
                .exclude(phone_line=self.instance)
                .count()
            )
            if employee_active_lines_count >= MAX_ACTIVE_LINES_PER_EMPLOYEE:
                self.add_error(
                    "employee",
                    (
                        f"O funcionario {employee.full_name} "
                        "ja possui 2 linhas alocadas ativas."
                    ),
                )

        return cleaned_data


class CombinedSimLineForm(forms.Form):
    phone_number = forms.CharField(label="Linha", max_length=20)
    iccid = forms.CharField(label="ICCID", max_length=22)
    carrier = forms.CharField(label="Operadora", max_length=100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_iccid(self):
        iccid = normalize_iccid(self.cleaned_data["iccid"])
        validate_iccid_format(iccid)
        if SIMcard.objects.filter(iccid=iccid, is_deleted=False).exists():
            raise forms.ValidationError("ICCID já cadastrado.")
        return iccid

    def clean_phone_number(self):
        phone = normalize_phone_number(self.cleaned_data["phone_number"])
        validate_phone_number_format(phone)
        if PhoneLine.objects.filter(phone_number=phone, is_deleted=False).exists():
            raise forms.ValidationError("Número já cadastrado.")
        return phone
