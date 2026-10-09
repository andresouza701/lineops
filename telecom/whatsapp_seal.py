"""Regras de domínio do selo WHATS LINEOPS aplicado a uma linha telefônica."""

import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class WhatsAppSeal(models.TextChoices):
    META_ONE = "META_ONE", "META ONE"
    META_VERIFIED = "META_VERIFIED", "META VERIFICADO"


class WhatsAppSealPayment(models.TextChoices):
    CREDIT_CARD = "CREDIT_CARD", "CARTÃO CRÉDITO"
    GOOGLE_GIFT_CARD = "GOOGLE_GIFT_CARD", "GIFT CARD GOOGLE"


class WhatsAppSealActivationStatus(models.TextChoices):
    """Situação de ativação do selo. Vazio ("") não é um membro desta
    classe: representa ausência de selo/situação, nunca uma linha com
    selo persistido — ver validate_seal_fields."""

    NOT_ACTIVATED = "NOT_ACTIVATED", "Não ativado"
    ACTIVE = "ACTIVE", "Ativo"


class WhatsAppSealCategory(models.TextChoices):
    CREATORS_BUSINESSES = "CREATORS_BUSINESSES", "Criadores / Empresas"
    PERSONAL_CREATOR = "PERSONAL_CREATOR", "Pessoa Física (Uso Pessoal / Criador)"
    BUSINESS_SME = "BUSINESS_SME", "Pessoa Jurídica (Empresas / PMEs)"
    BUSINESS = "BUSINESS", "Pessoa Jurídica (Empresas)"


class WhatsAppSealPlan(models.TextChoices):
    ONE_ESSENTIAL = "ONE_ESSENTIAL", "One Essencial"
    STANDARD = "STANDARD", "Standard"
    BUSINESS_BASIC = "BUSINESS_BASIC", "Business Básico"
    BUSINESS_PLUS = "BUSINESS_PLUS", "Business Plus"


# Catálogo centralizado — as quatro combinações aprovadas de selo/categoria/
# plano (fonte: docs/superpowers/specs/2026-09-30-whatsapp-seal-activation-
# value-design.md, adendo de 01/10/2026). Usado para validação cruzada; não
# há tabela/tela de gestão de catálogo nesta entrega. Ordem fixada (mesma da
# tabela da spec) para serialização determinística ao formulário (SEV-06,
# ver seal_catalog_entries) — SEAL_CATALOG_COMBINATIONS deriva desta ordem,
# não duplica a fonte.
SEAL_CATALOG_ORDER = (
    (WhatsAppSeal.META_ONE, WhatsAppSealCategory.CREATORS_BUSINESSES, WhatsAppSealPlan.ONE_ESSENTIAL),
    (WhatsAppSeal.META_VERIFIED, WhatsAppSealCategory.PERSONAL_CREATOR, WhatsAppSealPlan.STANDARD),
    (WhatsAppSeal.META_VERIFIED, WhatsAppSealCategory.BUSINESS_SME, WhatsAppSealPlan.BUSINESS_BASIC),
    (WhatsAppSeal.META_VERIFIED, WhatsAppSealCategory.BUSINESS, WhatsAppSealPlan.BUSINESS_PLUS),
)
SEAL_CATALOG_COMBINATIONS = frozenset(SEAL_CATALOG_ORDER)

# Referências de preço — ajuda visual (SEV-06), nunca limite de validação:
# faixas não cabem em Decimal e não restringem nem preenchem o valor efetivo.
SEAL_PRICE_REFERENCE_LABELS = {
    (WhatsAppSeal.META_ONE, WhatsAppSealCategory.CREATORS_BUSINESSES, WhatsAppSealPlan.ONE_ESSENTIAL): "R$ 59,00",
    (WhatsAppSeal.META_VERIFIED, WhatsAppSealCategory.PERSONAL_CREATOR, WhatsAppSealPlan.STANDARD): (
        "R$ 53,90 a R$ 69,90 (varia por app/iOS/web)"
    ),
    (WhatsAppSeal.META_VERIFIED, WhatsAppSealCategory.BUSINESS_SME, WhatsAppSealPlan.BUSINESS_BASIC): "R$ 53,90",
    (WhatsAppSeal.META_VERIFIED, WhatsAppSealCategory.BUSINESS, WhatsAppSealPlan.BUSINESS_PLUS): (
        "R$ 109,00 a R$ 120,90"
    ),
}


