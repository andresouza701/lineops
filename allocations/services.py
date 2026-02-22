from django.core.exceptions import PermissionDenied
from django.utils import timezone as utc

from allocations.models import LineAllocation

class AllocationService:

    @staticmethod
    def allocate_line(employee, phone_line, allocated_by):
        
        if not allocated_by.is_admin():
            raise PermissionDenied("Only admins can allocate lines.")

        allocation = LineAllocation.objects.create(
            employee=employee,
            phone_line=phone_line,
            allocated_by=allocated_by
        )
        return allocation

    @staticmethod
    def release_line(allocation, released_by):
        if not released_by.is_admin():
            raise PermissionDenied("Only admins can release lines.")

        allocation.released_at = utc.now()
        allocation.save(update_fields=['status', 'released_at'])
        return allocation