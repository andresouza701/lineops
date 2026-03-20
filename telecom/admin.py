from django import forms
from django.contrib import admin
from django.db import transaction

from core.validation import normalize_phone_number, validate_phone_number_format

from .models import BlipConfiguration, PhoneLine, SIMcard


class SIMcardAdminForm(forms.ModelForm):
    phone_number = forms.CharField(
        label="Linha",
        max_length=20,
        required=True,
        help_text="Numero da linha vinculado ao SIM card.",
    )
    origem = forms.ChoiceField(
        label="Origem",
        choices=PhoneLine.Origem.choices,
        required=False,
    )
    line_status = forms.ChoiceField(
        label="Status da linha",
        choices=PhoneLine.Status.choices,
        required=True,
        initial=PhoneLine.Status.AVAILABLE,
    )

    class Meta:
        model = SIMcard
        fields = ["iccid", "carrier", "status", "activated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and hasattr(self.instance, "phone_line"):
            self.fields["phone_number"].initial = self.instance.phone_line.phone_number
            self.fields["origem"].initial = self.instance.phone_line.origem
            self.fields["line_status"].initial = self.instance.phone_line.status

    def clean_phone_number(self):
        phone_number = normalize_phone_number(self.cleaned_data.get("phone_number"))
        validate_phone_number_format(phone_number)
        current_line_id = None
        if self.instance and self.instance.pk and hasattr(self.instance, "phone_line"):
            current_line_id = self.instance.phone_line.id

        queryset = PhoneLine.active_phone_number_conflicts(phone_number)
        if current_line_id:
            queryset = queryset.exclude(pk=current_line_id)
        if queryset.exists():
            raise forms.ValidationError("Numero de linha ja cadastrado.")
        return phone_number


@admin.register(SIMcard)
class SIMcardAdmin(admin.ModelAdmin):
    form = SIMcardAdminForm
    list_display = (
        "iccid",
        "carrier",
        "status",
        "phone_number",
        "line_status",
        "origem",
        "activated_at",
    )
    search_fields = ("iccid", "carrier", "phone_line__phone_number")
    list_filter = ("status", "carrier", "phone_line__status", "phone_line__origem")

    @admin.display(description="Linha")
    def phone_number(self, obj):
        return getattr(getattr(obj, "phone_line", None), "phone_number", "-")

    @admin.display(description="Status da linha")
    def line_status(self, obj):
        phone_line = getattr(obj, "phone_line", None)
        return phone_line.get_status_display() if phone_line else "-"

    @admin.display(description="Origem")
    def origem(self, obj):
        phone_line = getattr(obj, "phone_line", None)
        return phone_line.get_origem_display() if phone_line and phone_line.origem else "-"

    def _delete_with_related_phone_line(self, request, sim_card):
        sim_card.delete(released_by=request.user)

    def get_deleted_objects(self, objs, request):
        deleted_objects = []
        model_count = {}

        for sim_card in objs:
            deleted_objects.append(str(sim_card))
            model_count["simcards"] = model_count.get("simcards", 0) + 1

            phone_line = PhoneLine.all_objects.filter(sim_card=sim_card).first()
            if phone_line and not phone_line.is_deleted:
                deleted_objects.append(
                    f"Linha vinculada (soft delete): {phone_line.phone_number}"
                )
                model_count["phone lines"] = model_count.get("phone lines", 0) + 1

        return deleted_objects, model_count, set(), []

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        phone_number = form.cleaned_data["phone_number"]
        origem = form.cleaned_data.get("origem")
        line_status = form.cleaned_data["line_status"]

        line = getattr(obj, "phone_line", None)
        if line:
            updated_fields = []
            if line.phone_number != phone_number:
                line.phone_number = phone_number
                updated_fields.append("phone_number")
            if line.origem != origem:
                line.origem = origem
                updated_fields.append("origem")
            if line.status != line_status:
                line.status = line_status
                updated_fields.append("status")
            if updated_fields:
                line.save(update_fields=updated_fields)
            return

        PhoneLine.create_or_reuse(
            phone_number=phone_number,
            sim_card=obj,
            status=line_status,
            origem=origem,
        )

    @transaction.atomic
    def delete_model(self, request, obj):
        self._delete_with_related_phone_line(request, obj)

    @transaction.atomic
    def delete_queryset(self, request, queryset):
        for sim_card in queryset.select_related("phone_line"):
            self._delete_with_related_phone_line(request, sim_card)


@admin.register(BlipConfiguration)
class BlipConfigurationAdmin(admin.ModelAdmin):
    list_display = ("blip_id", "type", "description", "phone_number", "key", "value")
    search_fields = ("blip_id", "description", "value")
    list_filter = ("type", "key")
