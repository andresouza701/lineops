from typing import cast

from django import forms
from django.apps import apps

from core.normalization import normalize_carrier_name
from core.services.allocation_service import MAX_ACTIVE_ALLOCATIONS_PER_EMPLOYEE
from core.validation import (
    normalize_iccid,
    normalize_phone_number,
    validate_iccid_format,
    validate_phone_number_format,
)
from employees.models import Employee

from .models import BlipConfiguration, PhoneLine, SIMcard
from .whatsapp_seal import REQUIRED_FIELD_ERRORS, WhatsAppSeal

SEAL_DETAIL_FIELDS = [
    "whatsapp_seal_activated_on",
    "whatsapp_seal_expires_on",
    "whatsapp_seal_email",
    "whatsapp_seal_payment",
]

OPTIONAL_SELECT_CHOICES = [("", "---------")]


class SIMcardForm(forms.ModelForm):
    class Meta:
        model = SIMcard
        fields = ["iccid", "carrier"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["iccid"].widget.attrs.setdefault("class", "form-control")
        self.fields["carrier"].widget.attrs.setdefault("class", "form-control")

    def clean_carrier(self):
        return normalize_carrier_name(self.cleaned_data.get("carrier"))


class SIMcardCreateWithLineForm(SIMcardForm):
    phone_number = forms.CharField(
        label="Linha",
        max_length=20,
        required=True,
        help_text="Número da linha vinculado ao SIM card.",
    )
    origem = forms.ChoiceField(
        label="Origem",
        choices=OPTIONAL_SELECT_CHOICES + list(PhoneLine.Origem.choices),
        required=False,
    )
    canal = forms.ChoiceField(
        label="Canal",
        choices=OPTIONAL_SELECT_CHOICES + list(PhoneLine.Canal.choices),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone_number"].widget.attrs.setdefault("class", "form-control")
        self.fields["origem"].widget.attrs.setdefault("class", "form-select")
        self.fields["canal"].widget.attrs.setdefault("class", "form-select")

    def clean_phone_number(self):
        phone_number = normalize_phone_number(self.cleaned_data.get("phone_number"))
        validate_phone_number_format(phone_number)
        if PhoneLine.active_phone_number_conflicts(phone_number).exists():
            raise forms.ValidationError("Número de linha já cadastrado.")
        return phone_number


class PhoneLineForm(forms.ModelForm):
    class Meta:
        model = PhoneLine
        fields = [
            "phone_number",
            "sim_card",
            "origem",
            "canal",
            "whatsapp_seal",
            "whatsapp_seal_activated_on",
            "whatsapp_seal_expires_on",
            "whatsapp_seal_email",
            "whatsapp_seal_payment",
        ]
        widgets = {
            "whatsapp_seal": forms.Select(attrs={"class": "form-select"}),
            "whatsapp_seal_activated_on": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"
            ),
            "whatsapp_seal_expires_on": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"
            ),
            "whatsapp_seal_email": forms.EmailInput(attrs={"class": "form-control"}),
            "whatsapp_seal_payment": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "whatsapp_seal": "Selo",
            "whatsapp_seal_activated_on": "Ativação",
            "whatsapp_seal_expires_on": "Vencimento",
            "whatsapp_seal_email": "E-mail cadastrado",
            "whatsapp_seal_payment": "Pagamento",
        }

    def full_clean(self):
        if self.is_bound and not self.data.get("whatsapp_seal"):
            data = self.data.copy()
            for field_name in SEAL_DETAIL_FIELDS:
                data[field_name] = ""
            self.data = data
        return super().full_clean()

    def _post_clean(self):
        # Um campo de detalhe do selo com valor preenchido em formato
        # inválido (ex.: e-mail sem "@") falha na validação própria do
        # campo e fica fora de cleaned_data; construct_instance() não
        # atualiza o atributo da instância, que permanece vazio, e
        # PhoneLine.clean() (validate_seal_fields, disparado
        # automaticamente por super()._post_clean()) soma "é obrigatório"
        # à mesma lista — mensagem contraditória, pois um valor foi
        # digitado. Registrado apenas para os campos que já tinham erro de
        # formato antes da validação de domínio rodar.
        fields_with_format_errors = {
            field_name for field_name in SEAL_DETAIL_FIELDS if field_name in self.errors
        }
        super()._post_clean()
        for field_name in fields_with_format_errors:
            required_message = REQUIRED_FIELD_ERRORS.get(field_name)
            if not required_message or field_name not in self.errors:
                continue
            remaining = [
                message
                for message in self.errors[field_name]
                if message != required_message
            ]
            if remaining and len(remaining) != len(self.errors[field_name]):
                self.errors[field_name] = self.error_class(remaining)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        available_simcards = SIMcard.available_for_line_registration()

        if self.instance and self.instance.pk and self.instance.sim_card_id:
            available_simcards = (
                available_simcards
                | SIMcard.objects.filter(pk=self.instance.sim_card_id, is_deleted=False)
            ).distinct()

        sim_card_field = cast(forms.ModelChoiceField, self.fields["sim_card"])
        sim_card_field.queryset = available_simcards
        self.fields["phone_number"].widget.attrs.setdefault("class", "form-control")
        self.fields["sim_card"].widget.attrs.setdefault("class", "form-select")
        self.fields["origem"].widget.attrs.setdefault("class", "form-select")
        self.fields["canal"].widget.attrs.setdefault("class", "form-select")

        for field_name in self.fields:
            self.fields[field_name].widget.attrs.setdefault(
                "aria-describedby", f"id_{field_name}_error"
            )

        # Progressive enhancement: os quatro campos de detalhe do selo nunca
        # recebem `required` no HTML gerado pelo servidor. Sem JavaScript
        # eles precisam ficar sempre preenchíveis/enviáveis (inclusive para
        # trocar um selo existente por Sem selo); `required` é adicionado e
        # removido só pelo JavaScript, conforme a seleção corrente no
        # navegador. PhoneLine.clean() continua sendo a única autoridade de
        # validação de obrigatoriedade condicional.
        self.fields["whatsapp_seal"].choices = [("", "Sem selo")] + list(
            WhatsAppSeal.choices
        )

    def clean_phone_number(self):
        phone_number = normalize_phone_number(self.cleaned_data.get("phone_number"))
        validate_phone_number_format(phone_number)

        existing_lines = PhoneLine.active_phone_number_conflicts(
            phone_number,
            exclude_id=self.instance.pk if self.instance and self.instance.pk else None,
        )

        if existing_lines.exists():
            raise forms.ValidationError("Número de linha já cadastrado.")

        return phone_number

    def save(self, commit=True):
        if self.instance and self.instance.pk:
            return super().save(commit=commit)

        if not commit:
            return super().save(commit=False)

        return PhoneLine.create_or_reuse(
            phone_number=self.cleaned_data["phone_number"],
            sim_card=self.cleaned_data["sim_card"],
            status=PhoneLine.Status.AVAILABLE,
            origem=self.cleaned_data.get("origem"),
            canal=self.cleaned_data.get("canal"),
            whatsapp_seal=self.cleaned_data.get("whatsapp_seal", ""),
            whatsapp_seal_activated_on=self.cleaned_data.get(
                "whatsapp_seal_activated_on"
            ),
            whatsapp_seal_expires_on=self.cleaned_data.get(
                "whatsapp_seal_expires_on"
            ),
            whatsapp_seal_email=self.cleaned_data.get("whatsapp_seal_email", ""),
            whatsapp_seal_payment=self.cleaned_data.get(
                "whatsapp_seal_payment", ""
            ),
        )


