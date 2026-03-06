"""
Script para resolver ações antigas não resolvidas em DailyUserAction.

Uso: python manage.py shell < scripts/resolve_old_actions.py
"""

from dashboard.models import DailyUserAction

# Marcar todas as ações não resolvidas como resolvidas
# (limpeza de dados antigos)
old_actions = DailyUserAction.objects.filter(is_resolved=False)

if old_actions.exists():
    count = old_actions.count()
    old_actions.update(is_resolved=True)
    print(f"✓ {count} ação(ões) antiga(s) marcada(s) como resolvida(s)")
else:
    print("✓ Nenhuma ação antiga encontrada")

# Verificar resultado
remaining = DailyUserAction.objects.filter(is_resolved=False).count()
print(f"✓ Ações não resolvidas restantes: {remaining}")
