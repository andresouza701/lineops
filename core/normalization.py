import re
import unicodedata

from core.constants import B2B_PORTFOLIOS, B2C_PORTFOLIOS

NAME_LOWERCASE_PARTICLES = {"da", "das", "de", "do", "dos", "e"}
FORCE_UPPERCASE_TOKENS = {
    "algar",
    "b2b",
    "b2c",
    "claro",
    "mv",
    "oi",
    "pa",
    "qa",
    "rh",
    "tim",
    "vivo",
}
PORTFOLIO_ALIASES = {
    "viasata": "ViaSat",
}
CARRIER_ALIASES = {
    "algar": "ALGAR",
    "claro": "CLARO",
    "nextel": "Nextel",
    "oi": "OI",
    "tim": "TIM",
    "vivo": "VIVO",
}
UNIT_CHOICES = (
    "Joinville",
    "Araquari",
)


def collapse_whitespace(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def normalize_lookup_key(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", collapse_whitespace(value))
    without_diacritics = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9]+", "", without_diacritics.lower())


def _build_choice_map(values: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for value, label in values:
        mapping[normalize_lookup_key(value)] = value
        mapping[normalize_lookup_key(label)] = value
    return mapping


PORTFOLIO_CANONICAL_MAP = _build_choice_map(B2B_PORTFOLIOS + B2C_PORTFOLIOS)
UNIT_CANONICAL_MAP = {
    normalize_lookup_key(unit): unit for unit in UNIT_CHOICES
}


def normalize_full_name(value: str | None) -> str:
    raw = collapse_whitespace(value)
    if not raw:
        return ""

    tokens = []
    for index, token in enumerate(raw.lower().split()):
        if index > 0 and token in NAME_LOWERCASE_PARTICLES:
            tokens.append(token)
            continue
        tokens.append(_normalize_name_token(token))
    return " ".join(tokens)


def _normalize_name_token(token: str) -> str:
    apostrophe_parts = token.split("'")
    normalized_parts = []
    for part in apostrophe_parts:
        hyphen_parts = [piece.capitalize() for piece in part.split("-") if piece]
        normalized_parts.append("-".join(hyphen_parts))
    return "'".join(normalized_parts)


def normalize_email_address(value: str | None) -> str:
    return collapse_whitespace(value).lower()


def normalize_portfolio_value(value: str | None) -> str:
    raw = collapse_whitespace(value)
    if not raw:
        return ""

    key = normalize_lookup_key(raw)
    if key in PORTFOLIO_ALIASES:
        return PORTFOLIO_ALIASES[key]
    return PORTFOLIO_CANONICAL_MAP.get(key, raw)


def normalize_unit_value(value: str | None) -> str:
    raw = collapse_whitespace(value)
    if not raw:
        return ""

    key = normalize_lookup_key(raw)
    return UNIT_CANONICAL_MAP.get(key, raw)


def normalize_carrier_name(value: str | None) -> str:
    raw = collapse_whitespace(value)
    if not raw:
        return ""

    key = normalize_lookup_key(raw)
    if key in CARRIER_ALIASES:
        return CARRIER_ALIASES[key]
    if raw.islower() or raw.isupper():
        return _normalize_label_case(raw)
    return raw


def _normalize_label_case(value: str) -> str:
    tokens = []
    for token in value.split():
        pieces = re.split(r"([-/])", token)
        normalized = []
        for piece in pieces:
            if piece in {"-", "/"}:
                normalized.append(piece)
                continue
            normalized.append(_normalize_label_piece(piece))
        tokens.append("".join(normalized))
    return " ".join(tokens)


def _normalize_label_piece(piece: str) -> str:
    if not piece:
        return ""

    key = normalize_lookup_key(piece)
    if key in FORCE_UPPERCASE_TOKENS:
        return piece.upper()

    compact = re.sub(r"[^A-Za-z0-9]+", "", piece)
    if compact.isalpha() and len(compact) <= 2:
        return piece.upper()

    return piece[:1].upper() + piece[1:].lower()
