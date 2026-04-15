import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pendencies", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PendencyObservationNotification",
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
                    "observation_text",
                    models.CharField(
                        max_length=350,
                        verbose_name="Texto da observação",
                    ),
                ),
                (
                    "is_read",
                    models.BooleanField(default=False, verbose_name="Lida"),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Criada em"
                    ),
                ),
                (
                    "pendency",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="observation_notifications",
                        to="pendencies.allocationpendency",
                        verbose_name="Pendência",
                    ),
                ),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pendency_notifications",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Destinatário",
                    ),
                ),
                (
                    "sent_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sent_pendency_notifications",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Enviado por",
                    ),
                ),
            ],
            options={
                "verbose_name": "Notificação de Observação de Pendência",
                "verbose_name_plural": "Notificações de Observação de Pendência",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="pendencyobservationnotification",
            index=models.Index(
                fields=["recipient", "is_read"],
                name="pendency_notif_recip_read_idx",
            ),
        ),
    ]
