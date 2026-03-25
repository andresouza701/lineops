from django.core.management.base import BaseCommand

from whatsapp.models import MeowInstance
from whatsapp.services.health_service import MeowHealthCheckService


class Command(BaseCommand):
    help = "Atualiza o health_status das instancias Meow."

    def add_arguments(self, parser):
        parser.add_argument(
            "--instance-id",
            type=int,
            help="Executa o health check apenas para a instancia informada.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Inclui instancias inativas na verificacao.",
        )

    def handle(self, *args, **options):
        queryset = MeowInstance.objects.all()
        instance_id = options.get("instance_id")
        if instance_id:
            queryset = queryset.filter(pk=instance_id)

        service = MeowHealthCheckService()
        results = service.check_instances(
            queryset=queryset,
            include_inactive=options.get("include_inactive", False),
        )

        if not results:
            self.stdout.write(self.style.WARNING("Nenhuma instancia Meow encontrada."))
            return

        for result in results:
            self.stdout.write(
                f"{result.instance.name}: {result.health_status} - {result.detail}"
            )

        healthy = sum(result.health_status == "HEALTHY" for result in results)
        degraded = sum(result.health_status == "DEGRADED" for result in results)
        unavailable = sum(result.health_status == "UNAVAILABLE" for result in results)
        self.stdout.write(
            self.style.SUCCESS(
                "Resumo: "
                f"{healthy} healthy, {degraded} degraded, "
                f"{unavailable} unavailable."
            )
        )
