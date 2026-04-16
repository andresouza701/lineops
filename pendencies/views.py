import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View

from allocations.models import LineAllocation
from core.mixins import RoleRequiredMixin
from employees.models import Employee
from telecom.models import PhoneLineHistory
from users.models import SystemUser

from .models import AllocationPendency, PendencyObservationNotification
from .services import notify_observation_change

# Roles que podem VER e interagir com a tela de pendências
PENDENCY_ALLOWED_ROLES = list(SystemUser.EMPLOYEE_ACCESS_ROLES)


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


def _pendency_to_json(pendency, allocation):
    """Serializa a pendência para o payload do modal."""
    employee = pendency.employee
    tech = pendency.technical_responsible

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
        return JsonResponse(_pendency_to_json(pendency, allocation))


class PendencyUpdateView(RoleRequiredMixin, View):
    """POST: atualiza ação, observação e/ou status da linha."""

    allowed_roles = PENDENCY_ALLOWED_ROLES

    def post(self, request):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "JSON inválido."}, status=400)

        pendency_id = body.get("pendency_id")
        new_action = body.get("action", "").strip()
        new_observation = body.get("observation", "").strip()
        new_line_status = body.get("line_status", "").strip()

        pendency = get_object_or_404(
            AllocationPendency.objects.select_related(
                "employee", "allocation__phone_line", "technical_responsible"
            ),
            pk=pendency_id,
        )

        # Valida escopo: o usuário deve ter acesso ao funcionário
        scoped_qs = request.user.scope_employee_queryset(Employee.objects.all())
        if not scoped_qs.filter(pk=pendency.employee_id).exists():
            raise PermissionDenied("Sem acesso a este funcionário.")

        is_admin = request.user.role == SystemUser.Role.ADMIN
        now = timezone.now()
        errors = []
        update_fields = []

        # --- Ação ---
        valid_actions = dict(AllocationPendency.ActionType.choices)
        if new_action and new_action not in valid_actions:
            return JsonResponse({"error": "Valor de ação inválido."}, status=400)

        if new_action != pendency.action:
            # super/gerente/backoffice só podem definir valor != "no_action"
            if not is_admin and new_action == AllocationPendency.ActionType.NO_ACTION:
                errors.append("Somente admin pode definir ação como 'Sem Ação'.")
            else:
                pendency.record_action_change(
                    new_action, actor_role=request.user.role, now=now
                )
                update_fields += [
                    "action",
                    "last_action_changed_at",
                    "last_submitted_action",
                    "pendency_submitted_at",
                    "resolved_at",
                ]

        if errors:
            return JsonResponse({"errors": errors}, status=403)

        # --- Observação (qualquer role) ---
        old_observation = pendency.observation
        observation_changed = new_observation != old_observation
        if observation_changed:
            pendency.observation = new_observation[:350]
            update_fields.append("observation")

        # --- Status da Linha (somente admin) ---
        if new_line_status and is_admin:
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

                    # Auto-resolução: se a linha voltou a Ativo enquanto havia
                    # uma pendência RECONNECT_WHATSAPP aberta, resolve automaticamente.
                    if (
                        new_line_status == LineAllocation.LineStatus.ACTIVE
                        and pendency.action == AllocationPendency.ActionType.RECONNECT_WHATSAPP
                    ):
                        pendency.record_action_change(
                            AllocationPendency.ActionType.NO_ACTION,
                            actor_role=request.user.role,
                            now=now,
                        )
                        update_fields += [
                            "action",
                            "last_submitted_action",
                            "pendency_submitted_at",
                            "resolved_at",
                        ]

        # --- Salva pendência ---
        if update_fields:
            pendency.updated_by = request.user
            update_fields.append("updated_by")
            pendency.save(update_fields=list(set(update_fields)))

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
    """POST: admin se atribui como Responsável Técnico."""

    allowed_roles = [SystemUser.Role.ADMIN]

    def post(self, request):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "JSON inválido."}, status=400)

        pendency_id = body.get("pendency_id")
        pendency = get_object_or_404(
            AllocationPendency.objects.select_related(
                "employee", "allocation__phone_line", "technical_responsible"
            ),
            pk=pendency_id,
        )

        # Valida escopo
        scoped_qs = request.user.scope_employee_queryset(Employee.objects.all())
        if not scoped_qs.filter(pk=pendency.employee_id).exists():
            raise PermissionDenied("Sem acesso a este funcionário.")

        pendency.technical_responsible = request.user
        pendency.updated_by = request.user
        pendency.save(update_fields=["technical_responsible", "updated_by"])

        allocation = pendency.allocation
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
