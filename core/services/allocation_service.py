import logging

from django.db import transaction
from django.utils import timezone

from allocations.models import LineAllocation
from core.exceptions.domain_exceptions import BusinessRuleException
from employees.models import Employee
from telecom.models import PhoneLine

logger = logging.getLogger(__name__)

MAX_ACTIVE_ALLOCATIONS_PER_EMPLOYEE = 2


class AllocationService:
    @staticmethod
    @transaction.atomic
    def allocate_line(employee: Employee, phone_line: PhoneLine, allocated_by):
        # Lock no funcionario para evitar race conditions na alocação de linhas
        employee = Employee.objects.select_for_update().get(pk=employee.pk)

        # Lock na linha para evitar alocações concorrentes
        phone_line = PhoneLine.objects.select_for_update().get(pk=phone_line.pk)

        """Regra de alocação máximo 2 linhas ativas por funcionário."""
        active_allocation = LineAllocation.objects.filter(
            employee=employee, is_active=True
        ).count()
        if active_allocation >= MAX_ACTIVE_ALLOCATIONS_PER_EMPLOYEE:
            logger.warning(
                "Allocation limit reached",
                extra={
                    "employee_id": employee.id,
                    "employee_employee_id": employee.employee_id,
                    "active_allocations": active_allocation,
                },
            )
            raise BusinessRuleException(
                f"O funcionário {employee.full_name} já possui "
                "2 linhas alocadas ativas."
            )

        if LineAllocation.objects.filter(
            phone_line=phone_line, is_active=True
        ).exists():
            logger.warning(
                "Line already allocated",
                extra={
                    "phone_line_id": phone_line.id,
                    "phone_number": phone_line.phone_number,
                },
            )
            raise BusinessRuleException(
                f"A linha {phone_line.phone_number} já está alocada."
            )

        allocation = LineAllocation.objects.create(
            employee=employee,
            phone_line=phone_line,
            allocated_by=allocated_by,
            is_active=True,
        )

        phone_line.status = PhoneLine.Status.ALLOCATED
        phone_line.save(update_fields=["status"])

        logger.info(
            "Line allocated",
            extra={
                "allocation_id": allocation.id,
                "employee_id": employee.id,
                "employee_employee_id": employee.employee_id,
                "phone_line_id": phone_line.id,
                "phone_number": phone_line.phone_number,
                "allocated_by_id": getattr(allocated_by, "id", None),
            },
        )

        return allocation

    @staticmethod
    @transaction.atomic
    def release_line(allocation: LineAllocation, released_by):
        """Release allocated phone line and update its status to available."""

        allocation.released_at = timezone.now()
        allocation.is_active = False
        allocation.released_by = released_by
        allocation.save(update_fields=["released_at", "is_active", "released_by"])

        phone_line = allocation.phone_line
        phone_line.status = PhoneLine.Status.AVAILABLE
        phone_line.save(update_fields=["status"])

        logger.info(
            "Line released",
            extra={
                "allocation_id": allocation.pk,
                "phone_line_id": phone_line.pk,
                "phone_number": phone_line.phone_number,
                "released_by_id": released_by.pk,
            },
        )
        logger.info(
            "Line released",
            extra={
                "allocation_id": allocation.id,
                "phone_line_id": phone_line.id,
                "phone_number": phone_line.phone_number,
                "released_by_id": getattr(released_by, "id", None),
            },
        )

        return allocation
