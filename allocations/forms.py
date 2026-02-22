from django import forms

from employees.models import Employee
from telecom.models import PhoneLine


class AllocationForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(
            is_deleted=False, status=Employee.Status.ACTIVE),
        label='Funcionário',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    phone_line = forms.ModelChoiceField(
        queryset=PhoneLine.objects.filter(
            is_deleted=False, status=PhoneLine.Status.AVAILABLE),
        label='Linha telefônica',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
