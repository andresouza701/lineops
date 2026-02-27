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

    full_name = models.CharField(max_length=255)
    corporate_email = models.CharField(
        max_length=255, unique=True, verbose_name="Supervisor"
    )
    employee_id = models.CharField(max_length=50, unique=True, verbose_name="Carteira")

    class UnitChoices(models.TextChoices):
        JOINVILLE = "Joinville", "Joinville"
        ARAQUARI = "Araquari", "Araquari"

    teams = models.CharField(
        max_length=20, choices=UnitChoices.choices, verbose_name="Unidade"
    )

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.INACTIVE, db_index=True
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
        indexes = [
            models.Index(fields=["employee_id"]),
            models.Index(fields=["corporate_email"]),
            models.Index(fields=["status", "is_deleted"]),
        ]
