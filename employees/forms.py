from django import forms

from .models import Employee


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ["full_name", "corporate_email", "teams", "employee_id", "status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.initial.get("status"):
            self.initial["status"] = Employee.Status.ACTIVE

        text_fields = ["full_name", "corporate_email", "employee_id", "teams"]
        for name in text_fields:
            self.fields[name].widget.attrs.setdefault("class", "form-control")

        self.fields["status"].widget.attrs.setdefault("class", "form-select")
