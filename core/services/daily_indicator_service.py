from datetime import datetime, time, timedelta

from django.db.models import F
from django.utils import timezone

from allocations.models import LineAllocation
from dashboard.models import DailyIndicator
from telecom.models import PhoneLine


class DailyIndicatorService:
    """
    Serviço para calcular e gerenciar indicadores diários.
    Responsável pelos cálculos automáticos baseado em dados do sistema.
    """

    @staticmethod
    def calculate_available_numbers(date, segment=None):
        """
        Calcula números disponíveis (em aquecimento por 15+ dias).

        Números que foram criados há 15+ dias mas nunca foram alocados.
        Args:
            date: Data para calcular
            segment: 'B2B' ou 'B2C' (opcional)
        Returns:
            int: Quantidade de números disponíveis
        """
        warmup_threshold = date - timedelta(days=15)

        query = PhoneLine.objects.filter(
            created_at__date__lte=warmup_threshold,
            status=PhoneLine.Status.AVAILABLE,
            is_deleted=False,
        )

        return query.count()

    @staticmethod
    def calculate_delivered_numbers(date, segment=None):
        """
        Calcula números entregues no dia (alocados ao negociador).

        Números que foram alocados naquele dia específico.
        Args:
            date: Data para calcular
            segment: 'B2B' ou 'B2C' (opcional)
        Returns:
            int: Quantidade de números entregues
        """
        end_of_day = timezone.make_aware(datetime.combine(date, time.max))
        start_of_day = timezone.make_aware(datetime.combine(date, time.min))

        query = LineAllocation.objects.filter(
            allocated_at__range=(start_of_day, end_of_day)
        )

        return query.count()

    @staticmethod
    def calculate_reconnected_numbers(date, segment=None):
        """
        Calcula números reconectados (alocados que já foram descontinuados antes).

        Números que foram recuperados e devolvidos ao mesmo negociador.
        Args:
            date: Data para calcular
            segment: 'B2B' ou 'B2C' (opcional)
        Returns:
            int: Quantidade de números reconectados
        """
        end_of_day = timezone.make_aware(datetime.combine(date, time.max))
        start_of_day = timezone.make_aware(datetime.combine(date, time.min))

        # Alocações do dia que tiveram uso anterior (foram liberadas e realocadas)
        reconnected = (
            LineAllocation.objects.filter(
                allocated_at__range=(start_of_day, end_of_day)
            )
            .filter(phone_line__allocations__released_at__lt=F("allocated_at"))
            .distinct()
            .count()
        )

        return reconnected

    @staticmethod
    def calculate_new_numbers(date, segment=None):
        """
        Calcula números novos atribuídos no dia.

        Números que ainda não foram usados e foram criados naquele dia.
        Args:
            date: Data para calcular
            segment: 'B2B' ou 'B2C' (opcional)
        Returns:
            int: Quantidade de números novos
        """
        end_of_day = timezone.make_aware(datetime.combine(date, time.max))
        start_of_day = timezone.make_aware(datetime.combine(date, time.min))

        query = PhoneLine.objects.filter(
            created_at__range=(start_of_day, end_of_day), is_deleted=False
        )

        return query.count()

    @staticmethod
    def populate_daily_indicators(date=None):
        """
        Task agendada para preencher indicadores automáticos dos indicadores.

        Essa função:
        1. Busca todos os DailyIndicator do dia
        2. Calcula os valores automáticos
        3. Atualiza os registros

        Args:
            date: Data para popular (padrão: hoje)
        """
        if date is None:
            date = timezone.localdate()

        # Atualizar todos os indicadores do dia com valores calculados
        indicators = DailyIndicator.objects.filter(date=date)

        if not indicators.exists():
            return 0

        available = DailyIndicatorService.calculate_available_numbers(date)
        delivered = DailyIndicatorService.calculate_delivered_numbers(date)
        reconnected = DailyIndicatorService.calculate_reconnected_numbers(date)
        new = DailyIndicatorService.calculate_new_numbers(date)

        indicators.update(
            numbers_available=available,
            numbers_delivered=delivered,
            numbers_reconnected=reconnected,
            numbers_new=new,
        )

        return indicators.count()

    @staticmethod
    def get_summary_for_period(start_date, end_date, segment=None):
        """
        Retorna um resumo dos indicadores para um período.

        Args:
            start_date: Data inicial
            end_date: Data final
            segment: Filtrar por segmento (optional)
        Returns:
            dict: Resumo com totais e médias
        """
        query = DailyIndicator.objects.filter(date__range=(start_date, end_date))

        if segment:
            query = query.filter(segment=segment)

        if not query.exists():
            return {
                "total_records": 0,
                "total_people_logged": 0,
                "avg_people_logged": 0,
                "total_numbers_available": 0,
                "total_numbers_delivered": 0,
                "total_numbers_reconnected": 0,
                "total_numbers_new": 0,
            }

        from django.db.models import Sum

        aggregation = query.aggregate(
            total_people_logged=Sum("people_logged_in"),
            total_numbers_available=Sum("numbers_available"),
            total_numbers_delivered=Sum("numbers_delivered"),
            total_numbers_reconnected=Sum("numbers_reconnected"),
            total_numbers_new=Sum("numbers_new"),
        )

        count = query.count()

        return {
            "total_records": count,
            "total_people_logged": aggregation["total_people_logged"] or 0,
            "avg_people_logged": (
                round((aggregation["total_people_logged"] or 0) / count, 2)
                if count > 0
                else 0
            ),
            "total_numbers_available": aggregation["total_numbers_available"] or 0,
            "total_numbers_delivered": aggregation["total_numbers_delivered"] or 0,
            "total_numbers_reconnected": aggregation["total_numbers_reconnected"] or 0,
            "total_numbers_new": aggregation["total_numbers_new"] or 0,
        }
