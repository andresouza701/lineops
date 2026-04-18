"""
Context processors para disponibilizar dados globalmente nos templates.
"""

from django.conf import settings

from dashboard.services.context_service import get_pending_actions_count_for_user
from users.models import SystemUser

def pending_actions_count(request):
    """
    Disponibiliza o contador de pendencias de "Acoes do Dia" para ADMINs.

    Retorna:
        dict: Dicionario com pending_actions_count (int)
    """
    count = 0

    is_admin = (
        request.user.is_authenticated
        and request.user.role == SystemUser.Role.ADMIN
    )
    if is_admin:
        count = get_pending_actions_count_for_user(request.user)

    return {"pending_actions_count": count}


def app_metadata(request):
    """Disponibiliza metadados globais da aplicacao para os templates."""

    return {"app_version": settings.APP_VERSION}
