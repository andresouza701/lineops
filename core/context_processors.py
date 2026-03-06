"""
Context processors para disponibilizar dados globalmente nos templates.
"""

from dashboard.models import DailyUserAction
from employees.models import Employee
from users.models import SystemUser


def pending_actions_count(request):
    """
    Disponibiliza o contador de pendências de 'Ações do Dia' para ADMINs.

    Conta apenas ações não resolvidas com tipo definido, de funcionários ativos.

    Retorna:
        dict: Dicionário com pending_actions_count (int)
              - Para ADMINs: total de ações pendentes visíveis
              - Para outros usuários: 0
    """
    count = 0

    if request.user.is_authenticated and request.user.role == SystemUser.Role.ADMIN:
        # Buscar ações não resolvidas de funcionários ativos (não deletados)
        active_employees = Employee.objects.filter(is_deleted=False).values_list(
            "id", flat=True
        )

        # Contar ações onde:
        # - is_resolved=False (não resolvida)
        # - action_type definido (não vazio)
        # - employee ativo (não deletado)
        # - SE tiver allocation, deve estar ativa (is_active=True)
        from django.db.models import Q

        count = (
            DailyUserAction.objects.filter(
                is_resolved=False,
                action_type__isnull=False,
                employee_id__in=active_employees,
            )
            .exclude(action_type="")
            .filter(
                Q(allocation__isnull=True) | Q(allocation__is_active=True)
            )  # allocation é null OU está ativa
            .count()
        )

    return {"pending_actions_count": count}
