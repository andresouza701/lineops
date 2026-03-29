"""
Telephony Use Case: Orchestrates telephony operations (SIM, PhoneLine, allocation).

Extracts business logic from views to improve testability and maintainability.
"""

import logging
from dataclasses import dataclass

from django.db import transaction

from core.services.allocation_service import AllocationService
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard

logger = logging.getLogger(__name__)


@dataclass
class TelephonyResult:
    """Result of a telephony operation."""

    success: bool
    message: str
    phone_line: PhoneLine | None = None
    sim_card: SIMcard | None = None
    allocated: bool = False


class TelephonyUseCase:
    """Encapsulates telephony-related business logic."""

    @staticmethod
    @transaction.atomic
    def change_line_status(
        phone_line_id: int, new_status: str, actor
    ) -> TelephonyResult:
        """Change the status of an existing phone line."""
        phone_line = PhoneLine.objects.select_for_update().get(pk=phone_line_id)
        phone_line.status = new_status
        phone_line.save(update_fields=["status"])

        logger.info(
            "Line status changed",
            extra={
                "phone_line_id": phone_line.pk,
                "phone_number": phone_line.phone_number,
                "new_status": new_status,
                "actor_id": getattr(actor, "id", None),
            },
        )

        return TelephonyResult(
            success=True,
            message="Status da linha alterado com sucesso!",
            phone_line=phone_line,
        )

    @staticmethod
    @transaction.atomic
    def create_new_line_with_allocation(
        line_data: dict[str, str],
        employee: Employee | None,
        actor,
    ) -> TelephonyResult:
        """
        Create a new SIM card and phone line, optionally allocating
        to an employee.
        """
        sim = SIMcard.objects.create(
            iccid=line_data["iccid"],
            carrier=line_data["carrier"],
            status=SIMcard.Status.AVAILABLE,
        )

        phone_line = PhoneLine.create_or_reuse(
            phone_number=line_data["phone_number"],
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
            origem=line_data["origem"],
            canal=line_data.get("canal"),
        )

        logger.info(
            "New line created",
            extra={
                "phone_line_id": phone_line.pk,
                "phone_number": line_data["phone_number"],
                "sim_iccid": line_data["iccid"],
                "actor_id": getattr(actor, "id", None),
            },
        )

        allocated = False
        if employee:
            AllocationService.allocate_line(
                employee=employee,
                phone_line=phone_line,
                allocated_by=actor,
            )
            allocated = True

        message = (
            "Dados de telefonia salvos e linha alocada com sucesso!"
            if allocated
            else ("Número cadastrado com sucesso! " "Linha disponível para alocação.")
        )

        return TelephonyResult(
            success=True,
            message=message,
            phone_line=phone_line,
            sim_card=sim,
            allocated=allocated,
        )

    @staticmethod
    @transaction.atomic
    def allocate_existing_line(
        phone_line: PhoneLine, employee: Employee, actor
    ) -> TelephonyResult:
        """Allocate an existing phone line to an employee."""
        AllocationService.allocate_line(
            employee=employee,
            phone_line=phone_line,
            allocated_by=actor,
        )

        logger.info(
            "Existing line allocated",
            extra={
                "phone_line_id": phone_line.pk,
                "phone_number": phone_line.phone_number,
                "employee_id": employee.pk,
                "actor_id": getattr(actor, "id", None),
            },
        )

        return TelephonyResult(
            success=True,
            message="Dados de telefonia salvos e linha alocada com sucesso!",
            phone_line=phone_line,
            allocated=True,
        )
