from pathlib import Path
from uuid import uuid4

from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename

from telecom.models import PhoneLine
from telecom.whatsapp_seal import WhatsAppSeal, WhatsAppSealPayment

REPORT_CHOICES = [
    ("whatsapp_seal", "Selos WhatsApp"),
    ("line_inventory", "Inventário de linhas"),
    ("allocations", "Alocações"),
    ("pendencies", "Pendências"),
    ("line_history", "Histórico da linha"),
    ("daily_indicators", "Indicadores diários"),
]

SITUACAO_CHOICES = [
    ("", "Todas"),
    ("regular", "Vence após 7 dias"),
    ("warning", "Vence em até 7 dias"),
    ("today", "Vence hoje"),
    ("expired", "Vencido"),
    ("missing_expiry", "Sem vencimento informado"),
]


class UploadForm(forms.Form):
    file = forms.FileField(label="Arquivo (CSV ou XLSX)")

    allowed_extensions = {".csv", ".xlsx"}
    max_upload_size = 25 * 1024 * 1024  # 25 MB

    def clean_file(self):
        uploaded_file = self.cleaned_data.get("file")
        if not uploaded_file:
            raise ValidationError("Nenhum arquivo foi enviado.")

        extension = Path(uploaded_file.name).suffix.lower()
        if extension not in self.allowed_extensions:
            raise ValidationError("Envie um arquivo CSV ou XLSX.")

        if uploaded_file.size > self.max_upload_size:
            raise ValidationError("Arquivo muito grande. Limite de 25 MB.")

        sample = uploaded_file.read(2048)
        uploaded_file.seek(0)
        if extension == ".xlsx" and not sample.startswith(b"PK\x03\x04"):
            raise ValidationError("Arquivo XLSX invalido ou corrompido.")
        if extension == ".csv" and b"\x00" in sample:
            raise ValidationError("Arquivo CSV invalido.")

        # Sanitize user-provided filenames and avoid path traversal/collisions.
        stem = get_valid_filename(Path(uploaded_file.name).stem) or "upload"
        uploaded_file.name = f"{stem}-{uuid4().hex[:8]}{extension}"
        return uploaded_file


class WhatsAppSealReportQueryForm(forms.Form):
    """Contrato comum (REL-07) + especifico (REL-08-C) da consulta de
    Selos WhatsApp. Nao valida acesso/role — apenas forma e valores."""

    relatorio = forms.ChoiceField(
        choices=REPORT_CHOICES,
        error_messages={
            "required": "Selecione um relatório.",
            "invalid_choice": "Relatório desconhecido.",
        },
    )
    data_inicial = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        error_messages={
            "required": "Data inicial é obrigatória.",
            "invalid": "Data inicial inválida.",
        },
    )
    data_final = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        error_messages={
            "required": "Data final é obrigatória.",
            "invalid": "Data final inválida.",
        },
    )
    incluir_excluidos = forms.TypedChoiceField(
        choices=[("0", "Não"), ("1", "Sim")],
        required=False,
        coerce=lambda value: value == "1",
        empty_value=False,
        error_messages={"invalid_choice": "Valor inválido para incluir excluídos."},
    )
    page = forms.IntegerField(
        required=False,
        min_value=1,
        error_messages={
            "invalid": "Página inválida.",
            "min_value": "Página inválida.",
        },
    )
    selo = forms.ChoiceField(
        choices=[("", "Todos")] + list(WhatsAppSeal.choices),
        required=False,
        error_messages={"invalid_choice": "Tipo de selo desconhecido."},
    )
    pagamento = forms.ChoiceField(
        choices=[("", "Todos")] + list(WhatsAppSealPayment.choices),
        required=False,
        error_messages={"invalid_choice": "Forma de pagamento desconhecida."},
    )
    situacao = forms.ChoiceField(
        choices=SITUACAO_CHOICES,
        required=False,
        error_messages={"invalid_choice": "Situação de vencimento desconhecida."},
    )
    linha = forms.CharField(required=False, max_length=20, strip=True)

    def clean(self):
        cleaned_data = super().clean()
        data_inicial = cleaned_data.get("data_inicial")
        data_final = cleaned_data.get("data_final")
        if data_inicial and data_final and data_final < data_inicial:
            self.add_error(
                "data_final", "Data final não pode ser anterior à data inicial."
            )
        return cleaned_data


class LineInventoryReportQueryForm(forms.Form):
    """Contrato comum (REL-07) + especifico (REL-09-C, com as definicoes
    aprovadas em 2026-09-25: tokens com/sem para com_selo/com_vinculo e
    limite de 100 caracteres pos-trim para operadora) da consulta de
    Inventario de linhas. Nao valida acesso/role — apenas forma e valores."""

    relatorio = forms.ChoiceField(
        choices=REPORT_CHOICES,
        error_messages={
            "required": "Selecione um relatório.",
            "invalid_choice": "Relatório desconhecido.",
        },
    )
    data_inicial = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        error_messages={
            "required": "Data inicial é obrigatória.",
            "invalid": "Data inicial inválida.",
        },
    )
    data_final = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        error_messages={
            "required": "Data final é obrigatória.",
            "invalid": "Data final inválida.",
        },
    )
    incluir_excluidos = forms.TypedChoiceField(
        choices=[("0", "Não"), ("1", "Sim")],
        required=False,
        coerce=lambda value: value == "1",
        empty_value=False,
        error_messages={"invalid_choice": "Valor inválido para incluir excluídos."},
    )
    page = forms.IntegerField(
        required=False,
        min_value=1,
        error_messages={
            "invalid": "Página inválida.",
            "min_value": "Página inválida.",
        },
    )
    status_linha = forms.ChoiceField(
        choices=[("", "Todos")] + list(PhoneLine.Status.choices),
        required=False,
        error_messages={"invalid_choice": "Status desconhecido."},
    )
    operadora = forms.CharField(required=False, max_length=100, strip=True)
    origem = forms.ChoiceField(
        choices=[("", "Todos")] + list(PhoneLine.Origem.choices),
        required=False,
        error_messages={"invalid_choice": "Origem desconhecida."},
    )
    canal = forms.ChoiceField(
        choices=[("", "Todos")] + list(PhoneLine.Canal.choices),
        required=False,
        error_messages={"invalid_choice": "Canal desconhecido."},
    )
    com_selo = forms.ChoiceField(
        choices=[("", "Todos"), ("com", "Com selo"), ("sem", "Sem selo")],
        required=False,
        error_messages={"invalid_choice": "Valor inválido para presença de selo."},
    )
    com_vinculo = forms.ChoiceField(
        choices=[("", "Todos"), ("com", "Com vínculo"), ("sem", "Sem vínculo")],
        required=False,
        error_messages={"invalid_choice": "Valor inválido para vínculo."},
    )
    linha = forms.CharField(required=False, max_length=20, strip=True)

    def clean(self):
        cleaned_data = super().clean()
        data_inicial = cleaned_data.get("data_inicial")
        data_final = cleaned_data.get("data_final")
        if data_inicial and data_final and data_final < data_inicial:
            self.add_error(
                "data_final", "Data final não pode ser anterior à data inicial."
            )
        return cleaned_data
