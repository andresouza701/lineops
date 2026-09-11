import uuid

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.current_user import get_current_user
from core.normalization import normalize_carrier_name


def _current_authenticated_user():
    """Usuário atual autenticado, ou None quando indisponível (jobs, shell)."""
    user = get_current_user()
    return user if getattr(user, "is_authenticated", False) else None


class SoftDeleteQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_deleted=False)

    def delete(self):
        deleted = 0
        details = {self.model._meta.label: 0}
        with transaction.atomic():
            for instance in self:
                instance.delete()
                deleted += 1
                details[self.model._meta.label] += 1
        return deleted, details


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).active()


class SIMcard(models.Model):
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        ACTIVE = "ACTIVE", "Active"
        BLOCKED = "BLOCKED", "Blocked"
        CANCELLED = "CANCELLED", "Cancelled"

    iccid = models.CharField(max_length=22, db_index=True)
    carrier = models.CharField(max_length=100)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AVAILABLE, db_index=True
    )

    activated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_deleted = models.BooleanField(default=False, db_index=True)

    def save(self, *args, **kwargs):
        self.carrier = normalize_carrier_name(self.carrier)
        return super().save(*args, **kwargs)

    @classmethod
    def available_for_line_registration(cls):
        return cls.objects.filter(status=cls.Status.AVAILABLE).filter(
            Q(phone_line__isnull=True) | Q(phone_line__is_deleted=True)
        )

    def delete(self, using=None, keep_parents=False, released_by=None):
        phone_line = PhoneLine.all_objects.filter(sim_card=self).first()
        if phone_line and not phone_line.is_deleted:
            phone_line.delete(released_by=released_by)

        if self.is_deleted:
            return

        self.is_deleted = True
        self.updated_at = timezone.now()
        self.save(update_fields=["is_deleted", "updated_at"])

    def __str__(self):
        return f"{self.iccid} - {self.status}"

    class Meta:
        verbose_name = "SIMcard"
        verbose_name_plural = "SIMcards"
        indexes = [
            models.Index(fields=["status", "is_deleted"]),
        ]


