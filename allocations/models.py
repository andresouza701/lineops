from django.db import models
from django.db.models import PROTECT
from django.conf import settings

from employees.models import Employee
from telecom.models import PhoneLine


class LineAllocation(models.Model):
    employee = models.ForeignKey(
        Employee, on_delete=PROTECT, related_name='allocations')
    phone_line = models.ForeignKey(
        PhoneLine, on_delete=PROTECT, related_name='allocations')

    allocated_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)

    allocated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='allocations_made'
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-allocated_at']
        indexes = [
            models.Index(fields=['employee', 'is_active', 'allocated_at']),
            models.Index(fields=['phone_line', 'is_active', 'allocated_at']),
        ]

    def __str__(self):
        return f"{self.employee} - {self.phone_line}"

    @property
    def employee_full_name(self):
        return self.employee.full_name