def seal_catalog_entries():
    """Serialização segura do catálogo para o formulário (SEV-06): uma lista
    ordenada de dicts (JSON-serializável via json_script), derivada de
    SEAL_CATALOG_ORDER/SEAL_PRICE_REFERENCE_LABELS — nenhuma segunda fonte de
    catálogo é criada. Usada pelo JS para filtrar categoria/plano por tipo de
    selo e exibir a referência de preço, sem concatenar HTML/JS com dados."""
    return [
        {
            "seal": seal.value,
            "category": category.value,
            "category_label": WhatsAppSealCategory(category).label,
            "plan": plan.value,
            "plan_label": WhatsAppSealPlan(plan).label,
            "price_reference": SEAL_PRICE_REFERENCE_LABELS.get((seal, category, plan), ""),
        }
        for seal, category, plan in SEAL_CATALOG_ORDER
    ]


SEAL_MONTHLY_VALUE_MAX = Decimal("299.00")
SEAL_MONTHLY_VALUE_ACTIVE_MIN = Decimal("0.01")
SEAL_MONTHLY_VALUE_NOT_ACTIVATED_MIN = Decimal("0.00")

REQUIRED_FIELD_ERRORS = {
    "whatsapp_seal_activated_on": "Data de ativação do selo é obrigatória.",
    "whatsapp_seal_expires_on": "Data de vencimento do selo é obrigatória.",
    "whatsapp_seal_email": "E-mail cadastrado do selo é obrigatório.",
    "whatsapp_seal_payment": "Forma de pagamento do selo é obrigatória.",
    "whatsapp_seal_activation_status": "Situação de ativação do selo é obrigatória.",
    "whatsapp_seal_category": "Categoria do selo é obrigatória.",
    "whatsapp_seal_plan": "Plano do selo é obrigatório.",
    "whatsapp_seal_monthly_value": "Valor mensal do selo é obrigatório.",
}


