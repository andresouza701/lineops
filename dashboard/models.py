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
