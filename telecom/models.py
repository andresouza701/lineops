from django.db import models


class SIMcard(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        ACTIVE = 'ACTIVE', 'Active'
        BLOCKED = 'BLOCKED', 'Blocked'
        CANCELLED = 'CANCELLED', 'Cancelled'

    iccid = models.CharField(max_length=22, unique=True)
    carrier = models.CharField(max_length=100)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AVAILABLE, db_index=True)

    activated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_deleted = models.BooleanField(default=False, db_index=True)

    def __str__(self):
        return f"{self.iccid} - {self.status}"

    class Meta:
        indexes = [
            models.Index(fields=['iccid']),
            models.Index(fields=['status', 'is_deleted']),
        ]


class PhoneLine(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        ALLOCATED = 'ALLOCATED', 'Allocated'
        SUSPENDED = 'SUSPENDED', 'Suspended'
        CANCELLED = 'CANCELLED', 'Cancelled'

    phone_number = models.CharField(max_length=20, unique=True)

    sim_card = models.OneToOneField(
        'SIMcard', on_delete=models.PROTECT, related_name='phone_line')

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AVAILABLE, db_index=True)

    activated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_deleted = models.BooleanField(default=False, db_index=True)

    def __str__(self):
        return f"{self.phone_number} - {self.status}"

    class Meta:
        indexes = [
            models.Index(fields=['phone_number']),
            models.Index(fields=['status', 'is_deleted']),
        ]
