"""Resolução de PhoneLine autorizada para BlipConfiguration.phone_number
(SVI-05). BlipConfiguration.phone_number é BigIntegerField sem FK — a
mesma regra de "conjunto autorizado" já usada por BlipConfigurationForm
(origem=BLIP, não excluído, SIMcard não excluído, PhoneLine.visible_to_user)
é reaproveitada aqui, não duplicada com critério divergente, para que
lista/formulário/indicador nunca discordem sobre o que é uma linha BLIP
"autorizada".

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md, borda aprovada #2 do fechamento SVI-02: associação
exata, única e autorizada; número fora do conjunto, ou cuja normalização
numérica colida entre duas linhas autorizadas, nunca resolve — nunca por
exclusão ou escolha arbitrária.
"""

from telecom.models import PhoneLine


def get_authorized_blip_lines_queryset(user):
    """Mesmo critério de candidatos do BlipConfigurationForm (telecom/
    forms.py::BlipConfigurationForm.__init__): única fonte de verdade do
    conjunto "autorizado" para número BLIP."""
    return PhoneLine.visible_to_user(
        user,
        PhoneLine.objects.filter(
            is_deleted=False,
            sim_card__is_deleted=False,
            origem=PhoneLine.Origem.BLIP,
        ),
    )


def build_authorized_blip_line_index(user):
    """Uma única consulta em lote: {numero_normalizado: PhoneLine | None}.
    None marca um número cuja normalização colide entre duas (ou mais)
    linhas autorizadas distintas — ambíguo, nunca escolhido arbitrariamente,
    tratado como não resolvível pelo chamador (mesma política de "Selo
    indisponível" de uma linha ausente)."""
    index = {}
    for line in get_authorized_blip_lines_queryset(user):
        try:
            key = int(line.phone_number)
        except (TypeError, ValueError):
            continue
        if key in index:
            index[key] = None
        else:
            index[key] = line
    return index


def resolve_blip_phone_line(user, phone_number):
    """Resolve um único BlipConfiguration.phone_number (int) a partir do
    mesmo índice em lote — usada pela tela de edição (um registro por
    página), nunca em loop por linha de lista."""
    return build_authorized_blip_line_index(user).get(int(phone_number))
