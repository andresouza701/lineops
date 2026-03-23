from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0006_alter_dailyuseraction_unique_together_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="DashboardDailySnapshot",
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
                    "date",
                    models.DateField(db_index=True, unique=True, verbose_name="Data"),
                ),
                (
                    "people_logged_in",
                    models.IntegerField(default=0, verbose_name="Pessoas Logadas"),
                ),
                (
                    "percentage_without_whatsapp",
                    models.FloatField(default=0, verbose_name="% sem Whats"),
                ),
                (
                    "b2b_without_whatsapp",
                    models.IntegerField(default=0, verbose_name="B2B sem Whats"),
                ),
                (
                    "b2c_without_whatsapp",
                    models.IntegerField(default=0, verbose_name="B2C sem Whats"),
                ),
                (
                    "numbers_available",
                    models.IntegerField(default=0, verbose_name="Números Disponíveis"),
                ),
                (
                    "numbers_delivered",
                    models.IntegerField(default=0, verbose_name="Números Entregues"),
                ),
                (
                    "numbers_reconnected",
                    models.IntegerField(default=0, verbose_name="Reconectados"),
                ),
                ("numbers_new", models.IntegerField(default=0, verbose_name="Novos")),
                (
                    "total_uncovered_day",
                    models.IntegerField(default=0, verbose_name="Total Descoberto DIA"),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Criado em"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Atualizado em"),
                ),
            ],
            options={
                "verbose_name": "Snapshot Diário do Dashboard",
                "verbose_name_plural": "Snapshots Diários do Dashboard",
                "ordering": ["-date"],
                "indexes": [
                    models.Index(fields=["-date"], name="dashboard_d_date_1cf480_idx")
                ],
            },
        ),
    ]
