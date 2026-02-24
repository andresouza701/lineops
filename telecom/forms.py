from django import forms

from .models import PhoneLine, SIMcard


class SIMcardForm(forms.ModelForm):
    class Meta:
        model = SIMcard
        fields = ["iccid", "carrier"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["iccid"].widget.attrs.setdefault("class", "form-control")
        self.fields["carrier"].widget.attrs.setdefault("class", "form-control")


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


class CombinedSimLineForm(forms.Form):
    phone_number = forms.CharField(label="Linha", max_length=20)
    iccid = forms.CharField(label="ICCID", max_length=22)
    carrier = forms.CharField(label="Operadora", max_length=100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_iccid(self):
        iccid = self.cleaned_data["iccid"]
        if SIMcard.objects.filter(iccid=iccid, is_deleted=False).exists():
            raise forms.ValidationError("ICCID já cadastrado.")
        return iccid

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"]
        if PhoneLine.objects.filter(phone_number=phone, is_deleted=False).exists():
            raise forms.ValidationError("Número já cadastrado.")
        return phone
