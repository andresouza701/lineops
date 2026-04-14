from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0007_dashboarddailysnapshot"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dailyuseraction",
            name="action_type",
            field=models.CharField(
                choices=[
                    ("new_number", "NÃºmero novo"),
                    ("reconnect_whatsapp", "Reconectar WhatsApp"),
                    ("pending", "Pendência"),
                ],
                max_length=30,
                verbose_name="Tipo de aÃ§Ã£o",
            ),
        ),
    ]
