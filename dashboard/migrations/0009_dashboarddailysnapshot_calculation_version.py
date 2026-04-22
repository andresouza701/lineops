from django.db import migrations, models


def mark_existing_snapshots_as_legacy(apps, schema_editor):
    DashboardDailySnapshot = apps.get_model("dashboard", "DashboardDailySnapshot")
    DashboardDailySnapshot.objects.all().update(calculation_version=1)


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0008_alter_dailyuseraction_action_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="dashboarddailysnapshot",
            name="calculation_version",
            field=models.PositiveSmallIntegerField(
                default=2,
                verbose_name="Versao do Calculo",
            ),
        ),
        migrations.RunPython(
            mark_existing_snapshots_as_legacy,
            migrations.RunPython.noop,
        ),
    ]
