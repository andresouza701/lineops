from django.conf import settings
from django.db import models
from django.utils import timezone


class EmployeeQuerySet(models.QuerySet):
    def delete(self):
        return super().update(is_deleted=True, updated_at=timezone.now())


class EmployeeManager(models.Manager):
    def get_queryset(self):
        return EmployeeQuerySet(self.model, using=self._db).filter(is_deleted=False)


class Employee(models.Model):
    objects = EmployeeManager()
    all_objects = models.Manager()

    class Status(models.TextChoices):
        ACTIVE = "active", "Ativo"
        INACTIVE = "inactive", "Inativo"

    class LineStatus(models.TextChoices):
        UNDER_ANALYSIS = "under_analysis", "Em analise"
        RESTRICTED = "restricted", "Restrito"
        PERMANENTLY_BANNED = "permanently_banned", "Banido permanentemente"
        ACTIVE = "active", "Ativo"

    full_name = models.CharField(max_length=40)
    corporate_email = models.CharField(max_length=40, verbose_name="Supervisor")
    employee_id = models.CharField(max_length=40, verbose_name="Carteira")

    class UnitChoices(models.TextChoices):
        JOINVILLE = "Joinville", "Joinville"
        ARAQUARI = "Araquari", "Araquari"

    teams = models.CharField(
        max_length=15, choices=UnitChoices.choices, verbose_name="Unidade"
    )

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.INACTIVE, db_index=True
    )
    line_status = models.CharField(
        max_length=30,
        choices=LineStatus.choices,
        default=LineStatus.ACTIVE,
        db_index=True,
        verbose_name="Status da linha",
        help_text="Status da linha do negociador",
    )
    pa = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="PA",
        help_text="Preenchimento opcional",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_deleted = models.BooleanField(default=False, db_index=True)

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.updated_at = timezone.now()
        self.save(update_fields=["is_deleted", "updated_at"])

    def __str__(self):
        return f"{self.full_name} ({self.employee_id})"

    class Meta:
        verbose_name = "NEGOCIADOR"
        verbose_name_plural = "NEGOCIADOR"
        indexes = [
            models.Index(fields=["employee_id"]),
            models.Index(fields=["corporate_email"]),
            models.Index(fields=["status", "is_deleted"]),
        ]


class EmployeeHistory(models.Model):
    class ActionType(models.TextChoices):
        CREATED = "CREATED", "Criado"
        UPDATED = "UPDATED", "Atualizado"
        STATUS_CHANGED = "STATUS_CHANGED", "Status alterado"
        DELETED = "DELETED", "Desativado"

    employee = models.ForeignKey(
        "Employee",
        on_delete=models.CASCADE,
        related_name="history",
        verbose_name="Usuario",
    )
    action = models.CharField(
        max_length=20,
        choices=ActionType.choices,
        verbose_name="Acao",
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
    description = models.TextField(blank=True, verbose_name="Descricao")

    class Meta:
        ordering = ["-changed_at"]
        indexes = [
            models.Index(fields=["employee", "-changed_at"]),
            models.Index(fields=["-changed_at"]),
        ]

    def __str__(self):
        return (
            f"{self.employee.full_name} - "
            f"{self.get_action_display()} - {self.changed_at}"
        )
