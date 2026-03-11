"""
Context processors para disponibilizar dados globalmente nos templates.
"""

from django.db.models import F, Q

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
        # Badge deve refletir apenas pendências que podem aparecer em
        # "Ações do Dia":
        # - ação sem alocação; ou
        # - ação com alocação ativa vinculada ao mesmo employee da ação.
        # Também deduplicamos por (employee, allocation), mantendo só a ação
        # mais recente por chave (mesma regra da tela).
        pending_actions = (
            DailyUserAction.objects.filter(
                is_resolved=False,
                employee__is_deleted=False,
            )
            .filter(
                Q(allocation__isnull=True)
                | Q(
                    allocation__is_active=True,
                    allocation__employee_id=F("employee_id"),
                )
            )
            .order_by("employee_id", "allocation_id", "-day", "-id")
            .values_list("employee_id", "allocation_id")
        )

        seen_keys = set()
        for employee_id, allocation_id in pending_actions:
            key = (employee_id, allocation_id)
            if key in seen_keys:
                continue
            seen_keys.add(key)
        count = len(seen_keys)

    return {"pending_actions_count": count}
