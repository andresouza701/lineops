from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Cria o indice unico parcial em phone_number na collection reconnect_sessions. "
        "Obrigatorio antes de habilitar RECONNECT_ENABLED=True em producao."
    )

    def handle(self, *args, **options):
        from django.conf import settings

        if not getattr(settings, "RECONNECT_ENABLED", False):
            raise CommandError(
                "RECONNECT_ENABLED esta desabilitado. "
                "Configure as variaveis de ambiente do Mongo antes de criar os indices."
            )

        from telecom.repositories.reconnect_sessions import MongoReconnectSessionRepository

        repo = MongoReconnectSessionRepository.from_settings()
        collection = repo.collection

        index_name = collection.create_index(
            [("phone_number", 1)],
            unique=True,
            partialFilterExpression={"active_lock": True},
            name="phone_number_active_lock_unique",
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Indice criado com sucesso: {index_name}\n"
                "Collection: "
                f"{settings.RECONNECT_MONGO_DATABASE}.{settings.RECONNECT_MONGO_COLLECTION}"
            )
        )
