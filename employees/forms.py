from django import forms
from django.apps import apps

from core.constants import B2B_PORTFOLIOS, B2C_PORTFOLIOS

from .models import Employee

ALL_PORTFOLIOS = list(dict.fromkeys(B2B_PORTFOLIOS + B2C_PORTFOLIOS))


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "full_name",
            "corporate_email",
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
        # Só valida se já existe (edição)
        if instance and instance.pk and status == Employee.Status.INACTIVE:
            # Verifica se há linha ativa vinculada
            line_allocation_model = apps.get_model("allocations", "LineAllocation")
            has_active_line = line_allocation_model.objects.filter(
                employee=instance, is_active=True
            ).exists()
            if has_active_line:
                raise forms.ValidationError(
                    "Não é permitido inativar um usuário que possui "
                    "linha vinculada ativa."
                )

        cleaned_data["supervisor_email"] = cleaned_data.get("corporate_email")
        cleaned_data["portfolio"] = cleaned_data.get("employee_id")
        return cleaned_data

    def clean_corporate_email(self):
        corporate_email = (self.cleaned_data.get("corporate_email") or "").strip()
        allowed_emails = getattr(self, "_allowed_supervisor_emails", [])
        if allowed_emails and corporate_email not in allowed_emails:
            raise forms.ValidationError("Selecione um supervisor valido.")
        return corporate_email

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.initial.get("status"):
            self.initial["status"] = Employee.Status.ACTIVE

        # Supervisor dropdown
        from users.models import SystemUser

        super_users = SystemUser.objects.filter(role=SystemUser.Role.SUPER)
        self._allowed_supervisor_emails = [user.email for user in super_users]
        supervisor_choices = [
            (email, email) for email in self._allowed_supervisor_emails
        ]
        if supervisor_choices:
            self.fields["corporate_email"].required = True
            self.fields["corporate_email"].widget = forms.Select(
                attrs={"class": "form-select"},
                choices=supervisor_choices,
            )
        else:
            self.fields["corporate_email"].widget = forms.TextInput(
                attrs={"class": "form-control"}
            )

        self.fields["employee_id"] = forms.ChoiceField(
            label="Carteira",
            choices=ALL_PORTFOLIOS,
            widget=forms.Select(attrs={"class": "form-select"}),
            initial=self.instance.employee_id if self.instance else None,
            required=True,
        )

        # Unidade dropdown (garante ChoiceField com opções do model)
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
        self.fields["status"].widget.attrs.setdefault("class", "form-select")
        self.fields["pa"].required = False
        self.fields["pa"].widget.attrs.setdefault("class", "form-control")
