import logging

from django.db import transaction
from django.utils import timezone

from allocations.models import LineAllocation
from core.exceptions.domain_exceptions import BusinessRuleException
from employees.models import Employee
from telecom.models import PhoneLine
from whatsapp.models import MeowInstance, WhatsAppSession
from whatsapp.services import WhatsAppProvisioningService
from whatsapp.services.instance_selector import (
    InstanceSelectorService,
    NoAvailableMeowInstanceError,
)

logger = logging.getLogger(__name__)

MAX_ACTIVE_ALLOCATIONS_PER_EMPLOYEE = 4


class AllocationService:
    @staticmethod
    def _line_requires_new_whatsapp_session(phone_line: PhoneLine) -> bool:
        return not WhatsAppSession.objects.filter(line=phone_line).exists()

    @staticmethod
    def _ensure_whatsapp_capacity_for_new_session(phone_line: PhoneLine) -> None:
        if not AllocationService._line_requires_new_whatsapp_session(phone_line):
            return

        if not MeowInstance.objects.exists():
            return

        try:
            InstanceSelectorService.select_available_instance(
                allow_above_warning=True
            )
        except NoAvailableMeowInstanceError as exc:
            logger.warning(
                "Allocation blocked due to unavailable Meow capacity",
                extra={
                    "phone_line_id": phone_line.id,
                    "phone_number": phone_line.phone_number,
                },
            )
            raise BusinessRuleException(
                (
                    f"A linha {phone_line.phone_number} precisa de uma nova sessao "
                    "WhatsApp, mas nao ha instancia Meow ativa com capacidade "
                    "disponivel."
                )
            ) from exc

    @staticmethod
    def _run_provisioning_callback(
        callback_name: str,
        *,
        allocation_id: int,
        actor,
    ) -> None:
        try:
            allocation = (
                LineAllocation.objects.select_related("employee", "phone_line")
                .get(pk=allocation_id)
            )
            service = WhatsAppProvisioningService()
            getattr(service, callback_name)(allocation=allocation, actor=actor)
        except Exception:
            logger.exception(
                "WhatsApp provisioning callback failed",
                extra={
                    "callback_name": callback_name,
                    "allocation_id": allocation_id,
                    "actor_id": getattr(actor, "id", None),
                },
            )

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
                f"O usuario {employee.full_name} ja possui "
                f"{MAX_ACTIVE_ALLOCATIONS_PER_EMPLOYEE} linhas alocadas ativas."
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

        AllocationService._ensure_whatsapp_capacity_for_new_session(phone_line)

        allocation = LineAllocation.objects.create(
            employee=employee,
            phone_line=phone_line,
            allocated_by=allocated_by,
            is_active=True,
        )

        phone_line.status = PhoneLine.Status.ALLOCATED
        phone_line._history_origin_action = "ALLOCATED"
        phone_line.save(update_fields=["status"])
        if hasattr(phone_line, "_history_origin_action"):
            delattr(phone_line, "_history_origin_action")

        transaction.on_commit(
            lambda: AllocationService._run_provisioning_callback(
                "mark_allocation_pending",
                allocation_id=allocation.pk,
                actor=allocated_by,
            )
        )

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
        phone_line._history_origin_action = "RELEASED"
        phone_line.save(update_fields=["status"])
        if hasattr(phone_line, "_history_origin_action"):
            delattr(phone_line, "_history_origin_action")

        transaction.on_commit(
            lambda: AllocationService._run_provisioning_callback(
                "resolve_allocation_pending",
                allocation_id=allocation.pk,
                actor=released_by,
            )
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
