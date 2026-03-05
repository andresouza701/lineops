from django.conf import settings
from django.db import models


class PhoneLineHistory(models.Model):
    """Histórico de alterações nas linhas telefônicas"""

    class ActionType(models.TextChoices):
        CREATED = "CREATED", "Criada"
        STATUS_CHANGED = "STATUS_CHANGED", "Status alterado"
        SIMCARD_CHANGED = "SIMCARD_CHANGED", "SIM card alterado"
        EMPLOYEE_CHANGED = "EMPLOYEE_CHANGED", "Usuário alterado"
        DELETED = "DELETED", "Excluída"
        ALLOCATED = "ALLOCATED", "Alocada"
        RELEASED = "RELEASED", "Liberada"
        DAILY_ACTION_CHANGED = "DAILY_ACTION_CHANGED", "Ação diária alterada"

    phone_line = models.ForeignKey(
        "PhoneLine",
        on_delete=models.CASCADE,
        related_name="history",
        verbose_name="Linha",
    )

    action = models.CharField(
        max_length=20, choices=ActionType.choices, verbose_name="Ação"
    )

    old_value = models.TextField(blank=True, null=True, verbose_name="Valor anterior")
    new_value = models.TextField(blank=True, null=True, verbose_name="Novo valor")

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Alterado por",
    )

    changed_at = models.DateTimeField(auto_now_add=True, verbose_name="Data/Hora")

    description = models.TextField(blank=True, verbose_name="Descrição")

    class Meta:
        ordering = ["-changed_at"]
        verbose_name = "Histórico de Linha"
        verbose_name_plural = "Históricos de Linhas"
        indexes = [
            models.Index(fields=["phone_line", "-changed_at"]),
            models.Index(fields=["-changed_at"]),
        ]

    def __str__(self):
        return (
            f"{self.phone_line.phone_number} - "
            f"{self.get_action_display()} - {self.changed_at}"
        )
