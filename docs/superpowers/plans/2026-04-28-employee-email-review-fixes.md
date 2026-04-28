# Plano de Correcao: Employee Email Review Fixes

## Contexto
A feature `Employee.email` adiciona email opcional e unico por negociador ativo, mantendo `corporate_email` como email do supervisor. A revisao tecnica retornou `REQUEST CHANGES` com 1 blocker, 2 warnings e sugestoes adicionais.

## Veredicto Da Revisao
- Status: `REQUEST CHANGES`
- Blocker: `F-1` precisa ser corrigido antes de merge.
- Warnings: `F-2` e `F-3` devem ser resolvidos com contrato explicito e documentacao minima.
- Suggestions: aplicar as seguras e deixar item pre-existente fora do escopo.

## Spec Summary
- `Employee.email` continua opcional.
- Quando preenchido, o email deve ser normalizado com trim/lowercase.
- Quando preenchido, o email deve ser unico entre negociadores ativos (`is_deleted=False`), case-insensitive.
- Negociadores soft-deleted nao bloqueiam reutilizacao do email.
- `corporate_email` continua representando supervisor e nao deve mudar de significado.
- Upload aceita `email` e `employee_email`.

## Gap Analysis
- A constraint `employees_employee_unique_active_email_ci` pode gerar `IntegrityError` em submissao concorrente apos a validacao do form.
- Os views `EmployeeCreateView` e `EmployeeUpdateView` atualmente tratam apenas constraint de nome duplicado.
- Upload com coluna `email` vazia preserva o valor existente, mas esse contrato ainda nao esta documentado/testado.
- `normalize_email_address` retorna string vazia para entrada vazia/None, mas isso nao esta documentado.
- `employee_detail.html` tem badges duplicados para status, um bug visual pre-existente que pode ser corrigido com baixo risco.

## Implementation Plan

### 1. Corrigir blocker de `IntegrityError` por email duplicado
Arquivos:
- `core/integrity.py`
- `employees/views.py`
- `employees/tests.py`

Passos:
- Adicionar constante `DUPLICATE_EMPLOYEE_EMAIL_CONSTRAINT = "employees_employee_unique_active_email_ci"`.
- Adicionar funcao `is_duplicate_employee_email_error(exc: IntegrityError) -> bool`.
- Atualizar `EmployeeCreateView.form_valid` e `EmployeeUpdateView.form_valid`.
- Quando a constraint de email for detectada:
  - `form.add_error("email", "Ja existe um negociador cadastrado com este email.")`
  - `messages.error(self.request, "Corrija os erros do usuario.")`
  - retornar `self.form_invalid(form)`
- Preservar fallback atual de nome duplicado.
- Relevantar exceptions desconhecidas com `raise`.

Testes:
- Create view converte `IntegrityError` da constraint de email em erro de formulario.
- Update view converte `IntegrityError` da constraint de email em erro de formulario.

### 2. Documentar contrato de upload com email vazio
Arquivos:
- `core/services/upload_service.py`
- `core/tests/test_upload_service.py`

Decisao:
- Usar a opcao minima: email vazio no upload preserva o email existente.
- Nao implementar limpeza explicita de email via CSV nesta correcao.

Passos:
- Adicionar comentario curto no trecho de `_upsert_employee`.
- Adicionar teste: update com coluna `email` vazia preserva email existente.
- Adicionar teste: upload com email duplicado para negociador ativo retorna erro no `summary.errors`.

### 3. Documentar contrato de `normalize_email_address`
Arquivo:
- `core/normalization.py`

Passos:
- Adicionar docstring:
  - retorna email normalizado por trim/lowercase
  - retorna `""` para entrada vazia/None
  - callers que persistem em campo nullable devem aplicar `or None`

### 4. Corrigir badges duplicados no detalhe do negociador
Arquivo:
- `templates/employees/employee_detail.html`

Passos:
- Remover os spans duplicados sem icone.
- Manter apenas um badge por status.
- Nao alterar layout fora desse bloco.

### 5. Completar testes importantes
Arquivo:
- `employees/tests.py`

Casos:
- `EmployeeForm` permite manter o mesmo email na mesma instancia.
- `EmployeeAdminForm` permite manter o mesmo email na mesma instancia.
- `EmployeeForm` permite reutilizar email de negociador soft-deleted.
- AJAX retorna `email: ""` quando negociador nao tem email.

