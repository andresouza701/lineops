import json
import uuid

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View

from allocations.models import LineAllocation
from core.mixins import RoleRequiredMixin
from employees.models import Employee
from telecom.daily_action_audit import build_pendency_state, record_line_daily_action_event
from telecom.models import LineDailyActionAuditEvent, PhoneLineHistory
from users.models import SystemUser

from .models import AllocationPendency, PendencyObservationNotification
from .services import notify_observation_change

SUPER_LIKE_ROLES = (
    SystemUser.Role.SUPER,
    SystemUser.Role.BACKOFFICE,
    SystemUser.Role.GERENTE,
)

# Roles que podem VER e interagir com a tela de pendências
PENDENCY_ALLOWED_ROLES = list(SystemUser.EMPLOYEE_ACCESS_ROLES)
OBSERVATION_LOCKED_REASON = (
    "Observacao bloqueada enquanto o status da linha estiver Em analise."
)


def _get_or_create_pendency(employee, allocation):
    """Retorna ou cria o registro de pendência para o par (employee, allocation)."""
    pendency, _ = AllocationPendency.objects.select_related(
        "technical_responsible"
    ).get_or_create(
        employee=employee,
        allocation=allocation,
    )
    return pendency


def _supervisor_name(employee):
    """Retorna a parte do e-mail do supervisor antes do @."""
    email = employee.corporate_email or ""
    return email.split("@")[0] if "@" in email else email


def _format_dt(dt):
    """Formata datetime para exibição ou retorna None."""
    if not dt:
        return None
    local = timezone.localtime(dt)
    return local.strftime("%d/%m/%Y %H:%M")


def _is_observation_locked(employee, allocation):
    if allocation:
        return allocation.line_status == LineAllocation.LineStatus.UNDER_ANALYSIS
    return employee.line_status == Employee.LineStatus.UNDER_ANALYSIS


def _pendency_to_json(pendency, allocation):
    """Serializa a pendência para o payload do modal."""
    employee = pendency.employee
    tech = (
        pendency.technical_responsible
        if pendency.action != AllocationPendency.ActionType.NO_ACTION
        else None
    )
    observation_locked = _is_observation_locked(employee, allocation)

    line_number = ""
    line_status = ""
    line_status_display = ""
    allocation_id = ""

    if allocation:
        line_number = allocation.phone_line.phone_number if allocation.phone_line else ""
        line_status = allocation.line_status
        line_status_display = allocation.get_line_status_display()
        allocation_id = allocation.pk
    else:
        # Funcionário sem linha ativa: usa line_status do próprio employee
        line_status = employee.line_status
        line_status_display = employee.get_line_status_display()

    return {
        "id": pendency.pk,
        "employee_id": employee.pk,
        "allocation_id": allocation_id,
        # Campos read-only
        "pa": employee.pa or "-",
        "usuario": employee.full_name,
        "carteira": employee.employee_id,
        "supervisor": _supervisor_name(employee),
        "linha": line_number or "-",
        # Campos editáveis
        "action": pendency.action,
        "action_display": pendency.get_action_display(),
        "line_status": line_status,
        "line_status_display": line_status_display,
        "observation": pendency.observation,
        "observation_locked": observation_locked,
        "observation_locked_reason": (
            OBSERVATION_LOCKED_REASON if observation_locked else ""
        ),
        # Responsável técnico
        "technical_responsible_name": (
            tech.get_full_name().strip() or tech.email if tech else ""
        ),
        # Timestamps
        "last_action_changed_at": _format_dt(pendency.last_action_changed_at),
        "pendency_submitted_at": _format_dt(pendency.pendency_submitted_at),
        "resolved_at": _format_dt(pendency.resolved_at),
        # Choices disponíveis
        "action_choices": [
            {"value": v, "label": l}
            for v, l in AllocationPendency.ActionType.choices
        ],
        "line_status_choices": [
            {"value": v, "label": l}
            for v, l in Employee.LineStatus.choices
        ],
    }


def _is_current_technical_responsible(pendency, user):
    return (
        user.role == SystemUser.Role.ADMIN
        and pendency.technical_responsible_id == user.id
    )


def _load_locked_pendency_for_scope(request, pendency_id):
    """Carrega a pendência com lock de linha e valida escopo do usuário."""
    pendency = get_object_or_404(
        AllocationPendency.objects.select_for_update(of=("self",)).select_related(
            "employee", "allocation__phone_line", "technical_responsible"
        ),
        pk=pendency_id,
    )
    if not request.user.scope_employee_queryset(Employee.objects.all()).filter(
        pk=pendency.employee_id
    ).exists():
        raise PermissionDenied("Sem acesso a este funcionário.")
    return pendency


