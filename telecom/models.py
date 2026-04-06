from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction
from django.db.models import Q
from django.utils import timezone


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


class PhoneLineManager(SoftDeleteManager):
    def create(self, **kwargs):
        phone_number = kwargs.get("phone_number")
        sim_card = kwargs.get("sim_card")

        if phone_number is None or sim_card is None:
            return super().create(**kwargs)

        try:
            return self.model.create_or_reuse(
                phone_number=phone_number,
                sim_card=sim_card,
                status=kwargs.get("status"),
                origem=kwargs.get("origem"),
                activated_at=kwargs.get("activated_at"),
            )
        except ValidationError:
            # Preserve the previous behavior for active duplicates and let the
            # database constraint surface the conflict.
            return super().create(**kwargs)


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
    objects = PhoneLineManager()
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
        APARELHO = "APARELHO", "APARELHO"
        PESSOAL = "PESSOAL", "PESSOAL"

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

        if role in {"super", "gerente"}:
            allocation_model = apps.get_model("allocations", "LineAllocation")
            employee_ids = user.scope_employee_queryset().values("pk")
            queryset = queryset.filter(
                pk__in=allocation_model.objects.filter(
                    is_active=True,
                    employee_id__in=employee_ids,
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
        cls,
        *,
        phone_number,
        sim_card,
        status=None,
        origem=None,
        activated_at=None,
    ):
        if status is None:
            status = cls._meta.get_field("status").get_default()

        existing_line = (
            cls.all_objects.select_related("sim_card")
            .filter(phone_number=phone_number)
            .first()
        )
        if existing_line:
            if not existing_line.is_deleted and not existing_line.sim_card.is_deleted:
                raise ValidationError("Número de linha já cadastrado.")

            existing_line.sim_card = sim_card
            existing_line.status = status
            existing_line.origem = origem
            existing_line.activated_at = activated_at
            existing_line.is_deleted = False
            existing_line.updated_at = timezone.now()
            existing_line.save(
                update_fields=[
                    "sim_card",
                    "status",
                    "origem",
                    "activated_at",
                    "is_deleted",
                    "updated_at",
                ]
            )
            return existing_line

        return cls.all_objects.create(
            phone_number=phone_number,
            sim_card=sim_card,
            status=status,
            origem=origem,
            activated_at=activated_at,
        )

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
