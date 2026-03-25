from django.core.management.base import BaseCommand, CommandError

from whatsapp.models import WhatsAppSession
from whatsapp.services.load_test_service import WhatsAppLoadTestService


class Command(BaseCommand):
    help = "Executa carga concorrente nas operacoes de sessao WhatsApp."

    def add_arguments(self, parser):
        parser.add_argument(
            "--scenario",
            required=True,
            choices=sorted(WhatsAppLoadTestService.SCENARIO_LABELS),
            help="Cenario de carga a executar.",
        )
        parser.add_argument(
            "--session-limit",
            type=int,
            default=200,
            help="Quantidade maxima de sessoes usadas na amostra.",
        )
        parser.add_argument(
            "--min-sessions",
            type=int,
            default=0,
            help="Falha se menos que esse numero de sessoes for encontrado.",
        )
        parser.add_argument(
            "--concurrency",
            type=int,
            default=20,
            help="Numero de workers concorrentes.",
        )
        parser.add_argument(
            "--instance-id",
            type=int,
            help="Restringe o teste a uma unica instancia Meow.",
        )
        parser.add_argument(
            "--connected-only",
            action="store_true",
            help="Usa apenas sessoes locais marcadas como conectadas.",
        )

    def handle(self, *args, **options):
        queryset = WhatsAppSession.objects.all()
        instance_id = options.get("instance_id")
        if instance_id:
            queryset = queryset.filter(meow_instance_id=instance_id)

        service = WhatsAppLoadTestService()
        try:
            summary = service.run(
                scenario=options["scenario"],
                queryset=queryset,
                session_limit=options.get("session_limit"),
                concurrency=options.get("concurrency", 20),
                min_sessions=options.get("min_sessions", 0),
                connected_only=options.get("connected_only", False),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"Cenario: {summary.label}")
        self.stdout.write(f"Sessoes selecionadas: {summary.selected_sessions}")
        self.stdout.write(f"Concorrencia: {summary.concurrency}")
        self.stdout.write(
            f"Sucesso: {summary.success_count} | Falha: {summary.failure_count}"
        )
        self.stdout.write(
            "Latencia: "
            f"media={summary.average_latency_ms if summary.average_latency_ms is not None else '-'}ms "
            f"p95={summary.p95_latency_ms if summary.p95_latency_ms is not None else '-'}ms"
        )
        self.stdout.write("Resumo por instancia:")
        for item in summary.instance_summaries:
            self.stdout.write(
                f"- {item.instance_name}: "
                f"total={item.total_requests} "
                f"success={item.success_count} "
                f"failure={item.failure_count}"
            )

        if summary.failures:
            self.stdout.write(self.style.WARNING("Falhas amostradas:"))
            for failure in summary.failures[:10]:
                self.stdout.write(
                    f"- {failure.session_id}: {failure.detail or 'sem detalhe'}"
                )
