from django import forms
from django.contrib import admin
from django.db import transaction

from .models import PhoneLine, SIMcard


class SIMcardAdminForm(forms.ModelForm):
    phone_number = forms.CharField(
        label="Linha",
        max_length=20,
        required=True,
        help_text="Numero da linha vinculado ao SIM card.",
    )

    class Meta:
        model = SIMcard
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and hasattr(self.instance, "phone_line"):
            self.fields["phone_number"].initial = self.instance.phone_line.phone_number

    def clean_phone_number(self):
        phone_number = (self.cleaned_data.get("phone_number") or "").strip()
        current_line_id = None
        if self.instance and self.instance.pk and hasattr(self.instance, "phone_line"):
            current_line_id = self.instance.phone_line.id

        queryset = PhoneLine.objects.filter(phone_number=phone_number)
        if current_line_id:
            queryset = queryset.exclude(pk=current_line_id)
        if queryset.exists():
            raise forms.ValidationError("Numero de linha ja cadastrado.")
        return phone_number


@admin.register(SIMcard)
class SIMcardAdmin(admin.ModelAdmin):
    form = SIMcardAdminForm
    list_display = ("iccid", "carrier", "status", "activated_at")
    search_fields = ("iccid", "carrier")
    list_filter = ("status", "carrier")

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        phone_number = form.cleaned_data["phone_number"]

        line = getattr(obj, "phone_line", None)
        if line:
            if line.phone_number != phone_number:
                line.phone_number = phone_number
                line.save(update_fields=["phone_number"])
            return

        PhoneLine.objects.create(
            phone_number=phone_number,
            sim_card=obj,
            status=PhoneLine.Status.AVAILABLE,
        )