class PhoneLine(models.Model):
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Disponível"
        ALLOCATED = "ALLOCATED", "Alocado"
        SUSPENDED = "SUSPENDED", "Quarentena"
        CANCELLED = "CANCELLED", "Cancelado"
        AQUECENDO = "AQUECENDO", "Aquecendo"
        NOVO = "NOVO", "Novo"

    class Origem(models.TextChoices):
        SRVMEMU_01 = "SRVMEMU-01", "SRVMEMU-01"
        SRVMEMU_02 = "SRVMEMU-02", "SRVMEMU-02"
        SRVMEMU_03 = "SRVMEMU-03", "SRVMEMU-03"
        SRVMEMU_04 = "SRVMEMU-04", "SRVMEMU-04"
        SRVMEMU_05 = "SRVMEMU-05", "SRVMEMU-05"
        SRVMEMU_06 = "SRVMEMU-06", "SRVMEMU-06"
        BLIP = "BLIP", "Blip"
        APARELHO = "APARELHO", "Aparelho"
        PESSOAL = "PESSOAL", "Aparelho Pessoal"
        APARELHO_OP = "APARELHO OP", "Aparelho OP"

    class Canal(models.TextChoices):
        WEB = "WEB", "Whatsapp Web"
        MYLOOP = "MYLOOP", "MyLoop"
        ANYCALL = "ANYCALL", "AnyCall"

    phone_number = models.CharField(max_length=20, unique=True)

    sim_card = models.OneToOneField(
        "SIMcard", on_delete=models.PROTECT, related_name="phone_line"
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AVAILABLE, db_index=True
    )

    origem = models.CharField(
        max_length=20, choices=Origem.choices, null=True, blank=True
    )
    canal = models.CharField(
        max_length=20, choices=Canal.choices, null=True, blank=True
    )

    activated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_deleted = models.BooleanField(default=False, db_index=True)

    @classmethod
    def visible_to_user(cls, user, queryset=None):
        queryset = queryset if queryset is not None else cls.objects.all()
        role = (getattr(user, "role", "") or "").lower()

        if role in {"admin", "dev"}:
            return queryset

        queryset = queryset.exclude(origem=cls.Origem.BLIP)

        if role in {"super", "backoffice", "gerente"}:
            allocation_model = apps.get_model("allocations", "LineAllocation")
            employee_ids = user.scope_employee_queryset().values("pk")
            queryset = queryset.filter(
                pk__in=allocation_model.objects.filter(
                    is_active=True,
                    employee_id__in=employee_ids,
                ).values("phone_line_id")
            )
        elif role == "operator":
            allocation_model = apps.get_model("allocations", "LineAllocation")
            queryset = queryset.filter(
                pk__in=allocation_model.objects.filter(
                    is_active=True,
                    employee__email__iexact=user.email,
                    employee__is_deleted=False,
                ).values("phone_line_id")
            )

        return queryset

    @classmethod
    def active_phone_number_conflicts(cls, phone_number, exclude_id=None):
        queryset = cls.all_objects.filter(
            phone_number=phone_number,
            is_deleted=False,
            sim_card__is_deleted=False,
        )
        if exclude_id is not None:
            queryset = queryset.exclude(pk=exclude_id)
        return queryset

    @classmethod
    def create_or_reuse(
        cls, *, phone_number, sim_card, status, origem=None, canal=None
    ):
        origem = origem or None
        canal = canal or None

        with transaction.atomic():
            existing_line = (
                cls.all_objects.select_for_update()
                .select_related("sim_card")
                .filter(phone_number=phone_number)
                .first()
            )

            if not existing_line:
                return cls.objects.create(
                    phone_number=phone_number,
                    sim_card=sim_card,
                    status=status,
                    origem=origem,
                    canal=canal,
                )

            if not existing_line.is_deleted and not existing_line.sim_card.is_deleted:
                raise ValidationError("Número de linha já cadastrado.")

            was_deleted = existing_line.is_deleted
            previous_status_display = existing_line.get_status_display()
            previous_sim_iccid = existing_line.sim_card.iccid

            existing_line.sim_card = sim_card
            existing_line.status = status
            existing_line.origem = origem
            existing_line.canal = canal
            existing_line.is_deleted = False
            existing_line.updated_at = timezone.now()
            existing_line.save(
                update_fields=[
                    "sim_card",
                    "status",
                    "origem",
                    "canal",
                    "is_deleted",
                    "updated_at",
                ]
            )

            if was_deleted:
                PhoneLineHistory.objects.create(
                    phone_line=existing_line,
                    action=PhoneLineHistory.ActionType.REACTIVATED,
                    old_value=(
                        f"Status: {previous_status_display}, "
                        f"SIM: {previous_sim_iccid} (linha excluída)"
                    ),
                    new_value=(
                        f"Status: {existing_line.get_status_display()}, "
                        f"SIM: {existing_line.sim_card.iccid} (linha ativa)"
                    ),
                    changed_by=_current_authenticated_user(),
                    description=f"Linha {existing_line.phone_number} reativada",
                )

            return existing_line

    def delete(self, using=None, keep_parents=False, released_by=None):
        if self.is_deleted:
            return

        from allocations.models import LineAllocation
        from core.services.allocation_service import AllocationService

        active_allocation = (
            LineAllocation.objects.filter(phone_line=self, is_active=True)
            .select_related("employee")
            .first()
        )
        if active_allocation:
            AllocationService.release_line(active_allocation, released_by=released_by)

        self.is_deleted = True
        self.updated_at = timezone.now()
        self.save(update_fields=["is_deleted", "updated_at"])

    def __str__(self):
        return f"{self.phone_number} - {self.status}"

    class Meta:
        indexes = [
            models.Index(fields=["status", "is_deleted"]),
        ]


