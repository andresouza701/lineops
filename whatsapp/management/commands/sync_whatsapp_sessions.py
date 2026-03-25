from django.core.management.base import BaseCommand

from whatsapp.models import WhatsAppSession
from whatsapp.services.sync_service import WhatsAppSessionSyncService


class Command(BaseCommand):
    help = "Sincroniza o status local das sessoes WhatsApp com o Meow."

    def add_arguments(self, parser):
        parser.add_argument(
            "--session-id",
            help="Sincroniza apenas a sessao informada.",
        )
        parser.add_argument(
            "--instance-id",
            type=int,
            help="Sincroniza apenas sessoes da instancia informada.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Inclui sessoes inativas na sincronizacao.",
        )

    def handle(self, *args, **options):
        queryset = WhatsAppSession.objects.all()
        session_id = options.get("session_id")
        instance_id = options.get("instance_id")

        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if instance_id:
            queryset = queryset.filter(meow_instance_id=instance_id)

        results = WhatsAppSessionSyncService().sync_sessions(
            queryset=queryset,
            include_inactive=options.get("include_inactive", False),
        )

        if not results:
            self.stdout.write(self.style.WARNING("Nenhuma sessao WhatsApp encontrada."))
            return

        for result in results:
            outcome = "OK" if result.success else "FAIL"
            self.stdout.write(
                f"{result.session.session_id}: {outcome} | "
                f"status={result.status} | detail={result.detail}"
            )

        success_count = sum(result.success for result in results)
        failure_count = len(results) - success_count
        self.stdout.write(
            self.style.SUCCESS(
                "Resumo: "
                f"{success_count} sincronizadas com sucesso, "
                f"{failure_count} com falha."
            )
        )
