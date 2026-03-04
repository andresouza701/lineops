from django.conf import settings
from django.db import models
from django.utils import timezone


class DailyIndicator(models.Model):
    SEGMENT_CHOICES = [
        ("B2B", "B2B"),
        ("B2C", "B2C"),
    ]

    supervisor = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name="Supervisor",
        help_text="Nome do supervisor responsável",
    )
    portfolio = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name="Carteira",
        help_text="Nome da carteira/portfolio",
    )
    segment = models.CharField(
        max_length=10, choices=SEGMENT_CHOICES, db_index=True, verbose_name="Segmento"
    )

    # Indicadores inseridos manualmente pelos supervisores
    people_logged_in = models.IntegerField(
        default=0,
        verbose_name="Pessoas Logadas",
        help_text="Quantidade de pessoas logadas no dia",
    )

    # Indicadores calculados automaticamente pelo sistema
    numbers_available = models.IntegerField(
        default=0,
        verbose_name="Números Disponíveis",
        help_text="Números em aquecimento (15+ dias sem alocação)",
    )
    numbers_delivered = models.IntegerField(
        default=0,
        verbose_name="Números Entregues",
        help_text="Números alocados aos negociadores no dia",
    )
    numbers_reconnected = models.IntegerField(
        default=0,
        verbose_name="Números Reconectados",
        help_text="Números recuperados e realocados ao mesmo negociador",
    )
    numbers_new = models.IntegerField(
        default=0,
        verbose_name="Números Novos",
        help_text="Números novos atribuídos no dia",
    )

    date = models.DateField(
        db_index=True, default=timezone.now, verbose_name="Data do Indicador"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_indicators_created",
        verbose_name="Criado por",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_indicators_updated",
        verbose_name="Atualizado por",
    )

    class Meta:
        unique_together = ("supervisor", "portfolio", "segment", "date")
        ordering = ["-date", "supervisor", "portfolio"]
        verbose_name = "Indicador Diário"
        verbose_name_plural = "Indicadores Diários"
        indexes = [
            models.Index(fields=["date", "segment"]),
            models.Index(fields=["supervisor", "date"]),
            models.Index(fields=["portfolio", "date"]),
            models.Index(fields=["segment", "supervisor", "date"]),
        ]

    def __str__(self):
        return (
            f"{self.supervisor} - {self.portfolio} ({self.date.strftime('%d/%m/%Y')})"
        )


class DailyUserAction(models.Model):
    class ActionType(models.TextChoices):
        NEW_NUMBER = "new_number", "Precisa numero novo"
        RECONNECT_WHATSAPP = "reconnect_whatsapp", "Precisa reconectar Whats"

    day = models.DateField(db_index=True, default=timezone.now, verbose_name="Dia")
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="daily_actions",
        verbose_name="Usuario",
    )
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_actions_supervised",
        verbose_name="Supervisor responsavel",
    )
    action_type = models.CharField(
        max_length=30,
        choices=ActionType.choices,
        verbose_name="Tipo de acao",
    )
    note = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Observacao",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_actions_created",
        verbose_name="Criado por",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_actions_updated",
        verbose_name="Atualizado por",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    class Meta:
        unique_together = ("day", "employee")
        ordering = ["-day", "employee__full_name"]
        indexes = [
            models.Index(fields=["day", "action_type"]),
            models.Index(fields=["employee", "day"]),
        ]
        verbose_name = "Acao diaria por usuario"
        verbose_name_plural = "Acoes diarias por usuario"

    def __str__(self):
        return (
            f"{self.day.strftime('%d/%m/%Y')} - {self.employee.full_name} - "
            f"{self.get_action_type_display()}"
        )
