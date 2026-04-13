from django import forms
from django.apps import apps

from core.constants import B2B_PORTFOLIOS, B2C_PORTFOLIOS
from core.normalization import normalize_email_address, normalize_full_name

from .models import Employee

def sort_choice_pairs(choices):
    return sorted(list(dict.fromkeys(choices)), key=lambda item: str(item[1]).casefold())


ALL_PORTFOLIOS = sort_choice_pairs(B2B_PORTFOLIOS + B2C_PORTFOLIOS)


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "full_name",
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

    def clean_corporate_email(self):
        corporate_email = normalize_email_address(
            self.cleaned_data.get("corporate_email")
        )
        allowed_emails = getattr(self, "_allowed_supervisor_emails", [])
        if allowed_emails and corporate_email not in allowed_emails:
            raise forms.ValidationError("Selecione um supervisor valido.")
        return corporate_email

    def clean_manager_email(self):
        manager_email = normalize_email_address(self.cleaned_data.get("manager_email"))
        allowed_emails = getattr(self, "_allowed_manager_emails", [])
        if allowed_emails and manager_email not in allowed_emails:
            raise forms.ValidationError("Selecione um gerente valido.")
        return manager_email

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.initial.get("status"):
            self.initial["status"] = Employee.Status.ACTIVE

        from users.models import SystemUser

        super_users = SystemUser.objects.filter(role__in=SystemUser.SUPERVISOR_ROLES)
        manager_users = SystemUser.objects.filter(role=SystemUser.Role.GERENTE)
        self._allowed_supervisor_emails = sorted(
            [normalize_email_address(user.email) for user in super_users]
        )
        self._allowed_manager_emails = sorted(
            [normalize_email_address(user.email) for user in manager_users]
        )
        supervisor_choices = [
            (email, email) for email in self._allowed_supervisor_emails
        ]
        manager_choices = [(email, email) for email in self._allowed_manager_emails]
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
        if manager_choices:
            self.fields["manager_email"].required = True
            self.fields["manager_email"].widget = forms.Select(
                attrs={"class": "form-select"},
                choices=manager_choices,
            )
        else:
            self.fields["manager_email"].widget = forms.TextInput(
                attrs={"class": "form-control"}
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
        self.fields["status"].widget.attrs.setdefault("class", "form-select")
        self.fields["pa"].required = False
        self.fields["pa"].widget.attrs.setdefault("class", "form-control")
