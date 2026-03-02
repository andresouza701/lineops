from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from allocations.models import LineAllocation

from .models import PhoneLine, PhoneLineHistory


@receiver(post_save, sender=PhoneLine)
def track_phoneline_creation(sender, instance, created, **kwargs):
    """Registra quando uma nova linha é criada"""
    if created:
        PhoneLineHistory.objects.create(
            phone_line=instance,
            action=PhoneLineHistory.ActionType.CREATED,
            new_value=f"Status: {instance.status}, SIM: {instance.sim_card.iccid}",
            description=f"Linha {instance.phone_number} criada",
        )


@receiver(pre_save, sender=PhoneLine)
def track_phoneline_changes(sender, instance, **kwargs):
    """Registra mudanças de status e SIM card"""
    if instance.pk:  # Só se for update (não create)
        try:
            old_instance = PhoneLine.objects.get(pk=instance.pk)

            # Mudança de status
            if old_instance.status != instance.status:
                PhoneLineHistory.objects.create(
                    phone_line=instance,
                    action=PhoneLineHistory.ActionType.STATUS_CHANGED,
                    old_value=old_instance.get_status_display(),
                    new_value=instance.get_status_display(),
                    description=(
                        f"Status alterado de {old_instance.get_status_display()} "
                        f"para {instance.get_status_display()}"
                    ),
                )

            # Mudança de SIM card
            if old_instance.sim_card_id != instance.sim_card_id:
                PhoneLineHistory.objects.create(
                    phone_line=instance,
                    action=PhoneLineHistory.ActionType.SIMCARD_CHANGED,
                    old_value=old_instance.sim_card.iccid,
                    new_value=instance.sim_card.iccid,
                    description=(
                        f"SIM card alterado de {old_instance.sim_card.iccid} "
                        f"para {instance.sim_card.iccid}"
                    ),
                )
        except PhoneLine.DoesNotExist:
            pass


@receiver(pre_delete, sender=PhoneLine)
def track_phoneline_deletion(sender, instance, **kwargs):
    """Registra quando uma linha é excluída"""
    PhoneLineHistory.objects.create(
        phone_line=instance,
        action=PhoneLineHistory.ActionType.DELETED,
        old_value=f"Status: {instance.status}, SIM: {instance.sim_card.iccid}",
        description=f"Linha {instance.phone_number} excluída",
    )


@receiver(post_save, sender=LineAllocation)
def track_line_allocation(sender, instance, created, **kwargs):
    """Registra quando uma linha é alocada"""
    if created and instance.is_active:
        PhoneLineHistory.objects.create(
            phone_line=instance.phone_line,
            action=PhoneLineHistory.ActionType.ALLOCATED,
            new_value=f"Usuário: {instance.employee.full_name}",
            changed_by=instance.allocated_by,
            description=f"Linha alocada para {instance.employee.full_name}",
        )


@receiver(pre_save, sender=LineAllocation)
def track_line_release(sender, instance, **kwargs):
    """Registra quando uma linha é liberada"""
    if instance.pk:
        try:
            old_instance = LineAllocation.objects.get(pk=instance.pk)
            # Se mudou de ativo para inativo = liberação
            if old_instance.is_active and not instance.is_active:
                PhoneLineHistory.objects.create(
                    phone_line=instance.phone_line,
                    action=PhoneLineHistory.ActionType.RELEASED,
                    old_value=f"Usuário: {instance.employee.full_name}",
                    changed_by=instance.released_by,
                    description=f"Linha liberada de {instance.employee.full_name}",
                )
            # Se mudou o employee = troca de usuário
            elif old_instance.employee_id != instance.employee_id:
                PhoneLineHistory.objects.create(
                    phone_line=instance.phone_line,
                    action=PhoneLineHistory.ActionType.EMPLOYEE_CHANGED,
                    old_value=old_instance.employee.full_name,
                    new_value=instance.employee.full_name,
                    description=(
                        f"Usuário alterado de {old_instance.employee.full_name} "
                        f"para {instance.employee.full_name}"
                    ),
                )
        except LineAllocation.DoesNotExist:
            pass
