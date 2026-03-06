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
              - Para ADMINs: total de ações não resolvidas
              - Para outros usuários: 0
    """
    count = 0

    if request.user.is_authenticated and request.user.role == SystemUser.Role.ADMIN:
        # Contar apenas ações não resolvidas (is_resolved=False)
        count = DailyUserAction.objects.filter(is_resolved=False).count()

    return {"pending_actions_count": count}
