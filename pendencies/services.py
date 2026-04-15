from users.models import SystemUser

from .models import AllocationPendency, PendencyObservationNotification

# Roles que recebem notificação quando um admin salva
_NOTIFIABLE_BY_ADMIN = [
    SystemUser.Role.SUPER,
    SystemUser.Role.BACKOFFICE,
    SystemUser.Role.GERENTE,
]

# Roles que recebem notificação quando super/backoffice/gerente salva
_NOTIFIABLE_BY_OTHERS = [SystemUser.Role.ADMIN]


def notify_observation_change(
    pendency: AllocationPendency,
    sender: SystemUser,
    new_text: str,
) -> int:
    """
    Cria notificações em massa quando a observação de uma pendência é alterada.

    Regras:
    - Só dispara se new_text não for vazio.
    - Admin → notifica super, backoffice, gerente ativos.
    - Super/backoffice/gerente → notifica admins ativos.
    - Outros roles (operator, dev) não disparam notificações.
    - O próprio remetente nunca recebe notificação.

    Retorna o número de notificações criadas.
    """
    if not new_text:
        return 0

    if sender.role == SystemUser.Role.ADMIN:
        recipient_roles = _NOTIFIABLE_BY_ADMIN
    elif sender.role in _NOTIFIABLE_BY_ADMIN:
        recipient_roles = _NOTIFIABLE_BY_OTHERS
    else:
        return 0

    recipients = (
        SystemUser.objects.filter(role__in=recipient_roles, is_active=True)
        .exclude(pk=sender.pk)
        .only("id")
    )

    notifications = [
        PendencyObservationNotification(
            pendency=pendency,
            recipient=recipient,
            sent_by=sender,
            observation_text=new_text[:350],
        )
        for recipient in recipients
    ]

    if notifications:
        PendencyObservationNotification.objects.bulk_create(notifications)

    return len(notifications)
