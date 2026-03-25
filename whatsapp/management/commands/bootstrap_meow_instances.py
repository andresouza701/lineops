import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from whatsapp.models import MeowInstance


class Command(BaseCommand):
    help = "Cria ou atualiza instancias Meow a partir de um arquivo JSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "--config",
            required=True,
            help="Caminho para o arquivo JSON com as instancias Meow.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Valida o arquivo e exibe o que seria alterado sem persistir.",
        )

    def handle(self, *args, **options):
        config_path = Path(options["config"]).expanduser()
        if not config_path.exists():
            raise CommandError(f"Arquivo de configuracao nao encontrado: {config_path}")

        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"JSON invalido em {config_path}: {exc}") from exc

        if not isinstance(payload, list) or not payload:
            raise CommandError("O arquivo JSON deve conter uma lista nao vazia.")

        dry_run = options.get("dry_run", False)
        created_count = 0
        updated_count = 0
        seen_names = set()
        validated_items = []

        for item in payload:
            name = self._extract_name(item)
            if name in seen_names:
                raise CommandError(f"Nome de instancia duplicado no JSON: {name}")
            seen_names.add(name)

            instance = MeowInstance.objects.filter(name=name).first()
            normalized = self._normalize_item(item, existing_instance=instance)
            validated_items.append((normalized, instance))

        for normalized, instance in validated_items:
            action = "create" if instance is None else "update"

            if dry_run:
                self.stdout.write(
                    "[dry-run] "
                    f"{action}: {normalized['name']} -> {normalized['base_url']}"
                )
                if action == "create":
                    created_count += 1
                else:
                    updated_count += 1
                continue

            if instance is None:
                MeowInstance.objects.create(**normalized)
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Criada instancia {normalized['name']}.")
                )
                continue

            for field, value in normalized.items():
                setattr(instance, field, value)
            instance.save()
            updated_count += 1
            self.stdout.write(
                self.style.SUCCESS(f"Atualizada instancia {normalized['name']}.")
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry-run concluido: {created_count} criaria(m), "
                    f"{updated_count} atualizaria(m), sem persistencia."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Bootstrap concluido: {created_count} criada(s), "
                f"{updated_count} atualizada(s)."
            )
        )

    def _extract_name(self, item):
        if not isinstance(item, dict):
            raise CommandError("Cada item do JSON deve ser um objeto.")

        name = (item.get("name") or "").strip()
        if not name:
            raise CommandError("Cada instancia precisa de 'name' e 'base_url'.")
        return name

    def _normalize_item(self, item, *, existing_instance=None):
        if not isinstance(item, dict):
            raise CommandError("Cada item do JSON deve ser um objeto.")

        name = (item.get("name") or "").strip()
        base_url = (item.get("base_url") or "").strip()
        if not name or not base_url:
            raise CommandError("Cada instancia precisa de 'name' e 'base_url'.")

        normalized = {
            "name": name,
            "base_url": base_url,
            "is_active": bool(item.get("is_active", True)),
            "target_sessions": int(item.get("target_sessions", 35)),
            "warning_sessions": int(item.get("warning_sessions", 40)),
            "max_sessions": int(item.get("max_sessions", 45)),
        }

        probe = existing_instance or MeowInstance()
        for field, value in normalized.items():
            setattr(probe, field, value)
        probe.full_clean()
        return normalized
