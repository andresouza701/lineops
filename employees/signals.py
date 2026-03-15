from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from core.current_user import get_current_user

from .models import Employee, EmployeeHistory


def _safe_current_user():
    user = get_current_user()
    return user if getattr(user, "is_authenticated", False) else None


@receiver(post_save, sender=Employee)
def track_employee_creation(sender, instance, created, **kwargs):
    if created:
        EmployeeHistory.objects.create(
            employee=instance,
            action=EmployeeHistory.ActionType.CREATED,
            new_value=(
                f"Nome: {instance.full_name}, "
                f"Supervisor: {instance.corporate_email}, "
                f"Gerente: {instance.manager_email or '-'}, "
                f"Carteira: {instance.employee_id}, "
                f"PA: {instance.pa or '-'}, "
                f"Equipe: {instance.teams}, "
                f"Status: {instance.get_status_display()}"
            ),
            changed_by=_safe_current_user(),
            description=f"Usuario {instance.full_name} criado",
        )


@receiver(pre_save, sender=Employee)
def track_employee_changes(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        old_instance = Employee.all_objects.get(pk=instance.pk)
    except Employee.DoesNotExist:
        return

    changed_by = _safe_current_user()

    if not old_instance.is_deleted and instance.is_deleted:
        EmployeeHistory.objects.create(
            employee=instance,
            action=EmployeeHistory.ActionType.DELETED,
            old_value=(
                f"Nome: {old_instance.full_name}, "
                f"Status: {old_instance.get_status_display()}"
            ),
            changed_by=changed_by,
            description=f"Usuario {old_instance.full_name} desativado",
        )
        return

    if old_instance.status != instance.status:
        EmployeeHistory.objects.create(
            employee=instance,
            action=EmployeeHistory.ActionType.STATUS_CHANGED,
            old_value=old_instance.get_status_display(),
            new_value=instance.get_status_display(),
            changed_by=changed_by,
            description=(
                f"Status alterado de {old_instance.get_status_display()} "
                f"para {instance.get_status_display()}"
            ),
        )

    old_values = []
    new_values = []
    field_labels = {
        "full_name": "Nome",
        "corporate_email": "Supervisor",
        "manager_email": "Gerente",
        "employee_id": "Carteira",
        "pa": "PA",
        "teams": "Equipe",
    }
    for field in field_labels:
        old_value = getattr(old_instance, field)
        new_value = getattr(instance, field)
        if old_value != new_value:
            label = field_labels[field]
            old_values.append(f"{label}: {old_value}")
            new_values.append(f"{label}: {new_value}")

    if old_values:
        EmployeeHistory.objects.create(
            employee=instance,
            action=EmployeeHistory.ActionType.UPDATED,
            old_value=", ".join(old_values),
            new_value=", ".join(new_values),
            changed_by=changed_by,
            description="Dados do usuario atualizados",
        )
