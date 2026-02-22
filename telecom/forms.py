from django import forms

from .models import PhoneLine

class PhoneLineForm(forms.ModelForm):
    class Meta:
        model = PhoneLine
        fields = ['phone_number', 'sim_card']
        # widgets = {
        #     'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
        #     'sim_card': forms.Select(attrs={'class': 'form-control'}),
        # }