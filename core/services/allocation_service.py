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
        employee = Employee.objects.select_for_update().get(pk=employee.pk)
        phone_line = PhoneLine.objects.select_for_update().get(pk=phone_line.pk)

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
                f"O funcionario {employee.full_name} "
                "ja possui 2 linhas alocadas ativas."
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
                f"A linha {phone_line.phone_number} ja esta alocada."
            )

        if phone_line.status != PhoneLine.Status.AVAILABLE:
            raise BusinessRuleException(
                f"A linha {phone_line.phone_number} nao esta disponivel para alocacao."
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
                "allocation_id": allocation.id,
                "phone_line_id": phone_line.id,
                "phone_number": phone_line.phone_number,
                "released_by_id": getattr(released_by, "id", None),
            },
        )

        return allocation
