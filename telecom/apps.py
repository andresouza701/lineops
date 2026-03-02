from django.apps import AppConfig


class TelecomConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "telecom"

    def ready(self):
        import telecom.signals  # noqa
