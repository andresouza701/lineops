"""
Context processors para disponibilizar dados globalmente nos templates.
"""

from dashboard.models import DailyUserAction
from users.models import SystemUser


def pending_actions_count(request):
    """
    Disponibiliza o contador de pendências de 'Ações do Dia' para ADMINs.

    Retorna:
        dict: Dicionário com pending_actions_count (int)
              - Para ADMINs: total de ações não resolvidas com tipo definido
              - Para outros usuários: 0
    """
    count = 0

    if request.user.is_authenticated and request.user.role == SystemUser.Role.ADMIN:
        # Contar apenas ações não resolvidas (is_resolved=False)
        # E que tenham um tipo de ação definido (action_type não vazio)
        # Isso garante que contamos apenas pendências reais, não placeholders
        count = (
            DailyUserAction.objects.filter(is_resolved=False, action_type__isnull=False)
            .exclude(action_type="")
            .count()
        )

    return {"pending_actions_count": count}
