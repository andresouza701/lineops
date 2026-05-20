from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pendencies", "0005_deduplicate_employee_null_allocation"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="allocationpendency",
            constraint=models.UniqueConstraint(
                fields=["employee"],
                condition=models.Q(allocation__isnull=True),
                name="uq_pendency_employee_without_allocation",
            ),
        ),
    ]
