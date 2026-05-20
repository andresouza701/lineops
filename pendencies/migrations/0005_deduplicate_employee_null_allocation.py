"""
Data migration: deduplicate AllocationPendency rows with allocation IS NULL
before adding the partial unique constraint in 0006.
"""

from django.db import migrations

from pendencies.migrations._0005_deduplicate_employee_null_allocation import (
    deduplicate_employee_null_pendencies,
)


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("pendencies", "0004_backfill_resolved_at_reconnect"),
    ]

    operations = [
        migrations.RunPython(
            deduplicate_employee_null_pendencies,
            reverse_code=reverse_noop,
        ),
    ]
