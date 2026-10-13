import threading

from django import forms
from django.contrib import admin
from django.db import transaction
from django.utils.html import format_html

from core.normalization import normalize_carrier_name
from core.validation import normalize_phone_number, validate_phone_number_format

from .blip_lines import build_authorized_blip_line_index
from .models import BlipConfiguration, PhoneLine, SIMcard
from .seal_indicator import render_seal_indicator_html

OPTIONAL_SELECT_CHOICES = [("", "---------")]


class SIMcardAdminForm(forms.ModelForm):
    phone_number = forms.CharField(
        label="Linha",
        max_length=20,
        required=True,
        help_text="Numero da linha vinculado ao SIM card.",
    )
    origem = forms.ChoiceField(
        label="Origem",
        choices=OPTIONAL_SELECT_CHOICES + list(PhoneLine.Origem.choices),
        required=False,
    )
    canal = forms.ChoiceField(
        label="Canal",
        choices=OPTIONAL_SELECT_CHOICES + list(PhoneLine.Canal.choices),
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
            self.fields["canal"].initial = self.instance.phone_line.canal
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

    def clean_carrier(self):
        return normalize_carrier_name(self.cleaned_data.get("carrier"))


@admin.register(SIMcard)
class SIMcardAdmin(admin.ModelAdmin):
    form = SIMcardAdminForm
    list_select_related = ("phone_line",)

    class Media:
        # SVI-07 (checagem final): so o CSS ESCOPADO do indicador — o
        # Admin do Django nao carrega CSS do projeto por padrao, e
        # carregar static/css/styles.css INTEIRO vazava regras globais
        # (body/input/select/h1/table) para os controles nativos do
        # Admin (achado real, texto quase ilegivel em <input> — ver
        # docs/superpowers/evidence/SVI-07/admin_css_check/). Sem este
        # arquivo, o indicador fica no DOM mas sem forma/cor/foco (ver
        # telecom/test_seal_indicator_admin_styles_svi07.py).
        css = {"all": ("css/seal_indicator.css",)}
    list_display = (
        "iccid",
        "carrier",
        "status",
        "phone_number",
        "line_status",
        "origem",
        "canal",
        "activated_at",
    )
    search_fields = ("iccid", "carrier", "phone_line__phone_number")
    list_filter = (
        "status",
        "carrier",
        "phone_line__status",
        "phone_line__origem",
        "phone_line__canal",
    )

    @admin.display(description="Linha")
    def phone_number(self, obj):
        phone_line = getattr(obj, "phone_line", None)
        number = getattr(phone_line, "phone_number", "-")
        if phone_line is None:
            return number
        return format_html("{}{}", render_seal_indicator_html(phone_line), number)

    @admin.display(description="Status da linha")
    def line_status(self, obj):
        phone_line = getattr(obj, "phone_line", None)
        return phone_line.get_status_display() if phone_line else "-"

    @admin.display(description="Origem")
    def origem(self, obj):
        phone_line = getattr(obj, "phone_line", None)
        return phone_line.get_origem_display() if phone_line and phone_line.origem else "-"

    @admin.display(description="Canal")
    def canal(self, obj):
        phone_line = getattr(obj, "phone_line", None)
        return phone_line.get_canal_display() if phone_line and phone_line.canal else "-"

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
        canal = form.cleaned_data.get("canal")
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
            if line.canal != canal:
                line.canal = canal
                updated_fields.append("canal")
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
            canal=canal,
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
    class Media:
        # SVI-07 (checagem final): ver SIMcardAdmin.Media acima — mesma
        # causa/correcao (so o CSS escopado, nao o arquivo inteiro).
        css = {"all": ("css/seal_indicator.css",)}

    list_display = (
        "blip_id",
        "type",
        "description",
        "phone_number_display",
        "key",
        "value",
    )
    search_fields = ("blip_id", "description", "value")
    list_filter = ("type", "key")

    # SVI-07: nao usar atributo de instancia (self) para este cache. A
    # instancia de ModelAdmin e um singleton por processo (registrado uma
    # vez em admin.site), compartilhado entre threads do mesmo worker
    # gunicorn (--threads 2..4, ver Dockerfile/docker-compose.yml; gunicorn
    # promove automaticamente sync->gthread quando threads>1, confirmado
    # no source de gunicorn/config.py instalado no venv — ver docstring de
    # telecom/test_seal_indicator_admin_concurrency_svi07.py). Duas
    # requisicoes concorrentes (inclusive de usuarios com roles/escopos
    # diferentes) podiam sobrescrever o indice uma da outra antes da
    # renderizacao terminar (defeito confirmado e corrigido em SVI-07).
    # threading.local() isola por thread; Django chama get_queryset(request)
    # exatamente uma vez por requisicao de changelist, sincronamente, antes
    # de qualquer list_display (django/contrib/admin/views/main.py,
    # ChangeList.__init__) — sob gthread (threads de SO reais, sem
    # corrotinas que intercalem dentro de uma thread), isolar por thread
    # equivale a isolar por requisicao. RETIFICACAO (checagem final
    # SVI-07): essa equivalencia e CONDICIONAL, nao automatica — gthread
    # REUTILIZA threads entre requisicoes ao longo da vida do worker (nao
    # e thread nova por requisicao); a seguranca vem de get_queryset
    # SEMPRE substituir o indice ANTES de qualquer leitura por
    # phone_number_display PARA A MESMA requisicao (garantido pelo
    # ChangeList do Django, nao por threading.local em si). Se esse
    # invariante de ordem de chamada for quebrado no futuro, a protecao
    # deixa de valer mesmo com threading.local() em uso. Testado:
    # concorrencia real entre threads (test_second_thread_request_...),
    # reuso sequencial na mesma thread
    # (test_successive_requests_on_same_thread_...), e caminho de excecao
    # (test_failed_get_queryset_...) — ver
    # telecom/test_seal_indicator_admin_concurrency_svi07.py.
    _blip_line_index_storage = threading.local()

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # BlipConfiguration.phone_number nao tem FK (I26, mesma lacuna de
        # I23): resolve em UMA consulta em lote por changelist, nunca por
        # linha.
        self._blip_line_index_storage.index = build_authorized_blip_line_index(request.user)
        return queryset

    @admin.display(description="Numero Telefone")
    def phone_number_display(self, obj):
        index = getattr(self._blip_line_index_storage, "index", None) or {}
        phone_line = index.get(obj.phone_number)
        return format_html(
            "{}{}", render_seal_indicator_html(phone_line), obj.phone_number
        )
