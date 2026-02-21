from django.db import transaction
from django.utils import timezone

from allocations.models import LineAllocation
from telecom.models import PhoneLine
from employees.models import Employee
from core.exceptions.domain_exceptions import BusinessLogicError
from allocations.models import LineAllocation

class AllocationService:
    @staticmethod
    @transaction.atomic
    def allocate_line(employee: Employee, phone_line: PhoneLine, allocated_by):
        """Regra de alocação maximo 2 linhas ativas por funcionário"""
        active_allocation = LineAllocation.objects.filter(
            employee=employee, is_active=True).count()
        if active_allocation >=2:
            raise BusinessLogicError(
                f"O funcionário {employee.full_name} já possui 2 linhas alocadas ativas."
            )

        allocation = LineAllocation.objects.create(
            employee=employee,
            phone_line=phone_line,
            allocated_by=allocated_by,
            is_active=True,
        )
        
        phone_line.status = PhoneLine.Status.ALLOCATED
        phone_line.save(update_fields=['status'])

        return allocation
    
    @staticmethod
    @transaction.atomic
    def release_line(allocation: LineAllocation, released_by):
        """Releases an allocated phone line, marking the allocation as inactive and updating the line status."""

        allocation.released_at = timezone.now()
        allocation.is_active = False
        allocation.save(update_fields=['released_at', 'is_active'])

        phone_line = allocation.phone_line
        phone_line.status = PhoneLine.Status.AVAILABLE
        phone_line.save(update_fields=['status'])

        return allocation
    
