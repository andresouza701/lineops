from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class AllocationPendency(models.Model):
    """
    Rastreia o estado de pendência de uma alocação de linha de forma persistente.

    Uma pendência é criada por get_or_create ao abrir o modal pela primeira vez.
    - action = "no_action" → sem pendência ativa.
    - action != "no_action" → pendência em aberto.
    - resolved_at preenchido → pendência resolvida pelo admin.
    """

    class ActionType(models.TextChoices):
        NO_ACTION = "no_action", "Sem Ação"
        NEW_NUMBER = "new_number", "Número Novo"
        RECONNECT_WHATSAPP = "reconnect_whatsapp", "Reconectar WhatsApp"
        PENDING = "pending", "Pendência"

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="pendencies",
        verbose_name="Usuário",
    )
    allocation = models.OneToOneField(
        "allocations.LineAllocation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="pendency",
        verbose_name="Alocação",
    )

    action = models.CharField(
        max_length=30,
        choices=ActionType.choices,
        default=ActionType.NO_ACTION,
        verbose_name="Ação",
    )
    observation = models.CharField(
        max_length=350,
        blank=True,
        default="",
        verbose_name="Observação",
    )
    technical_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claimed_pendencies",
        verbose_name="Responsável Técnico",
    )

    # Rastreia qual ação foi enviada pela última vez (antes de uma eventual
    # resolução). Preenchido junto com pendency_submitted_at e permanece
    # intacto quando a pendência é resolvida (action volta a NO_ACTION).
    # Permite saber que tipo de pendência foi resolvida pelo admin.
    last_submitted_action = models.CharField(
        max_length=30,
        choices=ActionType.choices,
        null=True,
        blank=True,
        verbose_name="Última ação enviada",
        help_text=(
            "Ação que estava ativa quando a pendência foi submetida. "
            "Mantida após a resolução para auditoria e contagem de reconexões."
        ),
    )

    # Timestamps de ciclo de vida da pendência
    last_action_changed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Últ. alt. ação",
        help_text="Última alteração em Ação ou Status da Linha pelo admin.",
    )
    pendency_submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Envio da pendência",
        help_text="Quando a ação foi definida como diferente de Sem Ação.",
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Resolução",
        help_text="Quando o admin definiu a ação como Sem Ação.",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_pendencies",
        verbose_name="Atualizado por",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    class Meta:
        verbose_name = "Pendência de Alocação"
        verbose_name_plural = "Pendências de Alocação"
        # Uma pendência por alocação; para funcionários sem linha, allocation=None
        # e a unicidade é garantida por restrição parcial via signal/view.
        indexes = [
            models.Index(fields=["employee", "action"]),
            models.Index(fields=["allocation"]),
            models.Index(
                fields=["resolved_at", "last_submitted_action"],
                name="pendency_resolved_action_idx",
            ),
        ]

    def __str__(self):
        allocation_info = (
            self.allocation.phone_line.phone_number
            if self.allocation and self.allocation.phone_line_id
            else "sem linha"
        )
        return (
            f"{self.employee.full_name} / {allocation_info} — "
            f"{self.get_action_display()}"
        )

    @property
    def is_open(self):
        """Retorna True se há uma pendência em aberto (ação != Sem Ação)."""
        return self.action != self.ActionType.NO_ACTION

    def record_action_change(self, new_action: str, actor_role: str, now=None):
        """
        Atualiza o action e registra os timestamps de ciclo de vida.

        Regras:
        - Qualquer role pode definir action para valor != no_action → pendency_submitted_at
        - Admin atualizar action (qualquer valor) → last_action_changed_at
        - Resolução (NO_ACTION ← qualquer ação): resolved_at setado aqui,
          independente do line_status.
        - Reabertura (NO_ACTION → qualquer ação): pendency_submitted_at e
          last_submitted_action registrados, resolved_at limpo.
        """
        if now is None:
            now = timezone.now()

        old_action = self.action
        self.action = new_action

        was_no_action = old_action == self.ActionType.NO_ACTION
        is_now_no_action = new_action == self.ActionType.NO_ACTION

        if not is_now_no_action and was_no_action:
            # Reabertura: registra envio, limpa resolução anterior e
            # snapshot qual ação foi submetida para auditoria/reconexões.
            self.pendency_submitted_at = now
            self.resolved_at = None
            self.last_submitted_action = new_action
        elif is_now_no_action and not was_no_action:
            # Resolução pelo admin: registra resolved_at, limpa responsável técnico
            # e garante que last_submitted_action reflita a ação que estava ativa.
            self.resolved_at = now
            self.technical_responsible = None
            if not self.last_submitted_action:
                self.last_submitted_action = old_action

        if actor_role == "admin":
            self.last_action_changed_at = now

    def record_line_status_change(self, now=None):
        """Admin alterou Status da Linha → atualiza last_action_changed_at."""
        if now is None:
            now = timezone.now()
        self.last_action_changed_at = now


class PendencyObservationNotification(models.Model):
    """
    Notificação gerada quando a Observação de uma pendência é alterada.

    - Admin salva observação → notifica super, backoffice, gerente.
    - Super/backoffice/gerente salva observação → notifica admins.
    """

    pendency = models.ForeignKey(
        AllocationPendency,
        on_delete=models.CASCADE,
        related_name="observation_notifications",
        verbose_name=_("Pendência"),
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pendency_notifications",
        verbose_name=_("Destinatário"),
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_pendency_notifications",
        verbose_name=_("Enviado por"),
    )
    observation_text = models.CharField(
        max_length=350,
        verbose_name=_("Texto da observação"),
    )
    is_read = models.BooleanField(
        default=False,
        verbose_name=_("Lida"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Criada em"),
    )

    class Meta:
        verbose_name = _("Notificação de Observação de Pendência")
        verbose_name_plural = _("Notificações de Observação de Pendência")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"], name="pendency_notif_recip_read_idx"),
        ]

    def __str__(self):
        return (
            f"Notif → {self.recipient_id} | "
            f"pendência {self.pendency_id} | "
            f"{'lida' if self.is_read else 'não lida'}"
        )
