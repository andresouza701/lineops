import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("allocations", "0008_alter_lineallocation_line_status"),
        ("employees", "0020_rename_heineki_portfolio"),
        ("telecom", "0016_alter_phonelinehistory_action_reactivated"),
    ]

    operations = [
        migrations.CreateModel(
            name="LineDailyActionAuditEvent",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("OPENED", "Aberta"),
                            ("ACTION_CHANGED", "Acao alterada"),
                            ("NOTE_CHANGED", "Nota alterada"),
                            ("RESPONSIBLE_ASSIGNED", "Tecnico assumiu"),
                            ("RESPONSIBLE_RELEASED", "Tecnico liberou"),
                            ("LINE_STATUS_CHANGED", "Status alterado"),
                            ("RESOLVED", "Resolvida"),
                            ("REOPENED", "Reaberta"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("DAILY_USER_ACTION", "Acao diaria"),
                            ("ALLOCATION_PENDENCY", "Pendencia"),
                        ],
                        max_length=30,
                    ),
                ),
                ("source_object_id", models.BigIntegerField()),
                ("operation_id", models.UUIDField(db_index=True, default=uuid.uuid4)),
                ("payload_version", models.PositiveSmallIntegerField(default=1)),
                ("occurred_at", models.DateTimeField(db_index=True)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "phone_number_snapshot",
                    models.CharField(blank=True, default="", max_length=20),
                ),
                (
                    "allocation_id_snapshot",
                    models.BigIntegerField(blank=True, null=True),
                ),
                (
                    "employee_name_snapshot",
                    models.CharField(blank=True, default="", max_length=40),
                ),
                (
                    "performed_by_name_snapshot",
                    models.CharField(blank=True, default="", max_length=150),
                ),
                (
                    "performed_by_email_snapshot",
                    models.EmailField(blank=True, default="", max_length=254),
                ),
                ("before_state", models.JSONField()),
                ("after_state", models.JSONField()),
                (
                    "allocation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="daily_action_audit_events",
                        to="allocations.lineallocation",
                        verbose_name="Alocacao",
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="daily_action_audit_events",
                        to="employees.employee",
                        verbose_name="Usuario",
                    ),
                ),
                (
                    "performed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="daily_action_audit_events_performed",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Executado por",
                    ),
                ),
                (
                    "phone_line",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="daily_action_audit_events",
                        to="telecom.phoneline",
                        verbose_name="Linha",
                    ),
                ),
            ],
            options={
                "verbose_name": "Evento de Auditoria de Acao de Linha",
                "verbose_name_plural": "Eventos de Auditoria de Acao de Linha",
                "ordering": ["-occurred_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="linedailyactionauditevent",
            index=models.Index(
                fields=["phone_line", "-occurred_at"], name="ldaae_phone_line_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="linedailyactionauditevent",
            index=models.Index(
                fields=["allocation", "-occurred_at"], name="ldaae_allocation_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="linedailyactionauditevent",
            index=models.Index(
                fields=["employee", "-occurred_at"], name="ldaae_employee_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="linedailyactionauditevent",
            index=models.Index(
                fields=["event_type", "-occurred_at"], name="ldaae_event_type_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="linedailyactionauditevent",
            index=models.Index(
                fields=["source", "source_object_id"], name="ldaae_source_obj_idx"
            ),
        ),
    ]