class PhoneLineUpdateForm(PhoneLineForm):
    employee = forms.ModelChoiceField(
        label="Usuário vinculado",
        queryset=Employee.objects.none(),
        required=False,
        empty_label="Sem vínculo",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta(PhoneLineForm.Meta):
        fields = [
            "phone_number",
            "sim_card",
            "status",
            "origem",
            "canal",
            "whatsapp_seal",
            "whatsapp_seal_activated_on",
            "whatsapp_seal_expires_on",
            "whatsapp_seal_email",
            "whatsapp_seal_payment",
        ]

    def __init__(self, *args, **kwargs):
        can_edit_origem = kwargs.pop("can_edit_origem", False)
        super().__init__(*args, **kwargs)
        self.fields["sim_card"].label = "SIM card"
        self.fields["status"].label = "Status"
        self.fields["status"].widget.attrs.setdefault("class", "form-select")

        if self.instance and self.instance.pk:
            self.fields["phone_number"].disabled = True
            self.fields["sim_card"].disabled = True
            if not can_edit_origem:
                self.fields["origem"].disabled = True

        employee_field = cast(forms.ModelChoiceField, self.fields["employee"])
        employee_field.queryset = Employee.objects.filter(
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
                "Quando houver usuário vinculado, o status deve ser Alocado.",
            )

        if not employee and status == PhoneLine.Status.ALLOCATED:
            self.add_error(
                "employee",
                "Selecione um usuário para manter a linha como Alocado.",
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
            if employee_active_lines_count >= MAX_ACTIVE_ALLOCATIONS_PER_EMPLOYEE:
                self.add_error(
                    "employee",
                    (
                        f"O usuário {employee.full_name} já possui "
                        f"{MAX_ACTIVE_ALLOCATIONS_PER_EMPLOYEE} "
                        f"linhas alocadas ativas."
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
        return iccid

    def clean_phone_number(self):
        phone = normalize_phone_number(self.cleaned_data["phone_number"])
        validate_phone_number_format(phone)
        if PhoneLine.active_phone_number_conflicts(phone).exists():
            raise forms.ValidationError("Número já cadastrado!")
        return phone

    def clean_carrier(self):
        return normalize_carrier_name(self.cleaned_data.get("carrier"))


class BlipConfigurationForm(forms.ModelForm):
    phone_number = forms.TypedChoiceField(
        label="Número Telefone",
        choices=(),
        coerce=int,
    )

    class Meta:
        model = BlipConfiguration
        fields = ["blip_id", "type", "description", "phone_number", "key", "value"]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        for field_name in ["blip_id", "description", "value"]:
            self.fields[field_name].widget.attrs.setdefault("class", "form-control")

        self.fields["phone_number"].widget.attrs.setdefault("class", "form-select")
        for field_name in ["type", "key"]:
            self.fields[field_name].widget.attrs.setdefault("class", "form-select")

        available_lines = PhoneLine.visible_to_user(
            self.user,
            PhoneLine.objects.filter(
                is_deleted=False,
                sim_card__is_deleted=False,
                origem=PhoneLine.Origem.BLIP,
            ).order_by("phone_number"),
        )
        phone_choices = [
            (line.phone_number, line.phone_number) for line in available_lines
        ]

        current_phone_number = getattr(self.instance, "phone_number", None)
        if current_phone_number is not None:
            current_phone_str = str(current_phone_number)
            if all(value != current_phone_str for value, _ in phone_choices):
                phone_choices.insert(0, (current_phone_str, current_phone_str))

        self.fields["phone_number"].choices = phone_choices
