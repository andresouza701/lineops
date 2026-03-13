from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("telecom", "0010_phoneline_origem"),
    ]

    operations = [
        migrations.AlterField(
            model_name="simcard",
            name="iccid",
            field=models.CharField(db_index=True, max_length=22),
        ),
    ]