class PhoneLineHistory(models.Model):
    """Histórico de alterações nas linhas telefônicas"""

    class ActionType(models.TextChoices):
        CREATED = "CREATED", "Criada"
        STATUS_CHANGED = "STATUS_CHANGED", "Status alterado"
        SIMCARD_CHANGED = "SIMCARD_CHANGED", "SIMcard alterado"
        EMPLOYEE_CHANGED = "EMPLOYEE_CHANGED", "Usuário alterado"
        DELETED = "DELETED", "Excluída"
        REACTIVATED = "REACTIVATED", "Reativada"
        ALLOCATED = "ALLOCATED", "Alocada"
        RELEASED = "RELEASED", "Liberada"
        DAILY_ACTION_CHANGED = "DAILY_ACTION_CHANGED", "Ação diária alterada"

    phone_line = models.ForeignKey(
        "PhoneLine",
        on_delete=models.CASCADE,
        related_name="history",
        verbose_name="Linha",
    )

    action = models.CharField(
        max_length=20, choices=ActionType.choices, verbose_name="Ação"
    )

    old_value = models.TextField(blank=True, null=True, verbose_name="Valor anterior")
    new_value = models.TextField(blank=True, null=True, verbose_name="Novo valor")

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Alterado por",
    )

    changed_at = models.DateTimeField(auto_now_add=True, verbose_name="Data/Hora")

    description = models.TextField(blank=True, verbose_name="Descrição")

    class Meta:
        ordering = ["-changed_at"]
        verbose_name = "Histórico de Linha"
        verbose_name_plural = "Históricos de Linhas"
        indexes = [
            models.Index(fields=["phone_line", "-changed_at"]),
            models.Index(fields=["-changed_at"]),
        ]

    def __str__(self):
        return (
            f"{self.phone_line.phone_number} - "
            f"{self.get_action_display()} - {self.changed_at}"
        )


class LineDailyActionAuditEventQuerySet(models.QuerySet):
    """Bloqueia mutação em massa. Django usa UpdateQuery/consultas internas
    (não este QuerySet) para o SET_NULL de cascata de exclusão de FK, então
    esse bloqueio não impede a retenção de snapshot após exclusão física."""

    def delete(self):
        raise ValidationError(
            "Eventos de auditoria sao imutaveis: delete em massa bloqueado."
        )

    def update(self, **kwargs):
        raise ValidationError(
            "Eventos de auditoria sao imutaveis: update em massa bloqueado."
        )


class LineDailyActionAuditEventManager(models.Manager):
    def get_queryset(self):
        return LineDailyActionAuditEventQuerySet(self.model, using=self._db)


class LineDailyActionAuditEvent(models.Model):
    """
    Fato de auditoria append-only para ações diárias de linha (Ações do Dia e
    Pendências de Alocação). Cada linha registra o antes/depois completo de
    uma mudança material. Nunca é atualizada ou apagada pela aplicação.
    """

    objects = LineDailyActionAuditEventManager()

    class EventType(models.TextChoices):
        OPENED = "OPENED", "Aberta"
        ACTION_CHANGED = "ACTION_CHANGED", "Acao alterada"
        NOTE_CHANGED = "NOTE_CHANGED", "Nota alterada"
        RESPONSIBLE_ASSIGNED = "RESPONSIBLE_ASSIGNED", "Tecnico assumiu"
        RESPONSIBLE_RELEASED = "RESPONSIBLE_RELEASED", "Tecnico liberou"
        LINE_STATUS_CHANGED = "LINE_STATUS_CHANGED", "Status alterado"
        RESOLVED = "RESOLVED", "Resolvida"
        REOPENED = "REOPENED", "Reaberta"

    class Source(models.TextChoices):
        DAILY_USER_ACTION = "DAILY_USER_ACTION", "Acao diaria"
        ALLOCATION_PENDENCY = "ALLOCATION_PENDENCY", "Pendencia"
        LINE_ALLOCATION = "LINE_ALLOCATION", "Status da linha"

    event_type = models.CharField(max_length=30, choices=EventType.choices)
    source = models.CharField(max_length=30, choices=Source.choices)
    source_object_id = models.BigIntegerField()
    operation_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    payload_version = models.PositiveSmallIntegerField(default=1)

    occurred_at = models.DateTimeField(db_index=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    phone_line = models.ForeignKey(
        "PhoneLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_action_audit_events",
        verbose_name="Linha",
    )
    allocation = models.ForeignKey(
        "allocations.LineAllocation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_action_audit_events",
        verbose_name="Alocacao",
    )
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_action_audit_events",
        verbose_name="Usuario",
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_action_audit_events_performed",
        verbose_name="Executado por",
    )

    phone_number_snapshot = models.CharField(max_length=20, blank=True, default="")
    allocation_id_snapshot = models.BigIntegerField(null=True, blank=True)
    employee_name_snapshot = models.CharField(max_length=40, blank=True, default="")
    performed_by_name_snapshot = models.CharField(max_length=150, blank=True, default="")
    performed_by_email_snapshot = models.EmailField(
        max_length=254, blank=True, default=""
    )

    before_state = models.JSONField()
    after_state = models.JSONField()

    class Meta:
        verbose_name = "Evento de Auditoria de Acao de Linha"
        verbose_name_plural = "Eventos de Auditoria de Acao de Linha"
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(
                fields=["phone_line", "-occurred_at"],
                name="ldaae_phone_line_idx",
            ),
            models.Index(
                fields=["allocation", "-occurred_at"],
                name="ldaae_allocation_idx",
            ),
            models.Index(
                fields=["employee", "-occurred_at"],
                name="ldaae_employee_idx",
            ),
            models.Index(
                fields=["event_type", "-occurred_at"],
                name="ldaae_event_type_idx",
            ),
            models.Index(
                fields=["source", "source_object_id"],
                name="ldaae_source_obj_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Eventos de auditoria sao imutaveis.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Eventos de auditoria sao imutaveis: delete bloqueado.")

    def __str__(self):
        return f"{self.get_event_type_display()} - {self.source} #{self.source_object_id}"


