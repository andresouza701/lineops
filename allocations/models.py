from django.conf import settings
from django.db import models
from django.db.models import PROTECT, F, Q

from core.exceptions.domain_exceptions import BusinessRuleException
from employees.models import Employee
from telecom.models import PhoneLine


class LineAllocationQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related(
            "employee", "phone_line", "allocated_by", "released_by"
        )


class LineAllocation(models.Model):
    objects = LineAllocationQuerySet.as_manager()

    class LineStatus(models.TextChoices):
        UNDER_ANALYSIS = "under_analysis", "Em analise"
        RESTRICTED = "restricted", "Restrito"
        PERMANENTLY_BANNED = "permanently_banned", "Banido permanentemente"
        ACTIVE = "active", "Ativo"

    employee = models.ForeignKey(
        Employee, on_delete=PROTECT, related_name="allocations"
    )
    phone_line = models.ForeignKey(
        PhoneLine, on_delete=PROTECT, related_name="allocations"
    )

    allocated_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)

    allocated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="allocations_made",
    )

    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="allocations_released",
    )

    is_active = models.BooleanField(default=True)
    line_status = models.CharField(
        max_length=30,
        choices=LineStatus.choices,
        default=LineStatus.ACTIVE,
        db_index=True,
        verbose_name="Status da linha",
        help_text="Status individual da linha",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-allocated_at"]
        indexes = [
            models.Index(fields=["employee", "is_active", "allocated_at"]),
            models.Index(fields=["phone_line", "is_active", "allocated_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(released_at__isnull=True)
                | Q(released_at__gte=F("allocated_at")),
                name="ck_allocation_release_after_allocate",
            ),
            models.CheckConstraint(
                check=(
                    Q(is_active=True, released_at__isnull=True)
                    | Q(is_active=False, released_at__isnull=False)
                ),
                name="ck_allocation_active_release_consistency",
            ),
        ]

    def __str__(self):
        return f"{self.employee} - {self.phone_line}"

    @property
    def employee_full_name(self):
        return self.employee.full_name

    def delete(self, using=None, keep_parents=False):
        raise BusinessRuleException("LineAllocation não pode ser deletada.")
