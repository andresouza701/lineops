from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0006_alter_systemuser_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemuser",
            name="supervisor_email",
            field=models.EmailField(
                blank=True,
                max_length=254,
                null=True,
                verbose_name="Supervisor vinculado",
            ),
        ),
        migrations.AlterField(
            model_name="systemuser",
            name="role",
            field=models.CharField(
                choices=[
                    ("admin", "Admin"),
                    ("dev", "Dev"),
                    ("super", "Super"),
                    ("backoffice", "Backoffice"),
                    ("gerente", "Gerente"),
                    ("operator", "Operator"),
                ],
                default="operator",
                max_length=20,
            ),
        ),
    ]