class WhatsappReconnectHistory(models.Model):
    """Histórico persistido de sessões de reconexão de WhatsApp."""

    class Outcome(models.TextChoices):
        CONNECTED = "CONNECTED", "Conectado"
        FAILED = "FAILED", "Falhou"
        CANCELLED = "CANCELLED", "Cancelado"

    phone_line = models.ForeignKey(
        "PhoneLine",
        on_delete=models.CASCADE,
        related_name="reconnect_history",
        verbose_name="Linha",
    )
    session_id = models.CharField(
        max_length=120,
        unique=True,
        verbose_name="ID da sessão",
    )
    outcome = models.CharField(
        max_length=20,
        choices=Outcome.choices,
        null=True,
        blank=True,
        verbose_name="Resultado",
        help_text="Nulo enquanto a sessão está em andamento.",
    )
    error_code = models.CharField(
        max_length=100, blank=True, default="", verbose_name="Código de erro"
    )
    error_message = models.TextField(
        blank=True, default="", verbose_name="Mensagem de erro"
    )
    attempt_count = models.IntegerField(default=0, verbose_name="Tentativas")
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reconnect_sessions_started",
        verbose_name="Iniciado por",
    )
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Iniciado em")
    finished_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Finalizado em"
    )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Histórico de Reconexão WhatsApp"
        verbose_name_plural = "Históricos de Reconexão WhatsApp"
        indexes = [
            models.Index(
                fields=["phone_line", "-started_at"],
                name="telecom_wha_phone_l_1edc23_idx",
            ),
        ]

    def __str__(self):
        outcome_display = self.get_outcome_display() if self.outcome else "Em andamento"
        return f"{self.phone_line.phone_number} — {outcome_display} — {self.started_at:%d/%m/%Y %H:%M}"


class BlipConfiguration(models.Model):
    class ConfigurationType(models.TextChoices):
        FLOW = "FLOW", "Fluxo"
        ROUTER = "ROUTER", "Roteador"

    class KeyType(models.TextChoices):
        ACCESS = "ACCESS", "Acesso"
        HTTP = "HTTP", "Http"

    blip_id = models.CharField(max_length=255, verbose_name="Blip ID", db_index=True)
    type = models.CharField(
        max_length=20,
        choices=ConfigurationType.choices,
        verbose_name="Tipo",
    )
    description = models.CharField(max_length=255, verbose_name="Descricao")
    phone_number = models.BigIntegerField(verbose_name="Numero Telefone", db_index=True)
    key = models.CharField(
        max_length=20,
        choices=KeyType.choices,
        verbose_name="Chave",
    )
    value = models.CharField(max_length=255, verbose_name="Valor")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuracao Blip"
        verbose_name_plural = "Configuracoes Blip"
        ordering = ["blip_id", "phone_number", "type"]
        indexes = [
            models.Index(fields=["blip_id", "type"]),
            models.Index(fields=["phone_number", "key"]),
        ]

    def __str__(self):
        return f"{self.blip_id} - {self.get_type_display()}"
