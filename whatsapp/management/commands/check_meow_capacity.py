from django.core.management.base import BaseCommand

from whatsapp.models import MeowInstance
from whatsapp.services.capacity_service import MeowCapacityService


class Command(BaseCommand):
    help = "Exibe a distribuicao de sessoes WhatsApp por instancia Meow."

    def add_arguments(self, parser):
        parser.add_argument(
            "--instance-id",
            type=int,
            help="Exibe a capacidade apenas da instancia informada.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Inclui instancias inativas no relatorio.",
        )

    def handle(self, *args, **options):
        queryset = MeowInstance.objects.all()
        instance_id = options.get("instance_id")
        if instance_id:
            queryset = queryset.filter(pk=instance_id)

        summaries = MeowCapacityService().summarize_instances(
            queryset=queryset,
            include_inactive=options.get("include_inactive", False),
        )

        if not summaries:
            self.stdout.write(self.style.WARNING("Nenhuma instancia Meow encontrada."))
            return

        for summary in summaries:
            self.stdout.write(
                f"{summary.instance.name}: {summary.capacity_level} | "
                f"active={summary.active_sessions} "
                f"connected={summary.connected_sessions} "
                f"pending={summary.pending_sessions} "
                f"degraded={summary.degraded_sessions} "
                f"target={summary.instance.target_sessions} "
                f"warning={summary.instance.warning_sessions} "
                f"max={summary.instance.max_sessions}"
            )

        ok_count = sum(summary.capacity_level == "OK" for summary in summaries)
        warning_count = sum(
            summary.capacity_level == "WARNING" for summary in summaries
        )
        critical_count = sum(
            summary.capacity_level == "CRITICAL" for summary in summaries
        )
        over_capacity_count = sum(
            summary.capacity_level == "OVER_CAPACITY" for summary in summaries
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Resumo: "
                f"{ok_count} ok, "
                f"{warning_count} warning, "
                f"{critical_count} critical, "
                f"{over_capacity_count} over_capacity."
            )
        )
