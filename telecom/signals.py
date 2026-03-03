from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from allocations.models import LineAllocation
from core.current_user import get_current_user

from .models import PhoneLine, PhoneLineHistory


def _safe_current_user():
    user = get_current_user()
    return user if getattr(user, "is_authenticated", False) else None


@receiver(post_save, sender=PhoneLine)
def track_phoneline_creation(sender, instance, created, **kwargs):
    """Registra quando uma nova linha e criada."""
    if created:
        PhoneLineHistory.objects.create(
            phone_line=instance,
            action=PhoneLineHistory.ActionType.CREATED,
            new_value=f"Status: {instance.status}, SIM: {instance.sim_card.iccid}",
            changed_by=_safe_current_user(),
            description=f"Linha {instance.phone_number} criada",
        )


@receiver(pre_save, sender=PhoneLine)
def track_phoneline_changes(sender, instance, **kwargs):
    """Registra mudancas de status, SIM e soft delete."""
    if not instance.pk:
        return

    try:
        old_instance = PhoneLine.objects.get(pk=instance.pk)
    except PhoneLine.DoesNotExist:
        return

    changed_by = _safe_current_user()

    # Soft delete (is_deleted de False para True)
    if not old_instance.is_deleted and instance.is_deleted:
        PhoneLineHistory.objects.create(
            phone_line=instance,
            action=PhoneLineHistory.ActionType.DELETED,
            old_value=(
                f"Status: {old_instance.get_status_display()}, "
                f"SIM: {old_instance.sim_card.iccid}"
            ),
            changed_by=changed_by,
            description=f"Linha {old_instance.phone_number} excluida",
        )

    origin_action = getattr(instance, "_history_origin_action", None)
    is_status_from_allocation_flow = origin_action in {
        PhoneLineHistory.ActionType.ALLOCATED,
        PhoneLineHistory.ActionType.RELEASED,
    }

    if old_instance.status != instance.status and not is_status_from_allocation_flow:
        PhoneLineHistory.objects.create(
            phone_line=instance,
            action=PhoneLineHistory.ActionType.STATUS_CHANGED,
            old_value=old_instance.get_status_display(),
            new_value=instance.get_status_display(),
            changed_by=changed_by,
            description=(
                f"Status alterado de {old_instance.get_status_display()} "
                f"para {instance.get_status_display()}"
            ),
        )

    if old_instance.sim_card_id != instance.sim_card_id:
        PhoneLineHistory.objects.create(
            phone_line=instance,
            action=PhoneLineHistory.ActionType.SIMCARD_CHANGED,
            old_value=old_instance.sim_card.iccid,
            new_value=instance.sim_card.iccid,
            changed_by=changed_by,
            description=(
                f"SIM card alterado de {old_instance.sim_card.iccid} "
                f"para {instance.sim_card.iccid}"
            ),
        )


@receiver(pre_delete, sender=PhoneLine)
def track_phoneline_deletion(sender, instance, **kwargs):
    """Registra exclusao fisica de linha (fallback)."""
    PhoneLineHistory.objects.create(
        phone_line=instance,
        action=PhoneLineHistory.ActionType.DELETED,
        old_value=f"Status: {instance.status}, SIM: {instance.sim_card.iccid}",
        changed_by=_safe_current_user(),
        description=f"Linha {instance.phone_number} excluida",
    )


@receiver(post_save, sender=LineAllocation)
def track_line_allocation(sender, instance, created, **kwargs):
    """Registra quando uma linha e alocada."""
    if created and instance.is_active:
        PhoneLineHistory.objects.create(
            phone_line=instance.phone_line,
            action=PhoneLineHistory.ActionType.ALLOCATED,
            new_value=f"Usuario: {instance.employee.full_name}",
            changed_by=instance.allocated_by or _safe_current_user(),
            description=f"Linha alocada para {instance.employee.full_name}",
        )


@receiver(pre_save, sender=LineAllocation)
def track_line_release(sender, instance, **kwargs):
    """Registra liberacao e troca de usuario na alocacao."""
    if not instance.pk:
        return

    try:
        old_instance = LineAllocation.objects.get(pk=instance.pk)
    except LineAllocation.DoesNotExist:
        return

    changed_by = _safe_current_user()

    if old_instance.is_active and not instance.is_active:
        PhoneLineHistory.objects.create(
            phone_line=instance.phone_line,
            action=PhoneLineHistory.ActionType.RELEASED,
            old_value=f"Usuario: {instance.employee.full_name}",
            changed_by=instance.released_by or changed_by,
            description=f"Linha liberada de {instance.employee.full_name}",
        )
    elif old_instance.employee_id != instance.employee_id:
        PhoneLineHistory.objects.create(
            phone_line=instance.phone_line,
            action=PhoneLineHistory.ActionType.EMPLOYEE_CHANGED,
            old_value=old_instance.employee.full_name,
            new_value=instance.employee.full_name,
            changed_by=changed_by,
            description=(
                f"Usuario alterado de {old_instance.employee.full_name} "
                f"para {instance.employee.full_name}"
            ),
        )
