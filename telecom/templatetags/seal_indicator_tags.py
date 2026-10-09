"""Template tag do componente visual compartilhado do indicador de selo
(SVI-04). Renderiza telecom/_seal_indicator.html a partir de um
SealIndicator (telecom/seal_indicator.py) já construído pelo chamador —
esta tag não calcula estado, não acessa banco e não recebe PhoneLine."""

import json

from django import template

from telecom.seal_indicator import seal_indicator_for_phone_line

register = template.Library()


@register.inclusion_tag("telecom/_seal_indicator.html")
def seal_indicator(indicator):
    return {"indicator": indicator}


@register.filter
def to_seal_indicator(phone_line, is_historical=False):
    """Converte uma PhoneLine já carregada (ou None) num SealIndicator,
    para uso direto em template: `{% seal_indicator line|to_seal_indicator %}`.
    Não acessa banco (telecom/seal_indicator.py::seal_indicator_for_phone_line)."""
    return seal_indicator_for_phone_line(phone_line, is_historical=is_historical)


@register.filter
def seal_indicator_json(indicator):
    """Serializa um SealIndicator ja construido para JSON, para uso num
    atributo data-* consumido por SealIndicator.createNode (JS) — caso de
    botao/trigger server-rendered que alimenta um modal sincrono (sem AJAX),
    sem introduzir uma segunda fonte de verdade do HTML do indicador."""
    return json.dumps(indicator.as_dict())


@register.filter
def dict_get(mapping, key):
    """Busca por chave dinâmica num dict já resolvido em lote na view —
    Django não resolve `{{ dict.variavel }}` como lookup por variável,
    apenas por token literal. Nenhuma consulta aqui, só leitura do dict."""
    if mapping is None:
        return None
    return mapping.get(key)
