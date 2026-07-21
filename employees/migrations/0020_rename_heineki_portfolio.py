from django.db import migrations


def rename_heineki_to_heineken(apps, schema_editor):
    employee_model = apps.get_model("employees", "Employee")
    employee_model.objects.filter(employee_id="Heineki").update(
        employee_id="Heineken"
    )


def rename_heineken_to_heineki(apps, schema_editor):
    employee_model = apps.get_model("employees", "Employee")
    employee_model.objects.filter(employee_id="Heineken").update(
        employee_id="Heineki"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("employees", "0019_alter_employee_line_status"),
    ]

    operations = [
        migrations.RunPython(
            rename_heineki_to_heineken,
            reverse_code=rename_heineken_to_heineki,
        ),
    ]
