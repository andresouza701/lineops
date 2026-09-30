from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename

from pendencies.models import AllocationPendency
from telecom.models import LineDailyActionAuditEvent, PhoneLine, PhoneLineHistory
from telecom.whatsapp_seal import WhatsAppSeal, WhatsAppSealPayment

# REPORTS_SENIOR_REVIEW achado 3: Alocacoes/Historico da linha/Inventario de
# linhas/Pendencias calculam o limite exclusivo do periodo somando 1 dia a
# `data_final` (ver `_period_bounds` em core/services/*_report_service.py).
# Com data_final=date.max esse `+ timedelta(days=1)` estoura
# (`OverflowError: date value out of range`) antes de qualquer consulta ao
# banco — nunca capturado pela view. O ultimo `data_final` calculavel sem
# estourar e portanto date.max menos 1 dia; validado aqui como erro de
# campo (mesmo form usado por consulta e exportacao), nao como excecao
# tratada dentro do servico. Indicadores diarios e Selos WhatsApp NAO usam
# esse `+1 dia` (seus `_period_bounds` fecham em `time.max` do proprio
# `data_final`, sem aritmetica de data) e por isso nao precisam deste
# limite.
MAX_PERIOD_END_DATE = date.max - timedelta(days=1)


def _validate_period_end_within_representable_bound(form, cleaned_data):
    data_final = cleaned_data.get("data_final")
    if data_final and data_final > MAX_PERIOD_END_DATE:
        form.add_error(
            "data_final",
            f"Data final não pode ser posterior a "
            f"{MAX_PERIOD_END_DATE.strftime('%d/%m/%Y')}.",
        )


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


class AllocationsReportQueryForm(forms.Form):
    """Contrato comum (REL-07) + especifico (REL-10-C) da consulta de
    Alocacoes. Nao valida acesso/role — apenas forma e valores."""

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
    situacao_alocacao = forms.ChoiceField(
        choices=[("", "Todas"), ("ativa", "Ativa"), ("liberada", "Liberada")],
        required=False,
        error_messages={"invalid_choice": "Situação de alocação desconhecida."},
    )
    funcionario = forms.CharField(required=False, max_length=40, strip=True)
    linha = forms.CharField(required=False, max_length=20, strip=True)

    def clean(self):
        cleaned_data = super().clean()
        data_inicial = cleaned_data.get("data_inicial")
        data_final = cleaned_data.get("data_final")
        if data_inicial and data_final and data_final < data_inicial:
            self.add_error(
                "data_final", "Data final não pode ser anterior à data inicial."
            )
        _validate_period_end_within_representable_bound(self, cleaned_data)
        return cleaned_data


class LineHistoryReportQueryForm(forms.Form):
    """Contrato comum (REL-07) + especifico (REL-12-C) da consulta de
    Historico da linha. Nao valida acesso/role — apenas forma e valores.
    tipo_evento combina os 9 ActionType (PhoneLineHistory) e os 8 EventType
    (LineDailyActionAuditEvent), sem colisao de codigos (confirmado em
    REL-12-C). fonte_evento cobre a fonte legada fixa mais as 3 Source de
    auditoria — filtro `alocacao` explicitamente fora do escopo (decisao E),
    nunca adicionado aqui."""

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
    tipo_evento = forms.ChoiceField(
        choices=[("", "Todos")]
        + list(PhoneLineHistory.ActionType.choices)
        + list(LineDailyActionAuditEvent.EventType.choices),
        required=False,
        error_messages={"invalid_choice": "Tipo de evento desconhecido."},
    )
    fonte_evento = forms.ChoiceField(
        choices=[("", "Todas"), ("PHONE_LINE_HISTORY", "Histórico da linha")]
        + list(LineDailyActionAuditEvent.Source.choices),
        required=False,
        error_messages={"invalid_choice": "Fonte de evento desconhecida."},
    )
    ator = forms.CharField(required=False, max_length=150, strip=True)
    linha = forms.CharField(required=False, max_length=20, strip=True)

    def clean(self):
        cleaned_data = super().clean()
        data_inicial = cleaned_data.get("data_inicial")
        data_final = cleaned_data.get("data_final")
        if data_inicial and data_final and data_final < data_inicial:
            self.add_error(
                "data_final", "Data final não pode ser anterior à data inicial."
            )
        _validate_period_end_within_representable_bound(self, cleaned_data)
        return cleaned_data


class DailyIndicatorsReportQueryForm(forms.Form):
    """Contrato comum (REL-07) + especifico (REL-13-C) da consulta de
    Indicadores diarios. Nao valida acesso/role — apenas forma e valores.
    Sem filtro especifico proprio (REL-13-C secao 3): `linha` e comum a
    todos os relatorios (REPORT_COMMON_PARAM_NAMES) mas nao tem dimensao
    aplicavel a um indicador agregado por dia, entao e aceito pelo
    whitelist e rejeitado explicitamente aqui (400 "nao aplicavel"), em vez
    de simplesmente ignorado. `incluir_excluidos` continua aceito e
    validado normalmente (0/1), mas o motor de consulta nunca o le —
    resultado identico com ou sem o parametro (contrato HTTP documentado em
    REL-13-C)."""

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
    linha = forms.CharField(required=False, max_length=20, strip=True)

    def clean_linha(self):
        linha = self.cleaned_data.get("linha")
        if linha:
            raise ValidationError("Parâmetro não aplicável a este relatório: linha.")
        return linha

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
        _validate_period_end_within_representable_bound(self, cleaned_data)
        return cleaned_data


class PendenciesReportQueryForm(forms.Form):
    """Contrato comum (REL-07) + especifico (REL-11-C) da consulta de
    Pendencias. Nao valida acesso/role — apenas forma e valores."""

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
    situacao_pendencia = forms.ChoiceField(
        choices=[("", "Todas"), ("aberta", "Aberta"), ("resolvida", "Resolvida")],
        required=False,
        error_messages={"invalid_choice": "Situação de pendência desconhecida."},
    )
    motivo_pendencia = forms.ChoiceField(
        choices=[("", "Todos")]
        + [
            (value, label)
            for value, label in AllocationPendency.ActionType.choices
            if value != AllocationPendency.ActionType.NO_ACTION
        ],
        required=False,
        error_messages={"invalid_choice": "Motivo de pendência desconhecido."},
    )
    com_responsavel = forms.ChoiceField(
        choices=[("", "Todos"), ("com", "Com responsável"), ("sem", "Sem responsável")],
        required=False,
        error_messages={"invalid_choice": "Valor inválido para responsável."},
    )
    funcionario = forms.CharField(required=False, max_length=40, strip=True)
    linha = forms.CharField(required=False, max_length=20, strip=True)

    def clean(self):
        cleaned_data = super().clean()
        data_inicial = cleaned_data.get("data_inicial")
        data_final = cleaned_data.get("data_final")
        if data_inicial and data_final and data_final < data_inicial:
            self.add_error(
                "data_final", "Data final não pode ser anterior à data inicial."
            )
        _validate_period_end_within_representable_bound(self, cleaned_data)
        return cleaned_data
