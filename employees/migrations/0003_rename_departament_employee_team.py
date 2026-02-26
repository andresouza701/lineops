from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("employees", "0002_alter_employee_is_deleted_alter_employee_status_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="employee",
            old_name="department",
            new_name="teams",
        ),
    ]