def _record_pendency_event(
    *, event_type, pendency, allocation, performed_by, before_state, after_state,
    operation_id, occurred_at,
):
    return record_line_daily_action_event(
        event_type=event_type,
        source=LineDailyActionAuditEvent.Source.ALLOCATION_PENDENCY,
        source_object_id=pendency.pk,
        phone_line=allocation.phone_line if allocation else None,
        allocation=allocation,
        employee=pendency.employee,
        performed_by=performed_by,
        before_state=before_state,
        after_state=after_state,
        occurred_at=occurred_at,
        operation_id=operation_id,
    )


class PendencyDetailView(RoleRequiredMixin, View):
    """GET: retorna JSON com dados da pendência para o modal."""

    allowed_roles = PENDENCY_ALLOWED_ROLES

    def get(self, request):
        employee_id = request.GET.get("employee_id")
        allocation_id = request.GET.get("allocation_id") or None

        employee = get_object_or_404(
            request.user.scope_employee_queryset(Employee.objects.all()),
            pk=employee_id,
        )

        allocation = None
        if allocation_id:
            allocation = get_object_or_404(
                LineAllocation,
                pk=allocation_id,
                employee=employee,
                is_active=True,
            )

        pendency = _get_or_create_pendency(employee, allocation)

        # Abertura do modal conta como leitura para as notificações desse colaborador.
        PendencyObservationNotification.objects.filter(
            recipient=request.user,
            is_read=False,
            pendency__employee_id=employee.pk,
        ).update(is_read=True)

        return JsonResponse(_pendency_to_json(pendency, allocation))


