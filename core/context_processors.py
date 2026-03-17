"""
Context processors para disponibilizar dados globalmente nos templates.
"""

from django.conf import settings
from django.db.models import Exists, F, OuterRef, Q

from allocations.models import LineAllocation
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
        active_allocations_for_employee = LineAllocation.objects.filter(
            employee_id=OuterRef("employee_id"),
            is_active=True,
        )

        pending_actions = (
            DailyUserAction.objects.filter(
                is_resolved=False,
                employee__is_deleted=False,
            )
            .annotate(has_active_allocation=Exists(active_allocations_for_employee))
            .filter(
                Q(allocation__isnull=True, has_active_allocation=False)
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


def app_metadata(request):
    """Disponibiliza metadados globais da aplicação para os templates."""

    return {"app_version": settings.APP_VERSION}
