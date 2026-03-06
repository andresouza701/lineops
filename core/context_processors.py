"""
Context processors para disponibilizar dados globalmente nos templates.
"""

from allocations.models import LineAllocation
from employees.models import Employee
from users.models import SystemUser


def pending_actions_count(request):
    """
    Disponibiliza o contador de pendências de 'Ações do Dia' para ADMINs.

    Conta todos os usuários na fila de ações:
    - Status da linha DIFERENTE de 'Ativo'

    Retorna:
        dict: Dicionário com pending_actions_count (int)
    """
    count = 0

    if request.user.is_authenticated and request.user.role == SystemUser.Role.ADMIN:
        # Buscar employees não deletados
        active_employees = Employee.objects.filter(is_deleted=False)

        pending_count = 0

        for employee in active_employees:
            has_non_active_line = False

            # Case 1: Employee com alocações ativas
            active_allocations = employee.allocations.filter(is_active=True)
            if active_allocations.exists():
                # Verificar se alguma alocação tem status ≠ ACTIVE
                for alloc in active_allocations:
                    if alloc.line_status != LineAllocation.LineStatus.ACTIVE:
                        has_non_active_line = True
                        break
            elif employee.line_status != Employee.LineStatus.ACTIVE:
                has_non_active_line = True

            # Se tem linha não-ativa, contar como pendência
            if has_non_active_line:
                pending_count += 1

        count = pending_count

    return {"pending_actions_count": count}
