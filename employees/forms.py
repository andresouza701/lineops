from django import forms

from .models import Employee


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ["full_name", "corporate_email", "employee_id", "teams", "status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.initial.get("status"):
            self.initial["status"] = Employee.Status.ACTIVE

        # Supervisor dropdown
        from users.models import SystemUser

        super_users = SystemUser.objects.filter(role=SystemUser.Role.SUPER)
        supervisor_choices = [(user.email, user.email) for user in super_users]
        if supervisor_choices:
            self.fields["corporate_email"] = forms.ChoiceField(
                label="Supervisor",
                choices=supervisor_choices,
                widget=forms.Select(attrs={"class": "form-select"}),
                initial=self.instance.corporate_email if self.instance else None,
                required=False,
            )
        else:
            self.fields["corporate_email"].widget = forms.TextInput(
                attrs={"class": "form-control"}
            )

        # Carteira dropdown
        carteira_choices = [
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
            ("MV - Ações", "MV - Ações"),
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
        ]
        self.fields["employee_id"] = forms.ChoiceField(
            label="Carteira",
            choices=carteira_choices,
            widget=forms.Select(attrs={"class": "form-select"}),
            initial=self.instance.employee_id if self.instance else None,
            required=False,
        )

        # Unidade dropdown (já é choices no model)
        self.fields["teams"].widget = forms.Select(attrs={"class": "form-select"})

        self.fields["full_name"].widget.attrs.setdefault("class", "form-control")
        self.fields["status"].widget.attrs.setdefault("class", "form-select")
