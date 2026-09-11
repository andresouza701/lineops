from django.db import migrations, models


class Migration(migrations.Migration):
    """Adiciona o choice LINE_ALLOCATION a LineDailyActionAuditEvent.source.

    Metadado apenas: `source` continua CharField sem constraint de DB para
    os valores de choices, entao nao ha alteracao de schema real. Mantido
    como migration isolada para preservar o historico de estado do model.
    """

    dependencies = [
        ("telecom", "0017_line_daily_action_audit_event"),
    ]

    operations = [
        migrations.AlterField(
            model_name="linedailyactionauditevent",
            name="source",
            field=models.CharField(
                choices=[
                    ("DAILY_USER_ACTION", "Acao diaria"),
                    ("ALLOCATION_PENDENCY", "Pendencia"),
                    ("LINE_ALLOCATION", "Status da linha"),
                ],
                max_length=30,
            ),
        ),
    ]
