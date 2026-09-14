from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("telecom", "0019_linedailyactionauditevent_db_immutability"),
    ]

    operations = [
        migrations.AlterField(
            model_name="linedailyactionauditevent",
            name="id",
            field=models.BigAutoField(
                auto_created=True,
                primary_key=True,
                serialize=False,
                verbose_name="ID",
            ),
        ),
    ]