class PendencyUpdateView(RoleRequiredMixin, View):
    """POST: atualiza ação, observação e/ou status da linha.

    Regras de autorização (contrato de auditoria de ações diárias):
    - Pendência sem ação aberta (action == no_action): admin tem acesso livre
      a nota/status da linha, como antes. Ninguém "possui" uma pendência vazia.
    - Pendência com ação aberta e sem responsável técnico: admin só pode
      assumi-la (endpoint de claim). Não pode alterar ação/nota/status aqui.
    - Pendência com ação aberta e responsável técnico definido: somente o
      próprio responsável (admin) pode alterar ação, nota, status, liberar
      ou resolver.
    - super/backoffice/gerente: só podem abrir (no_action -> outro valor) ou
      reabrir (após resolução) e alterar a observação. Nunca definem status
      de linha, nunca definem no_action, nunca trocam a ação já aberta.
    """

    allowed_roles = PENDENCY_ALLOWED_ROLES

    def post(self, request):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "JSON inválido."}, status=400)

        pendency_id = body.get("pendency_id")
        new_action = (body.get("action") or "").strip()
        new_observation = (body.get("observation") or "").strip()
        new_line_status = (body.get("line_status") or "").strip()

        valid_actions = dict(AllocationPendency.ActionType.choices)
        if new_action and new_action not in valid_actions:
            return JsonResponse({"error": "Valor de ação inválido."}, status=400)

        with transaction.atomic():
            pendency = _load_locked_pendency_for_scope(request, pendency_id)
            allocation = pendency.allocation

            is_admin = request.user.role == SystemUser.Role.ADMIN
            is_super_like = request.user.role in SUPER_LIKE_ROLES
            is_current_responsible = _is_current_technical_responsible(
                pendency, request.user
            )
            pendency_is_open = pendency.action != AllocationPendency.ActionType.NO_ACTION

            now = timezone.now()
            operation_id = uuid.uuid4()
            errors = []
            update_fields = []
            events_to_record = []
            action_event_type = None

            current_state = build_pendency_state(pendency, allocation)

            # --- Ação ---
            action_changed = bool(new_action) and new_action != pendency.action
            if action_changed:
                was_no_action = pendency.action == AllocationPendency.ActionType.NO_ACTION
                will_be_no_action = new_action == AllocationPendency.ActionType.NO_ACTION

                if was_no_action and not will_be_no_action:
                    if not is_super_like:
                        errors.append(
                            "Somente super/backoffice/gerente pode abrir uma pendência."
                        )
                    else:
                        action_event_type = (
                            LineDailyActionAuditEvent.EventType.REOPENED
                            if pendency.resolved_at is not None
                            else LineDailyActionAuditEvent.EventType.OPENED
                        )
                elif will_be_no_action and not was_no_action:
                    if not is_current_responsible:
                        errors.append(
                            "Somente o técnico responsável pode resolver a pendência."
                        )
                    else:
                        action_event_type = LineDailyActionAuditEvent.EventType.RESOLVED
                else:
                    if not is_current_responsible:
                        errors.append(
                            "Somente o técnico responsável pode alterar a ação."
                        )
                    else:
                        action_event_type = LineDailyActionAuditEvent.EventType.ACTION_CHANGED

            if errors:
                return JsonResponse({"errors": errors}, status=403)

            if action_changed:
                pendency.record_action_change(
                    new_action, actor_role=request.user.role, now=now
                )
                update_fields += [
                    "action",
                    "last_action_changed_at",
                    "last_submitted_action",
                    "pendency_submitted_at",
                    "resolved_at",
                    "technical_responsible",
                ]
                next_state = build_pendency_state(pendency, allocation)
                events_to_record.append((action_event_type, current_state, next_state))
                current_state = next_state

            # --- Observação ---
            old_observation = pendency.observation
            observation_changed = new_observation != old_observation
            if observation_changed and _is_observation_locked(
                pendency.employee,
                pendency.allocation,
            ):
                return JsonResponse({"errors": [OBSERVATION_LOCKED_REASON]}, status=403)

            note_allowed = is_super_like or (
                is_admin and (not pendency_is_open or is_current_responsible)
            )
            if observation_changed and not note_allowed:
                return JsonResponse(
                    {
                        "errors": [
                            "Somente o técnico responsável pode alterar a observação."
                        ]
                    },
                    status=403,
                )

            if observation_changed:
                pendency.observation = new_observation[:350]
                update_fields.append("observation")
                next_state = build_pendency_state(pendency, allocation)
                events_to_record.append(
                    (
                        LineDailyActionAuditEvent.EventType.NOTE_CHANGED,
                        current_state,
                        next_state,
                    )
                )
                current_state = next_state

            # --- Status da Linha (somente admin, e somente se dono ou pendência vazia) ---
            if new_line_status and is_admin:
                if pendency_is_open and not is_current_responsible:
                    return JsonResponse(
                        {
                            "errors": [
                                "Somente o técnico responsável pode alterar o "
                                "status da linha."
                            ]
                        },
                        status=403,
                    )

                valid_line_statuses = dict(Employee.LineStatus.choices)
                if new_line_status not in valid_line_statuses:
                    return JsonResponse({"error": "Status de linha inválido."}, status=400)

                if pendency.allocation:
                    allocation = pendency.allocation
                    if allocation.line_status != new_line_status:
                        old_display = allocation.get_line_status_display()
                        allocation.line_status = new_line_status
                        allocation.save(update_fields=["line_status"])
                        PhoneLineHistory.objects.create(
                            phone_line=allocation.phone_line,
                            action=PhoneLineHistory.ActionType.STATUS_CHANGED,
                            old_value=f"Status da linha: {old_display}",
                            new_value=(
                                f"Status da linha: "
                                f"{allocation.get_line_status_display()}"
                            ),
                            changed_by=request.user,
                            description=(
                                "Status da linha alterado via modal de Pendência"
                            ),
                        )
                        pendency.record_line_status_change(now=now)
                        update_fields.append("last_action_changed_at")
                        next_state = build_pendency_state(pendency, allocation)
                        events_to_record.append(
                            (
                                LineDailyActionAuditEvent.EventType.LINE_STATUS_CHANGED,
                                current_state,
                                next_state,
                            )
                        )
                        current_state = next_state

            # Regra de persistência: no save de admin, se a linha estiver ativa e
            # a ação estiver em "Sem Ação", o responsável técnico deve ser limpo.
            if (
                is_admin
                and pendency.allocation
                and pendency.allocation.line_status == Employee.LineStatus.ACTIVE
                and pendency.action == AllocationPendency.ActionType.NO_ACTION
                and pendency.technical_responsible_id
            ):
                pendency.technical_responsible = None
                update_fields.append("technical_responsible")

            # --- Salva pendência ---
            if update_fields:
                pendency.updated_by = request.user
                update_fields.append("updated_by")
                pendency.save(update_fields=list(set(update_fields)))

            for event_type, before_state, after_state in events_to_record:
                _record_pendency_event(
                    event_type=event_type,
                    pendency=pendency,
                    allocation=allocation,
                    performed_by=request.user,
                    before_state=before_state,
                    after_state=after_state,
                    operation_id=operation_id,
                    occurred_at=now,
                )

            # --- Notificação de observação ---
            notifications_sent = 0
            if observation_changed and new_observation:
                notifications_sent = notify_observation_change(
                    pendency, request.user, new_observation
                )

            # Re-fetch allocation para retornar estado atual
            allocation = pendency.allocation

        return JsonResponse(
            {
                "ok": True,
                "notifications_sent": notifications_sent,
                **_pendency_to_json(pendency, allocation),
            }
        )


