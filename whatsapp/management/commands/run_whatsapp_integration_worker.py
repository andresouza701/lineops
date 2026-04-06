import time

from django.conf import settings
from django.core.management.base import BaseCommand

from whatsapp.services.worker_service import WhatsAppIntegrationWorkerService


class Command(BaseCommand):
    help = "Executa o worker assicrono da integracao WhatsApp em processo dedicado."

    def add_arguments(self, parser):
        parser.add_argument(
            "--run-once",
            action="store_true",
            help="Processa um unico ciclo e encerra.",
        )
        parser.add_argument(
            "--worker-code",
            default="default",
            help="Identificador logico do worker.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Quantidade maxima de jobs por ciclo.",
        )
        parser.add_argument(
            "--tick-seconds",
            type=int,
            help="Sobrescreve o intervalo de espera entre ciclos.",
        )

    def handle(self, *args, **options):
        service = WhatsAppIntegrationWorkerService()
        worker_code = options["worker_code"]
        tick_seconds = options.get("tick_seconds") or int(
            getattr(settings, "WHATSAPP_INTEGRATION_WORKER_TICK_SECONDS", 10)
        )
        limit = int(options["limit"])

        if options.get("run_once", False):
            self._run_cycle(service, worker_code=worker_code, limit=limit)
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Worker WhatsApp iniciado: code={worker_code}, tick={tick_seconds}s."
            )
        )
        try:
            while True:
                self._run_cycle(service, worker_code=worker_code, limit=limit)
                time.sleep(tick_seconds)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Worker WhatsApp encerrado."))

    def _run_cycle(
        self,
        service: WhatsAppIntegrationWorkerService,
        *,
        worker_code: str,
        limit: int,
    ) -> None:
        summary = service.run_once(worker_code=worker_code, limit=limit)
        self.stdout.write(
            "worker={worker} claimed={claimed} processed={processed} failed={failed}".format(
                worker=summary.worker_code,
                claimed=summary.claimed_jobs,
                processed=summary.processed_jobs,
                failed=summary.failed_jobs,
            )
        )
