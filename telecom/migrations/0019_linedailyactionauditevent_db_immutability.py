from django.db import migrations

TABLE = "telecom_linedailyactionauditevent"

CREATE_BLOCK_DELETE_FN = f"""
CREATE OR REPLACE FUNCTION telecom_ldaae_block_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'Eventos de auditoria sao imutaveis: DELETE bloqueado (id=%)', OLD.id;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

CREATE_DELETE_TRIGGER = f"""
CREATE TRIGGER telecom_ldaae_no_delete
BEFORE DELETE ON {TABLE}
FOR EACH ROW EXECUTE FUNCTION telecom_ldaae_block_delete();
"""

# Todo campo de conteudo/identidade e imutavel. Apenas as 4 FKs operacionais
# podem transicionar de um valor preenchido para NULL (retencao apos
# exclusao fisica via SET_NULL); nunca para outro id, nunca de volta.
CREATE_BLOCK_UPDATE_FN = f"""
CREATE OR REPLACE FUNCTION telecom_ldaae_block_update() RETURNS trigger AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.event_type IS DISTINCT FROM OLD.event_type
       OR NEW.source IS DISTINCT FROM OLD.source
       OR NEW.source_object_id IS DISTINCT FROM OLD.source_object_id
       OR NEW.operation_id IS DISTINCT FROM OLD.operation_id
       OR NEW.payload_version IS DISTINCT FROM OLD.payload_version
       OR NEW.occurred_at IS DISTINCT FROM OLD.occurred_at
       OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at
       OR NEW.phone_number_snapshot IS DISTINCT FROM OLD.phone_number_snapshot
       OR NEW.allocation_id_snapshot IS DISTINCT FROM OLD.allocation_id_snapshot
       OR NEW.employee_name_snapshot IS DISTINCT FROM OLD.employee_name_snapshot
       OR NEW.performed_by_name_snapshot IS DISTINCT FROM OLD.performed_by_name_snapshot
       OR NEW.performed_by_email_snapshot IS DISTINCT FROM OLD.performed_by_email_snapshot
       OR NEW.before_state IS DISTINCT FROM OLD.before_state
       OR NEW.after_state IS DISTINCT FROM OLD.after_state
    THEN
        RAISE EXCEPTION
            'Eventos de auditoria sao imutaveis: apenas SET NULL de FK e permitido (id=%)',
            OLD.id;
    END IF;

    IF NEW.phone_line_id IS DISTINCT FROM OLD.phone_line_id
       AND NEW.phone_line_id IS NOT NULL THEN
        RAISE EXCEPTION
            'Eventos de auditoria: phone_line so pode ser definido como NULL (id=%)',
            OLD.id;
    END IF;
    IF NEW.allocation_id IS DISTINCT FROM OLD.allocation_id
       AND NEW.allocation_id IS NOT NULL THEN
        RAISE EXCEPTION
            'Eventos de auditoria: allocation so pode ser definido como NULL (id=%)',
            OLD.id;
    END IF;
    IF NEW.employee_id IS DISTINCT FROM OLD.employee_id
       AND NEW.employee_id IS NOT NULL THEN
        RAISE EXCEPTION
            'Eventos de auditoria: employee so pode ser definido como NULL (id=%)',
            OLD.id;
    END IF;
    IF NEW.performed_by_id IS DISTINCT FROM OLD.performed_by_id
       AND NEW.performed_by_id IS NOT NULL THEN
        RAISE EXCEPTION
            'Eventos de auditoria: performed_by so pode ser definido como NULL (id=%)',
            OLD.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

CREATE_UPDATE_TRIGGER = f"""
CREATE TRIGGER telecom_ldaae_no_mutate
BEFORE UPDATE ON {TABLE}
FOR EACH ROW EXECUTE FUNCTION telecom_ldaae_block_update();
"""

DROP_DELETE_TRIGGER = f"DROP TRIGGER IF EXISTS telecom_ldaae_no_delete ON {TABLE};"
DROP_DELETE_FN = "DROP FUNCTION IF EXISTS telecom_ldaae_block_delete();"
DROP_UPDATE_TRIGGER = f"DROP TRIGGER IF EXISTS telecom_ldaae_no_mutate ON {TABLE};"
DROP_UPDATE_FN = "DROP FUNCTION IF EXISTS telecom_ldaae_block_update();"


def create_triggers(apps, schema_editor):
    # Protecao DB-level so existe/faz sentido em Postgres (producao). A
    # suite local roda em SQLite (manage.py test forca esse backend), entao
    # esta migration deve ser no-op seguro la.
    if schema_editor.connection.vendor != "postgresql":
        return
    # params=None: sql cru, sem tentativa de bind de parametros. As funcoes
    # PL/pgSQL usam `%` em RAISE EXCEPTION (format specifier do Postgres),
    # que colide com o placeholder `%s` do DB-API se schema_editor.execute()
    # receber o default params=() — psycopg tenta interpolar e quebra com
    # "tuple index out of range".
    schema_editor.execute(CREATE_BLOCK_DELETE_FN, params=None)
    schema_editor.execute(CREATE_DELETE_TRIGGER, params=None)
    schema_editor.execute(CREATE_BLOCK_UPDATE_FN, params=None)
    schema_editor.execute(CREATE_UPDATE_TRIGGER, params=None)


def drop_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(DROP_DELETE_TRIGGER, params=None)
    schema_editor.execute(DROP_DELETE_FN, params=None)
    schema_editor.execute(DROP_UPDATE_TRIGGER, params=None)
    schema_editor.execute(DROP_UPDATE_FN, params=None)


class Migration(migrations.Migration):
    """Protecao DB-level (Postgres) contra DELETE e UPDATE de conteudo em
    LineDailyActionAuditEvent. Complementa o guard de aplicacao (manager
    customizado) para o caso de acesso direto ao banco fora do ORM.

    Nao bloqueia o SET_NULL de FK do proprio Django (retencao apos exclusao
    fisica de phone_line/allocation/employee/performed_by): a trigger de
    UPDATE permite explicitamente a transicao de qualquer uma dessas 4 FKs
    de um valor preenchido para NULL.
    """

    dependencies = [
        ("telecom", "0018_linedailyactionauditevent_source_line_allocation"),
    ]

    operations = [
        migrations.RunPython(create_triggers, drop_triggers),
    ]
