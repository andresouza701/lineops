"""Regras de domínio do selo WHATS LINEOPS aplicado a uma linha telefônica."""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class WhatsAppSeal(models.TextChoices):
    META_ONE = "META_ONE", "META ONE"
    META_VERIFIED = "META_VERIFIED", "META VERIFICADO"


class WhatsAppSealPayment(models.TextChoices):
    CREDIT_CARD = "CREDIT_CARD", "CARTÃO CRÉDITO"
    GOOGLE_GIFT_CARD = "GOOGLE_GIFT_CARD", "GIFT CARD GOOGLE"


REQUIRED_FIELD_ERRORS = {
    "whatsapp_seal_activated_on": "Data de ativação do selo é obrigatória.",
    "whatsapp_seal_expires_on": "Data de vencimento do selo é obrigatória.",
    "whatsapp_seal_email": "E-mail cadastrado do selo é obrigatório.",
    "whatsapp_seal_payment": "Forma de pagamento do selo é obrigatória.",
}


def validate_seal_fields(*, seal, activated_on, expires_on, email, payment):
    """Valida obrigatoriedade condicional e ordem das datas do selo.

    Sem selo (seal vazio), nenhum campo adicional é exigido aqui — a
    limpeza dos dados relacionados é responsabilidade do fluxo de domínio
    que grava a linha (create_or_reuse / formulários), fora deste escopo.
    """
    if not seal:
        return

    errors = {}
    if not activated_on:
        errors["whatsapp_seal_activated_on"] = REQUIRED_FIELD_ERRORS["whatsapp_seal_activated_on"]
    if not expires_on:
        errors["whatsapp_seal_expires_on"] = REQUIRED_FIELD_ERRORS["whatsapp_seal_expires_on"]
    if not email:
        errors["whatsapp_seal_email"] = REQUIRED_FIELD_ERRORS["whatsapp_seal_email"]
    if not payment:
        errors["whatsapp_seal_payment"] = REQUIRED_FIELD_ERRORS["whatsapp_seal_payment"]

    if activated_on and expires_on and expires_on < activated_on:
        errors["whatsapp_seal_expires_on"] = (
            "Data de vencimento não pode ser anterior à data de ativação."
        )

    if errors:
        raise ValidationError(errors)


def clear_seal_fields(instance):
    """Limpa os dados do selo no fluxo de domínio quando não há selo ativo."""
    instance.whatsapp_seal = ""
    instance.whatsapp_seal_activated_on = None
    instance.whatsapp_seal_expires_on = None
    instance.whatsapp_seal_email = ""
    instance.whatsapp_seal_payment = ""


def compute_seal_status(seal, expires_on):
    """Indicador calculado pela data local da aplicação; nada é persistido."""
    if not seal or not expires_on:
        return {"tone": "neutral", "label": "Sem selo"}

    today = timezone.localdate()
    delta = (expires_on - today).days

    if delta > 7:
        return {"tone": "neutral", "label": f"Vence em {expires_on.strftime('%d/%m/%Y')}"}
    if delta > 0:
        unit = "dia" if delta == 1 else "dias"
        return {"tone": "warning", "label": f"Vence em {delta} {unit}"}
    if delta == 0:
        return {"tone": "today", "label": "Vence hoje"}

    overdue = abs(delta)
    unit = "dia" if overdue == 1 else "dias"
    return {"tone": "expired", "label": f"Vencido há {overdue} {unit}"}
