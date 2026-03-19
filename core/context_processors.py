"""
Context processors para disponibilizar dados globalmente nos templates.
"""

from django.conf import settings

from dashboard.views import (
    build_daily_user_action_rows,
    count_visible_pending_actions,
    get_supervised_employees_queryset,
)
from employees.models import Employee
from users.models import SystemUser


def pending_actions_count(request):
    """
    Disponibiliza o contador de pendencias de "Acoes do Dia" para ADMINs.

    Retorna:
        dict: Dicionario com pending_actions_count (int)
    """
    count = 0

    if request.user.is_authenticated and request.user.role == SystemUser.Role.ADMIN:
        employees_qs = get_supervised_employees_queryset(request.user).filter(
            status=Employee.Status.ACTIVE,
            is_deleted=False,
        )
        rows = build_daily_user_action_rows(employees_qs, request.user)
        action_counts = count_visible_pending_actions(rows)
        count = action_counts["new_number"] + action_counts["reconnect_whatsapp"]

    return {"pending_actions_count": count}


def app_metadata(request):
    """Disponibiliza metadados globais da aplicacao para os templates."""

    return {"app_version": settings.APP_VERSION}
