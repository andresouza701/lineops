from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("allocations", "0002_lineallocation_allocations_employe_8009f2_idx_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="lineallocation",
            name="released_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="allocations_released",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
