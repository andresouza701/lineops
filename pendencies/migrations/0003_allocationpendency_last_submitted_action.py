from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pendencies", "0002_pendencyobservationnotification"),
    ]

    operations = [
        migrations.AddField(
            model_name="allocationpendency",
            name="last_submitted_action",
            field=models.CharField(
                blank=True,
                choices=[
                    ("no_action", "Sem Ação"),
                    ("new_number", "Número Novo"),
                    ("reconnect_whatsapp", "Reconectar WhatsApp"),
                    ("pending", "Pendência"),
                ],
                help_text=(
                    "Ação que estava ativa quando a pendência foi submetida. "
                    "Mantida após a resolução para auditoria e contagem de reconexões."
                ),
                max_length=30,
                null=True,
                verbose_name="Última ação enviada",
            ),
        ),
        migrations.AddIndex(
            model_name="allocationpendency",
            index=models.Index(
                fields=["resolved_at", "last_submitted_action"],
                name="pendency_resolved_action_idx",
            ),
        ),
    ]
