"""Política compartilhada de bloqueio de abertura/reabertura de pendência
por origem da linha (POR-04).

Fonte da verdade: docs/superpowers/specs/2026-10-13-pendency-origin-
restriction-design.md, seção "Fechamento das quatro decisões — 2026-10-13".
Função pura de domínio: recebe a instância de PhoneLine já persistida (ou
None) e nunca lê origem do payload do cliente nem da permissão de quem
chama. Único ponto que lista as origens bloqueadas e a mensagem aprovada —
reaproveitado por pendencies.views, pendencies.admin e dashboard.views, sem
duplicar a regra em cada chamador.
"""

from telecom.models import PhoneLine

BLOCKED_ORIGINS = frozenset({PhoneLine.Origem.APARELHO_OP, PhoneLine.Origem.PESSOAL})

OPEN_BLOCKED_MESSAGE = (
    "Não é permitido abrir pendência para linhas com origem Aparelho "
    "Operação ou Aparelho pessoal. Fale com o supervisor ou backoffice"
)


def is_origin_blocked_for_opening(phone_line):
    """True quando a origem persistida da linha impede abrir/reabrir uma
    pendência. phone_line=None (operação sem linha vinculada) nunca
    bloqueia — contrato explícito de ausência de inferência de origem."""
    if phone_line is None:
        return False
    return phone_line.origem in BLOCKED_ORIGINS


def origin_open_block_reason(phone_line):
    """Mensagem exata aprovada quando bloqueado; string vazia quando a
    origem é permitida (inclusive sem linha)."""
    return OPEN_BLOCKED_MESSAGE if is_origin_blocked_for_opening(phone_line) else ""
