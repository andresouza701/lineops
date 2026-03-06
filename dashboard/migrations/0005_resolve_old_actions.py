"""
Migration para resolver todas as ações antigas não resolvidas.
"""

from django.db import migrations


def resolve_old_actions(apps, schema_editor):
    """Marca todas as ações não resolvidas como resolvidas."""
    DailyUserAction = apps.get_model("dashboard", "DailyUserAction")
    count = DailyUserAction.objects.filter(is_resolved=False).update(is_resolved=True)
    if count > 0:
        print(f"\n✓ {count} ação(ões) marcada(s) como resolvida(s)")


def reverse_resolve(apps, schema_editor):
    """Reverse não faz nada - apenas mantém o estado."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0004_alter_dailyuseraction_unique_together_and_more"),
    ]

    operations = [
        migrations.RunPython(resolve_old_actions, reverse_resolve),
    ]
