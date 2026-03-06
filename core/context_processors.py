"""
Context processors para disponibilizar dados globalmente nos templates.
"""

from dashboard.models import DailyUserAction
from users.models import SystemUser


def pending_actions_count(request):
    """
    Disponibiliza o contador de pendências de 'Ações do Dia' para ADMINs.

    Conta ações não resolvidas (coluna 'Atualizar ação'):
    - DailyUserAction com is_resolved=False

    Retorna:
        dict: Dicionário com pending_actions_count (int)
    """
    count = 0

    if request.user.is_authenticated and request.user.role == SystemUser.Role.ADMIN:
        # Contar apenas ações não resolvidas
        count = DailyUserAction.objects.filter(is_resolved=False).count()

    return {"pending_actions_count": count}
