from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("telecom", "0013_phoneline_canal_alter_phoneline_origem"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WhatsappReconnectHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "session_id",
                    models.CharField(
                        max_length=120, unique=True, verbose_name="ID da sessão"
                    ),
                ),
                (
                    "outcome",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("CONNECTED", "Conectado"),
                            ("FAILED", "Falhou"),
                            ("CANCELLED", "Cancelado"),
                        ],
                        max_length=20,
                        null=True,
                        verbose_name="Resultado",
                        help_text="Nulo enquanto a sessão está em andamento.",
                    ),
                ),
                (
                    "error_code",
                    models.CharField(
                        blank=True, default="", max_length=100, verbose_name="Código de erro"
                    ),
                ),
                (
                    "error_message",
                    models.TextField(blank=True, default="", verbose_name="Mensagem de erro"),
                ),
                (
                    "attempt_count",
                    models.IntegerField(default=0, verbose_name="Tentativas"),
                ),
                (
                    "started_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Iniciado em"),
                ),
                (
                    "finished_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Finalizado em"
                    ),
                ),
                (
                    "phone_line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reconnect_history",
                        to="telecom.phoneline",
                        verbose_name="Linha",
                    ),
                ),
                (
                    "started_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reconnect_sessions_started",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Iniciado por",
                    ),
                ),
            ],
            options={
                "verbose_name": "Histórico de Reconexão WhatsApp",
                "verbose_name_plural": "Históricos de Reconexão WhatsApp",
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="whatsappreconnecthistory",
            index=models.Index(
                fields=["phone_line", "-started_at"],
                name="telecom_wha_phone_l_started_idx",
            ),
        ),
    ]
