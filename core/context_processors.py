"""
Context processors para disponibilizar dados globalmente nos templates.
"""

from django.db.models import Q

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
        # Badge deve refletir apenas ações ainda visíveis em "Ações do Dia".
        # Ações ligadas a alocações já liberadas (is_active=False) saem da tela
        # e, portanto, não devem permanecer no contador global.
        count = (
            DailyUserAction.objects.filter(
                is_resolved=False,
                employee__is_deleted=False,
            )
            .filter(Q(allocation__isnull=True) | Q(allocation__is_active=True))
            .count()
        )

    return {"pending_actions_count": count}
