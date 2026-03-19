import re

from django.core.exceptions import ValidationError

ICCID_PATTERN = re.compile(r"^\d{19,22}$")
PHONE_NUMBER_PATTERN = re.compile(r"^\+?\d{10,15}$")


def normalize_iccid(value: str | None) -> str:
    return (value or "").strip()


def normalize_phone_number(value: str | None) -> str:
    raw = (value or "").strip()
    return re.sub(r"[\s\-()]+", "", raw)


def validate_iccid_format(iccid: str) -> str:
    if not ICCID_PATTERN.match(iccid):
        raise ValidationError("ICCID deve conter de 19 a 22 digitos numericos.")
    return iccid


def validate_phone_number_format(phone_number: str) -> str:
    if not PHONE_NUMBER_PATTERN.match(phone_number):
        raise ValidationError(
            "Linha deve conter entre 10 e 15 digitos (com + opcional)."
        )
    return phone_number


def parse_non_negative_int(value, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 0)