def validate_seal_fields(
    *,
    seal,
    activation_status,
    activated_on,
    expires_on,
    email,
    payment,
    category,
    plan,
    monthly_value,
):
    """Validação única e incondicional do contrato de selo: situação,
    categoria, plano e valor mensal são obrigatórios e validados (catálogo,
    fronteiras monetárias) sempre que há selo — sem exceção, sem portão de
    compatibilidade. Ausência simultânea dos 4 campos novos NÃO dispensa a
    obrigatoriedade; é exatamente o caso que deve ser rejeitado.

    Chamada por PhoneLine.clean() incondicionalmente quando há selo. Quem
    invoca full_clean() sobre uma instância com selo e os 4 campos novos
    ausentes — incluindo o ModelForm atual, que ainda não os expõe — deve
    receber um ValidationError com esses campos, não uma aprovação
    silenciosa. A integração de telecom/forms.py com esses campos (SEV-05)
    é o que falta para que o formulário exiba esse erro corretamente; ver
    Registro de execução (retificação de SEV-04) para o estado exato dessa
    fronteira — isto não resolve nem mascara essa integração ausente.

    Sem selo (seal vazio), nenhum campo adicional é exigido aqui — a limpeza
    é responsabilidade de normalize_seal_fields, explicitamente separada
    desta validação.
    """
    if not seal:
        return

    errors = {}

    if not activation_status:
        errors["whatsapp_seal_activation_status"] = REQUIRED_FIELD_ERRORS[
            "whatsapp_seal_activation_status"
        ]
    elif activation_status not in WhatsAppSealActivationStatus.values:
        errors["whatsapp_seal_activation_status"] = "Situação de ativação do selo é inválida."

    if not category:
        errors["whatsapp_seal_category"] = REQUIRED_FIELD_ERRORS["whatsapp_seal_category"]
    elif category not in WhatsAppSealCategory.values:
        errors["whatsapp_seal_category"] = "Categoria do selo é inválida."

    if not plan:
        errors["whatsapp_seal_plan"] = REQUIRED_FIELD_ERRORS["whatsapp_seal_plan"]
    elif plan not in WhatsAppSealPlan.values:
        errors["whatsapp_seal_plan"] = "Plano do selo é inválido."

    if (
        "whatsapp_seal_category" not in errors
        and "whatsapp_seal_plan" not in errors
        and (seal, category, plan) not in SEAL_CATALOG_COMBINATIONS
    ):
        errors["whatsapp_seal_plan"] = (
            "Combinação de selo, categoria e plano não faz parte do catálogo."
        )

    if not email:
        errors["whatsapp_seal_email"] = REQUIRED_FIELD_ERRORS["whatsapp_seal_email"]
    if not payment:
        errors["whatsapp_seal_payment"] = REQUIRED_FIELD_ERRORS["whatsapp_seal_payment"]

    if activation_status == WhatsAppSealActivationStatus.ACTIVE:
        if not activated_on:
            errors["whatsapp_seal_activated_on"] = REQUIRED_FIELD_ERRORS[
                "whatsapp_seal_activated_on"
            ]
        if not expires_on:
            errors["whatsapp_seal_expires_on"] = REQUIRED_FIELD_ERRORS[
                "whatsapp_seal_expires_on"
            ]
    elif activation_status == WhatsAppSealActivationStatus.NOT_ACTIVATED:
        if activated_on is not None or expires_on is not None:
            errors["whatsapp_seal_activated_on"] = (
                "Selo não ativado não pode ter datas de ativação/vencimento preenchidas."
            )

    # Independente da situação: datas invertidas nunca fazem sentido quando
    # ambas estão presentes (checagem preservada do comportamento anterior
    # a este adendo, não condicionada a ACTIVE).
    if (
        "whatsapp_seal_expires_on" not in errors
        and activated_on
        and expires_on
        and expires_on < activated_on
    ):
        errors["whatsapp_seal_expires_on"] = (
            "Data de vencimento não pode ser anterior à data de ativação."
        )

    if monthly_value is None:
        errors["whatsapp_seal_monthly_value"] = REQUIRED_FIELD_ERRORS[
            "whatsapp_seal_monthly_value"
        ]
    elif monthly_value < 0:
        errors["whatsapp_seal_monthly_value"] = "Valor mensal do selo não pode ser negativo."
    elif (
        activation_status == WhatsAppSealActivationStatus.ACTIVE
        and monthly_value < SEAL_MONTHLY_VALUE_ACTIVE_MIN
    ):
        errors["whatsapp_seal_monthly_value"] = (
            "Selo ativo exige valor mensal maior que zero."
        )
    elif monthly_value > SEAL_MONTHLY_VALUE_MAX:
        errors["whatsapp_seal_monthly_value"] = (
            f"Valor mensal do selo não pode ultrapassar R$ {SEAL_MONTHLY_VALUE_MAX}."
        )

    if errors:
        raise ValidationError(errors)


# Formato textual aceito pelo campo de valor mensal do formulário (SEV-02):
# dígitos, separador decimal opcional (vírgula ou ponto) com 1-2 casas,
# nunca sinal. Qualquer sinal de menos — inclusive em "-0,00" — é rejeitado
# aqui, antes de qualquer interpretação numérica: o contrato exige rejeitar
# "-0,00" mesmo sendo numericamente igual a zero (Decimal("-0.00") < 0 é
# False em Python), então a rejeição precisa ser textual, não aritmética.
_SEAL_MONTHLY_VALUE_PATTERN = re.compile(r"^\d+([.,]\d{1,2})?$")


