from django.conf import settings
from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_deleted=False)

    def delete(self):
        return self.update(is_deleted=True, updated_at=timezone.now())


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).active()


class SIMcard(models.Model):
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        ACTIVE = "ACTIVE", "Active"
        BLOCKED = "BLOCKED", "Blocked"
        CANCELLED = "CANCELLED", "Cancelled"

    iccid = models.CharField(max_length=22, db_index=True)
    carrier = models.CharField(max_length=100)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AVAILABLE, db_index=True
    )

    activated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_deleted = models.BooleanField(default=False, db_index=True)

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.updated_at = timezone.now()
        self.save(update_fields=["is_deleted", "updated_at"])

    def __str__(self):
        return f"{self.iccid} - {self.status}"

    class Meta:
        verbose_name = "SIMcard"
        verbose_name_plural = "SIMcards"
        indexes = [
            models.Index(fields=["status", "is_deleted"]),
        ]


class PhoneLine(models.Model):
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Disponível"
        ALLOCATED = "ALLOCATED", "Alocado"
        SUSPENDED = "SUSPENDED", "Quarentena"
        CANCELLED = "CANCELLED", "Cancelado"
        AQUECENDO = "AQUECENDO", "Aquecendo"
        NOVO = "NOVO", "Novo"

    class Origem(models.TextChoices):
        SRVMEMU_01 = "SRVMEMU-01", "SRVMEMU-01"
        SRVMEMU_02 = "SRVMEMU-02", "SRVMEMU-02"
        SRVMEMU_03 = "SRVMEMU-03", "SRVMEMU-03"
        SRVMEMU_04 = "SRVMEMU-04", "SRVMEMU-04"
        SRVMEMU_05 = "SRVMEMU-05", "SRVMEMU-05"
        SRVMEMU_06 = "SRVMEMU-06", "SRVMEMU-06"
        APARELHO = "APARELHO", "APARELHO"
        PESSOAL = "PESSOAL", "PESSOAL"

    phone_number = models.CharField(max_length=20, unique=True)

    sim_card = models.OneToOneField(
        "SIMcard", on_delete=models.PROTECT, related_name="phone_line"
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AVAILABLE, db_index=True
    )

    origem = models.CharField(
        max_length=20, choices=Origem.choices, null=True, blank=True
    )

    activated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_deleted = models.BooleanField(default=False, db_index=True)

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.updated_at = timezone.now()
        self.save(update_fields=["is_deleted", "updated_at"])

    def __str__(self):
        return f"{self.phone_number} - {self.status}"

    class Meta:
        indexes = [
            models.Index(fields=["status", "is_deleted"]),
        ]


class PhoneLineHistory(models.Model):
    """Histórico de alterações nas linhas telefônicas"""

    class ActionType(models.TextChoices):
        CREATED = "CREATED", "Criada"
        STATUS_CHANGED = "STATUS_CHANGED", "Status alterado"
        SIMCARD_CHANGED = "SIMCARD_CHANGED", "SIMcard alterado"
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
