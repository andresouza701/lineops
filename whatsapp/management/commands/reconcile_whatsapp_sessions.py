from django.core.management.base import BaseCommand

from whatsapp.models import WhatsAppSession
from whatsapp.services.reconcile_service import WhatsAppSessionReconcileService


class Command(BaseCommand):
    help = "Verifica inconsistencias locais nas sessoes WhatsApp."

    def add_arguments(self, parser):
        parser.add_argument(
            "--session-id",
            help="Reconcilia apenas a sessao informada.",
        )
        parser.add_argument(
            "--instance-id",
            type=int,
            help="Reconcilia apenas sessoes da instancia informada.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Inclui sessoes inativas na analise.",
        )

    def handle(self, *args, **options):
        queryset = WhatsAppSession.objects.all()
        session_id = options.get("session_id")
        instance_id = options.get("instance_id")

        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if instance_id:
            queryset = queryset.filter(meow_instance_id=instance_id)

        results = WhatsAppSessionReconcileService().reconcile_sessions(
            queryset=queryset,
            include_inactive=options.get("include_inactive", False),
        )

        if not results:
            self.stdout.write(self.style.WARNING("Nenhuma sessao WhatsApp encontrada."))
            return

        for result in results:
            outcome = "OK" if result.is_consistent else "ISSUES"
            issues = ",".join(result.issue_codes) if result.issue_codes else "-"
            self.stdout.write(
                f"{result.session.session_id}: {outcome} | "
                f"issues={issues} | detail={result.detail}"
            )

        inconsistent_count = sum(not result.is_consistent for result in results)
        self.stdout.write(
            self.style.SUCCESS(
                "Resumo: "
                f"{len(results) - inconsistent_count} consistentes, "
                f"{inconsistent_count} com inconsistencias."
            )
        )