def parse_seal_monthly_value(raw):
    """Converte a entrada textual do valor mensal do selo em Decimal.

    Aceita dígitos com zero, uma ou duas casas decimais, separador vírgula
    ou ponto, espaços externos. Rejeita símbolo monetário, separador de
    milhar, separadores misturados, notação científica, NaN/Infinity, mais
    de duas casas e qualquer sinal (inclusive "-0,00"). String vazia (após
    remover espaços) retorna None — ausência de valor, distinta de zero
    explícito. Levanta ValueError para qualquer formato inválido; quem
    chama decide como transformar isso em erro de campo.
    """
    if raw is None:
        return None
    text = raw.strip()
    if text == "":
        return None
    if not _SEAL_MONTHLY_VALUE_PATTERN.match(text):
        raise ValueError(f"Formato de valor monetário inválido: {raw!r}")
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"Formato de valor monetário inválido: {raw!r}") from exc


def clear_seal_fields(instance):
    """Limpa todos os dados próprios do selo (fluxo de domínio Sem selo)."""
    instance.whatsapp_seal = ""
    instance.whatsapp_seal_activation_status = ""
    instance.whatsapp_seal_category = ""
    instance.whatsapp_seal_plan = ""
    instance.whatsapp_seal_monthly_value = None
    instance.whatsapp_seal_activated_on = None
    instance.whatsapp_seal_expires_on = None
    instance.whatsapp_seal_email = ""
    instance.whatsapp_seal_payment = ""


def normalize_seal_fields(instance):
    """Normalização explícita, separada da validação (validate_seal_fields).

    - Sem selo: limpa todos os dados próprios do selo.
    - Não ativado: limpa apenas as datas (inaplicáveis), preserva tipo,
      categoria, plano, valor, e-mail e pagamento.
    - Ativo (ou qualquer outro estado): não normaliza nada; validação decide.
    """
    if not instance.whatsapp_seal:
        clear_seal_fields(instance)
        return

    if instance.whatsapp_seal_activation_status == WhatsAppSealActivationStatus.NOT_ACTIVATED:
        instance.whatsapp_seal_activated_on = None
        instance.whatsapp_seal_expires_on = None


def classify_seal_expiry(expires_on):
    """Classifica um vencimento em faixa relativa a hoje (timezone.localdate()).

    Única rotina de cálculo de dias restantes do domínio de selo: fonte
    única reaproveitada por compute_seal_status (rótulo textual, abaixo) e
    pela projeção de apresentação (SVI-04, cor do indicador), para que a
    fronteira de dias nunca seja recalculada em dois lugares.

    Retorna {"bucket": ..., "days": delta}. bucket é "ok" (> 7 dias),
    "warning" (1 a 7 dias), "today" (vence hoje) ou "expired" (vencido).
    Não trata Sem selo/Não ativado: responsabilidade de quem chama.
    """
    today = timezone.localdate()
    delta = (expires_on - today).days

    if delta > 7:
        bucket = "ok"
    elif delta > 0:
        bucket = "warning"
    elif delta == 0:
        bucket = "today"
    else:
        bucket = "expired"
    return {"bucket": bucket, "days": delta}


def compute_seal_status(seal, expires_on, activation_status=""):
    """Indicador calculado pela data local da aplicação; nada é persistido.

    Não ativado (explícito via activation_status, ou implícito quando não
    há vencimento cadastrado) nunca gera alerta de vencimento — distinto de
    Sem selo. Selo ativo vencido permanece ACTIVE quanto à ativação; apenas
    o rótulo do indicador muda (ver ramos de alerta abaixo).
    """
    if not seal:
        return {"tone": "neutral", "label": "Sem selo"}

    if activation_status == WhatsAppSealActivationStatus.NOT_ACTIVATED or not expires_on:
        return {"tone": "neutral", "label": "Não ativado"}

    classification = classify_seal_expiry(expires_on)
    delta = classification["days"]

    if classification["bucket"] == "ok":
        return {"tone": "neutral", "label": f"Vence em {expires_on.strftime('%d/%m/%Y')}"}
    if classification["bucket"] == "warning":
        unit = "dia" if delta == 1 else "dias"
        return {"tone": "warning", "label": f"Vence em {delta} {unit}"}
    if classification["bucket"] == "today":
        return {"tone": "today", "label": "Vence hoje"}

    overdue = abs(delta)
    unit = "dia" if overdue == 1 else "dias"
    return {"tone": "expired", "label": f"Vencido há {overdue} {unit}"}
