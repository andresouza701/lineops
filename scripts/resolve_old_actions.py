"""
Script para resolver ações antigas não resolvidas em DailyUserAction.

Uso: python manage.py shell < scripts/resolve_old_actions.py

Delega a logica para telecom.daily_action_audit.resolve_old_daily_user_actions,
que resolve uma linha por vez (lock + snapshot + evento RESOLVED), nunca em
bulk, para que cada resolucao fique auditada em LineDailyActionAuditEvent.
"""

from dashboard.models import DailyUserAction
from telecom.daily_action_audit import resolve_old_daily_user_actions

count = resolve_old_daily_user_actions()

if count:
    print(f"✓ {count} ação(ões) antiga(s) marcada(s) como resolvida(s)")
else:
    print("✓ Nenhuma ação antiga encontrada")

# Verificar resultado
remaining = DailyUserAction.objects.filter(is_resolved=False).count()
print(f"✓ Ações não resolvidas restantes: {remaining}")
