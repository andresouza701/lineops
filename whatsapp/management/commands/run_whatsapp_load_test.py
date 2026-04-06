from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

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
        parser.add_argument(
            "--report-file",
            help="Caminho opcional para salvar um relatorio Markdown da execucao.",
        )
        parser.add_argument(
            "--environment-label",
            default="qa",
            help="Identificador do ambiente registrado no relatorio.",
        )
        parser.add_argument(
            "--notes",
            default="",
            help="Observacoes livres para registrar no relatorio.",
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
        if summary.scenario_note:
            self.stdout.write(f"Observacao: {summary.scenario_note}")
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

        report_file = options.get("report_file")
        if report_file:
            report_path = Path(report_file)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                self._build_report(
                    summary=summary,
                    options=options,
                ),
                encoding="utf-8",
            )
            self.stdout.write(f"Relatorio salvo em: {report_path}")

    def _build_report(self, *, summary, options) -> str:
        executed_at = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S %Z")
        lines = [
            "# Evidencia de Load Test WhatsApp",
            "",
            f"- Executado em: {executed_at}",
            f"- Ambiente: {options.get('environment_label') or 'qa'}",
            f"- Cenario: {summary.label}",
            f"- Chave do cenario: `{summary.scenario}`",
            f"- Session limit: {options.get('session_limit')}",
            f"- Min sessions: {options.get('min_sessions')}",
            f"- Concorrencia: {summary.concurrency}",
            f"- Connected only: {bool(options.get('connected_only'))}",
            "",
            "## Resultado",
            "",
            f"- Sessoes selecionadas: {summary.selected_sessions}",
            f"- Sucesso: {summary.success_count}",
            f"- Falha: {summary.failure_count}",
            (
                "- Latencia media (ms): "
                f"{summary.average_latency_ms if summary.average_latency_ms is not None else '-'}"
            ),
            (
                "- Latencia p95 (ms): "
                f"{summary.p95_latency_ms if summary.p95_latency_ms is not None else '-'}"
            ),
        ]
        if summary.scenario_note:
            lines.extend(
                [
                    "",
                    "## Observacao de Escopo",
                    "",
                    f"- {summary.scenario_note}",
                ]
            )

        lines.extend(
            [
                "",
                "## Resumo por Instancia",
                "",
            ]
        )
        for item in summary.instance_summaries:
            lines.append(
                (
                    f"- {item.instance_name}: total={item.total_requests} "
                    f"success={item.success_count} failure={item.failure_count}"
                )
            )

        lines.extend(
            [
                "",
                "## Falhas Amostradas",
                "",
            ]
        )
        if summary.failures:
            for failure in summary.failures[:10]:
                lines.append(
                    f"- {failure.session_id}: {failure.detail or 'sem detalhe'}"
                )
        else:
            lines.append("- Nenhuma falha amostrada.")

        notes = (options.get("notes") or "").strip()
        if notes:
            lines.extend(
                [
                    "",
                    "## Notas",
                    "",
                    f"- {notes}",
                ]
            )

        return "\n".join(lines) + "\n"
