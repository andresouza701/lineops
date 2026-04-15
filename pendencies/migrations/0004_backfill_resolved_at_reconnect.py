"""
Data migration: backfill resolved_at em pendências RECONNECT_WHATSAPP resolvidas.

Pendências com action=NO_ACTION e resolved_at=NULL existem porque o campo
só passou a ser preenchido após o fix de 2026-04-15. Para cada uma dessas
pendências usa last_action_changed_at como melhor aproximação do momento
real de resolução; se também for NULL, cai para updated_at.

Somente afeta pendências onde last_submitted_action=RECONNECT_WHATSAPP para
não alterar registros que nunca tiveram ação real de reconexão.
"""

from django.db import migrations
from django.db.models import F


def backfill_resolved_at(apps, schema_editor):
    AllocationPendency = apps.get_model("pendencies", "AllocationPendency")

    # Pendências resolvidas (NO_ACTION) sem resolved_at — reconexões
    qs = AllocationPendency.objects.filter(
        action="no_action",
        resolved_at__isnull=True,
        last_submitted_action="reconnect_whatsapp",
    )

    # Prefere last_action_changed_at; cai para updated_at se NULL
    updated = 0
    for pendency in qs.only(
        "pk", "resolved_at", "last_action_changed_at", "updated_at"
    ):
        resolved_at = pendency.last_action_changed_at or pendency.updated_at
        if resolved_at:
            pendency.resolved_at = resolved_at
            pendency.save(update_fields=["resolved_at"])
            updated += 1

    print(f"\n  Backfill resolved_at: {updated} pendência(s) atualizada(s).")


def reverse_backfill(apps, schema_editor):
    # Irreversível por design: não sabemos quais resolved_at eram NULL antes.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("pendencies", "0003_allocationpendency_last_submitted_action"),
    ]

    operations = [
        migrations.RunPython(
            backfill_resolved_at,
            reverse_code=reverse_backfill,
        ),
    ]
