from django.conf import settings
from django.db import models
from django.utils import timezone


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
        - resolved_at é setado na view após verificar a condição combinada
          (action == NO_ACTION E line_status == ACTIVE)
        """
        if now is None:
            now = timezone.now()

        old_action = self.action
        self.action = new_action

        was_no_action = old_action == self.ActionType.NO_ACTION
        is_now_no_action = new_action == self.ActionType.NO_ACTION

        if not is_now_no_action and was_no_action:
            # Reabertura: registra envio e limpa resolução anterior
            self.pendency_submitted_at = now
            self.resolved_at = None

        if actor_role == "admin":
            self.last_action_changed_at = now

    def record_line_status_change(self, now=None):
        """Admin alterou Status da Linha → atualiza last_action_changed_at."""
        if now is None:
            now = timezone.now()
        self.last_action_changed_at = now
