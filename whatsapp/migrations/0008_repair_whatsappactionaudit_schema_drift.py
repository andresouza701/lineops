from django.db import migrations


def _get_columns(connection, table_name):
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table_name)
    return {
        getattr(column, "name", column[0]): column
        for column in description
    }


def _get_constraints(connection, table_name):
    with connection.cursor() as cursor:
        return connection.introspection.get_constraints(cursor, table_name)


def repair_whatsappactionaudit_schema(apps, schema_editor):
    connection = schema_editor.connection
    audit_model = apps.get_model("whatsapp", "WhatsAppActionAudit")
    table_name = audit_model._meta.db_table

    columns = _get_columns(connection, table_name)

    if "meow_instance_id" not in columns:
        schema_editor.add_field(
            audit_model,
            audit_model._meta.get_field("meow_instance"),
        )
        columns = _get_columns(connection, table_name)

    session_column = columns.get("session_id")
    session_field = audit_model._meta.get_field("session")
    if session_column is not None and getattr(session_column, "null_ok", None) is False:
        old_session_field = session_field.clone()
        old_session_field.null = False
        old_session_field.blank = False
        schema_editor.alter_field(
            audit_model,
            old_session_field,
            session_field,
            strict=False,
        )

    for audit in audit_model.objects.filter(
        session__isnull=False,
        meow_instance__isnull=True,
    ).select_related("session"):
        audit.meow_instance_id = audit.session.meow_instance_id
        audit.save(update_fields=["meow_instance"])

    constraints = _get_constraints(connection, table_name)
    if "whatsapp_audit_has_target" not in constraints:
        constraint = next(
            item
            for item in audit_model._meta.constraints
            if item.name == "whatsapp_audit_has_target"
        )
        schema_editor.add_constraint(audit_model, constraint)


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("whatsapp", "0007_whatsappactionaudit_correlation_id_and_more"),
    ]

    operations = [
        migrations.RunPython(repair_whatsappactionaudit_schema, noop_reverse),
    ]