class PendencyClaimView(RoleRequiredMixin, View):
    """POST: admin assume pendência aberta, mesmo atribuída a outro admin."""

    allowed_roles = [SystemUser.Role.ADMIN]

    def post(self, request):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "JSON inválido."}, status=400)

        pendency_id = body.get("pendency_id")

        with transaction.atomic():
            pendency = _load_locked_pendency_for_scope(request, pendency_id)

            if pendency.action == AllocationPendency.ActionType.NO_ACTION:
                return JsonResponse(
                    {"errors": ["Não há pendência aberta para assumir."]}, status=403
                )
            allocation = pendency.allocation
            before_state = build_pendency_state(pendency, allocation)

            pendency.technical_responsible = request.user
            pendency.updated_by = request.user
            pendency.save(update_fields=["technical_responsible", "updated_by"])

            after_state = build_pendency_state(pendency, allocation)
            _record_pendency_event(
                event_type=LineDailyActionAuditEvent.EventType.RESPONSIBLE_ASSIGNED,
                pendency=pendency,
                allocation=allocation,
                performed_by=request.user,
                before_state=before_state,
                after_state=after_state,
                operation_id=uuid.uuid4(),
                occurred_at=timezone.now(),
            )

        return JsonResponse(
            {"ok": True, **_pendency_to_json(pendency, allocation)}
        )


class PendencyReleaseView(RoleRequiredMixin, View):
    """POST: qualquer admin libera uma pendência aberta."""

    allowed_roles = [SystemUser.Role.ADMIN]

    def post(self, request):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "JSON inválido."}, status=400)

        pendency_id = body.get("pendency_id")

        with transaction.atomic():
            pendency = _load_locked_pendency_for_scope(request, pendency_id)

            if pendency.technical_responsible_id is None:
                return JsonResponse(
                    {"errors": ["Pendência não possui técnico responsável."]},
                    status=403,
                )

            allocation = pendency.allocation
            before_state = build_pendency_state(pendency, allocation)

            pendency.technical_responsible = None
            pendency.updated_by = request.user
            pendency.save(update_fields=["technical_responsible", "updated_by"])

            after_state = build_pendency_state(pendency, allocation)
            _record_pendency_event(
                event_type=LineDailyActionAuditEvent.EventType.RESPONSIBLE_RELEASED,
                pendency=pendency,
                allocation=allocation,
                performed_by=request.user,
                before_state=before_state,
                after_state=after_state,
                operation_id=uuid.uuid4(),
                occurred_at=timezone.now(),
            )

        return JsonResponse(
            {"ok": True, **_pendency_to_json(pendency, allocation)}
        )


class PendencyNotificationsView(LoginRequiredMixin, View):
    """
    GET: retorna notificações de observação não lidas do usuário logado
    e marca todas como lidas.
    """

    def get(self, request):
        qs = (
            PendencyObservationNotification.objects.filter(
                recipient=request.user,
                is_read=False,
            )
            .select_related("pendency__employee", "sent_by")
            .order_by("-created_at")
        )

        notifications = []
        ids_to_mark = []
        for notif in qs:
            ids_to_mark.append(notif.pk)
            sent_by_name = ""
            if notif.sent_by:
                sent_by_name = (
                    notif.sent_by.get_full_name().strip()
                    or notif.sent_by.email
                )
            notifications.append(
                {
                    "id": notif.pk,
                    "text": notif.observation_text,
                    "sent_by": sent_by_name,
                    "employee_name": (
                        notif.pendency.employee.full_name
                        if notif.pendency_id
                        else ""
                    ),
                    "created_at": _format_dt(notif.created_at),
                }
            )

        if ids_to_mark:
            PendencyObservationNotification.objects.filter(
                pk__in=ids_to_mark
            ).update(is_read=True)

        return JsonResponse({"notifications": notifications})
