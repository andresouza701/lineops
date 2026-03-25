from django.core.management.base import BaseCommand, CommandError

from whatsapp.models import MeowInstance
from whatsapp.services.rollout_service import MeowRolloutService


class Command(BaseCommand):
    help = "Aplica uma etapa padrao do rollout operacional nas instancias Meow."

    def add_arguments(self, parser):
        parser.add_argument(
            "--stage",
            type=int,
            required=True,
            help="Capacidade liberada por instancia para a etapa do rollout.",
        )
        parser.add_argument(
            "--instance-id",
            type=int,
            help="Aplica a etapa apenas na instancia informada.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Inclui instancias inativas quando o rollout for em lote.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Exibe o que seria alterado sem persistir.",
        )

    def handle(self, *args, **options):
        queryset = MeowInstance.objects.all()
        instance_id = options.get("instance_id")
        if instance_id:
            queryset = queryset.filter(pk=instance_id)
        elif not options.get("include_inactive", False):
            queryset = queryset.filter(is_active=True)

        instances = list(queryset.order_by("name"))
        if not instances:
            self.stdout.write(self.style.WARNING("Nenhuma instancia Meow encontrada."))
            return

        service = MeowRolloutService()
        try:
            stage = service.get_stage(options["stage"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        updated_instances = service.apply_stage(
            stage.stage_sessions,
            queryset=queryset,
            dry_run=options.get("dry_run", False),
        )

        prefix = "[dry-run] " if options.get("dry_run", False) else ""
        for instance in updated_instances:
            self.stdout.write(
                f"{prefix}{instance.name}: "
                f"target={instance.target_sessions} "
                f"warning={instance.warning_sessions} "
                f"max={instance.max_sessions}"
            )

        if options.get("dry_run", False):
            self.stdout.write(
                self.style.WARNING(
                    f"Dry-run concluido: {len(updated_instances)} instancia(s) "
                    f"seriam ajustadas para a etapa {stage.stage_sessions}."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Rollout aplicado em {len(updated_instances)} instancia(s) para "
                f"a etapa {stage.stage_sessions}."
            )
        )
