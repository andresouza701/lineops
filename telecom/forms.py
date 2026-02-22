from django import forms

from .models import PhoneLine, SIMcard


class SIMcardForm(forms.ModelForm):
    class Meta:
        model = SIMcard
        fields = ['iccid', 'carrier']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['iccid'].widget.attrs.setdefault('class', 'form-control')
        self.fields['carrier'].widget.attrs.setdefault('class', 'form-control')


class PhoneLineForm(forms.ModelForm):
    class Meta:
        model = PhoneLine
        fields = ['phone_number', 'sim_card']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        available_simcards = SIMcard.objects.filter(
            is_deleted=False,
            phone_line__isnull=True,
            status=SIMcard.Status.AVAILABLE,
        )

        if self.instance and self.instance.pk and self.instance.sim_card_id:
            available_simcards = (
                available_simcards | SIMcard.objects.filter(
                    pk=self.instance.sim_card_id, is_deleted=False)
            ).distinct()

        self.fields['sim_card'].queryset = available_simcards
        self.fields['phone_number'].widget.attrs.setdefault(
            'class', 'form-control')
        self.fields['sim_card'].widget.attrs.setdefault('class', 'form-select')
