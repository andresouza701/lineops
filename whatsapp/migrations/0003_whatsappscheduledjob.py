from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("whatsapp", "0002_whatsappactionaudit_duration_ms"),
    ]

    operations = [
        migrations.CreateModel(
            name="WhatsAppScheduledJob",
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
                    "job_code",
                    models.CharField(
                        choices=[
                            ("HEALTH_CHECK", "Health check"),
                            ("SESSION_SYNC", "Session sync"),
                            ("SESSION_RECONCILE", "Session reconcile"),
                        ],
                        db_index=True,
                        max_length=32,
                        unique=True,
                    ),
                ),
                ("interval_seconds", models.PositiveIntegerField()),
                ("is_running", models.BooleanField(db_index=True, default=False)),
                (
                    "last_status",
                    models.CharField(
                        choices=[
                            ("IDLE", "Idle"),
                            ("RUNNING", "Running"),
                            ("SUCCESS", "Success"),
                            ("FAILURE", "Failure"),
                        ],
                        default="IDLE",
                        max_length=16,
                    ),
                ),
                ("last_detail", models.TextField(blank=True)),
                ("last_started_at", models.DateTimeField(blank=True, null=True)),
                ("last_finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "next_run_at",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["job_code"],
                "indexes": [
                    models.Index(
                        fields=["is_running", "next_run_at"],
                        name="whatsapp_wh_is_runn_c9c0af_idx",
                    )
                ],
            },
        ),
    ]