## Out Of Scope
- Nao otimizar `EmployeeListView.get_context_data` por avaliacao dupla de queryset. Esse risco e pre-existente.
- Nao implementar limpeza explicita de email via upload sem nova spec.
- Nao renomear `corporate_email`.
- Nao alterar regras de escopo por supervisor/backoffice/gerente.

## Test Checklist
- [ ] Create view trata `IntegrityError` da constraint de email sem 500.
- [ ] Update view trata `IntegrityError` da constraint de email sem 500.
- [ ] Upload com email duplicado reporta erro visivel em `summary.errors`.
- [ ] Upload com email vazio preserva email existente.
- [ ] Form permite manter mesmo email na mesma instancia.
- [ ] Admin form permite manter mesmo email na mesma instancia.
- [ ] Form permite reutilizar email de soft-deleted.
- [ ] AJAX retorna `email: ""` quando vazio.
- [ ] Detail nao renderiza badges duplicados.

## Validation Commands
```powershell
.\venv\Scripts\python.exe manage.py test employees core.tests.test_upload_service
.\venv\Scripts\python.exe manage.py test employees core.tests.test_upload_service allocations config telecom
.\venv\Scripts\python.exe manage.py makemigrations employees --check --dry-run
git diff --check
```

## Known Environment Notes
- `python manage.py test` global sem labels falha por problema pre-existente de descoberta em `dashboard/tests`.
- `makemigrations --check` global aponta migracoes pendentes pre-existentes em `dashboard` e `telecom`.
- `black` nao esta instalado no `venv`; se o agente tiver formatter disponivel, pode rodar apenas nos arquivos tocados.

## Prompt Para Agente Dev
```text
Voce esta no repositorio:
C:\Users\andre.souza\Desktop\lineops-main\lineops-git-Atual-Abril

Objetivo:
Corrigir o review da feature Employee.email. Siga SDD/TDD e implemente somente o escopo abaixo.

Contexto:
Employee.email foi adicionado como email opcional e unico por negociador ativo. corporate_email continua sendo supervisor e nao pode mudar de significado.

Plano aprovado:
1. Corrigir blocker F-1:
   - Em core/integrity.py, adicionar suporte para a constraint employees_employee_unique_active_email_ci.
   - Criar is_duplicate_employee_email_error(exc).
   - Em EmployeeCreateView.form_valid e EmployeeUpdateView.form_valid, tratar IntegrityError de email duplicado como erro no campo email, sem 500.
   - Preservar tratamento atual de nome duplicado.

2. Upload:
   - Manter contrato minimo: coluna email vazia em update preserva email existente.
   - Adicionar comentario no codigo e teste cobrindo esse comportamento.
   - Adicionar teste para upload com email duplicado retornando erro em summary.errors.

3. Normalizacao:
   - Adicionar docstring em normalize_email_address explicando retorno "" para entrada vazia/None e necessidade de or None para campos nullable.

4. Template:
   - Remover badges duplicados em templates/employees/employee_detail.html.

5. Testes complementares:
   - EmployeeForm permite manter o mesmo email na mesma instancia.
   - EmployeeAdminForm permite manter o mesmo email na mesma instancia.
   - EmployeeForm permite reutilizar email de soft-deleted.
   - AJAX retorna email "" quando negociador nao tem email.

Arquivos esperados:
- core/integrity.py
- core/normalization.py
- core/services/upload_service.py
- core/tests/test_upload_service.py
- employees/views.py
- employees/tests.py
- templates/employees/employee_detail.html

Nao fazer:
- Nao renomear corporate_email.
- Nao mudar regras de escopo de supervisor/backoffice/gerente.
- Nao implementar limpeza explicita de email via upload.
- Nao otimizar queryset de EmployeeListView nesta tarefa.

Validacao obrigatoria:
.\venv\Scripts\python.exe manage.py test employees core.tests.test_upload_service
.\venv\Scripts\python.exe manage.py test employees core.tests.test_upload_service allocations config telecom
.\venv\Scripts\python.exe manage.py makemigrations employees --check --dry-run
git diff --check

Observacoes:
- python manage.py test global sem labels falha por problema pre-existente de descoberta em dashboard/tests.
- makemigrations --check global aponta migracoes pendentes pre-existentes em dashboard e telecom.

Ao final, reporte:
- Spec Summary
- Gap Analysis
- Implementation Plan executado
- Test Checklist
- Test Strategy
- Compliance Report
- Arquivos alterados
```
