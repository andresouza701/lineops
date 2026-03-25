from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("whatsapp", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappactionaudit",
            name="duration_ms",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
