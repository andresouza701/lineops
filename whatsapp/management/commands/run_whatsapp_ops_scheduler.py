import time

from django.core.management.base import BaseCommand

from whatsapp.services.scheduler_service import WhatsAppOpsSchedulerService


class Command(BaseCommand):
    help = "Executa o scheduler operacional do WhatsApp em processo dedicado."

    def add_arguments(self, parser):
        parser.add_argument(
            "--run-once",
            action="store_true",
            help="Executa um unico ciclo do scheduler e encerra.",
        )
        parser.add_argument(
            "--tick-seconds",
            type=int,
            help="Sobrescreve o intervalo de espera entre ciclos.",
        )

    def handle(self, *args, **options):
        service = WhatsAppOpsSchedulerService()
        tick_seconds = options.get("tick_seconds") or service.get_tick_seconds()

        if options.get("run_once", False):
            self._run_cycle(service)
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Scheduler operacional WhatsApp iniciado com tick de "
                f"{tick_seconds}s."
            )
        )
        try:
            while True:
                self._run_cycle(service)
                time.sleep(tick_seconds)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Scheduler operacional encerrado."))

    def _run_cycle(self, service: WhatsAppOpsSchedulerService) -> None:
        results = service.run_due_jobs()
        ran_results = [result for result in results if result.ran]
        if not ran_results:
            self.stdout.write(self.style.WARNING("Nenhum job elegivel neste ciclo."))
            return

        for result in ran_results:
            self.stdout.write(
                f"{result.job_code}: {result.status} | "
                f"detail={result.detail} | "
                f"next_run={result.next_run_at.isoformat() if result.next_run_at else '-'}"
            )
