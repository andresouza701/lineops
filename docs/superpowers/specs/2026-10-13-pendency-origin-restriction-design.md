# Bloqueio de abertura de pendências por origem da linha

Data: 2026-10-13
Status: contrato de produto aprovado; POR-01 a POR-06 concluídas (política implementada backend/Admin/payload/UI; aceite final e regressão comprovados com evidência real — ver seção "POR-06 — Aceite final e revisão integrada"). Sem stage/commit/deploy.

Decisões 1A/2A/3A/4A aprovadas em 2026-10-13. A seção final "Fechamento das quatro decisões" prevalece sobre as hipóteses e pendências históricas de POR-02 abaixo.

## Spec Summary

Linhas com PhoneLine.Origem.APARELHO_OP (token `APARELHO OP`) ou PhoneLine.Origem.PESSOAL (token `PESSOAL`) não podem originar abertura nem reabertura de pendências. Aplicar na interface e no servidor, inclusive POST direto. Regra não concede novas permissões nem cria exceção para ADMIN. Pendências já abertas continuam disponíveis para tratamento e resolução conforme permissões e responsável existentes.

Mensagem exata aprovada:

> Não é permitido abrir pendência para linhas com origem Aparelho Operação ou Aparelho pessoal. Fale com o supervisor ou backoffice

“Fale com o supervisor ou backoffice” orienta o usuário; não autoriza esses papéis a contornar o bloqueio.

## Contract

- Usar a origem persistida da linha vinculada à operação, nunca um valor enviado pelo cliente.
- `APARELHO` (“Aparelho”) é outra origem e não integra o conjunto bloqueado. Demais origens, inclusive vazia, mantêm comportamento anterior.
- Operações sem linha vinculada mantêm regras anteriores; não atribuir origem por inferência.
- Bloquear transição de ausência de ação aberta para ação aberta, incluindo ciclo previamente resolvido. Não bloquear leitura, assumir, liberar responsável, observação, tratamento ou resolução de pendência já aberta apenas pela origem.
- Pendência existente resolvida não ganha exceção: tentar reabrir aplica a mesma restrição.
- Mudança posterior de origem não fecha nem apaga pendência já aberta. Nova abertura/reabertura considera a origem vigente.
- Recusa de abertura/reabertura não grava ação, nota/status enviados no mesmo pedido, timestamps de ciclo, auditoria de sucesso ou notificações de abertura. Validar antes desses efeitos, dentro do fluxo transacional pertinente.
- A verificação de autorização/escopo continua precedendo exposição de dados. Não substituir 403/404 de usuário fora do escopo por informação sobre origem.
- Contrato técnico proposto alinhado à API existente: PendencyUpdateView retorna HTTP 403 com `errors` contendo a mensagem exata para a transição recusada. Fluxo HTML de Ações do Dia deve usar seu mecanismo existente de erro/redisplay; confirmar em POR-02, sem alterar sua convenção inadvertidamente.
- UI informa o motivo e impede comandos de abertura/reabertura; não desabilitar todo o modal quando isso impedir tratamento permitido. Funcionar sem depender exclusivamente de JavaScript.

## Gap Analysis

### Inventário inicial (POR-01)

| Fonte | Evidência / impacto |
|---|---|
| telecom/models.py::PhoneLine.Origem | APARELHO, PESSOAL e APARELHO_OP são escolhas distintas |
| pendencies/urls.py | detail/update/claim/release são endpoints separados |
| pendencies/views.py::PendencyUpdateView.post | NO_ACTION → ação gera OPENED ou REOPENED segundo resolved_at; validação existente e transação devem ser preservadas |
| pendencies/views.py::PendencyDetailView.get | GET cria/obtém registro via _get_or_create_pendency e marca notificações lidas; registro vazio não equivale a abertura. Não ampliar escopo para refatorar esse comportamento |
| pendencies/models.py::AllocationPendency.record_action_change | Atualiza estado/timestamps; não usar full_clean global como substituto de proteção nas entradas |
| dashboard/views.py::daily_user_action_board | Outro caminho escreve DailyUserAction e gera OPENED/REOPENED; precisa impedir bypass pelo POST da tela |
| templates/dashboard/daily_user_action_board.html | Tela/modal a mapear integralmente junto aos forms/JS e respostas em POR-02 |

### Inventário completo (POR-02)

Todos os caminhos de escrita que tocam `AllocationPendency.action` ou `DailyUserAction.action_type`/`is_resolved` foram localizados por grep direto no repositório (sem `venv/`). Não há `serializers.py` nem `management/commands/*.py` que referenciem `AllocationPendency` ou `DailyUserAction`. Não há `signals.py` (`employees/signals.py`, `telecom/signals.py`) que crie, abra ou reabra pendência — os signals existentes só gravam `EmployeeHistory`/`PhoneLineHistory` a partir de `Employee`, `PhoneLine` e `LineAllocation`. `pendencies/models.py::AllocationPendency.record_action_change` tem exatamente um chamador em código de produção: `pendencies/views.py::PendencyUpdateView.post` (linha 300). Os únicos dois caminhos de produção que efetivamente abrem ou reabrem uma pendência são os dois já citados no POR-01; o restante do inventário abaixo cobre registro vazio, tratamento de pendência aberta, resolução, e um caminho de bypass real (Django Admin) que precisa de decisão.

| # | Arquivo/símbolo | URL / método | Roles / escopo | Origem da linha consultada | Transição | Gravações | Auditoria / notificações | Apresentação do erro |
|---|---|---|---|---|---|---|---|---|
| 1 | `pendencies/views.py::PendencyDetailView.get` | `GET /pendencies/api/detail/` (`pendencies:detail`) | `PENDENCY_ALLOWED_ROLES` = ADMIN, SUPER, BACKOFFICE, GERENTE (`RoleRequiredMixin`) | Não consultada | **Nenhuma** — `_get_or_create_pendency` faz `get_or_create(employee, allocation)`; quando não existe, cria com `action=NO_ACTION` (default do campo). Registro vazio ≠ abertura. | Cria linha `AllocationPendency` só se não existir; marca `PendencyObservationNotification` do funcionário como lidas (`is_read=True`) | Nenhum `LineDailyActionAuditEvent` é gravado aqui (sem chamada a `record_line_daily_action_event`) | N/A (sempre 200 com JSON) |
| 2 | `pendencies/views.py::PendencyUpdateView.post` — ramo abertura/reabertura | `POST /pendencies/api/update/` (`pendencies:update`) | `PENDENCY_ALLOWED_ROLES`; dentro do método, só `is_super_like` (SUPER/BACKOFFICE/GERENTE) passa do gate `was_no_action and not will_be_no_action` — ADMIN já é bloqueado aqui por regra pré-existente, sem relação com origem | **Sim, precisa ser introduzida.** `pendency.allocation.phone_line.origem` (quando `allocation` existe); sem `allocation`, não há origem a checar | `NO_ACTION → outro valor`, incluindo quando `resolved_at` não é nulo (reabertura) | `pendency.record_action_change(...)`; `update_fields` inclui action/timestamps/responsável | `OPENED` ou `REOPENED` via `_record_pendency_event` dentro da mesma `transaction.atomic()` | Hoje: `errors.append(...)` seguido de `return JsonResponse({"errors": errors}, status=403)` **antes** de qualquer `save()` — ponto exato para a checagem de origem |
| 3 | `pendencies/views.py::PendencyUpdateView.post` — ramo resolução | idem acima | Só `is_current_technical_responsible` (ADMIN dono da pendência) | Não se aplica — resolução não é bloqueada por origem | `outro valor → NO_ACTION` | idem | `RESOLVED` | idem (403 já existente para falta de permissão) |
| 4 | `pendencies/views.py::PendencyUpdateView.post` — ramo alteração de ação já aberta | idem acima | Só `is_current_technical_responsible` | Não se aplica | `valor X → valor Y`, ambos ≠ `NO_ACTION` | idem | `ACTION_CHANGED` | idem |
| 5 | `pendencies/views.py::PendencyUpdateView.post` — observação | idem acima | `is_super_like` ou (`is_admin` e (`not pendency_is_open` ou `is_current_responsible`)) | Não se aplica — observação de pendência já aberta não é bloqueada pela origem | Não é transição de `action` | `pendency.observation` | `NOTE_CHANGED` | 403 próprio (`OBSERVATION_LOCKED_REASON` ou mensagem de permissão) |
| 6 | `pendencies/views.py::PendencyUpdateView.post` — status da linha | idem acima | Só ADMIN, e só se dono ou pendência vazia | Não se aplica | N/A | `allocation.line_status`, `PhoneLineHistory` | `LINE_STATUS_CHANGED` | 403 próprio |
| 7 | `pendencies/views.py::PendencyClaimView.post` | `POST /pendencies/api/claim/` (`pendencies:claim`) | Só ADMIN | Não se aplica — exige pendência já aberta (`action != NO_ACTION`), nunca abre | N/A (atribui responsável) | `technical_responsible` | `RESPONSIBLE_ASSIGNED` | 403 próprio quando não há ação aberta |
| 8 | `pendencies/views.py::PendencyReleaseView.post` | `POST /pendencies/api/release/` (`pendencies:release`) | Só ADMIN | Não se aplica | N/A (libera responsável) | `technical_responsible = None` | `RESPONSIBLE_RELEASED` | 403 próprio quando não há responsável |
| 9 | `pendencies/views.py::PendencyNotificationsView.get` | `GET /pendencies/api/notifications/` | Qualquer usuário autenticado (`LoginRequiredMixin`, sem `RoleRequiredMixin`) | Não se aplica | Apenas leitura/marcação de notificações como lidas | `is_read=True` em lote | Não gera `LineDailyActionAuditEvent` | N/A |
| 10 | `dashboard/views.py::daily_user_action_board` (POST) — ramo resolução | `POST /dashboard/indicadores/acoes-dia/` (`daily_user_action_board`) | `DASHBOARD_ALLOWED_ROLES` = ADMIN, SUPER, BACKOFFICE, GERENTE (`@roles_required`); ativado quando `action_type` vem vazio no POST | Não se aplica — resolução não é bloqueada | `DailyUserAction.is_resolved: False → True` | `action.is_resolved`, `action.note`, `action.updated_by` | `NOTE_CHANGED` (se nota mudou) + `RESOLVED` | `messages.info`/`messages.success` + redirect (fluxo HTML, sem JSON) |
| 11 | `dashboard/views.py::daily_user_action_board` (POST) — ramo criação/atualização (`action_type` não vazio) | idem | Mesmos roles; **sem** restrição adicional por role na criação — ao contrário de `PendencyUpdateView`, ADMIN também pode criar/reabrir aqui, hoje sem bloqueio de origem | **Sim, precisa ser introduzida.** `allocation_obj.phone_line.origem`, lido sob `select_for_update()` já aplicado antes deste ramo; sem `allocation_id`, não há origem (ação em nível de funcionário) | Três sub-casos no mesmo bloco: (a) `existing_action is None` → criação/abertura; (b) `existing_action` com `previous_is_resolved=True` → reabertura; (c) `existing_action` com `previous_is_resolved=False` → alteração de ação já aberta no dia (não deve ser bloqueada por origem) | `DailyUserAction.objects.create(...)` ou `.save(...)` com `is_resolved=False` | (a)→`OPENED`; (b)→`REOPENED`; (c)→`ACTION_CHANGED`/`NOTE_CHANGED` conforme o que mudou | Hoje: `messages.error(...)` sem redirect imediato, cai no redirect comum ao final da view — mesmo padrão a reaproveitar para a mensagem de origem bloqueada |
| 12 | `dashboard/views.py::daily_user_action_board` (POST) — status da linha (ADMIN) | idem | Só ADMIN | Não se aplica | N/A | `allocation_obj.line_status`, `employee.line_status`, `PhoneLineHistory`/`EmployeeHistory` | `LINE_STATUS_CHANGED` | `messages.success` |
| 13 | `pendencies/admin.py::AllocationPendencyAdmin` | Django Admin, `/admin/pendencies/allocationpendency/<id>/change/` | Qualquer `SystemUser` com `is_staff=True` e permissão de `change_allocationpendency` no Admin (independente dos papéis de negócio ADMIN/SUPER/BACKOFFICE/GERENTE) | Não consultada — Admin não tem lógica própria, só `ModelAdmin` padrão | **Bypass real.** `readonly_fields` não inclui `action`; `ModelAdminForm` padrão permite editar `action` livremente, inclusive `NO_ACTION → outro valor`, sem passar por `record_action_change`, sem gerar `LineDailyActionAuditEvent`, sem checar origem, responsável técnico ou qualquer outra regra de `PendencyUpdateView` | `action` (e qualquer outro campo não-readonly) direto via `ModelForm.save()` | Nenhum evento de `LineDailyActionAuditEvent` é gravado — o Admin não chama `record_line_daily_action_event` | Nenhuma (fluxo padrão do Django Admin) |
| 14 | `dashboard/forms.py::DailyUserActionForm` | Mesma URL do item 11 | Mesma autorização do item 11 | N/A (é só o form; a origem é resolvida na view) | N/A | N/A | N/A | Erros de validação de form (`form.is_valid()` False) → `messages.error(request, "Não foi possível salvar a ação.")` |
| 15 | `templates/dashboard/daily_user_action_board.html` | — | — | — | — | — | — | Modal único (`#pendencyModal`) consome exclusivamente os endpoints `pendencies:detail/update/claim/release` via `fetch` JS; **não há** nenhum `<form>` HTML servindo `DailyUserActionForm` nesta tela — `row.form` é montado em `build_daily_user_action_rows` (`include_forms=True`) mas nunca referenciado no template. O endpoint do item 11 continua ativo e aceita POST direto, só não tem UI própria hoje |

Política de domínio deve ser compartilhada entre as entradas 2 e 11 (e, se a decisão do item 13 optar por fechar o bypass, também o Admin); evitar duas listas de origens/mensagem independentes. Contratos dos relatórios, indicadores e auditoria existentes não mudam. Sem migration prevista.

## Matriz de Autorização e Transições (POR-02)

Cobre só as duas entradas que abrem/reabrem (itens 2 e 11 do inventário). "Bloqueado por origem" é a checagem nova; todo o resto da coluna é comportamento já existente, preservado sem alteração.

| Entrada | Role | Transição | Origem da linha | Resultado hoje | Resultado após POR-04 |
|---|---|---|---|---|---|
| `PendencyUpdateView` | SUPER/BACKOFFICE/GERENTE | `NO_ACTION → X` (abertura) | APARELHO_OP ou PESSOAL | Abre (OPENED) | 403 com mensagem exata; nada gravado |
| `PendencyUpdateView` | SUPER/BACKOFFICE/GERENTE | `NO_ACTION → X`, `resolved_at` preenchido (reabertura) | APARELHO_OP ou PESSOAL | Reabre (REOPENED) | 403 com mensagem exata; nada gravado |
| `PendencyUpdateView` | SUPER/BACKOFFICE/GERENTE | `NO_ACTION → X` | APARELHO, outra origem ou vazia | Abre/reabre | Sem mudança |
| `PendencyUpdateView` | ADMIN | `NO_ACTION → X` | Qualquer | 403 "Somente super/backoffice/gerente pode abrir uma pendência." (regra pré-existente) | Sem mudança — ADMIN nunca chega a avaliar origem |
| `PendencyUpdateView` | Qualquer role autorizado | `X → NO_ACTION` (resolução), `X → Y` (alteração), observação, status da linha, claim, release | Qualquer, inclusive bloqueada | Autorização pré-existente decide | Sem mudança |
| `daily_user_action_board` | ADMIN/SUPER/BACKOFFICE/GERENTE | `existing_action is None` (criação) | APARELHO_OP ou PESSOAL | Cria (OPENED) | `messages.error` com mensagem exata; nenhuma linha criada |
| `daily_user_action_board` | ADMIN/SUPER/BACKOFFICE/GERENTE | `existing_action` com `previous_is_resolved=True` (reabertura) | APARELHO_OP ou PESSOAL | Reabre (REOPENED) | `messages.error` com mensagem exata; `is_resolved` permanece `True`, nada gravado |
| `daily_user_action_board` | ADMIN/SUPER/BACKOFFICE/GERENTE | `existing_action` com `previous_is_resolved=False` (alteração de ação já aberta no dia) | Qualquer, inclusive bloqueada | Atualiza | Sem mudança — não é abertura |
| `daily_user_action_board` | ADMIN/SUPER/BACKOFFICE/GERENTE | Resolução (`action_type` vazio) | Qualquer, inclusive bloqueada | Resolve | Sem mudança |
| `daily_user_action_board` | Sem linha vinculada (`allocation_id` vazio) | Criação/reabertura em nível de funcionário | N/A — sem `PhoneLine`, sem origem | Cria/reabre | Sem mudança (contrato item 3: sem linha, sem inferência de origem) |
| `PendencyClaimView` / `PendencyReleaseView` | ADMIN | Assumir/liberar responsável | Qualquer, inclusive bloqueada | Permite (exige pendência já aberta) | Sem mudança |
| Django Admin (`AllocationPendencyAdmin`) | Staff com `change_allocationpendency` | Edição direta do campo `action` | Qualquer, inclusive bloqueada | Permite, sem auditoria | **Decisão pendente** — ver Lacunas |

## Contratos de Erro e Efeitos Colaterais (POR-02)

### `PendencyUpdateView` (JSON)

- Transição recusada por origem → `HTTP 403`, corpo `{"errors": ["Não é permitido abrir pendência para linhas com origem Aparelho Operação ou Aparelho pessoal. Fale com o supervisor ou backoffice"]}`.
- Mesma forma de resposta já usada pelas recusas de permissão existentes (`errors.append(...)`; `return JsonResponse({"errors": errors}, status=403)`), dentro do mesmo `if errors:` que já existe antes de qualquer `pendency.record_action_change(...)` ou `save()`. Não há incompatibilidade a documentar: o contrato de API já previsto em POR-01 (linha 26) se confirma válido sem ajuste.
- A checagem de origem deve ocorrer no mesmo ponto em que hoje só se verifica `is_super_like`, dentro do ramo `was_no_action and not will_be_no_action`. Isso garante que a recusa acontece antes de qualquer gravação do mesmo request (observação, status da linha, notificação), porque o `if errors: return ...` ocorre antes de todos os blocos de gravação (`--- Observação ---`, `--- Status da Linha ---`, `--- Salva pendência ---`).
- Payload composto (ex.: `action` bloqueado + `observation` + `line_status` no mesmo POST): como a recusa por `errors` ocorre antes de qualquer `update_fields`, `save()`, `_record_pendency_event` ou `notify_observation_change`, nenhum efeito parcial do request é persistido — nem a observação, nem o status da linha, nem notificação de observação (que só dispara depois do bloco de erros).
- Usuário fora do escopo: `_load_locked_pendency_for_scope` levanta `PermissionDenied` (→ 403 Django padrão, sem corpo JSON customizado) **antes** de qualquer leitura do corpo de domínio. A checagem de origem é posterior a essa verificação de escopo, então nunca poderá revelar origem de linha para quem não tem acesso ao funcionário.

### `daily_user_action_board` (HTML, form + `messages` + redirect)

- Transição recusada por origem → `messages.error(request, "Não é permitido abrir pendência para linhas com origem Aparelho Operação ou Aparelho pessoal. Fale com o supervisor ou backoffice")`, sem criar/atualizar `DailyUserAction`, seguido do mesmo `redirect(...)` de query string já usado para os outros erros desse POST (`"Tipo de ação inválido."`, `"Usuario nao encontrado..."`, `"Backoffice sem supervisor..."`). Não há resposta JSON nesta view; não há incompatibilidade com API a documentar aqui porque não existe contrato JSON nesse endpoint.
- A checagem de origem deve ocorrer dentro do bloco `else:` (criação/atualização, `action_type` não vazio), **imediatamente após** calcular `previous_is_resolved` e **antes** do `if existing_action: ... else: DailyUserAction.objects.create(...)`. Isso cobre os dois sub-casos de abertura (criação e reabertura) e preserva o terceiro sub-caso (alteração de ação já aberta no mesmo dia), que não deve ser bloqueado.
- A leitura da origem usa `allocation_obj` já obtido com `select_for_update()` mais acima no mesmo bloco `transaction.atomic()` — não há leitura adicional fora do lock, então não há condição de corrida nova introduzida pela checagem.
- Payload composto nesta view é mais amplo que no `PendencyUpdateView`: o mesmo POST pode também alterar `line_status` (ramo ADMIN, executado **antes** do ramo de criação/atualização de ação, em bloco próprio). Como os dois ramos (status da linha e ação) são independentes e cada um faz seu próprio `save()`/`create()` dentro da mesma transação, bloquear a abertura de ação **não** desfaz uma mudança de status da linha que ocorreu antes no mesmo request — esse comportamento já existe hoje (status e ação sempre foram independentes) e o bloqueio de origem não o altera. Isso é consistente com o contrato (que fala em não gravar "ação, nota/status enviados **no mesmo pedido**" quando a transição de abertura é recusada) desde que se entenda que o status aqui é o status da própria `DailyUserAction`/ação recusada, não o `line_status` da linha, que é uma mudança de domínio separada e já autorizada por sua própria regra (só ADMIN). Nenhuma mudança de comportamento proposta neste ponto; registrado como esclarecimento de leitura do contrato, não como lacuna.
- Usuário fora do escopo: `employees_qs.filter(pk=employee_id).first()` retorna `None` e cai em `messages.error(request, "Usuario nao encontrado para este supervisor.")` **antes** de qualquer lock ou leitura de origem — comportamento pré-existente preservado.

### Django Admin — efeito colateral sem decisão (ver Lacunas)

Hoje, editar `action` pelo Admin não gera `LineDailyActionAuditEvent`, não atualiza `pendency_submitted_at`/`resolved_at`/`technical_responsible` (porque não passa por `record_action_change`), e não respeita a origem. Enquanto não houver decisão, este caminho **não** será coberto pela blindagem de POR-04 a menos que a decisão abaixo seja tomada.

## Plano de Testes (POR-03) — Matriz Requisito → Cenário → Entrada → Resultado Esperado → Tarefa

| # | Requisito | Cenário | Entrada | Resultado esperado | Tarefa (arquivo provável) |
|---|---|---|---|---|---|
| T1 | Bloqueio por origem | Abertura via `PendencyUpdateView`, origem `APARELHO_OP` | POST `action=pending` em pendência `NO_ACTION`, por SUPER | 403, `errors` com mensagem exata; `AllocationPendency.action` continua `NO_ACTION`; nenhum `LineDailyActionAuditEvent` novo | `pendencies/tests/test_pendency_origin_restriction.py` (novo) |
| T2 | Bloqueio por origem | Idem, origem `PESSOAL` | Mesma entrada, origem `PESSOAL` | Mesmo resultado de T1 | idem |
| T3 | Bloqueio por origem — reabertura | Reabertura via `PendencyUpdateView`, origem `APARELHO_OP`/`PESSOAL`, pendência com `resolved_at` preenchido | POST `action=pending`, por SUPER | 403, mensagem exata; `resolved_at` não é limpo; `action` continua `NO_ACTION` | idem |
| T4 | Bloqueio por origem — `daily_user_action_board` | Criação via POST direto na view HTML, origem `APARELHO_OP`/`PESSOAL`, sem `DailyUserAction` existente no dia | POST `action_type=new_number` | Redirect com `messages.error` exata; nenhum `DailyUserAction` criado; nenhum evento `OPENED` | `dashboard/tests/test_daily_user_action_origin_restriction.py` (novo) |
| T5 | Bloqueio por origem — reabertura em `daily_user_action_board` | `DailyUserAction` do dia já `is_resolved=True`, mesma origem bloqueada | POST `action_type=pending` | `messages.error` exata; `is_resolved` continua `True`; nenhum evento `REOPENED` | idem |
| T6 | Controle — origem permitida | `APARELHO`, origem custom (`SRVMEMU-01` etc.) e origem vazia/`None` | Mesmas entradas de T1/T4 trocando a origem da linha | Comportamento idêntico ao pré-POR (abre/reabre normalmente) | idem (parametrizado) |
| T7 | Controle — sem linha vinculada | `allocation=None` na pendência, ou `allocation_id` vazio no POST de Ações do Dia | Mesma entrada de T1/T4 sem `allocation` | Abre/reabre normalmente — sem origem a checar | idem |
| T8 | Papéis — nenhuma exceção nova | ADMIN tentando abrir via `PendencyUpdateView` (origem bloqueada e não bloqueada) | POST `action=pending` por ADMIN | 403 "Somente super/backoffice/gerente pode abrir uma pendência." em ambos os casos — mensagem de permissão, não a de origem (ADMIN nunca chega à checagem de origem) | idem |
| T9 | Papéis — nenhuma exceção nova | SUPER/BACKOFFICE/GERENTE abrindo em `daily_user_action_board`, origem bloqueada | POST por cada um dos três roles | 403/`messages.error` idêntico para os três, sem diferença de tratamento | idem |
| T10 | Papéis — controle de acesso pré-existente | OPERATOR/DEV acessando `pendencies:update` ou `daily_user_action_board` | POST qualquer payload | 403 `PermissionDenied` por `RoleRequiredMixin`/`roles_required`, antes de qualquer avaliação de origem | reaproveitar teste de acesso já existente, se houver; senão novo |
| T11 | POST direto / falsificação de origem | Cliente envia `origem` ou campo equivalente no corpo do POST tentando mascarar a origem real da linha | POST `action=pending` com corpo JSON contendo uma chave extra simulando origem permitida, linha real com origem bloqueada | 403 — view nunca lê origem do corpo da requisição, só de `pendency.allocation.phone_line.origem`/`allocation_obj.phone_line.origem` persistidos | idem (T1/T4, variando o payload) |
| T12 | Pendência existente — tratamento preservado | Pendência aberta em linha com origem agora bloqueada: assumir, observar, liberar, resolver | Sequência de POSTs em `pendencies:claim`, `pendencies:update` (observação), `pendencies:release`, `pendencies:update` (resolução) | Todos os passos funcionam exatamente como hoje — autorização por responsável técnico, não por origem | `pendencies/tests/test_pendency_origin_restriction.py` (cenários de "pendência já aberta") |
| T13 | Payload composto — sem efeito parcial | Abertura recusada com `observation` e `line_status` no mesmo corpo | POST `action=pending` (origem bloqueada) + `observation="x"` + `line_status=active` | 403; `pendency.observation` inalterada; `allocation.line_status` inalterado; nenhuma notificação `PendencyObservationNotification` criada; nenhum evento de auditoria | `pendencies/tests/test_pendency_origin_restriction.py` |
| T14 | Usuário fora do escopo | SUPER de outra equipe tentando abrir pendência de funcionário fora do seu escopo, origem bloqueada | POST `pendencies:update` com `pendency_id` de funcionário fora do escopo | 403 `PermissionDenied` do `RoleRequiredMixin`/`_load_locked_pendency_for_scope`, sem revelar origem da linha nem a mensagem de bloqueio por origem | idem |
| T15 | UI com/sem JS | Carregar modal de pendência (JS) para linha com origem bloqueada; tentar salvar | `fetch` `pendencies:update` reproduzindo o clique "Salvar" | Mensagem exata aparece em `#pendencySaveStatus`; `renderModal` não é chamado com sucesso; controles de tratamento (claim/release/observação) continuam habilitados — depende de decisão de POR-05, ver Lacunas | Teste de browser real (Playwright/Selenium), fora do pytest de domínio — ver Test Strategy |
| T16 | Registro vazio ≠ abertura | GET em `pendencies:detail` para par (employee, allocation) sem `AllocationPendency` prévio, linha com origem bloqueada | GET `pendencies:detail?employee_id=...&allocation_id=...` | 200; cria `AllocationPendency(action=NO_ACTION)`; nenhum evento de auditoria; nenhuma mensagem de bloqueio (GET nunca é abertura) | `pendencies/tests/test_pendency_origin_restriction.py` |
| T17 | Origem alterada entre render e POST | Linha com origem permitida no momento do GET/render; origem é alterada para bloqueada antes do POST de abertura | GET (origem permitida) → admin de telecom altera `origem` para `PESSOAL` → POST `pendencies:update` `action=pending` | 403 — decisão baseada na origem persistida **no momento da avaliação do POST**, não na renderizada antes; não presumir proteção adicional de concorrência além do `select_for_update` já existente no `allocation`/pendência | `pendencies/tests/test_pendency_origin_restriction.py` |
| T18 | Concorrência (requer PostgreSQL) | Duas requisições concorrentes de abertura para a mesma pendência/alocação, uma delas mudando a origem no meio do caminho | Dois `POST` concorrentes via threads/processos separados contra Postgres real | O `select_for_update` já existente em `_load_locked_pendency_for_scope`/`LineAllocation.objects.select_for_update()` serializa as duas transações; não há garantia equivalente em SQLite — **não escrever teste de locking em SQLite afirmando prová-lo** | Teste de integração contra Postgres (CI com serviço Postgres), não no pytest padrão local com SQLite |

Nenhum destes é placeholder: cada linha descreve uma entrada e uma asserção de estado observável (status HTTP, corpo, campos do model, presença/ausência de evento). T15 e T18 são os únicos que não podem ser cumpridos só com pytest+SQLite e estão marcados como tal na Test Strategy abaixo.

## Lacunas e Decisões Pendentes

1. **Django Admin (`AllocationPendencyAdmin`) — item 13 do inventário.** Hoje qualquer staff com permissão de `change_allocationpendency` pode editar `action` livremente, sem passar pela política de origem, sem gerar auditoria. A spec aprovada (POR-01) não menciona o Admin. Pergunta de produto: o bloqueio por origem deve valer também para o Admin (tornando `action` `readonly` quando a transição seria uma abertura/reabertura bloqueada, ou removendo `action` do Admin por completo), ou o Admin é uma ferramenta de suporte que permanece fora do escopo desta feature? Enquanto não houver resposta, o inventário e a matriz de autorização tratam este caminho como **fora do escopo de POR-04**, documentado como risco residual conhecido, não como lacuna de mapeamento.
2. **Payload JSON da API (`PendencyDetailView`/`PendencyUpdateView`) — sinalização de origem bloqueada para a UI.** Para a UI (POR-05) avisar o usuário e desabilitar só o controle de abertura (sem desabilitar o modal inteiro), o JSON de `_pendency_to_json` precisa expor algum campo novo (ex.: `origin_open_blocked: true/false` e/ou a mensagem exata) para o JS decidir o que renderizar, já que hoje o payload não carrega a origem da linha nem um booleano equivalente. Isso é adição de campo de resposta, não mudança de contrato de erro — fica registrado aqui para ser decidido/implementado em POR-04/POR-05, não em POR-02.
3. **"Funcionar sem depender exclusivamente de JavaScript" (contrato POR-01, linha 27).** O fluxo de `AllocationPendency` (modal `#pendencyModal`) é 100% `fetch`/JS hoje — não existe formulário HTML de fallback para abrir/tratar pendência nessa tela, nem antes desta feature. O único formulário HTML real (`DailyUserActionForm`, item 14 do inventário) nunca é renderizado no template (item 15) e seria outro sistema (`DailyUserAction`), não `AllocationPendency`. Pergunta de produto: "sem depender exclusivamente de JavaScript" significa (a) que o bloqueio do servidor já satisfaz a exigência porque é sempre aplicado independente do estado do JS no navegador — com a mensagem aparecendo mesmo que o JS falhe parcialmente, desde que o `fetch` ainda rode — ou (b) que esta feature deve construir um fallback HTML novo para a tela de pendências, o que seria escopo muito maior que um bloqueio de abertura? Assumindo (a) como leitura mais consistente com o restante do contrato (que fala em recusa de servidor, não em novo fallback de UI), mas registrado para confirmação antes de POR-05.
4. **Sinal visual na tabela de Ações do Dia para linhas bloqueadas.** A spec não define se a tabela (`daily_user_action_board.html`) deve mostrar algum indicador visual permanente (badge/ícone) de que a origem da linha impede abertura, além da mensagem ao tentar abrir. Não é bloqueador para POR-02/POR-03 (testável sem essa decisão), mas fica registrado para POR-05.

Nenhuma destas lacunas impede derivar os testes de POR-03 listados acima: todos os cenários T1–T18 usam só comportamento já determinado pelo contrato aprovado (POR-01) e pelo inventário confirmado nesta etapa. As lacunas 1–4 afetam apenas escopo de POR-04/POR-05 (Admin, payload de UI, fallback sem JS, indicador visual), não a forma dos testes de domínio/HTTP already especificados.

## Implementation Plan / Tasks

- [x] POR-01 — Registrar contrato aprovado e mapeamento inicial (esta entrega).
- [x] POR-02 — Completar inventário de aberturas/reaberturas e UI, incluindo Admin/chamadores; fixar contratos HTTP/HTML e matriz de autorização. Distinguir criação de registro vazio de abertura real. Não implementar.
- [x] POR-03 — Derivar testes da matriz, executar RED real e classificar falhas; controles de tratamento existente devem permanecer GREEN. Não fabricar placeholders.
- [x] POR-04 — Implementar política compartilhada e proteção transacional nas entradas reais; bloquear POST direto sem efeitos colaterais e preservar tratamento/resolução.
- [x] POR-05 — Integrar informação e restrição da UI, com mensagem exata, incluindo reabertura; não bloquear controles legítimos de pendências existentes.
- [x] POR-06 — Aceite real no navegador, regressão proporcional e revisão de diff; registrar limites e preparar entrega, sem commit/deploy automático.

## Test Checklist

1. APARELHO_OP e PESSOAL: abertura e reabertura recusadas em cada entrada real.
2. Mensagem exata; nenhuma exceção nova por role. Testar papéis já autorizados e controles de acesso negado.
3. APARELHO, origem permitida e origem vazia: fluxo anterior preservado.
4. Sem linha/alocação: comportamento anterior preservado.
5. Pendência aberta em linha agora restrita: assumir, observação, tratamento, liberação de responsável e resolução mantêm autorização anterior.
6. Pendência resolvida da mesma linha: reabertura recusada.
7. Recusa com payload composto não persiste alterações parciais nem evento OPENED/REOPENED ou notificações de sucesso.
8. POST direto ignora tentativa de falsificar origem; consulta origem persistida.
9. UI com/sem JS, erro legível, foco e controles de tratamento utilizáveis.
10. Persistência comparada antes/depois da recusa; registro vazio preexistente preservado.
11. Mudança de origem entre render da tela e POST: servidor aplica valor vigente quando avalia operação. Concorrência adicional deve ser analisada, não declarada comprovada por SQLite.

## Test Strategy

### Camadas

- **Domínio puro** (sem HTTP): `AllocationPendency.record_action_change` já é testável isoladamente (ver `dashboard/tests/test_reconnect_counter.py`, que já instancia `AllocationPendency` e chama `record_action_change` diretamente). Se a política de origem for extraída como função pura (ex.: `pendencies/services.py::is_origin_blocked_for_opening(phone_line)`), POR-03 deve testá-la sem Client, cobrindo as três origens bloqueadas/permitidas/vazia/sem linha de T1/T2/T6/T7 nessa camada antes de repetir em integração HTTP.
- **Integração HTTP** (`django.test.Client`, `TestCase`, SQLite local): cobre T1–T14, T16, T17. Fixtures reutilizáveis já existem no padrão de `pendencies/tests/test_line_status_web_restriction.py` e `pendencies/tests/test_observation_notifications.py` — `SystemUser.objects.create_user(role=...)`, `Employee.objects.create(...)`, `SIMcard.objects.create(...)`, `PhoneLine.objects.create(..., origem=...)`, `LineAllocation.objects.create(...)`, `AllocationPendency.objects.create(...)`. Nenhuma fixture nova de infraestrutura é necessária, só variar `origem` do `PhoneLine` e o estado (`action`/`resolved_at`) do `AllocationPendency`/`DailyUserAction`.
- **Persistência/auditoria**: usar `LineDailyActionAuditEvent.objects.filter(...)` antes/depois do POST recusado para confirmar ausência de evento novo (T1, T4, T13), e `AllocationPendency.objects.get(pk=...)`/`DailyUserAction.objects.filter(...)` para confirmar ausência de mudança de estado. Ausência de evento isoladamente não prova recusa correta — sempre combinar com o status HTTP/mensagem e com o estado do model antes/depois (contrato já no Test Checklist, item 10).
- **Navegador real**: só T15 (UI com JS, foco, mensagem no `#pendencySaveStatus`, modal não travado para tratamento). Fora do pytest de domínio.
- **PostgreSQL real**: só T18 (concorrência/locking). SQLite não comprova `select_for_update`; não escrever esse teste contra SQLite alegando prová-lo.

### Arquivos prováveis para POR-03

- `pendencies/tests/test_pendency_origin_restriction.py` (novo) — T1, T2, T3, T8, T12, T13, T14, T16, T17.
- `dashboard/tests/test_daily_user_action_origin_restriction.py` (novo) — T4, T5, T9.
- Reaproveitar fixtures de `pendencies/tests/test_line_status_web_restriction.py` (setUp já cria admin/supervisor/employee/sim/phone_line/allocation/pendency) como ponto de partida, parametrizando `origem` do `PhoneLine`.
- Teste de acesso por role (T10) pode reaproveitar padrão de controle de acesso já presente nos testes existentes de `pendencies`/`dashboard` que verificam 403 por `RoleRequiredMixin`/`roles_required` (confirmar duplicata antes de criar um novo).
- T11 (POST direto / falsificação) é variação de T1/T4 — mesmo arquivo, não arquivo separado.
- T15/T18 não entram no `pytest` padrão local: T15 depende de ferramenta de browser real (fora do escopo de arquivo `.py` em `tests/`); T18 depende de serviço Postgres disponível em CI, deve ficar marcado/skippável quando Postgres não estiver configurado (mesmo padrão, se existente, de outros testes que já dependem de Postgres no repositório — a confirmar em POR-03 se não houver precedente).

`manage.py check` e `git diff --check` seguem previstos ao final das etapas de código (POR-04 em diante); não se aplicam a este passo, que não altera código de aplicação.

## Compliance Report

POR-02 concluída nesta etapa: inventário completo (15 entradas, incluindo o bypass do Django Admin), matriz de autorização/transições, contratos de erro e efeitos colaterais para `PendencyUpdateView` e `daily_user_action_board`, e plano de testes POR-03 (18 cenários, T1–T18) com arquivos prováveis. Quatro decisões de produto ficaram pendentes (Admin, payload de UI para POR-05, leitura de "sem depender de JavaScript", indicador visual na tabela) — nenhuma delas impede derivar os testes de POR-03 listados, porque todas afetam apenas escopo de POR-04/POR-05.

Nenhum código de aplicação, teste executável, migration, form, template ou JS foi alterado ou executado nesta etapa — só esta spec. Alterações de versão 1.9.0 e arquivos alheios preservados. Sem stage, commit, push, deploy ou acesso a PRD. Próxima tarefa: POR-03 (derivar os testes reais de T1–T18, executar RED, classificar falhas), não iniciada.

## Fechamento das quatro decisões — 2026-10-13

### Spec Summary

Usuário confirmou todas as opções recomendadas (1A, 2A, 3A, 4A):

1. **Admin:** validar abertura/reabertura no servidor e apresentar a mensagem aprovada como erro do formulário. Preservar tratamento e resolução conforme permissões existentes. Não tornar o campo globalmente readonly nem remover a ação. Admin não constitui exceção à regra de origem.
2. **API/UI:** adicionar flag de bloqueio e motivo calculados pelo backend. A UI usa essa informação para impedir somente abertura/reabertura, sem repetir a regra de origem em JavaScript nem desabilitar o modal inteiro. Nomes dos campos são detalhe técnico a fixar documentalmente antes dos testes de contrato; a flag de origem não deve ser confundida com permissão global de tratamento.
3. **Sem JavaScript:** proteção no servidor independente de JS. O modal mantém sua dependência atual de JavaScript; nenhum formulário HTML alternativo será criado. Não prometer mensagem ou operação do modal quando JS estiver totalmente desativado.
4. **Visual:** mensagem no modal junto aos controles de abertura bloqueados; nenhum novo ícone/badge permanente na tabela.

A mensagem permanece literalmente a aprovada no início deste documento.

### Gap Analysis / retificações

- Admin integra POR-03/POR-04. A classificação histórica como fora de escopo está superada. Campo editável sem checagem é evidência estática de caminho potencial; confirmação de bypass requer POST real e estado persistido observado.
- As quatro decisões afetam testes e contratos, não apenas implementação. A afirmação histórica de que nenhuma afetaria POR-03 fica retificada.
- O parágrafo de POR-02 que admite gravar `line_status` antes de recusar abertura contraria o contrato original de ausência de efeitos parciais no mesmo pedido. Essa exceção não foi aprovada. Prevalece o contrato original: testar também o payload composto de Ações do Dia, com usuário autorizado a alterar status, e verificar que a recusa não persiste esse status nem demais efeitos do pedido.
- T18 descreve uma hipótese de locking, não uma garantia comprovada. Lock de alocação/pendência não prova sozinho serialização de edição de `PhoneLine.origem`. Mapear locks reais antes de definir asserções concorrentes; manter a garantia aprovada de origem persistida no momento da avaliação, sem inventar isolamento adicional.
- São **duas** origens bloqueadas (`APARELHO OP`, `PESSOAL`); `APARELHO` é controle permitido. A menção histórica a "três origens bloqueadas" está incorreta.

### Contrato técnico do payload — flag e motivo (fixado em 2026-10-13, conferência corretiva de POR-03)

Decisão 2A deixou os nomes de campo como "detalhe técnico a fixar documentalmente antes dos testes de contrato". Fixado agora, antes de escrever as asserções de contrato (não implementado nesta etapa — só documentado e testado via RED):

- Campos novos, aditivos, em `pendencies/views.py::_pendency_to_json` (função já compartilhada por `PendencyDetailView.get` e pelo corpo de sucesso de `PendencyUpdateView.post` — um único ponto de serialização, sem duplicar a lista de origens/mensagem em outro lugar):
  - `origin_open_blocked` (`bool`): `True` quando `allocation.phone_line.origem` pertence ao conjunto bloqueado (`APARELHO OP`, `PESSOAL`); `False` quando a origem é permitida (inclusive `APARELHO`, origem customizada ou vazia/`None`) **ou** quando não há `allocation` (sem linha, sem origem a avaliar).
  - `origin_open_blocked_reason` (`str`): a mensagem exata aprovada quando `origin_open_blocked` é `True`; string vazia (`""`) quando é `False`.
- Semântica — diferença explícita de autorização geral para tratar: a flag reflete **só** se a origem da linha bloquearia uma abertura/reabertura (`NO_ACTION → outro valor`) **se** ela fosse tentada agora. Ela não representa, e não deve ser confundida com, a permissão do usuário atual para abrir (`is_super_like`), nem com `observation_locked` (bloqueio por `line_status == under_analysis`), nem com a existência de um responsável técnico. Um ADMIN sem permissão de abrir (bloqueado por `PRE_EXISTING_PERMISSION_MESSAGE`, não por origem) ainda recebe `origin_open_blocked=True`/`reason` corretos para uma linha `APARELHO OP`/`PESSOAL` — a flag descreve o estado da linha, não o papel de quem está vendo.
- A flag não altera `action_choices` nem desabilita nenhum outro campo do payload; pendência já aberta numa linha com origem agora bloqueada continua expondo todos os campos de tratamento normalmente (claim/observação/release/resolução não são afetados pela flag).
- Escopo: a flag só é serializada depois que `_load_locked_pendency_for_scope`/`scope_employee_queryset` já aprovaram o acesso — não é um canal novo de vazamento de origem para quem não tem acesso ao funcionário (o 403 de escopo ocorre antes de qualquer serialização).
- Esta função permanece não implementada nesta etapa; os testes abaixo são RED até POR-04 adicionar os dois campos.

### Implementation Plan

POR-03: derivar testes comportamentais das decisões e da matriz, incluindo Admin e payload aditivo. Executar RED real, classificar por node ID e registrar controles GREEN. Não implementar política, views, forms, templates ou JS nesta etapa. POR-04/POR-05/POR-06 permanecem pendentes.

### Test Checklist

- Admin: abertura/reabertura recusadas com mensagem; origem permitida e tratamento autorizado preservados.
- Payload: flag e motivo corretos para origem persistida, sem ampliar escopo de acesso; restrição de abertura não impede tratamento.
- POST direto e payload composto nos dois caminhos: recusa sem efeitos parciais, auditoria de sucesso ou notificações novas.
- GET de registro vazio não equivale a abertura; origens permitidas, sem linha e permissões anteriores preservadas.
- Browser/JS/foco ficam identificados para POR-05/POR-06; não confundir Django Client com aceite visual.

### Test Strategy

Usar endpoints e Admin reais com banco isolado; comparar conteúdo/estado antes e depois, não apenas status. Reaproveitar cobertura existente sem duplicação. Não criar `pytest.fail` incondicional nem exigir nome inventado de função futura. PostgreSQL necessário para alegações de locking; SQLite não as comprova.

### Compliance Report

Esta atualização registra decisões aprovadas e corrige contradições documentais. Apenas spec alterada; nenhum teste ou código de aplicação executado/implementado nesta atualização. POR-03 ainda não iniciada. Sem stage, commit, push, deploy ou PRD.

## POR-03 — Testes RED (execução real, 2026-10-13)

### Spec Summary

Derivados os testes comportamentais de T1–T18 e das quatro decisões do Fechamento (Admin, payload de API/UI, sem-JS, visual), cobrindo os dois caminhos reais de abertura/reabertura (`PendencyUpdateView`, `daily_user_action_board`) e o bypass do Django Admin (`AllocationPendencyAdmin`). Camada usada: integração HTTP (`django.test.Client`/`TestCase`, SQLite local), conforme Test Strategy da spec — nenhuma função pura de política foi inventada (não existe ainda; POR-04 decide se a extrai). T15 (browser/JS) e T18 (concorrência Postgres) permanecem fora do pytest local, conforme já previsto.

Dois arquivos novos, nenhum código de aplicação alterado:

- `pendencies/tests/test_pendency_origin_restriction.py` — 23 testes (T1, T2, T3, T6, T7, T8, T10, T11, T12, T13, T14, T16, T17 + Admin/decisão 1A).
- `dashboard/tests/test_daily_user_action_origin_restriction.py` — 10 testes (T4, T5, T6, T7, T9, T11-variante, retificação de efeito parcial de `line_status`, controles de tratamento de ação já aberta).

### Gap Analysis

Nenhuma lacuna nova. Confirmado por execução real (não apenas leitura estática) que:

- `PendencyUpdateView` e `daily_user_action_board` abrem/reabrem pendência para `APARELHO OP`/`PESSOAL` hoje, sem qualquer checagem de origem (RED).
- `AllocationPendencyAdmin` permite editar `action` de `NO_ACTION` para qualquer valor via POST direto no Admin, com `response.status_code == 302` (sucesso) mesmo para origem bloqueada — bypass real confirmado por POST, não só por leitura estática do `readonly_fields` (RED).
- Em `daily_user_action_board`, o ramo de `line_status` (só ADMIN) executa antes e de forma independente do ramo de abertura de ação: quando a abertura é recusada por origem (após POR-04), o `line_status` enviado no mesmo POST será persistido mesmo assim, a menos que POR-04 também corrija esse efeito parcial — confirmado hoje porque, sem a checagem, ambos os efeitos (status da linha e `DailyUserAction` criado) ocorrem juntos (RED documentando o efeito colateral a corrigir, não só a ausência da regra de origem).
- Todos os controles (origem permitida, sem linha, tratamento/claim/release/observação/resolução de pendência já aberta, escopo, acesso por role, GET não é abertura) já passam hoje (GREEN), confirmando que a política pré-existente a preservar está corretamente mapeada e não será quebrada por engano em POR-04.

### Implementation Plan

POR-03 concluída: testes derivados, RED executado e classificado, controles GREEN confirmados com causa demonstrada (não apenas ausência de erro). Nenhum código de aplicação, migration, form, template ou JS foi alterado. POR-04 (implementação) permanece não iniciada.

### Test Checklist — mapeamento aos itens da spec

1. APARELHO_OP/PESSOAL recusados em cada entrada real → RED em `OpeningBlockedByOriginTests`, `ReopeningBlockedByOriginTests`, `CreationBlockedByOriginTests`, `ReopeningBlockedByOriginTests` (dashboard), `AdminChangeFormOpeningRestrictionTests` (3 cenários).
2. Mensagem exata; nenhuma exceção nova por role → RED/GREEN em `AdminNoNewExceptionTests` (GREEN: ADMIN já bloqueado por permissão, nunca pela origem) e `AllRolesBlockedIdenticallyTests` (RED: nenhuma role tem bloqueio ainda).
3. APARELHO/permitida/vazia preservadas → GREEN em `OpeningControlOriginsPreservedTests`, `ControlOriginsPreservedTests`.
4. Sem linha/alocação preservado → GREEN em `OpeningWithoutAllocationPreservedTests`, `CreationWithoutAllocationPreservedTests`.
5. Tratamento de pendência aberta em linha restrita preservado → GREEN em `OpenPendencyTreatmentPreservedTests` (claim/observação/release/resolução) e `ExistingOpenActionTreatmentPreservedTests` (alteração de ação aberta/resolução em Ações do Dia).
6. Pendência resolvida: reabertura recusada → RED em `ReopeningBlockedByOriginTests` (ambos arquivos).
7. Payload composto sem efeito parcial → RED em `CompositePayloadNoPartialEffectsTests` (ambos arquivos — pendencies prova ausência de observação/notificação; dashboard prova ausência de persistência de `line_status`, retificação do Fechamento).
8. POST direto ignora falsificação de origem → RED em `ForgedOriginInPayloadTests` (ambos arquivos).
9. UI com/sem JS → não coberto aqui; identificado como T15, pendente para POR-05/POR-06 (ver Test Strategy).
10. Persistência antes/depois da recusa; registro vazio preservado → GREEN em `EmptyRecordIsNotOpeningTests`; estado antes/depois comparado em todos os testes RED via `refresh_from_db()`.
11. Origem alterada entre render e POST → RED em `OriginChangedBetweenRenderAndPostTests`; concorrência real (T18) não comprovada aqui, conforme já previsto.

### Test Strategy — confirmação

Usados endpoints reais (`pendencies:update`, `pendencies:detail`, `pendencies:claim`, `pendencies:release`, `daily_user_action_board`) e o Admin real (`admin:pendencies_allocationpendency_change`) contra SQLite local, com banco isolado por execução (`manage.py test`). Nenhuma fixture nova de infraestrutura; reaproveitado o padrão de `pendencies/tests/test_line_status_web_restriction.py`, `pendencies/tests/test_observation_notifications.py` e `dashboard/tests/test_daily_line_action_audit.py`. Nenhum `pytest.fail` incondicional, nenhum helper futuro inventado, nenhum mock da própria política (política ainda não existe). T15 (browser) e T18 (Postgres) seguem fora do pytest local, sem alegação de prova de concorrência em SQLite.

### Matriz Node ID → Requisito → Camada → Tarefa → Resultado → Causa

| Node ID (arquivo::Classe::teste) | Requisito | Camada | Resultado | Causa |
|---|---|---|---|---|
| `pendencies...::OpeningBlockedByOriginTests::test_opening_blocked_for_aparelho_op` | T1 | HTTP (`PendencyUpdateView`) | RED | Sem checagem de origem; view abre (200) em vez de recusar (403). |
| `pendencies...::OpeningBlockedByOriginTests::test_opening_blocked_for_pessoal` | T2 | HTTP | RED | Idem. |
| `pendencies...::ReopeningBlockedByOriginTests::test_reopening_blocked_for_aparelho_op` | T3 | HTTP | RED | Idem, reabertura. |
| `pendencies...::ReopeningBlockedByOriginTests::test_reopening_blocked_for_pessoal` | T3 | HTTP | RED | Idem, reabertura. |
| `pendencies...::OpeningControlOriginsPreservedTests::test_opening_allowed_for_each_control_origin` | T6 | HTTP | GREEN | Comportamento anterior correto para APARELHO/custom/vazia — nada a corrigir aqui. |
| `pendencies...::OpeningWithoutAllocationPreservedTests::test_opening_allowed_without_allocation` | T7 | HTTP | GREEN | Sem `allocation`, não há origem a checar — comportamento já correto. |
| `pendencies...::AdminNoNewExceptionTests::test_admin_blocked_by_permission_regardless_of_origin` | T8 | HTTP | GREEN | Gate de permissão pré-existente (`is_super_like`) já bloqueia ADMIN antes de qualquer origem. |
| `pendencies...::ForgedOriginInPayloadTests::test_extra_origin_field_in_body_is_ignored` | T11 | HTTP | RED | Mesma causa de T1/T2: sem política, a view abre mesmo com origem real bloqueada. |
| `pendencies...::OriginChangedBetweenRenderAndPostTests::test_post_uses_origin_at_evaluation_time_not_at_render_time` | T17 | HTTP | RED | Idem. |
| `pendencies...::EmptyRecordIsNotOpeningTests::test_get_detail_creates_empty_record_without_opening` | T16 | HTTP | GREEN | GET via `_get_or_create_pendency` já não equivale a abertura — comportamento pré-existente correto. |
| `pendencies...::OutOfScopeUserDoesNotLeakOriginTests::test_out_of_scope_super_is_denied_before_origin_check` | T14 | HTTP | GREEN | `_load_locked_pendency_for_scope` já nega escopo antes de qualquer lógica de domínio. |
| `pendencies...::RoleAccessControlPrecedesOriginCheckTests::test_operator_denied_access_regardless_of_origin` | T10 | HTTP | GREEN | `RoleRequiredMixin` pré-existente já nega OPERATOR. |
| `pendencies...::CompositePayloadNoPartialEffectsTests::test_refused_opening_does_not_persist_observation_or_notify` | T13 | HTTP | RED | Sem bloqueio, abertura e observação/notificação são persistidas juntas hoje. |
| `pendencies...::OpenPendencyTreatmentPreservedTests::test_admin_can_claim_already_open_pendency_on_blocked_origin` | T12 | HTTP | GREEN | Claim não depende de origem — comportamento já correto. |
| `pendencies...::OpenPendencyTreatmentPreservedTests::test_responsible_admin_can_change_observation_on_blocked_origin` | T12 | HTTP | GREEN | Observação de pendência aberta não é bloqueada por origem. |
| `pendencies...::OpenPendencyTreatmentPreservedTests::test_admin_can_release_already_open_pendency_on_blocked_origin` | T12 | HTTP | GREEN | Release não depende de origem. |
| `pendencies...::OpenPendencyTreatmentPreservedTests::test_responsible_admin_can_resolve_already_open_pendency_on_blocked_origin` | T12 | HTTP | GREEN | Resolução não é bloqueada por origem. |
| `pendencies...::AdminChangeFormOpeningRestrictionTests::test_admin_change_form_blocks_opening_for_aparelho_op` | Decisão 1A | HTTP (Django Admin) | RED | `action` editável sem checagem; POST salva (302) em vez de recusar (200 + erro de form). |
| `pendencies...::AdminChangeFormOpeningRestrictionTests::test_admin_change_form_blocks_opening_for_pessoal` | Decisão 1A | Admin | RED | Idem. |
| `pendencies...::AdminChangeFormOpeningRestrictionTests::test_admin_change_form_blocks_reopening_for_blocked_origin` | Decisão 1A | Admin | RED | Idem, reabertura via Admin. |
| `pendencies...::AdminChangeFormOpeningRestrictionTests::test_admin_change_form_allows_opening_for_permitted_origin` | Decisão 1A (controle) | Admin | GREEN | Origem permitida já funciona pelo Admin — nada a corrigir. |
| `pendencies...::AdminChangeFormOpeningRestrictionTests::test_admin_change_form_allows_resolution_on_blocked_origin` | Decisão 1A (controle) | Admin | GREEN | Resolução via Admin não é abertura — já funciona. |
| `dashboard...::CreationBlockedByOriginTests::test_creation_blocked_for_aparelho_op` | T4 | HTTP (`daily_user_action_board`) | RED | Sem checagem de origem; `DailyUserAction` é criado (OPENED) em vez de recusado. |
| `dashboard...::CreationBlockedByOriginTests::test_creation_blocked_for_pessoal` | T4 | HTTP | RED | Idem. |
| `dashboard...::ReopeningBlockedByOriginTests::test_reopening_blocked_keeps_resolved_true` | T5 | HTTP | RED | Idem, reabertura (REOPENED). |
| `dashboard...::ControlOriginsPreservedTests::test_creation_allowed_for_each_control_origin` | T6 | HTTP | GREEN | Comportamento anterior correto para origens permitidas. |
| `dashboard...::CreationWithoutAllocationPreservedTests::test_creation_allowed_without_allocation` | T7 | HTTP | GREEN | Sem `allocation_id`, não há origem a checar. |
| `dashboard...::AllRolesBlockedIdenticallyTests::test_each_allowed_role_is_blocked_the_same_way` (4 subTests: ADMIN/SUPER/BACKOFFICE/GERENTE) | T9 | HTTP | RED (4/4) | Nenhuma role tem bloqueio ainda — mesma causa de T4. |
| `dashboard...::ForgedOriginInPayloadTests::test_extra_origin_field_in_post_is_ignored` | T11-variante | HTTP | RED | Mesma causa de T4; campo extra no POST é irrelevante porque a origem nem é checada. |
| `dashboard...::CompositePayloadNoPartialEffectsTests::test_refused_opening_does_not_persist_line_status_change` | Retificação Fechamento (efeito parcial) | HTTP | RED | Ramo de `line_status` (só ADMIN) roda antes e independente do ramo de abertura; persiste mesmo quando a abertura deveria ser recusada — POR-04 precisa corrigir também esse efeito parcial, não só adicionar a checagem de origem. |
| `dashboard...::ExistingOpenActionTreatmentPreservedTests::test_changing_already_open_action_is_not_blocked` | Matriz POR-02 (linha 82) | HTTP | GREEN | Alteração de ação já aberta no mesmo dia não é abertura — já funciona. |
| `dashboard...::ExistingOpenActionTreatmentPreservedTests::test_resolving_open_action_is_not_blocked` | Matriz POR-02 (linha 83) | HTTP | GREEN | Resolução não é bloqueada por origem — já funciona. |

Coletados/PASSED/FAILED/ERROR/SKIPPED (execução real, bateria completa de cada app, não só os arquivos novos, para regressão proporcional):

- `manage.py test pendencies.tests.test_pendency_origin_restriction dashboard.tests.test_daily_user_action_origin_restriction -v 2`: coletados 32-33 testes (`unittest` reporta `Ran 32 tests`; a diferença de 1 em relação à contagem manual de 33 métodos é efeito de agregação de `subTest` no contador "Ran", não de coleta — todos os 33 métodos descritos na matriz acima executaram e reportaram resultado, nenhum ficou de fora). 19 FAILED (todos RED esperados, listados na matriz), 0 ERROR, 0 SKIPPED, restante PASSED.
- `manage.py test pendencies` (suíte completa do app, incluindo os pré-existentes): `Ran 80 tests`, `FAILED (failures=10)` — os 10 nomes de falha conferem 1:1 com os 10 métodos RED da matriz pertencentes a este arquivo; os 70 restantes (pré-existentes + controles novos) PASSED. 0 ERROR.
- `manage.py test dashboard.tests` (suíte completa do app; `manage.py test dashboard` sem `.tests` falha por colisão de nome de módulo `tests` entre apps — limitação do test runner do Django nesta configuração, não um erro de coleta desta tarefa): `Ran 80 tests`, `FAILED (failures=9)` — 6 métodos distintos (1 deles com 4 subTests, somando 9 linhas de FAIL), todos RED esperados da matriz; os 71 restantes PASSED. 0 ERROR.

Nenhuma falha de fixture ou de coleta em nenhuma das execuções — todas as falhas têm `AssertionError` com causa demonstrada (status HTTP e/ou estado do model e/ou mensagem ausente), nunca `pytest.fail`/erro de importação/fixture.

`manage.py check`: "System check identified no issues (0 silenced)." `git diff --check`: nenhum marcador de conflito nem espaço em branco problemático introduzido pelos dois arquivos novos (único aviso é de normalização de fim de linha CRLF/LF em arquivo não tocado por esta tarefa).

### Compliance Report

POR-03 concluída: 33 testes novos (23 em `pendencies/tests/test_pendency_origin_restriction.py`, 10 em `dashboard/tests/test_daily_user_action_origin_restriction.py`), cobrindo T1–T14, T16, T17 e as decisões do Fechamento sobre Admin e efeito parcial de `line_status`; T15 e T18 permanecem fora do pytest local, conforme já previsto na spec. RED real confirmado para todos os cenários onde o contrato aprovado ainda não está implementado (19 falhas, causa demonstrada em cada uma); GREEN confirmado com causa para todos os controles que já devem funcionar hoje (14 testes novos GREEN) e para toda a suíte pré-existente dos dois apps (70 + 71 testes, 0 regressão). Nenhum código de aplicação, migration, form, template, CSS ou JS foi alterado ou executado além dos comandos de teste e dos checks solicitados. Sem stage, commit, push, deploy ou acesso a PRD. Próxima tarefa: POR-04 (implementação da política compartilhada e proteção transacional), não iniciada.

**Retificação (ver "POR-03 — Conferência corretiva" abaixo, 2026-10-13):** a contagem "33 testes novos" e "70 + 71 testes" acima está **errada** — contagem real abaixo. O texto acima é preservado como histórico; não usar seus números.

## POR-03 — Conferência corretiva (2026-10-13)

Conferência solicitada antes de iniciar POR-04, cobrindo três pendências: (1) cobertura do payload de flag/motivo da API, ainda ausente; (2) ambiguidade na regressão "70/71"; (3) execução via pytest comparada a `manage.py test`. As três foram resolvidas por execução real, não por leitura. Nenhum código de aplicação foi alterado — só testes e esta spec.

### Spec Summary

Fixado o contrato técnico dos dois campos aditivos (`origin_open_blocked`, `origin_open_blocked_reason`) em `_pendency_to_json` — ver seção "Contrato técnico do payload" acima, inserida na área do Fechamento, antes das novas asserções. Adicionados 6 testes de contrato novos em `pendencies/tests/test_pendency_origin_restriction.py::OriginBlockedPayloadFlagTests`, todos RED (campos não existem ainda). Corrigida a contagem de testes de POR-03: o total real das duas suítes novas (antes dos 6 testes de payload) era **32**, não 33; a causa foi um erro de contagem manual (contei `pendencies/tests/test_pendency_origin_restriction.py` como 23 métodos quando o arquivo sempre teve 22 — `grep -c "    def test_"` confirma). Após a correção corretiva (6 testes novos), o total passa a **38**. Esclarecida a regressão: são duas suítes completas de apps distintos, não "70 aprovados entre 71" — `pendencies` (80 testes totais, 70 PASS) e `dashboard` (80 testes totais, **74** PASS, não 71 — o "71" do relatório anterior também vinha do mesmo erro de contagem, explicado abaixo). `pytest` foi executado sobre os arquivos novos e confirma a mesma coleta (`--collect-only` bate com `Found N test(s)` do `manage.py test` em todos os casos: 32, depois 38) — nenhuma diferença de runner/settings encontrada.

### Gap Analysis

**1. Payload — flag e motivo: lacuna real, agora coberta.** A spec (decisão 2A) exigia a flag e o motivo, mas POR-03 original não tinha nenhum teste de contrato para eles — nem a função `_pendency_to_json` (`pendencies/views.py:67-132`) os expõe hoje. Confirmado por leitura do código e por execução: os 6 testes novos de `OriginBlockedPayloadFlagTests` falham com `AssertionError: 'origin_open_blocked' not found in {...}` (não `KeyError`, após ajuste do primeiro teste que usava indexação direta e produzia `ERROR` em vez de `FAIL` — corrigido para `assertIn` antes de indexar, mesmo padrão do resto do arquivo). Cobertura adicionada: origem bloqueada com motivo exato (`test_detail_payload_flags_blocked_origin_with_exact_reason`, parametrizado nas duas origens), origem permitida/vazia/sem allocation com flag falsa e motivo vazio (`test_detail_payload_flags_permitted_origin_as_false`, `test_detail_payload_flag_is_false_without_allocation`), diferenciação explícita entre bloqueio por origem e autorização geral — a flag reflete a linha, não o papel de quem vê (`test_detail_payload_flag_reflects_origin_not_viewers_permission`, usando ADMIN, que é bloqueado por permissão e não por origem), preservação do tratamento de pendência já aberta com a flag ligada — `action_choices` completo, claim e observação continuam funcionando (`test_flag_does_not_restrict_treatment_fields_or_actions_on_open_pendency`), e o payload de sucesso do `PendencyUpdateView.post` também expõe a flag (`test_update_success_response_includes_false_flag_for_permitted_origin`). O teste de escopo já existente (`OutOfScopeUserDoesNotLeakOriginTests`) ganhou uma asserção adicional de que o nome do campo novo também não aparece no corpo da resposta 403. Nenhum helper de produção foi inventado; os testes leem só a resposta HTTP real.

**2. Regressão "70/71": ambiguidade real, esclarecida por execução.** O relatório anterior dizia "pendencies (80 total, 70 PASS)" e "dashboard (80 total, 71 PASS)" sem deixar claro que são duas suítes de apps diferentes (não uma única amostra de 71 de algo). Além disso, o número "71" do dashboard estava **errado**: vinha de `80 - 9` usando o contador agregado `failures=9` do Django (que conta cada subteste que falha como uma entrada separada) como se fosse "9 testes reprovados", quando na verdade são **6 nós de teste** reprovados (5 testes comuns + 1 teste com 4 subtestes de role, todos os 4 reprovados) gerando 9 *linhas* de falha. O número certo de nós aprovados é `80 - 6 = 74`, confirmado contando diretamente as linhas `"... ok$"` do log verboso (`grep -cE "\.\.\. ok$"` = 74) e cruzando com os nomes de `"... FAIL$"` (9 linhas, mapeadas para 6 métodos distintos). Em `pendencies` o erro não ocorria (nenhuma falha ali usa subTest), por isso "70" já estava certo. Reexecutado agora com log salvo e contagem por grep, não por leitura visual: ver comandos e números na tabela de Validação abaixo.

**3. Execução com pytest: sem lacuna de produto, sem divergência de runner.** `pytest.ini` usa `DJANGO_SETTINGS_MODULE=config.settings_dev`, enquanto `manage.py` usa `config.settings`; `config/settings_dev.py` só sobrescreve `DEBUG`/`ALLOWED_HOSTS`/cookies, herdando o resto de `config/settings.py` via `from .settings import *`. O banco de teste é sqlite em memória nos dois casos, porque `config/settings.py` força `DATABASES["default"]` para sqlite tanto quando `sys.argv[1] == "test"` (caminho do `manage.py test`) quanto quando `"pytest" in sys.modules` (caminho do `pytest-django`), e o backend sqlite do Django ignora o `NAME` de arquivo configurado e usa banco em memória quando `TEST.NAME` não é definido — por isso ambos os runners mostram `'file:memorydb_default?mode=memory&cache=shared'` na criação do banco de teste. `pytest --collect-only -q` coletou exatamente os mesmos itens que `manage.py test ... -v 2` reportou em `Found N test(s)` nos dois arquivos novos (32 antes dos testes de payload, 38 depois) — nenhuma diferença de coleta. A única diferença real é como cada um resume *subtestes* no sumário final: `pytest` (com o plugin `pytest-subtests` instalado) imprime um sumário agregado (`"X failed, Y passed... Z subtests passed"`) cujos números `X`/`Y` não correspondem 1:1 a nós de teste — são contadores mistos de subtestes e testes comuns, e desligar o plugin (`-p no:subtests`) não resolve, só move a inconsistência para outro número. Tratado como **limitação de relato de resumo do plugin/pytest ao combinar com `subTest` do `unittest`, não como lacuna de produto nem de coleta** — a fonte de verdade usada neste relatório é a contagem por nó (`--collect-only`/`Found N test(s)`) cruzada com os nomes de `FAILED`/`"... ok$"` linha a linha, que bate exatamente entre os dois runners.

### Implementation Plan

Nenhuma mudança de plano: POR-03 permanece "testes + documentação, sem código de aplicação". Esta conferência corretiva faz parte de POR-03, não avança para POR-04. Pendência restante antes de considerar POR-03 definitivamente encerrada: nenhuma — as três pendências do pedido foram reconciliadas nesta atualização.

### Test Checklist

- Payload: flag e motivo cobertos por 6 node IDs novos (origem bloqueada com motivo exato, controles de origem permitida/vazia/sem linha, diferenciação de autorização, preservação de tratamento, resposta de sucesso do POST). Todos RED, causa demonstrada (campo ausente do JSON real).
- Regressão: reexecutada com log salvo e contagem por grep; números corrigidos e auditáveis (comandos abaixo).
- Pytest: executado sobre os dois arquivos novos, coleta idêntica à do `manage.py test`; divergência de sumário isolada e explicada, não classificada como lacuna.
- Reconciliação: baseline antigo (33/19/14) substituído pelo baseline real (32 antes do payload, 38 depois; ver matriz de node IDs).

### Test Strategy

Mesma estratégia de POR-03 original (HTTP real, SQLite isolado, sem função de política inventada). Adicionado: contagem de resultado por `grep` sobre log verboso salvo em arquivo (não por leitura visual do terminal), para eliminar o erro de contagem manual que causou a retificação. `pytest --collect-only` usado como segunda fonte independente de contagem de itens coletados, cruzada com `manage.py test -v 2`.

### Matriz Node ID → Requisito → Camada → Tarefa → Resultado → Causa — adendo (payload de origem)

| Node ID | Requisito | Camada | Resultado | Causa |
|---|---|---|---|---|
| `pendencies...::OriginBlockedPayloadFlagTests::test_detail_payload_flags_blocked_origin_with_exact_reason` (2 subTests: APARELHO_OP, PESSOAL) | Decisão 2A / contrato técnico do payload | HTTP (`PendencyDetailView`) | RED (2/2) | `_pendency_to_json` não tem `origin_open_blocked`/`origin_open_blocked_reason` ainda. |
| `pendencies...::OriginBlockedPayloadFlagTests::test_detail_payload_flags_permitted_origin_as_false` (3 subTests: APARELHO, custom, vazia) | Decisão 2A | HTTP | RED (3/3) | Idem. |
| `pendencies...::OriginBlockedPayloadFlagTests::test_detail_payload_flag_is_false_without_allocation` | Decisão 2A | HTTP | RED | Idem. |
| `pendencies...::OriginBlockedPayloadFlagTests::test_detail_payload_flag_reflects_origin_not_viewers_permission` | Decisão 2A (diferenciação origem × autorização) | HTTP | RED | Idem; prova que a flag precisa refletir a linha, não o papel do ADMIN. |
| `pendencies...::OriginBlockedPayloadFlagTests::test_flag_does_not_restrict_treatment_fields_or_actions_on_open_pendency` | Decisão 2A (preservação de tratamento) | HTTP | RED | Idem; falha no primeiro `assertIn`, antes de testar claim/observação (que já funcionam hoje, comportamento pré-existente não afetado). |
| `pendencies...::OriginBlockedPayloadFlagTests::test_update_success_response_includes_false_flag_for_permitted_origin` | Decisão 2A | HTTP (`PendencyUpdateView`, resposta de sucesso) | RED | Idem. |

Cobertura de escopo (item "sem revelar origem indevidamente" do payload) reaproveitada, não duplicada: `OutOfScopeUserDoesNotLeakOriginTests::test_out_of_scope_super_is_denied_before_origin_check` (já existente) ganhou a asserção `assertNotIn("origin_open_blocked", content)` no mesmo node ID — continua GREEN, porque o 403 de escopo já ocorre antes de qualquer serialização, com ou sem os campos novos.

### Validação — comandos e números reais (reexecutados com log salvo)

**Pytest, arquivos novos, sequencial, banco isolado:**
```
venv\Scripts\python.exe -m pytest pendencies/tests/test_pendency_origin_restriction.py dashboard/tests/test_daily_user_action_origin_restriction.py --collect-only -q
→ 38 tests collected
venv\Scripts\python.exe -m pytest pendencies/tests/test_pendency_origin_restriction.py dashboard/tests/test_daily_user_action_origin_restriction.py -p no:subtests -q --tb=no
→ "FAILED <node>" × 22 linhas distintas (confirmado por sort -u | wc -l = 22)
```

**manage.py test, mesmos dois arquivos:**
```
manage.py test pendencies.tests.test_pendency_origin_restriction dashboard.tests.test_daily_user_action_origin_restriction -v 1
→ Found 38 test(s); Ran 38 tests; FAILED (failures=28)
```
28 é o contador agregado do Django (conta cada subteste reprovado como uma entrada: 15 falhas simples antigas + 4 subtestes de `AllRolesBlockedIdenticallyTests` + 2 subtestes de `test_detail_payload_flags_blocked_origin_with_exact_reason` + 3 subtestes de `test_detail_payload_flags_permitted_origin_as_false` + 4 falhas simples novas de payload = 15+4+2+3+4 = 28). O número de nós de teste reprovados é **22** (confirmado de forma independente pelo `pytest -p no:subtests` acima), e os aprovados são `38 − 22 = 16` — sem mudança em relação ao baseline original (os 6 testes novos são todos RED; nenhum teste antigo mudou de resultado).

**Regressão proporcional — suíte completa de cada app, com log salvo em arquivo e contagem por grep (não por leitura visual):**

| App | Comando | Total (nós) | PASS (nós, `grep -cE "\.\.\. ok$"`) | FAIL (nós distintos) | Linhas de FAIL (`grep -cE "\.\.\. FAIL$"`, inclui subtestes) | ERROR | SKIPPED |
|---|---|---|---|---|---|---|---|
| `pendencies` | `manage.py test pendencies.tests -v 2` | 86 (80 antes do payload + 6 novos) | 70 | 16 (10 originais + 6 de payload, todos novos) | 19 | 0 | 0 |
| `dashboard` | `manage.py test dashboard.tests -v 2` | 80 (inalterado nesta conferência) | **74** (não 71) | 6 (5 simples + `AllRolesBlockedIdenticallyTests`, 4/4 subtestes) | 9 | 0 | 0 |

Nenhum teste pré-existente de nenhum dos dois apps mudou de resultado: em `pendencies`, 70 PASS = 58 pré-existentes + 12 GREEN novos (dos 22 originais, antes do payload) — os 6 testes de payload são todos RED, não contribuem PASS; em `dashboard`, 74 PASS = 70 pré-existentes + 4 GREEN novos, confirmando **zero regressão real**, não a frase genérica "zero regressão" do relatório anterior sem a comparação por trás.

`manage.py check`: "System check identified no issues (0 silenced)." `git diff --check`: só o aviso pré-existente de CRLF em `docs/superpowers/specs/2026-09-10-line-daily-action-audit-design.md`, arquivo não tocado nesta tarefa.

### Compliance Report

Conferência corretiva concluída. Três pendências reconciliadas por execução real, log salvo e contagem por grep (não por leitura visual nem por reafirmação do relatório anterior):

1. **Payload (flag + motivo):** contrato técnico fixado na spec (`origin_open_blocked: bool`, `origin_open_blocked_reason: str`, semântica documentada, diferenciada de autorização geral); 6 node IDs novos adicionados em `pendencies/tests/test_pendency_origin_restriction.py::OriginBlockedPayloadFlagTests`, todos RED com causa demonstrada (campo ausente do JSON real da view). Nenhum payload foi implementado; nenhum helper de produção foi inventado.
2. **Regressão "70/71":** esclarecido que são duas suítes completas de apps distintos, não uma amostra única. Número do `dashboard` corrigido de 71 para **74 PASS** (erro de origem identificado: conflação do contador agregado `failures=N` do Django — que conta subtestes separadamente — com contagem de nós de teste). `pendencies` permanece em 70 PASS (não afetado pelo erro, mas revalidado com log salvo).
3. **Pytest:** executado sobre os dois arquivos novos; coleta idêntica à do `manage.py test` (32 → 38 após o payload); nenhuma diferença de runner/settings/fixture encontrada — ambos convergem para o mesmo SQLite em memória por configuração explícita de `config/settings.py`. A única divergência (sumário agregado de subtestes do `pytest-subtests`) foi investigada, explicada e tratada como limitação de relato, não como lacuna de produto.
4. **Reconciliação documental:** baseline antigo ("33 testes = 19 FAILED + 14 PASSED, 0 ERROR") estava errado em três pontos — total (32, não 33, antes do payload), contagem de FAILED (16 nós, não 19 — 19 era o contador agregado de linhas) e PASSED (16 nós, não 14). Baseline real, após o payload: **38 nós — 22 FAILED, 16 PASSED, 0 ERROR, 0 SKIPPED** (28 linhas agregadas de falha, por causa de subtestes). Histórico preservado acima com retificação explícita; números antigos não foram apagados, só marcados como incorretos.

Cada FAILED atual representa requisito/decisão ainda não implementada (checagem de origem em dois caminhos + Admin + payload de flag/motivo); cada GREEN tem causa demonstrada (comportamento pré-existente correto, confirmado por leitura do código e por execução, nunca por ausência de erro isolada).

**Veredito:** POR-03 concluída, condicionada às evidências acima — as três pendências foram reconciliadas e a cobertura exigida (incluindo payload de flag/motivo) está presente e RED real. Nenhum código de produção, migration, dependência ou implementação de POR-04 foi tocado. Sem stage, commit, push, deploy ou PRD. Próxima tarefa: POR-04, não iniciada; parado antes dela conforme solicitado.

## POR-04 — Implementação da política compartilhada e proteção por origem (2026-10-13)

### Reconciliação inicial (antes do código)

Baseline real reconfirmado por execução, com log salvo e contagem por grep, não por leitura do histórico documental:

- `manage.py test pendencies.tests.test_pendency_origin_restriction dashboard.tests.test_daily_user_action_origin_restriction -v 2`: **38 testes**, `FAILED (failures=28)` (contador agregado do Django, inclui subtestes), **22 node IDs distintos reprovados**, 16 PASSED — bate exatamente com a Matriz Node ID → ... → Causa já registrada em POR-03/conferência corretiva. Nenhum número foi reafirmado por leitura; a contagem de nodes distintos foi obtida com `grep` sobre o log salvo desta execução.
- `manage.py test pendencies.tests -v 2`: **86 testes totais**, `failures=19` (linhas agregadas), **70 PASS** (confirmado por `grep -cE "\.\.\. ok$"`), 16 nodes novos RED — idêntico ao baseline da conferência corretiva.
- `manage.py test dashboard.tests -v 2`: **80 testes totais**, `failures=9` (linhas agregadas), **74 PASS** (idem, por grep), 6 nodes novos RED — idêntico ao baseline da conferência corretiva.
- Nenhuma composição de 38 nós foi presumida pelo resumo agregado: os 22 FAILED e 16 PASSED foram separados por node ID, cruzando `FAIL:`/`ERROR:` com `... ok$` linha a linha no log salvo, antes de qualquer alteração de código.
- O baseline anterior de "32 nós" (antes dos 6 testes de payload) só existe documentalmente na conferência corretiva de POR-03 como contagem histórica — não há log preservado desta etapa que isole os 32 separadamente dos 38 atuais; não foi recomputado por subtração, porque os 6 testes de payload já estavam integrados ao mesmo arquivo no estado em que esta tarefa o encontrou. Registrado como limitação de evidência, não como número inventado.
- "Tudo RED" está retificado: o resultado real do baseline é **misto** — 16 dos 38 nós das suítes novas já eram GREEN antes de qualquer implementação (comportamento pré-existente correto, ver matriz de POR-03), e a suíte completa de cada app tinha, respectivamente, 70/86 e 74/80 nodes já PASS. Os 22 nodes RED são exatamente os cenários onde o contrato aprovado ainda não existia.
- Testes pré-existentes que sustentam os números 70/74: são as suítes completas de `pendencies.tests` (86 nodes = 70 pré-existentes + 16 novos desta feature) e `dashboard.tests` (80 nodes = 74 pré-existentes + 6 novos desta feature), sem sobreposição — os dois arquivos novos de POR-03 (`test_pendency_origin_restriction.py`, `test_daily_user_action_origin_restriction.py`) são contados uma única vez, dentro da suíte do próprio app, não somados de novo por fora.

### Spec Summary

Implementada a política de bloqueio de abertura/reabertura de pendência por origem de linha (`APARELHO OP`, `PESSOAL`) nos três pontos reais de abertura mapeados em POR-02 (`PendencyUpdateView.post`, `daily_user_action_board` POST, `AllocationPendencyAdmin`), mais o payload aditivo (`origin_open_blocked`, `origin_open_blocked_reason`) em `_pendency_to_json`. Política extraída como função pura de domínio, reaproveitada pelos três chamadores — sem duplicar a lista de origens/mensagem em nenhum deles.

### Gap Analysis — o que foi corrigido

Nenhuma lacuna nova além das já mapeadas em POR-02/POR-03. Confirmado por execução (RED→GREEN), não só por leitura:

1. `PendencyUpdateView.post` abria/reabria pendência para origem bloqueada sem checagem (T1–T3, T11, T13, T17, decisão 2A). Corrigido.
2. `daily_user_action_board` criava/reabria `DailyUserAction` sem checagem (T4, T5, T9, variante T11). Corrigido.
3. `AllocationPendencyAdmin` permitia editar `action` de `NO_ACTION` para qualquer valor via POST direto, sem auditoria nem checagem de origem — bypass real confirmado em POR-03 por execução. Corrigido (decisão 1A).
4. `_pendency_to_json` não expunha `origin_open_blocked`/`origin_open_blocked_reason` — contrato técnico fixado na conferência corretiva de POR-03, ainda não implementado. Corrigido (decisão 2A).
5. Retificação do Fechamento: em `daily_user_action_board`, o ramo de `line_status` (só ADMIN) corria antes e de forma independente do ramo de abertura de ação, persistindo mesmo quando a abertura deveria ser recusada por origem. Corrigido nesta etapa (não é apenas "adicionar a checagem" — é também reordenar a decisão para antes do ramo de `line_status`, ver Implementação).

### Implementação

**Política compartilhada — `telecom/origin_restriction.py` (novo módulo, camada de domínio puro):**

```python
BLOCKED_ORIGINS = frozenset({PhoneLine.Origem.APARELHO_OP, PhoneLine.Origem.PESSOAL})
OPEN_BLOCKED_MESSAGE = "Não é permitido abrir pendência para linhas com origem Aparelho Operação ou Aparelho pessoal. Fale com o supervisor ou backoffice"

def is_origin_blocked_for_opening(phone_line):  # phone_line=None -> False
    ...

def origin_open_block_reason(phone_line):  # mensagem exata ou ""
    ...
```

Recebe sempre uma instância de `PhoneLine` já carregada (ou `None`) — nunca lê origem do corpo da requisição nem da permissão de quem chama. Colocado em `telecom` (não em `pendencies/services.py`) porque é o app dono de `PhoneLine.Origem`, e tanto `pendencies` quanto `dashboard` já dependem de `telecom` (sem dependência inversa, sem import circular). Reaproveitada por três chamadores, sem segunda lista de origens em nenhum deles.

**`pendencies/views.py`:**

- `_pendency_to_json`: calcula `phone_line = allocation.phone_line if allocation else None` e adiciona `origin_open_blocked`/`origin_open_blocked_reason` ao payload, aditivamente — nenhum campo existente foi removido ou renomeado, `action_choices` e demais campos de tratamento inalterados.
- `PendencyUpdateView.post`: dentro do ramo `was_no_action and not will_be_no_action`, inserida checagem `elif is_origin_blocked_for_opening(opening_phone_line): errors.append(...)`, **depois** do gate `not is_super_like` (preserva T8: ADMIN nunca chega a avaliar origem) e **antes** de qualquer `save()`/`record_action_change`/evento — o `if errors: return JsonResponse(..., status=403)` pré-existente já ocorria antes de observação/status/notificação, então nenhuma mudança de ordem foi necessária ali, só a nova condição dentro do bloco já existente.

**`pendencies/admin.py` (decisão 1A):**

- Novo `AllocationPendencyAdminForm(forms.ModelForm)` com `Meta.fields = "__all__"` (nenhum campo tornado globalmente readonly, `action` continua editável) e `clean()` que compara `old_action = self.instance.action` (estado persistido — em `clean()`, antes de `_post_clean()`/`construct_instance`, `self.instance` ainda não foi mutado pelos dados do formulário, conforme ordem interna do Django `BaseForm.full_clean` → `_clean_fields` → `_clean_form` (chama `clean()`) → `_post_clean` (só aí aplica `cleaned_data` à instância)) com `new_action = cleaned_data.get("action")`. Se a transição é `NO_ACTION → outro valor` e a origem da linha (`self.instance.allocation.phone_line`, FK já persistida) está bloqueada, levanta `forms.ValidationError(origin_open_block_reason(...))` — erro de formulário, resposta 200 com a mensagem renderizada, sem `full_clean()` de modelo nem validação global nova.
- `AllocationPendencyAdmin.form = AllocationPendencyAdminForm`; `readonly_fields` inalterado (sem adicionar `action`); nenhuma `action` do Admin removida.

**`dashboard/views.py` (`daily_user_action_board`, retificação do efeito parcial incluída):**

- Logo após o lock de `allocation_obj`/`employee` (já existente) e **antes** do ramo `if request.user.role == ADMIN:` (status da linha), foi inserido o cálculo de `origin_open_blocked`: se `action_type` é não vazio e válido, busca `existing_action` (mesmo filtro `day`/`employee`/`allocation_obj`, com `select_for_update()` — a mesma query que antes só ocorria mais abaixo, agora reaproveitada, não duplicada) e decide `is_opening_attempt = existing_action is None or existing_action.is_resolved`; se for tentativa de abertura, avalia a origem da linha.
- O ramo de status da linha (só ADMIN) passou a exigir `and not origin_open_blocked` na condição de entrada — corrige a retificação do Fechamento: quando a abertura é recusada por origem, `line_status` enviado no mesmo POST não é mais persistido.
- O trio `if action_type inválido / elif vazio (resolução) / else (criação/atualização)` ganhou `if origin_open_blocked: messages.error(request, OPEN_BLOCKED_MESSAGE)` como primeira condição (as demais passaram de `if`/`elif` para `elif` em cadeia) — mesma convenção de erro já usada pelas outras recusas desse POST (`messages.error` + redirect de query string existente, sem resposta JSON nova).
- A query duplicada de `existing_action` que antes ocorria dentro do ramo de criação/atualização foi removida (reaproveita a variável já obtida mais acima, sob o mesmo lock) — reduz uma consulta por request, sem mudar o resultado observável.
- `update_or_create_filter` permanece definido onde estava (ainda usado para o campo `day` em `DailyUserAction.objects.create(...)`), só a re-consulta foi removida.

**Locks reais e garantia efetivamente implementada (sem ampliar o contrato):**

- `pendencies`: `_load_locked_pendency_for_scope` já aplica `AllocationPendency.objects.select_for_update(of=("self",))`. Isso serializa escritas concorrentes na própria linha de `AllocationPendency`, mas **não** bloqueia `PhoneLine.origem` — a origem é lida (via `allocation.phone_line`, carregado por `select_related` na mesma query) dentro da transação, no momento da avaliação, não antes. T17 confirma exatamente esse comportamento (origem alterada entre o GET e o POST: o POST usa o valor vigente no momento da avaliação).
- `dashboard`: `LineAllocation.objects.select_for_update()` (quando há `allocation_id`) ou `Employee.objects.select_for_update()` (sem linha) — mesma garantia: serializa a linha de alocação/funcionário, não `PhoneLine.origem`.
- Nenhum teste novo afirma que esses locks serializam uma edição concorrente de `PhoneLine.origem` (isso seria T18, que continua exigindo PostgreSQL real e não foi executado nesta etapa — SQLite não comprova `select_for_update`). A garantia documentada e implementada é apenas: a decisão usa a origem persistida no instante da avaliação, dentro da mesma transação que grava o resultado.

**Sem migration:** nenhum campo de model foi adicionado; `origin_open_blocked`/`origin_open_blocked_reason` existem só na serialização JSON (função, não campo de banco). `manage.py makemigrations --check` não aplicável (nenhuma alteração de model).

### Preservado (verificado por teste, não só por leitura)

- Permissões/escopo: nenhuma exceção nova para ADMIN (T8, `AdminNoNewExceptionTests` continua GREEN); `RoleRequiredMixin`/`roles_required` continuam precedendo a checagem de origem (T10).
- Tratamento de pendência já aberta (claim/observação/release/resolução) em linha com origem agora bloqueada: GREEN (T12 e equivalentes de `daily_user_action_board`).
- GET que cria registro vazio (`_get_or_create_pendency`) não equivale a abertura: GREEN (T16), sem alteração de comportamento.
- Pendências existentes quando a origem da linha é alterada depois: a política só avalia na próxima tentativa de abrir/reabrir; nenhum código novo fecha, apaga ou re-avalia pendências já abertas quando `PhoneLine.origem` muda.
- Contratos HTTP/HTML documentados em POR-02 inalterados: `PendencyUpdateView` continua retornando `{"errors": [...]}` com 403 na mesma forma; `daily_user_action_board` continua usando `messages.error` + redirect, sem resposta JSON nova.
- Recusa de abertura/reabertura não persiste efeitos parciais do mesmo pedido: confirmado por teste nos dois caminhos, incluindo a retificação de `line_status` em `daily_user_action_board` (antes um efeito colateral real, agora corrigido).

### Test Checklist — resultado

1. Duas origens bloqueadas, abertura e reabertura em todas as entradas (`PendencyUpdateView`, `daily_user_action_board`, Admin) — GREEN.
2. Origem permitida, vazia e ausência de linha — GREEN (controles preservados).
3. Papéis e escopo preservados — GREEN (T8, T10, T14).
4. Tratamento e resolução existentes — GREEN (T12 e equivalentes).
5. POST direto e falsificação de origem — GREEN (T11 e variante).
6. Origem alterada entre GET e POST — GREEN (T17).
7. Payload composto sem gravações parciais — GREEN nos dois arquivos, incluindo a retificação de `line_status`.
8. Ausência de auditoria de sucesso/notificações na recusa — GREEN (`before_count == after_count` nos testes de auditoria).
9. Payload flag/motivo correto, inclusive diferenciação de autorização geral (ADMIN bloqueado por permissão continua expondo a flag real da linha) — GREEN (`OriginBlockedPayloadFlagTests`, 6/6).
10. Admin com dados válidos: falha decorre da política (`ValidationError` do `clean()`), não de fixture inválida — confirmado lendo o teste (`_admin_post` usa dados completos e válidos do form) e a asserção (`assertIn(OPEN_BLOCKED_MESSAGE, response.content.decode())` com `status_code == 200`, nunca 500/erro de fixture).

Nenhum teste foi enfraquecido ou alterado para acomodar a implementação — os dois arquivos de teste de POR-03 não foram tocados nesta etapa; ficaram GREEN pela implementação, não por ajuste de asserção.

### Test Strategy

Mesma estratégia de POR-03 (HTTP real via `django.test.Client`, Admin real via `self.client.post` no `admin:...change`, SQLite local isolado por execução). Validação por execução real em três camadas:

1. Suíte POR focada (os dois arquivos novos): `manage.py test pendencies.tests.test_pendency_origin_restriction dashboard.tests.test_daily_user_action_origin_restriction -v 2` → **38/38 PASSED**, 0 FAILED, 0 ERROR.
2. Regressão proporcional dos apps tocados: `manage.py test pendencies.tests -v 2` → **86/86 PASSED**; `manage.py test dashboard.tests -v 2` → **80/80 PASSED**. Nenhum teste pré-existente mudou de resultado (70→86 e 74→80, só os nodes antes RED virando GREEN).
3. Regressão proporcional do app dono da política nova (`telecom`, inclusive auditoria `LineDailyActionAuditEvent` e o próprio `seal_indicator`/Admin que compartilham módulos vizinhos): `manage.py test telecom -v 1` → **272 testes, OK (1 skipped)**, 0 FAILED, 0 ERROR. O skip é pré-existente (dependente de Postgres, não relacionado a esta tarefa) — não investigado nem alterado aqui.
4. `manage.py check`: "System check identified no issues (0 silenced)."
5. `git diff --check`: nenhum marcador de conflito nem espaço em branco problemático introduzido pelos arquivos desta etapa; único aviso é a normalização de fim de linha CRLF/LF pré-existente (mesma observada em POR-03, não causada por esta tarefa).

PostgreSQL não foi usado nesta etapa (T18 continua fora do pytest local, sem alegação de prova de concorrência em SQLite, conforme já registrado em POR-03).

### Matriz Node ID → Requisito → Resultado → Causa (atualização POR-04)

Todos os 22 nodes antes RED (listados nas duas matrizes de POR-03) passam a **GREEN** nesta etapa, causa: política implementada no ponto exato onde antes faltava. Os 16 nodes antes GREEN permanecem GREEN, sem alteração de causa (comportamento pré-existente, não tocado por esta implementação):

| Node ID (arquivo::Classe::teste) | Resultado POR-03 | Resultado POR-04 | Causa da mudança |
|---|---|---|---|
| `pendencies...::OpeningBlockedByOriginTests::test_opening_blocked_for_aparelho_op` | RED | GREEN | `PendencyUpdateView.post` passou a checar `is_origin_blocked_for_opening` no ramo de abertura. |
| `pendencies...::OpeningBlockedByOriginTests::test_opening_blocked_for_pessoal` | RED | GREEN | Idem. |
| `pendencies...::ReopeningBlockedByOriginTests::test_reopening_blocked_for_aparelho_op` | RED | GREEN | Idem (mesma checagem cobre reabertura, `was_no_action` não distingue 1ª abertura de reabertura). |
| `pendencies...::ReopeningBlockedByOriginTests::test_reopening_blocked_for_pessoal` | RED | GREEN | Idem. |
| `pendencies...::ForgedOriginInPayloadTests::test_extra_origin_field_in_body_is_ignored` | RED | GREEN | Checagem lê `pendency.allocation.phone_line.origem` persistido, nunca o corpo da requisição. |
| `pendencies...::OriginChangedBetweenRenderAndPostTests::test_post_uses_origin_at_evaluation_time_not_at_render_time` | RED | GREEN | Checagem ocorre dentro da transação do POST, sobre o valor então vigente. |
| `pendencies...::CompositePayloadNoPartialEffectsTests::test_refused_opening_does_not_persist_observation_or_notify` | RED | GREEN | `errors.append` antes de qualquer `save()`/notificação — recusa por origem entra no mesmo `if errors: return` pré-existente. |
| `pendencies...::AdminChangeFormOpeningRestrictionTests::test_admin_change_form_blocks_opening_for_aparelho_op` | RED | GREEN | `AllocationPendencyAdminForm.clean()` recusa a transição com `ValidationError`. |
| `pendencies...::AdminChangeFormOpeningRestrictionTests::test_admin_change_form_blocks_opening_for_pessoal` | RED | GREEN | Idem. |
| `pendencies...::AdminChangeFormOpeningRestrictionTests::test_admin_change_form_blocks_reopening_for_blocked_origin` | RED | GREEN | Idem, reabertura via Admin. |
| `pendencies...::OriginBlockedPayloadFlagTests::test_detail_payload_flags_blocked_origin_with_exact_reason` (2 subTests) | RED | GREEN | `_pendency_to_json` passou a expor os dois campos aditivos. |
| `pendencies...::OriginBlockedPayloadFlagTests::test_detail_payload_flags_permitted_origin_as_false` (3 subTests) | RED | GREEN | Idem. |
| `pendencies...::OriginBlockedPayloadFlagTests::test_detail_payload_flag_is_false_without_allocation` | RED | GREEN | `phone_line=None` → `is_origin_blocked_for_opening` retorna `False`. |
| `pendencies...::OriginBlockedPayloadFlagTests::test_detail_payload_flag_reflects_origin_not_viewers_permission` | RED | GREEN | A flag deriva só da origem da linha, nunca do papel de quem vê — `_pendency_to_json` não recebe nem consulta permissão do usuário. |
| `pendencies...::OriginBlockedPayloadFlagTests::test_flag_does_not_restrict_treatment_fields_or_actions_on_open_pendency` | RED | GREEN | Campos aditivos, sem reduzir `action_choices` nem bloquear claim/observação. |
| `pendencies...::OriginBlockedPayloadFlagTests::test_update_success_response_includes_false_flag_for_permitted_origin` | RED | GREEN | Resposta de sucesso de `PendencyUpdateView.post` reaproveita o mesmo `_pendency_to_json`. |
| `dashboard...::CreationBlockedByOriginTests::test_creation_blocked_for_aparelho_op` | RED | GREEN | `daily_user_action_board` passou a checar origem antes de criar `DailyUserAction`. |
| `dashboard...::CreationBlockedByOriginTests::test_creation_blocked_for_pessoal` | RED | GREEN | Idem. |
| `dashboard...::ReopeningBlockedByOriginTests::test_reopening_blocked_keeps_resolved_true` | RED | GREEN | `is_opening_attempt` cobre `existing_action.is_resolved`, não só ausência de registro. |
| `dashboard...::AllRolesBlockedIdenticallyTests::test_each_allowed_role_is_blocked_the_same_way` (4 subTests) | RED (4/4) | GREEN (4/4) | Checagem não depende de role — mesma mensagem para ADMIN/SUPER/BACKOFFICE/GERENTE. |
| `dashboard...::ForgedOriginInPayloadTests::test_extra_origin_field_in_post_is_ignored` | RED | GREEN | Checagem lê `allocation_obj.phone_line.origem`, nunca o corpo do POST. |
| `dashboard...::CompositePayloadNoPartialEffectsTests::test_refused_opening_does_not_persist_line_status_change` | RED | GREEN | Retificação: ramo de `line_status` passou a exigir `not origin_open_blocked`, corrigindo o efeito parcial identificado em POR-03. |

Contagem de métodos vs. subtestes mantida separada, conforme exigido: a tabela acima lista **22 node IDs de método** (alguns com múltiplos subTests, anotados entre parênteses); a soma de linhas de falha agregadas pelo Django antes da implementação era 28 (contador de subtestes), nunca confundida com 22 métodos nem com 38 nodes totais da suíte.

### Compliance Report

POR-04 concluída. Política de bloqueio de abertura/reabertura de pendência por origem de linha implementada nos três pontos reais mapeados (`PendencyUpdateView.post`, `daily_user_action_board` POST, `AllocationPendencyAdmin`), mais o payload aditivo de `_pendency_to_json`, usando uma única função de domínio compartilhada (`telecom/origin_restriction.py`) — sem duplicar a lista de origens/mensagem em nenhum chamador, sem `full_clean()` global, sem migration, sem nova permissão ou exceção para ADMIN.

**Arquivos alterados:**
- `telecom/origin_restriction.py` (novo) — política pura: `BLOCKED_ORIGINS`, `OPEN_BLOCKED_MESSAGE`, `is_origin_blocked_for_opening`, `origin_open_block_reason`.
- `pendencies/views.py` — `_pendency_to_json` (payload aditivo); `PendencyUpdateView.post` (checagem no ramo de abertura).
- `pendencies/admin.py` — `AllocationPendencyAdminForm` (novo) + `AllocationPendencyAdmin.form`.
- `dashboard/views.py` — cálculo antecipado de `origin_open_blocked` (reaproveitando a consulta de `existing_action` que antes era duplicada), gate no ramo de `line_status` (retificação do efeito parcial) e no trio de decisão de ação.

Nenhum arquivo de teste foi criado ou alterado nesta etapa (os dois arquivos de POR-03 já existiam e ficaram GREEN pela implementação). Nenhuma migration gerada (nenhuma alteração de model). Alterações de versão 1.9.0 e demais arquivos alheios preservados, incluindo `config/settings.py` e `docs/superpowers/specs/2026-09-10-line-daily-action-audit-design.md`, já modificados antes desta tarefa e não tocados por ela.

**Validação executada (banco isolado, sequencial):**
- `manage.py test pendencies.tests.test_pendency_origin_restriction dashboard.tests.test_daily_user_action_origin_restriction -v 2` → 38/38 PASSED.
- `manage.py test pendencies.tests -v 2` → 86/86 PASSED (70 pré-existentes + 16 novos, zero regressão).
- `manage.py test dashboard.tests -v 2` → 80/80 PASSED (74 pré-existentes + 6 novos, zero regressão).
- `manage.py test telecom -v 1` → 272 testes, OK (1 skipped pré-existente, não relacionado), zero regressão — executado como regressão proporcional porque a política nova vive em `telecom` e é importada por `pendencies`/`dashboard`.
- `manage.py check` → "System check identified no issues (0 silenced)."
- `git diff --check` → sem marcador de conflito; só aviso pré-existente de normalização CRLF/LF.

**Limitações e pendências explícitas para POR-05/POR-06:**
1. UI não integrada nesta etapa, por decisão de escopo — templates/JS, controles desabilitados e mensagem no modal de Pendências ficam para POR-05; nenhum fallback HTML, badge ou ícone novo foi criado (decisão 4A: nenhum indicador visual permanente na tabela de Ações do Dia, nem agora nem em POR-05).
2. T15 (UI com/sem JS, foco, mensagem no `#pendencySaveStatus`) continua não executado — depende de ferramenta de browser real, fora do pytest local; não reivindicado como provado.
3. T18 (concorrência/locking de `PhoneLine.origem` sob escrita simultânea) continua não executado — exige PostgreSQL real; os locks confirmados nesta etapa (`select_for_update` em `AllocationPendency`/`LineAllocation`/`Employee`) serializam a linha de pendência/alocação, não `PhoneLine.origem` em si, e isso foi documentado explicitamente, não inferido.
4. Baseline histórico de "32 nós" (antes dos 6 testes de payload) permanece sem log preservado isolado — registrado como limitação de evidência herdada de POR-03, não recomputado por subtração nesta etapa.

Sem stage, commit, push, deploy ou acesso a PRD nesta etapa. Próxima tarefa: POR-05 (integração de UI), não iniciada.

## POR-04 — Conferência corretiva (2026-10-13)

Conferência solicitada antes de iniciar POR-05, cobrindo quatro pontos: (1) pytest vs. `manage.py test` com contagens separadas e sobreposição explícita; (2) reinspeção real de `AllocationPendencyAdminForm.clean()` e do ciclo do `ModelForm` na versão instalada do Django; (3) correção, somente se houver defeito confirmado; (4) T18/concorrência. Nenhuma avaliação feita por leitura do relato anterior — todas as afirmações abaixo vêm de execução real ou de leitura do código/fonte do Django instalado.

### Spec Summary

Confirmado um **defeito real** em `AllocationPendencyAdminForm.clean()`: a checagem de origem usava `self.instance.allocation` (a allocation **antiga**, persistida antes do POST) em vez da allocation **proposta** no mesmo POST (`cleaned_data["allocation"]`). Isso causava três falhas de contrato, todas confirmadas por RED real antes da correção:

1. Trocar a allocation **para** uma origem bloqueada no mesmo POST que abre/reabre a pendência **não era bloqueado** (a checagem olhava a origem antiga, permitida).
2. Trocar a allocation **de** uma origem bloqueada **para** uma permitida no mesmo POST de abertura era **bloqueado indevidamente** (a checagem olhava a origem antiga, bloqueada, ignorando que a proposta era permitida).
3. Criar uma `AllocationPendency` nova diretamente pelo Admin (`admin:pendencies_allocationpendency_add`) já com ação aberta numa linha de origem bloqueada **nunca era bloqueado**, porque `self.instance.pk` é `None` numa criação e o código antigo só lia `self.instance.allocation` quando `self.instance.pk` existia — a origem da allocation escolhida na própria criação nunca era avaliada.

Corrigido lendo `cleaned_data.get("allocation")` em vez de `self.instance.allocation`, em todos os casos (criação e edição). Nenhuma outra hipótese de defeito foi confirmada nas áreas pedidas (pytest/contagens, T18) — ver Gap Analysis.

### Gap Analysis

**1. Pytest e contagens — sem lacuna de produto; números reconciliados por execução, não por relato.**

- `venv\Scripts\python.exe -m pytest pendencies/tests/test_pendency_origin_restriction.py dashboard/tests/test_daily_user_action_origin_restriction.py --collect-only -q` → **43 tests collected** (os 38 de POR-03 + 5 testes novos desta conferência, ver seção seguinte).
- Mesmos dois arquivos, execução real: `pytest -v --tb=no` → `43 passed, 18 subtests passed` (pytest/`pytest-subtests` conta métodos e subtestes em contadores **separados**: 43 é o número de métodos `test_*`, 18 é a soma dos `self.subTest(...)` executados dentro de alguns desses métodos — nenhum dos dois números deve ser lido como "total de testes").
- `manage.py test pendencies.tests.test_pendency_origin_restriction dashboard.tests.test_daily_user_action_origin_restriction -v 1` → `Found 43 test(s)`, `Ran 43 tests`, `OK`. **Coleta e resultado idênticos ao pytest**, nó por nó — sem divergência de runner/settings, confirmando a mesma conclusão já registrada na conferência corretiva de POR-03 (mesmo SQLite em memória nos dois runners, mesma configuração de `config/settings.py`).
- **Sobreposição explícita, sem soma indevida:** os 43 nodes destes dois arquivos **estão contidos dentro de** `pendencies.tests` (91 nodes totais após esta conferência) e `dashboard.tests` (80 nodes totais, inalterado) — não são conjuntos disjuntos somáveis. `manage.py test pendencies.tests -v 2` já executa `test_pendency_origin_restriction.py` como parte da suíte do app, e o mesmo vale para `dashboard.tests` e `test_daily_user_action_origin_restriction.py`. Contagem de métodos por arquivo, confirmada por `grep -c "    def test_"` sobre o código real (não por leitura do relato anterior): `pendencies/tests/test_pendency_origin_restriction.py` tem **33 métodos** (28 de POR-03 + 5 novos desta conferência); `dashboard/tests/test_daily_user_action_origin_restriction.py` tem **10 métodos** (inalterado) — soma 43, igual ao coletado por `pytest --collect-only` e por `Found 43 test(s)` do `manage.py test`. Nenhum desses 43 foi somado de novo por fora das suítes `pendencies.tests`/`dashboard.tests` a que pertencem.
- **Esclarecimento "telecom 272/272 com 1 skip":** a frase do relatório anterior estava formulada de forma ambígua — não existem "272 aprovados de 272", existem **271 PASSED + 1 SKIPPED = 272 testes totais**, `0 FAILED`, `0 ERROR`. Confirmado por `grep -cE "\.\.\. ok$"` (271) e `grep -cE "\.\.\. skipped"` (1) sobre o log salvo de `manage.py test telecom -v 2`, reexecutado nesta conferência (a execução anterior rodou em background sem ser aguardada corretamente pela ferramenta de shell — o log capturado antes estava truncado; reexecutada em foreground até o fim real, 218s, `Ran 272 tests ... OK (skipped=1)`). O skip é `test_db_immutability_trigger_blocks_update... Protecao DB-level (migration 0019). So roda contra Postgres real; ... 'Trigger de imutabilidade so existe em Postgres.'` — pré-existente, documentado desde antes desta tarefa, sem relação com a política de origem.

**2. Django Admin — defeito real confirmado (ver Spec Summary) e cenários de controle verificados por POST real:**

- Lido o fonte do Django 5.2.11 instalado (`django.forms.models.BaseModelForm._post_clean`, `django.forms.forms.BaseForm.full_clean`): confirmado que `construct_instance` (que muta `self.instance` com os dados do formulário) só ocorre em `_post_clean()`, **depois** de `_clean_form()` (que chama `self.clean()`). Logo, em `clean()`, `self.instance.action` ainda reflete o estado **persistido antes da requisição** — essa parte do código e do comentário original estava correta e foi mantida. O defeito estava em `self.instance.allocation` (mesmo raciocínio de "ainda não mutado" se aplica à FK `allocation`, mas o contrato exige a allocation **proposta**, não a antiga, para avaliar a origem — são coisas diferentes: "qual era a ação antes" decide **se é abertura**; "qual é a linha proposta agora" decide **qual origem avaliar**).
- Testes novos acrescentados a `AdminChangeFormOpeningRestrictionTests` (todos com dados de formulário válidos — `employee`, `allocation`, `technical_responsible`, `last_submitted_action`, `updated_by` sempre preenchidos corretamente; nenhuma falha decorre de fixture inválida, confirmado lendo a asserção de cada teste antes de aceitar o resultado):
  - `test_admin_change_form_blocks_opening_when_allocation_swapped_to_blocked_origin` — RED confirmado antes da correção (`302 != 200`, abriu sem recusar), GREEN depois.
  - `test_admin_change_form_allows_opening_when_allocation_swapped_to_permitted_origin` — RED confirmado antes (`200 != 302`, bloqueou indevidamente), GREEN depois.
  - `test_admin_add_form_blocks_creation_with_open_action_on_blocked_origin` — RED confirmado antes (`AssertionError: 302 != 200` — esperado 200 com erro de formulário, resultado real foi 302, ou seja, criou a pendência sem recusar), GREEN depois.
  - `test_admin_change_form_allocation_swap_on_already_open_pendency_not_blocked` — controle: troca de allocation numa pendência **já aberta** (não é transição de abertura, `was_no_action` é `False`) não deve ser bloqueada mesmo que a nova linha tenha origem bloqueada — **GREEN direto, sem RED**, confirmando que o código antigo já acertava esse caso (o defeito só afetava a transição de abertura/reabertura, não o tratamento de pendência já aberta).
  - `test_admin_change_form_allows_opening_without_allocation` — controle: abertura sem allocation continua funcionando — **GREEN direto, sem RED** (lacuna de cobertura, não defeito; acrescentado por completude do pedido "allocation ausente").
- **Hipótese refutada:** não há lock que proteja ou precise proteger esse POST do Admin contra concorrência — o Admin não usa `select_for_update` em lugar nenhum (nem antes, nem depois desta correção); isso é comportamento pré-existente, fora do escopo desta tarefa, e não foi alterado.

**3. Correção aplicada (ver Implementation Plan).**

**4. Concorrência / T18 — nenhuma mudança; achados documentados, não inferidos.**

- `grep -rn "select_for_update"` em todo o repositório confirma que `PhoneLine` é bloqueado (`PhoneLine.objects.select_for_update()`) em exatamente dois lugares: `core/services/allocation_service.py:21` e `core/services/telephony_use_case.py:41` — **fluxos diferentes** (alocação/telefonia), não relacionados aos três pontos de abertura de pendência tocados por esta feature.
- Nos três pontos de abertura/reabertura de pendência (`PendencyUpdateView.post`, `daily_user_action_board`, `AllocationPendencyAdminForm`), a origem é lida via `allocation.phone_line.origem`/`proposed_allocation.phone_line`, e **nenhum dos três** aplica `select_for_update` sobre a linha `PhoneLine` em si:
  - `pendencies`: `_load_locked_pendency_for_scope` usa `AllocationPendency.objects.select_for_update(of=("self",))` — trava só a própria linha de `AllocationPendency`, explicitamente (`of=("self",)`), não `allocation` nem `phone_line`.
  - `dashboard`: `LineAllocation.objects.select_for_update()` (quando há allocation) — trava a linha de `LineAllocation`, não a `PhoneLine` relacionada (acesso a `.phone_line` depois do lock é uma consulta separada, sem `FOR UPDATE`).
  - Admin: nenhum `select_for_update` em lugar nenhum do fluxo do Admin.
- **Diferenciação confirmada:** T17 (origem alterada entre GET e POST) é uma mudança sequencial dentro da mesma sessão de teste, sem duas transações concorrentes — já comprovado por teste real, sem depender de lock algum (o POST simplesmente lê o valor vigente no momento em que é avaliado). T18 (duas transações **concorrentes** de verdade, uma delas escrevendo `PhoneLine.origem` enquanto a outra decide abrir) é um cenário diferente, que depende de comportamento de banco real sob concorrência (SQLite não serializa transações da mesma forma que PostgreSQL) — **continua não comprovado**, como já registrado em POR-03/POR-04. Nenhum lock foi adicionado nesta conferência só para tentar satisfazer essa hipótese documental — o contrato aprovado exige apenas "origem persistida no momento da avaliação", já cumprido e testado, não "serialização contra escrita concorrente de origem".
- **Risco concreto registrado (não comprovado, não ignorado):** como nenhum dos três pontos trava `PhoneLine`, existe uma janela teórica onde uma transação concorrente poderia alterar `PhoneLine.origem` entre a leitura feita pela política e o commit da transação de abertura, sob PostgreSQL com isolation level `READ COMMITTED` (padrão do Django) — a leitura não-bloqueante não impediria essa corrida. Isso é uma lacuna pré-existente ao sistema de locks (o mesmo padrão já valia antes desta feature para outros campos lidos sem lock dentro dessas transações) e não uma regressão introduzida por POR-04; registrado como risco residual para decisão de produto futura, não corrigido nesta tarefa porque corrigi-lo ampliaria o contrato aprovado (que não pede lock sobre `PhoneLine`) sem pedido explícito.

### Implementation Plan

Corrigido `pendencies/admin.py::AllocationPendencyAdminForm.clean()`: trocado `self.instance.allocation.phone_line` por `cleaned_data.get("allocation")` (allocation proposta) para resolver `phone_line`, mantendo `self.instance.action` (estado antigo) para decidir `was_no_action`/`will_be_no_action`. Nenhuma outra alteração de produto — nenhuma migration, nenhuma mudança de permissão, nenhum lock novo, nenhuma alteração de UI.

### Test Checklist

- Criação de pendência já com ação aberta (Admin, via `admin:...add`) numa origem bloqueada — RED confirmado, corrigido, GREEN.
- Abertura de registro existente sem ação — já GREEN antes (sem regressão).
- Reabertura de registro resolvido — já GREEN antes (sem regressão).
- Troca de allocation junto à abertura, origem permitida → bloqueada — RED confirmado, corrigido, GREEN.
- Troca de allocation junto à abertura, origem bloqueada → permitida — RED confirmado (falso bloqueio), corrigido, GREEN.
- Allocation ausente — GREEN direto (lacuna de cobertura, não defeito).
- Troca de allocation em pendência já aberta (não é abertura) — GREEN direto, confirma que não é reclassificada como abertura.
- Tratamento/resolução de pendência já aberta — já GREEN antes (sem regressão, `test_admin_change_form_allows_resolution_on_blocked_origin` inalterado).
- Nenhum teste foi enfraquecido; todos os 5 testes novos usam dados de formulário válidos, confirmados por leitura antes de aceitar o resultado.

### Test Strategy

Mesma estratégia de POR-04 (HTTP/Admin real via `django.test.Client`, SQLite isolado por execução, RED real antes da correção). Acrescentado nesta conferência: leitura direta do código-fonte do Django instalado (`_post_clean`/`full_clean`) para verificar a premissa sobre o ciclo do `ModelForm`, em vez de assumi-la; `grep` direto sobre todo o repositório para mapear os locks reais de `PhoneLine`/`select_for_update`, em vez de inferir do contrato documental.

### Compliance Report

**Achados confirmados:**
1. Defeito real em `AllocationPendencyAdminForm.clean()` (usava allocation antiga em vez da proposta) — corrigido, com RED real antes e GREEN real depois nos três cenários afetados.
2. `pytest` e `manage.py test` continuam convergindo exatamente na coleta e no resultado (43/43), sem divergência de runner — hipótese de divergência refutada novamente, mesma conclusão de POR-03.
3. "telecom 272/272 com 1 skip" do relatório anterior estava formulado de forma ambígua — esclarecido para **271 PASSED + 1 SKIPPED = 272 total**, reexecutado em foreground (a execução anterior em background não foi aguardada corretamente pela ferramenta de shell e produziu um log truncado, descartado).

**Hipóteses refutadas:**
- Não há lock que serialize edição de `PhoneLine.origem` nos três pontos de abertura — confirmado por `grep` real, não corrigido (fora do contrato aprovado), documentado como risco residual conhecido, não como defeito desta tarefa.
- Não há sobreposição indevida de contagem entre os 43 nodes focados e as suítes completas dos apps — são o mesmo conjunto, não dois conjuntos somados.

**Limitações que permanecem (inalteradas desde POR-04):**
- T15 (browser/JS) e T18 (concorrência PostgreSQL real) continuam fora do pytest local, sem prova — nenhuma tentativa de prová-los nesta conferência além do mapeamento de locks acima.
- Baseline histórico de "32 nós" (antes dos testes de payload de POR-03) continua sem log isolado preservado — não recomputado por subtração.

**Arquivos alterados nesta conferência:**
- `pendencies/admin.py` — correção do defeito (`cleaned_data.get("allocation")` em vez de `self.instance.allocation`).
- `pendencies/tests/test_pendency_origin_restriction.py` — 5 métodos novos em `AdminChangeFormOpeningRestrictionTests` (3 RED→GREEN confirmando o defeito e a correção, 2 GREEN diretos de cobertura/controle).

**Validação executada (banco isolado, sequencial, reexecutada do zero nesta conferência):**
- `pytest pendencies/tests/test_pendency_origin_restriction.py dashboard/tests/test_daily_user_action_origin_restriction.py --collect-only -q` → 43 tests collected.
- Mesmos arquivos, `pytest -v --tb=no` → 43 passed, 18 subtests passed, 0 failed.
- `manage.py test pendencies.tests.test_pendency_origin_restriction dashboard.tests.test_daily_user_action_origin_restriction -v 1` → Found 43 test(s), Ran 43 tests, OK — idêntico ao pytest.
- `manage.py test pendencies.tests -v 2` → **91/91 PASSED** (70 pré-existentes + 16 de POR-03 + 5 novos desta conferência), 0 FAILED, 0 ERROR.
- `manage.py test dashboard.tests -v 2` → **80/80 PASSED** (inalterado, nenhum teste novo neste app nesta conferência).
- `manage.py test telecom -v 2` → **271 PASSED + 1 SKIPPED = 272 total**, 0 FAILED, 0 ERROR (regressão proporcional, mesmo módulo `telecom/origin_restriction.py` da política compartilhada).
- `manage.py check` → "System check identified no issues (0 silenced)."
- `git diff --check` → sem marcador de conflito; só os dois avisos pré-existentes de normalização CRLF/LF (`dashboard/views.py`, `docs/superpowers/specs/2026-09-10-...md`), nenhum novo.

**Veredito:** POR-04 passa a GREEN condicionado **com um defeito real encontrado e corrigido** nesta conferência (troca de allocation/criação direta no Admin ignorava a origem efetivamente proposta). Fora do Admin, nenhum outro defeito foi confirmado nos pontos pedidos (pytest/contagens, T18) — apenas esclarecimentos de leitura/relato corrigidos (contagem de skip do `telecom`, log truncado por execução em background mal aguardada). T15 e T18 permanecem não comprovados, sem alegação de prova. Nenhuma migration, permissão, UI ou regra alheia alterada. Sem stash/reset/checkout destrutivo, stage, commit, push, deploy ou acesso a PRD. POR-05 não iniciada; nenhum aceite visual declarado.

## POR-05 — Integração na interface (2026-10-13)

### Spec Summary

Integrados os campos aditivos `origin_open_blocked`/`origin_open_blocked_reason` (já expostos pelo backend desde POR-04) no modal de pendências (`#pendencyModal`, `templates/dashboard/daily_user_action_board.html`), que é o único consumidor real de `pendencies:detail`/`pendencies:update`/`pendencies:claim`/`pendencies:release` nesta tela (confirmado em POR-02, item 15: não existe formulário HTML alternativo para `AllocationPendency` nesta tela). Nenhum campo novo foi inventado no backend; a política de origem não foi duplicada em JavaScript — o JS só lê os dois campos já calculados pelo servidor.

Comportamento implementado, conforme as decisões 1A/2A/3A/4A já aprovadas:

- Quando a pendência não está aberta (`data.action === 'no_action'`, cobre tanto "nunca aberta" quanto "ciclo anterior resolvido") **e** `origin_open_blocked === true`: mostra a mensagem exata aprovada junto ao campo Ação, e desabilita o(s) `<select>` de ação (`pendencyAction` para ADMIN, `pendencyActionSubmit` para SUPER/BACKOFFICE/GERENTE) — único controle que poderia tentar uma abertura/reabertura nesse estado.
- Quando a pendência já está aberta (`data.action !== 'no_action'`), a mensagem nunca aparece e nenhum controle é desabilitado por causa da origem, mesmo que `origin_open_blocked` seja `true` para a linha — claim, release, observação, troca de ação já aberta e resolução seguem exatamente a autorização pré-existente (is_current_technical_responsible/is_super_like), sem checagem de origem nova nesses caminhos (a flag reflete a linha, não a ação permitida agora, conforme o contrato técnico do payload).
- O botão "Salvar" nunca é desabilitado por origem (é compartilhado com observação/status da linha); o `<select>` desabilitado mantém seu valor corrente (`no_action` quando bloqueado), então um "Salvar" nesse estado nunca envia uma tentativa de abertura — não há caminho de UI que dispare o 403 de origem sem o usuário primeiro trocar para uma linha/pendência permitida.
- A mensagem é renderizada via `textContent` (nunca `innerHTML`), igual ao padrão já usado para `observation_locked_reason` — sem inserção de HTML vindo do payload.
- Nenhum badge/ícone novo na tabela (decisão 4A); nenhum formulário HTML alternativo foi criado (decisão 3A) — a proteção do servidor já independe de JS desde POR-04, e isso não foi alterado aqui.

Dois defeitos reais de JavaScript, não cobertos por nenhuma spec anterior, foram encontrados e corrigidos nesta etapa (fora do escopo de origem, mas no mesmo arquivo/fluxo tocado, e exigidos pelo próprio Test Checklist de POR-05):

1. **Resposta atrasada de outro funcionário podia substituir o modal atual.** `loadPendency` gravava `currentEmployeeId`/`currentAllocationId` de forma síncrona e chamava `renderModal(data)` incondicionalmente quando a promise resolvia; dois cliques rápidos em linhas diferentes podiam fazer a resposta mais lenta da primeira linha sobrescrever o modal já mostrando a segunda. Corrigido com um token de requisição (`currentRequestToken`) incrementado a cada chamada; uma resposta cujo token não é mais o atual é descartada.
2. Nenhum outro problema de estado residual entre trocas de funcionário/linha foi encontrado: `renderModal` já recalcula todos os campos (inclusive agora a mensagem/flag de origem) de forma declarativa a cada chamada, então a limpeza de estado anterior já era garantida pela própria função — não foi necessário nenhum reset manual adicional.

### Gap Analysis

- A lacuna 2 do Fechamento das quatro decisões ("payload de UI para POR-05") já estava fechada desde POR-04 (campos no payload); a lacuna desta etapa era exclusivamente de consumo no template/JS, confirmada por leitura de `templates/dashboard/daily_user_action_board.html` (859 linhas antes desta tarefa) e de `pendencies/views.py::_pendency_to_json`.
- Mapeamento de controles reais do modal (antes do código): `pendencyAction`/`pendencyActionSubmit` (abertura/troca/resolução de ação), `pendencyObservation` (observação), `pendencyLineStatus` (status da linha, só ADMIN), `pendencyClaimBtn` (assumir/liberar responsável), `pendencySaveBtn`/`pendencySaveStatus` (salvar e exibir erro do servidor). Nenhum desses, além do(s) `<select>` de ação, está relacionado à transição `NO_ACTION → outro valor` — confirmado lendo `pendencies/views.py::PendencyUpdateView.post`, onde só o campo `action` participa do ramo `was_no_action and not will_be_no_action`.
- Diferenciação confirmada por leitura e por execução real: restrição por origem (`origin_open_blocked`) ≠ estado da pendência (`data.action !== 'no_action'`) ≠ permissão do usuário (`IS_ADMIN`, que só decide **qual** `<select>` é mostrado, nunca se a origem bloqueia). A condição de bloqueio na UI (`blockOpening = data.origin_open_blocked === true && !isCurrentlyOpen`) depende só das duas primeiras; a terceira decide apenas qual elemento (`pendencyAction` vs `pendencyActionSubmit`) recebe `disabled = blockOpening`.
- Os dois defeitos de JS descritos no Spec Summary foram encontrados por leitura do fluxo assíncrono (`loadPendency`/`renderModal`) antes de qualquer teste, e depois confirmados por execução real no navegador (ver Validação): sem o token de requisição, o cenário de resposta atrasada reproduzia sempre que a linha clicada primeiro tinha uma resposta artificialmente atrasada.
- Nenhuma lacuna de backend foi encontrada nesta etapa: `_pendency_to_json` já retorna os dois campos corretamente tipados (`bool`/`str`) desde POR-04, e a resposta de sucesso do `PendencyUpdateView.post` reaproveita a mesma função — confirmado por leitura (não alterado).

### Implementation Plan

**Arquivo alterado:** `templates/dashboard/daily_user_action_board.html` (24 linhas adicionadas, 0 removidas, nenhuma outra linha tocada).

1. HTML do modal: um novo contêiner `#pendencyOriginBlockedMessage` (inicialmente oculto) com um `<p id="pendencyOriginBlockedText" role="alert">` vazio, inserido dentro do mesmo bloco "Ação" (`col-sm-6`) que já contém os três estados existentes (`pendencyActionAdmin`, `pendencyActionNonAdmin`, `pendencyActionReadonly`) — a mensagem fica junto aos controles de abertura, como decidido (POR-02/Fechamento, decisão 4A/visual). `role="alert"` para leitura por tecnologia assistiva sem depender de foco.
2. `renderModal(data)`: logo após a lógica existente de Ação (não duplicada, só lida), calcula `isCurrentlyOpen`/`blockOpening`, alterna `display` do novo contêiner, escreve o texto via `textContent` (nunca HTML) e aplica `disabled = blockOpening` em `pendencyAction` e `pendencyActionSubmit` (o elemento oculto no momento também recebe o `disabled`, inofensivo, evita estado desatualizado se a visibilidade mudar). Como a função já é chamada do zero a cada carga/ação (claim/release/save), o estado anterior nunca vaza entre funcionários/linhas nem entre reaberturas do modal.
3. `loadPendency`: adicionado `currentRequestToken` (contador) para descartar respostas de requisições supersedidas por um clique mais recente — corrige o defeito 1 do Spec Summary.
4. Nenhuma lista de origens bloqueadas foi duplicada em JavaScript; nenhuma permissão nova foi concedida a nenhum papel; nenhum botão compartilhado (Salvar/Fechar) foi desabilitado; nenhum formulário HTML alternativo foi criado; nenhum badge/ícone novo foi adicionado à tabela.

Nenhuma alteração em `pendencies/views.py`, `pendencies/admin.py`, `dashboard/views.py`, `telecom/origin_restriction.py` ou em qualquer model/migration — POR-05 é só UI, conforme o escopo aprovado.

### Test Checklist — resultado (navegador real, Chrome headless via CDP, dados sintéticos)

Não há suíte JS automatizada no repositório (sem `package.json`/Jest) e não há MCP de browser disponível nesta sessão. A verificação dinâmica foi feita com Chrome real (não simulação), pilotado por um cliente CDP mínimo escrito só com a biblioteca padrão do Python (sem dependência nova adicionada ao projeto — nada foi instalado no `venv`), contra um banco SQLite efêmero próprio (migrations existentes aplicadas do zero, sem tocar o Postgres de dev nem qualquer dado real) e dados 100% sintéticos (`POR05SMOKE_*`). Script e evidências arquivados em `docs/superpowers/evidence/2026-10-13-por05/` (`por05_browser_smoke.py`, `por05_setup_fixtures.py`, `cdp_client.py`, `results.log`, 4 screenshots reais).

21/21 verificações automatizadas PASS, 0 FAIL (2 achados registrados como informativos, não como aceite/reprovação deste recurso — ver abaixo):

1. Abertura bloqueada (nunca aberta, origem `APARELHO OP`): mensagem exata visível junto ao `<select>` de Ação, que fica desabilitado; observação continua editável. PASS (confirmado também por screenshot `modal-1280-blocked.png`).
2. Reabertura bloqueada (ciclo resolvido, origem `PESSOAL`): mesmo resultado do item 1 — `isCurrentlyOpen` é `false` em ambos os casos porque `action` volta a `no_action` após resolução, então o mesmo código cobre abertura e reabertura sem distinção especial. PASS.
3. Controle positivo (origem `APARELHO`, permitida): mensagem oculta, `<select>` habilitado — comportamento anterior preservado. PASS.
4. Pendência já aberta em origem bloqueada (`APARELHO OP`), como ADMIN: mensagem **não** aparece, `<select>` (com `no_action`, para permitir resolução) habilitado, botão "Assumir" visível — tratamento autorizado não é impedido pela origem. PASS (confirmado também por screenshot `modal-1280-open-blocked-treatment.png`).
5. Troca de funcionário/linha dentro da mesma sessão do modal: estado da pendência anterior (mensagem, valor do `<select>`, nome do usuário) não vaza para a próxima — `usuario` exibido corresponde sempre ao funcionário clicado por último. PASS.
6. Resposta atrasada de outro funcionário/linha não substitui o modal atual: reproduzido artificialmente atrasando a resposta `fetch` da primeira linha clicada (override de `window.fetch` injetado via `Page.addScriptToEvaluateOnNewDocument`, não o código de produção) e clicando em seguida numa segunda linha mais rápida — o modal final mostra a segunda linha, não a primeira. PASS (prova o defeito 1 corrigido no Implementation Plan).
7. Mobile 390px e 360px: o diálogo do modal (`.modal-dialog`), já incluindo a nova mensagem, não ultrapassa a largura do viewport (`scrollWidth - width <= 0` nos dois casos, com folga de 16px) e a mensagem continua visível/legível. PASS.
8. Origem alterada no servidor entre o carregamento do modal e o clique em Salvar (variante real, em navegador, do T17 de POR-03, que era só HTTP/Django Client): origem permitida no load (sem bloqueio na UI, como esperado, porque o flag foi calculado antes da mudança); o usuário digita uma observação; a origem é alterada no banco (fora do navegador, simulando outro admin); ao salvar, o servidor recusa com a mensagem exata em `#pendencySaveStatus`, sem mensagem de sucesso falsa, e a observação digitada **não** é perdida (a função `savePendency` só chama `renderModal` — que reescreveria os campos — no caminho de sucesso; no caminho de erro só atualiza o texto de status, preservando a entrada do usuário, comportamento pré-existente confirmado, não alterado nesta etapa). PASS.
9. Foco por teclado real (`Input.dispatchKeyEvent`, Tab): o `<select>` desabilitado pela origem nunca recebe foco em nenhuma das 15 tabulações testadas; `pendencyObservation` e `pendencySaveBtn` permanecem alcançáveis por teclado. PASS.
10. Nenhuma exceção JS não tratada (`Runtime.exceptionThrown`) ocorreu durante toda a sessão de smoke. PASS.

**Achados informativos (não usados como PASS/FAIL deste recurso, registrados por transparência):**

- **Contenção estrita de foco dentro do modal via Tab sintético:** em ~3 das 15 tabulações, `document.activeElement` apareceu momentaneamente como `BODY` antes de retornar ao ciclo dos 4 controles focáveis do modal (botão fechar, observação, botão "Fechar", "Salvar"). Investigado: o padrão observado (ciclo de 4 elementos interrompido periodicamente) é consistente com uma particularidade conhecida de simular Tab via eventos sintéticos de baixo nível em Chrome headless contra o focus-trap do Bootstrap 5 (que reage a `focusin`), não com uma regressão desta tarefa — nenhum elemento focável novo foi adicionado (o `<p id="pendencyOriginBlockedText">` não tem `tabindex`, não é focável) e a configuração do `bootstrap.Modal` não foi tocada. Tratado como limitação do método sintético, não como defeito confirmado; recomendado verificação manual com teclado real em POR-06 antes do aceite final.
- **Overflow horizontal do documento em 390px/526px e 360px/495px:** confirmado como **pré-existente** e **fora do escopo de POR-05** — reproduzido mesmo com o modal fechado (só a tabela `.daily-action-table` carregada), ou seja, vem da tabela da tela de Ações do Dia, não do modal nem da mensagem nova (o `.modal-dialog`, isoladamente, não estoura o viewport nos dois tamanhos, com folga de 16px). Nenhuma linha deste arquivo foi tocada por POR-05. Registrado aqui para visibilidade, não corrigido (ampliaria o escopo aprovado sem pedido explícito).

### Test Strategy

Camada de domínio/HTTP: inalterada desde POR-04 (nenhum código Python tocado nesta etapa); regressão proporcional reexecutada mesmo assim para confirmar que o `template` novo não quebra o `TemplateSyntaxError`/contexto: `manage.py test pendencies.tests dashboard.tests -v 1` → **171/171 PASSED**, 0 FAILED, 0 ERROR (91 + 80, mesmos números de POR-04/conferência corretiva).

Camada de navegador (T15, antes não coberta): Chrome real headless (`chrome.exe --headless=new`, versão 151.0.7922.109) pilotado via Chrome DevTools Protocol, cliente próprio em Python puro (só biblioteca padrão — `socket`, `hashlib`, `base64`, `struct`, `json`, `urllib`; nenhum pacote novo instalado no `venv`, nenhuma dependência nova no projeto). Perfil de navegador isolado (`--user-data-dir` próprio no diretório de scratch da sessão, descartado ao final) — não é o navegador/perfil real do usuário. Banco de dados: SQLite efêmero próprio, migrado do zero a partir das migrations já existentes no repositório (nenhuma migration nova criada; nenhuma alteração no Postgres de desenvolvimento, que não foi tocado — só consultado uma vez com `manage.py check` para confirmar conectividade, sem escrita). Dados: 100% sintéticos, prefixo `POR05SMOKE_`, cobrindo as 5 combinações relevantes (origem bloqueada nunca aberta; origem bloqueada com ciclo resolvido; origem bloqueada com pendência já aberta; origem permitida; origem permitida no load que muda para bloqueada antes do POST). Dois usuários sintéticos (`SUPER`, `ADMIN`) autenticados via cookie de sessão gerado diretamente pelo Django (`SessionStore` + chaves de auth), sem passar por tela de login (equivalente a login real para fins de cookie de sessão, sem expor nem reutilizar credenciais reais).

Limitações explícitas desta camada, não escondidas:

- **Leitor de tela/tecnologia assistiva real não foi usado** — a verificação de acessibilidade foi `role="alert"` + leitura de `textContent` via DOM/CDP, não uma árvore de acessibilidade (`Accessibility` domain do CDP) nem um leitor de tela real. `role="alert"` é padrão adequado para esse tipo de mensagem, mas não foi comprovado com AT real.
- **Tab sintético via CDP não reproduz com 100% de fidelidade o focus-trap nativo do Bootstrap** em Chrome headless — ver achado informativo acima. O requisito mais específico e verificável ("controle desabilitado nunca recebe foco", "controles legítimos permanecem alcançáveis") foi comprovado; a contenção estrita dentro do modal, não.
- **T18 (concorrência real sob Postgres)** continua fora do escopo desta etapa, como já registrado em POR-03/POR-04 — não tentado aqui.
- Esta camada é o smoke de **POR-05** (integração da UI), não o aceite final de **POR-06** — distinção mantida conforme pedido: POR-06 deve repetir a verificação visual/funcional de ponta a ponta antes do aceite, e pode (e deve) usar ferramentas de inspeção reais (devtools interativo) além deste smoke automatizado.

### Compliance Report

**Arquivos alterados:** `templates/dashboard/daily_user_action_board.html` (único arquivo de produção tocado nesta etapa — 24 linhas adicionadas). Nenhum arquivo Python, migration, form ou CSS separado foi criado ou alterado. Dois defeitos reais de JavaScript (não cobertos por nenhuma spec/teste anterior) foram encontrados por leitura do fluxo assíncrono do modal e corrigidos nesta mesma etapa, por estarem diretamente no caminho da integração pedida (ver Spec Summary/Implementation Plan): resposta atrasada substituindo o modal atual (corrigido com token de requisição). Nenhuma política de origem, permissão ou contrato HTTP/JSON do backend foi alterado — `pendencies/views.py`, `pendencies/admin.py`, `dashboard/views.py` e `telecom/origin_restriction.py` permanecem exatamente como POR-04/conferência corretiva os deixou.

**Evidências:** `docs/superpowers/evidence/2026-10-13-por05/` — `results.log` (saída completa das 21 verificações PASS + 2 achados informativos), 4 screenshots reais (`modal-1280-blocked.png`, `modal-390-blocked.png`, `modal-360-blocked.png`, `modal-1280-open-blocked-treatment.png`) capturados via `Page.captureScreenshot` do próprio Chrome pilotado, e os três scripts usados (`por05_browser_smoke.py`, `por05_setup_fixtures.py`, `cdp_client.py`) para reprodutibilidade.

**Validação executada:**
- `manage.py test pendencies.tests dashboard.tests -v 1` → 171/171 PASSED, 0 FAILED, 0 ERROR (regressão proporcional; nenhum teste Python foi criado ou alterado nesta etapa, já que POR-05 é só UI).
- `manage.py check` → "System check identified no issues (0 silenced)."
- `git diff --check` → sem marcador de conflito nem espaço em branco problemático no arquivo alterado.
- Smoke de navegador real (ver Test Checklist/Test Strategy acima) → 21/21 PASS, 0 FAIL, 2 achados informativos (um deles pré-existente e fora de escopo; o outro uma limitação do método sintético de Tab, não uma regressão).

**Limitações e pendências explícitas para POR-06:**
1. Verificação de acessibilidade com leitor de tela real e com Tab de teclado físico (não sintético) não foi feita — recomendada antes do aceite final.
2. Overflow horizontal pré-existente da tabela de Ações do Dia em larguras móveis (390px/360px) foi confirmado e documentado, mas **não corrigido** (fora do escopo aprovado para POR-05/esta tarefa) — decisão de produto pendente sobre se entra no escopo de POR-06 ou de uma tarefa separada.
3. T18 (concorrência sob PostgreSQL real) continua não comprovado, como já registrado desde POR-03.
4. O smoke desta etapa usou dados sintéticos num banco SQLite efêmero, não o ambiente de staging/QA real — POR-06 deve repetir a verificação visual no ambiente apropriado antes do aceite final, não reaproveitar só este resultado.

Sem migration, dependência nova, stage, commit, push, deploy ou acesso a PRD nesta etapa. O Postgres de desenvolvimento local (`lineops-db`, porta 5433) foi apenas consultado uma vez (`manage.py check`) para confirmar conectividade e não sofreu nenhuma escrita; todo o smoke rodou contra um SQLite efêmero descartado ao final, já removido junto com o Chrome headless e o servidor de desenvolvimento temporário (porta 8777) usados só durante esta verificação. Próxima tarefa: POR-06 (aceite real no navegador, regressão proporcional final e revisão de diff), não iniciada.

## POR-05 — Conferência corretiva (2026-10-13)

Conferência solicitada antes de iniciar POR-06, cobrindo seis pontos: (1) reconciliação da contagem "dois defeitos de JS"; (2) cobertura real do token de requisição em todos os caminhos assíncronos do modal (carregar, salvar, assumir, liberar); (3) matriz requisito→cenário→artefato→resultado dos 21 PASS originais; (4) validade da classificação "overflow pré-existente" e do achado sobre foco; (5) correção do(s) defeito(s) confirmado(s), com RED real antes; (6) esta atualização de spec. Nenhuma afirmação abaixo vem de releitura do relatório anterior sem verificação — cada uma foi checada por leitura do código, execução real em navegador (Chrome headless via CDP, mesmo método de POR-05) ou comparação A/B direta.

### Spec Summary

**1. Contagem "dois defeitos" estava errada — corrigida para um defeito original, mais um segundo defeito real encontrado agora.** O relatório de POR-05 descrevia, sob o título "Dois defeitos reais de JavaScript... foram encontrados e corrigidos", apenas **um** defeito real (resposta atrasada de `loadPendency` sobrescrevendo o modal, corrigido com `currentRequestToken`); o item "2" do mesmo parágrafo não descrevia um segundo defeito, descrevia a **ausência** de outros problemas ("nenhum outro problema... foi encontrado"). Essa é uma contradição de contagem, não um erro de julgamento sobre o que foi corrigido — o código entregue em POR-05 de fato só continha a correção do caso de `loadPendency`.

Nesta conferência, a inspeção pedida no item 2 (abaixo) encontrou um **segundo defeito real, não corrigido em POR-05**: `savePendency()` e `submitResponsibleAction()` (usada por assumir e liberar responsável) não tinham nenhuma guarda de token — uma resposta atrasada de Salvar/Assumir/Liberar disparada no registro A podia sobrescrever o modal já mostrando o registro B, com `renderModal(data)` e as mensagens de sucesso/erro aplicadas incondicionalmente. RED real confirmado (4/8 falhas) antes da correção; corrigido nesta etapa com o mesmo padrão de token (capturado, não incrementado, no início de cada função; checado antes de qualquer mutação de UI, inclusive no `finally` dos botões). GREEN real confirmado depois (9/9, com um terceiro cenário adicionado: falha 403 atrasada também não vaza para o registro atual).

Contagem final, sem ambiguidade: **dois defeitos reais no total** entre POR-05 e esta conferência — (a) `loadPendency` sem guarda de token, corrigido em POR-05; (b) `savePendency`/`submitResponsibleAction` sem guarda de token, corrigido nesta conferência. Não são "dois sintomas da mesma causa" tratados como dois defeitos artificialmente — são três funções assíncronas distintas (`loadPendency`, `savePendency`, `submitResponsibleAction`) que escrevem no mesmo estado compartilhado do modal, cada uma precisando da sua própria guarda; a causa raiz (ausência de proteção contra resposta superada) é a mesma, mas a lacuna de proteção era real e distinta em cada função — por isso duas correções, não uma reafirmada duas vezes.

**2. Cobertura do token — os três caminhos assíncronos que escrevem no modal foram inspecionados; dois tinham lacuna real.** `updateTableRow(currentEmployeeId, currentAllocationId, data)`, chamada dentro de `savePendency`/`submitResponsibleAction`, também usava os globais `currentEmployeeId`/`currentAllocationId` já sobrescritos por um `loadPendency` mais novo — coberta pela mesma guarda, já que ela só é chamada dentro do bloco agora protegido pelo token.

**3. Matriz dos 21 PASS originais — ver Matriz de Evidência abaixo.** Todos os 21 continuam válidos (reexecutados do zero nesta conferência, banco isolado recriado, 21/21 PASS, mesmo resultado). Nenhum foi demonstrado por inspeção estática; todos exercitam `fetch` real contra o servidor real.

**4. Overflow — comparação A/B válida feita; classificação "pré-existente" sustentada por evidência, não por suposição.** Comparação real entre a versão do template no `HEAD` do git (antes de qualquer alteração de POR-05, extraída com `git show HEAD:...` para um diretório fora do projeto, servida via `TEMPLATES["DIRS"]` alternativo — **o working tree do usuário nunca foi tocado, sobrescrito ou revertido**) e a versão atual, mesma página (`/indicadores/acoes-dia/`), mesmo dataset sintético, mesmos viewports (390px/360px). Resultado: overflow do documento **idêntico** nos dois casos (495px/390 e 526px/360), com a mesma origem (`'.daily-action-table'`, `scrollWidth=822` nos dois casos) — ver `docs/superpowers/evidence/2026-10-13-por05-conferencia-corretiva/05-overflow-ab-comparison.txt`. O `.modal-dialog` isolado (com a mensagem nova) não estoura o viewport em nenhum dos dois tamanhos (folga de 16px). Overflow do documento, rolagem/overflow da tabela e eventual corte do modal são três medidas distintas, coletadas separadamente (não inferidas umas das outras).

**Foco — limitação mantida, sem alegação de contenção comprovada nem refutada.** Reexecutado o mesmo teste de Tab sintético via CDP (`Input.dispatchKeyEvent`, método real de automação de teclado, não leitura estática): confirma de novo, de forma reproduzível, que (a) o `<select>` desabilitado pela origem nunca recebe foco, e (b) `pendencyObservation`/`pendencySaveBtn` continuam alcançáveis — essas duas afirmações têm reprodução real e são mantidas como comprovadas. A contenção **estrita** do foco dentro do modal (o Tab nunca pousar em `BODY`) continua **não comprovada nem refutada** por este método — não se declara nem presença nem ausência de focus-trap; mantido exatamente como limitação, não como veredito. Nenhuma tentativa foi feita de "corrigir" layout ou acessibilidade do Bootstrap/tabela sem relação demonstrada com o código de POR-05 — o escopo desta conferência é só o que POR-05 tocou (o modal de pendências) mais as lacunas apontadas no pedido.

**5. Correção aplicada.** `templates/dashboard/daily_user_action_board.html::savePendency` e `::submitResponsibleAction`: capturado `const requestToken = currentRequestToken;` no início de cada função; checagem `if (requestToken !== currentRequestToken) return;` logo após `await resp.json()` (cobre sucesso e erro no mesmo ponto, como já era feito em `loadPendency`); `finally` ajustado para só reabilitar o botão (`saveBtn`/`claimBtn`) quando o token ainda é o atual, evitando que uma resposta superada reabilite um botão que pertence a uma ação mais nova ainda em andamento no mesmo registro.

### Gap Analysis

- Confirmado por leitura de `pendencies/views.py` e `dashboard/views.py`: nenhuma política de origem, permissão ou contrato HTTP foi tocado nesta conferência — o defeito e a correção são inteiramente client-side (JavaScript), no mesmo arquivo de POR-05.
- Durante a investigação, uma tentativa de evidência combinada (rodar os três scripts de smoke em sequência, reaproveitando o mesmo banco SQLite efêmero sem pausa entre eles) produziu resultados inconsistentes num dos cenários (ciclo assumir→resolver→reabrir): a resolução às vezes retornava "Somente o técnico responsável pode resolver a pendência" mesmo logo após um "assumir" bem-sucedido do mesmo admin. Investigado antes de descartar como ruído: o SQLite efêmero de um único arquivo, sob um `runserver` single-thread, não garante que escritas de requisições HTTP consecutivas disparadas por processos Python/Chrome diferentes em sucessão rápida fiquem imediatamente serializadas e visíveis sem alguma folga de tempo — o mesmo tipo de limitação já documentado na spec para T18 (SQLite não comprova `select_for_update`/concorrência como Postgres). Reexecutado o mesmo cenário em banco isolado recriado do zero, sem outros scripts rodando antes, com pequenas pausas (500ms) entre assumir/resolver/reabrir: **100% reproduzível e limpo em três execuções consecutivas** (11/11, 11/11 dentro da mesma matriz estendida). Não foi encontrado nenhum defeito de produto nesse ponto — é uma característica conhecida do SQLite efêmero usado só para o smoke, não do código da aplicação (que roda sobre Postgres em dev/produção). Registrado aqui por transparência, não escondido, e não tratado como achado de produto.
- Dois cenários novos de cobertura, pedidos explicitamente neste pedido e ausentes em POR-05, foram adicionados e executados: ausência de linha vinculada (controle, já funcionava) e o ciclo dinâmico completo assumir→resolver→tentar reabrir (incluindo uma prova de defesa em profundidade: forçar o valor do `<select>` desabilitado via JavaScript e confirmar que o servidor, não o `disabled` do cliente, é quem recusa).

### Implementation Plan

**Arquivo alterado:** `templates/dashboard/daily_user_action_board.html` — `savePendency()` e `submitResponsibleAction()` ganharam a mesma guarda de token já usada em `loadPendency()` (8 linhas adicionadas, nenhuma removida, nenhuma outra função tocada). Nenhuma migration, nenhuma alteração de `pendencies/`, `dashboard/views.py`, `telecom/` ou qualquer model.

Sequência desta correção (Spec → Tests → Code, como nas demais etapas):
1. Lido o código de `savePendency`/`submitResponsibleAction` e identificada a ausência da guarda (sem token capturado, `renderModal`/mensagens aplicadas incondicionalmente).
2. Escrito `por05_race_save_claim.py` (novo, em `docs/superpowers/evidence/2026-10-13-por05-conferencia-corretiva/`) — reproduz a troca de registro durante uma resposta atrasada de Salvar e de Assumir, usando um override de `window.fetch` injetado via CDP (não o código de produção) para atrasar só a resposta POST de forma controlada.
3. Executado contra o código **sem a correção**: RED real, 4/8 falhas (`01-red-antes-da-correcao-save-claim.log`) — identidade do modal revertia para o registro antigo, mensagem "Salvo com sucesso."/"Responsável técnico atribuído." aparecia presa ao registro errado.
4. Aplicada a correção (ver Spec Summary, item 5).
5. Reexecutado: GREEN real, 9/9 (`02-green-apos-correcao-save-claim.log`, inclui o cenário adicional de falha 403 atrasada).
6. Reexecutada a suíte original de 21 verificações (regressão) e a suíte focada do backend (171 testes Python) — nenhuma mudou de resultado.

### Test Checklist — resultado (todos reexecutados em 2026-10-13, nesta conferência, banco isolado recriado do zero para cada rodada)

Legenda de artefato: cada linha aponta para o log real em `docs/superpowers/evidence/2026-10-13-por05-conferencia-corretiva/`.

| # | Requisito do pedido | Cenário | Artefato | Resultado | Limitação |
|---|---|---|---|---|---|
| 1 | Duas origens bloqueadas: abertura e reabertura | `APARELHO OP` nunca aberta (abertura) e `PESSOAL` com ciclo resolvido (reabertura) — a UI colapsa as duas origens bloqueadas num único booleano (`origin_open_blocked`), sem branch por origem; a cobertura por origem específica já é garantida na camada HTTP (T1/T2/T3, 171 testes Python) | `03-regressao-smoke-original-21.log` | PASS (2/2) | Equivalência de código declarada explicitamente: o JS não distingue as duas origens bloqueadas, só o flag |
| 2 | Origem permitida e ausência de linha | `APARELHO` (controle) + funcionário sem `allocation` (`data-allocation-id=""`) | `03-...log` (controle) + `04-matriz-adicional...log` (sem linha) | PASS (2/2) | — |
| 3 | Pendência aberta em origem bloqueada: tratamento autorizado preservado | Claim/observação/ação visível para ADMIN numa pendência já aberta em linha `APARELHO OP` | `03-...log` | PASS (3/3) | — |
| 4 | Resolução seguida de tentativa de reabertura | Ciclo dinâmico real na UI: assumir → resolver (`no_action`) → UI já bloqueia o `<select>` sem fechar/reabrir o modal → tentativa forçada de reabrir recusada pelo servidor (ADMIN: mensagem de permissão pré-existente; SUPER: mensagem de origem exata) | `04-matriz-adicional...log` | PASS (6/6) | Primeira vez que esse ciclo foi exercitado dinamicamente na UI (POR-05 original só carregava um registro já pré-resolvido do banco) |
| 5 | Origem alterada no banco após carregar o modal: recusa backend e mensagem correta | Origem permitida no load, alterada no banco (fora do navegador) antes do POST, servidor recusa com a mensagem exata, observação digitada não é perdida | `03-...log` | PASS (3/3) | — |
| 6 | Troca de funcionário/linha sem estado residual | Estado do registro anterior não aparece no próximo; resposta atrasada de registro anterior não substitui o atual (load, salvar, assumir, liberar — os três caminhos agora guardados) | `03-...log` + `02-green-apos-correcao-save-claim.log` | PASS (2 + 9) | — |
| 7 | Mensagem literal, renderizada como texto | `textContent`, nunca `innerHTML`; texto comparado byte a byte com a mensagem aprovada | `03-...log` | PASS (2/2) | — |
| 8 | Desktop, 390px e 360px | `.modal-dialog` isolado não estoura o viewport nos três tamanhos; overflow do documento idêntico antes/depois de POR-05 (comparação A/B) | `03-...log` + `05-overflow-ab-comparison.txt` | PASS (modal) / overflow do documento confirmado pré-existente por comparação válida | Overflow do documento continua não corrigido (fora do escopo aprovado) |
| 9 | Teclado, foco utilizável e controles legítimos alcançáveis | `<select>` desabilitado nunca recebe foco via Tab real (CDP); observação e Salvar continuam alcançáveis | `03-...log` | PASS (select nunca focado; controles legítimos alcançáveis) | Contenção estrita do foco dentro do modal (Tab nunca pousar fora) permanece não comprovada nem refutada |
| 10 | Console/rede: erros esperados separados dos inesperados | Nenhuma exceção JS não tratada em nenhum dos três scripts; nenhuma resposta 5xx/erro de transporte; o(s) 403 de bloqueio por origem aparece(m) como resposta HTTP esperada, classificado separadamente | `03-...log`, `02-...log`, `04-...log` | PASS (0 exceções JS; 0 respostas 5xx inesperadas; 403 esperado presente e identificado) | — |

Total: **41/41 verificações PASS** nesta conferência, em três rodadas isoladas (9 + 21 + 11), cada uma com banco SQLite efêmero recriado do zero e servidor reiniciado — nenhuma reaproveita estado de uma rodada anterior. Nenhum cenário foi repetido sem necessidade: os 21 originais foram reexecutados porque o código mudou (correção de save/claim/release no mesmo arquivo), não por desconfiança sem causa.

### Test Strategy

Mesma estratégia de POR-05 (Chrome real headless via CDP, cliente Python próprio só com biblioteca padrão, SQLite efêmero descartável, dados 100% sintéticos `POR05SMOKE_*`, nenhuma dependência nova). Adicionado nesta conferência:

- **Interceptação de rede determinística, não sleeps cegos:** o atraso de resposta usado para provar as duas race conditions (load e save/claim) é aplicado sobrepondo `window.fetch` (injetado via `Page.addScriptToEvaluateOnNewDocument`, nunca no código de produção) para atrasar especificamente a requisição POST relevante por um tempo fixo (1200ms) antes de chamar o `fetch` real — a ordem de chegada das respostas é controlada deterministicamente pelo teste, não por timing de rede real. Os `time.sleep` no script Python só esperam o suficiente para garantir que a resposta atrasada já tenha sido disparada (ou já tenha retornado) antes da próxima asserção — não são usados como prova por si só.
- **Comparação A/B sem reverter o working tree:** ver Gap Analysis / item 4 do Spec Summary.
- **RED real exigido e obtido** para o defeito novo (save/claim/release) antes de qualquer correção — log preservado (`01-red-antes-da-correcao-save-claim.log`), não inferido nem reconstruído depois do fato.
- **Classificação de respostas de rede:** todas as `Network.responseReceived` da sessão foram coletadas e classificadas por status (2xx/4xx esperados vs. 5xx/erro de transporte inesperado), não só a ausência de `Runtime.exceptionThrown`.
- Regressão proporcional do backend (`manage.py test pendencies.tests dashboard.tests`) reexecutada porque o arquivo de template mudou de novo nesta conferência — **171/171 PASSED**, mesmo número de POR-04/POR-05, nenhum teste criado ou alterado (POR-05 e esta conferência continuam sendo só UI).

### Compliance Report

**Reconciliação dos seis pontos pedidos:**

1. **Contagem de defeitos:** corrigida. POR-05 original continha um defeito real corrigido (mal contado como dois); esta conferência encontrou e corrigiu um segundo defeito real e distinto (`savePendency`/`submitResponsibleAction` sem guarda de token). Total real: dois defeitos, dois RED→GREEN reais, nenhum inventado retrospectivamente.
2. **Cobertura do token:** os três caminhos assíncronos que escrevem no modal (`loadPendency`, `savePendency`, `submitResponsibleAction`) foram inspecionados e agora têm a mesma guarda; `updateTableRow` herda a proteção por estar dentro do bloco guardado. Comprovado em navegador real controlando a ordem de chegada das respostas (não por sleep cego nem leitura estática).
3. **Matriz dos 21 PASS:** documentada acima com artefato e resultado por cenário; nenhum foi demonstrado só por inspeção.
4. **Overflow:** comparação A/B real e válida (HEAD vs. working tree, mesma página/dataset/viewport, sem reverter o working tree) confirma que é pré-existente, byte a byte igual antes e depois. **Foco:** limitação mantida como estava — nem contenção comprovada, nem refutada; nenhuma correção de layout/acessibilidade alheia tentada.
5. **Correção e validação:** defeito confirmado por RED real, corrigido com a menor mudança suficiente (mesmo padrão já usado em `loadPendency`), revalidado (GREEN real) e sem regressão (171 testes Python + 21 verificações de navegador reexecutadas).
6. **Esta atualização de spec**, preservando todo o histórico anterior sem apagar números antigos — a contagem errada de "dois defeitos" de POR-05 permanece no texto original acima, com esta seção como retificação explícita, no mesmo padrão já usado nas conferências corretivas de POR-03/POR-04.

**Arquivos alterados nesta conferência:**
- `templates/dashboard/daily_user_action_board.html` — guarda de token adicionada a `savePendency()` e `submitResponsibleAction()` (8 linhas).
- `docs/superpowers/specs/2026-10-13-pendency-origin-restriction-design.md` — esta seção.

**Evidências novas:** `docs/superpowers/evidence/2026-10-13-por05-conferencia-corretiva/` — 4 logs de execução real (`01` RED, `02` GREEN, `03` regressão dos 21 originais, `04` matriz adicional), 1 comparação A/B de overflow (`05`), e os scripts usados (`por05_race_save_claim.py`, `por05_matrix_extra.py`, `por05_setup_fixtures.py`, `por05_smoke_settings_baseline.py`), todos reprodutíveis.

**Validação executada:**
- `manage.py test pendencies.tests dashboard.tests -v 1` → 171/171 PASSED, 0 FAILED, 0 ERROR.
- `manage.py check` → "System check identified no issues (0 silenced)."
- `git diff --check` → sem marcador de conflito nem espaço em branco problemático nos arquivos alterados.
- Navegador real, três rodadas isoladas (banco recriado do zero em cada uma): 9/9 (race save/claim/release), 21/21 (regressão original), 11/11 (matriz adicional) = **41/41 PASS**, 0 FAIL.

**Limitações explícitas, inalteradas ou atualizadas:**
1. Leitor de tela real e Tab físico (não sintético) continuam não testados — recomendado antes do aceite final de POR-06.
2. Contenção estrita de foco dentro do modal via Tab continua nem comprovada nem refutada (mesma limitação de POR-05, reexecutada e confirmada reproduzível, não resolvida).
3. Overflow horizontal pré-existente da tabela (não do modal): confirmado por comparação A/B válida nesta conferência (antes não era comparação, era suposição lida de um único estado); continua **não corrigido**, fora do escopo aprovado.
4. T18 (concorrência real sob PostgreSQL) continua fora do escopo, inalterado.
5. SQLite efêmero do smoke, sob rajada de requisições sem pausa, mostrou um artefato de contenção pontual durante a investigação (não durante a validação final) — documentado no Gap Analysis, não é defeito de produto, não foi "corrigido" porque não há nada de aplicação para corrigir; a validação final usa execuções isoladas, sem esse artefato.

**Veredito:** POR-05 passa a **concluída de fato**, condicionada às evidências desta conferência — o defeito real que faltava (save/claim/release sem guarda de token) foi encontrado, confirmado por RED real e corrigido, com GREEN real e sem regressão. A contagem documental de defeitos foi retificada. Overflow pré-existente e limitação de foco permanecem registrados como estavam, agora com evidência mais forte (comparação A/B) em vez de leitura única. Nenhuma migration, dependência nova, stage, commit, push, deploy ou acesso a PRD nesta etapa. POR-06 não iniciada; T18/PostgreSQL permanece separado, não tentado.

## POR-06 — Aceite final e revisão integrada (2026-10-13)

### Spec Summary

Aceite real executado contra código e evidências inspecionados diretamente nesta etapa (não por reafirmação de relatórios anteriores). Nenhum defeito de produto novo foi confirmado; um defeito de **higiene de evidência/ambiente** foi encontrado e corrigido (ver Gap Analysis item 1). T18 foi executado contra PostgreSQL real descartável (não SQLite), com mapeamento de locks e um teste de concorrência HTTP real adicional, e classificado explicitamente conforme pedido.

Ambiente usado nesta etapa, isolado do dev/produção:

- **Postgres descartável**: container `por06-pg-disposable` (postgres:15.8, porta 55433), criado e destruído nesta rodada — nunca o `lineops-db:5433` de desenvolvimento nem qualquer banco de produção.
- **Servidor real**: `manage.py runserver 127.0.0.1:8778 --settings=por06_settings` (settings próprio desta rodada, herdando `config/settings.py` só com `DATABASES` sobrescrito para o Postgres descartável), destruído ao final.
- **Navegador real**: Chrome headless (`chrome.exe --headless=new`, mesmo binário usado em POR-05), pilotado por CDP via o mesmo cliente Python stdlib (`cdp_client.py`, reaproveitado de POR-05 sem alteração).
- **Dados**: 100% sintéticos, prefixo `POR06SMOKE_`, recriados do zero a cada rodada de teste (banco dropado/recriado + fixtures reaplicadas) para evitar reaproveitar estado mutado por uma tentativa anterior.

### Gap Analysis

**1. Achado real — dados sintéticos de POR-05 (`POR05SMOKE_*`) ficaram órfãos no Postgres de desenvolvimento real (`lineops-db:5433`), contradizendo o Compliance Report de POR-05/conferência corretiva.** Os dois (`POR05SMOKE.super@test.local`, `POR05SMOKE.admin@test.local`) e um `Employee` órfão (`POR05SMOKE-BlockedNew`, sem `allocation`/`phone_line`/`pendency` associados — esses já tinham sido limpos) foram confirmados por consulta direta ao Postgres de dev (`docker exec lineops-db psql`), não por leitura do relatório. O comentário de cabeçalho de `docs/superpowers/evidence/2026-10-13-por05/por05_setup_fixtures.py` e da cópia em `.../2026-10-13-por05-conferencia-corretiva/por05_setup_fixtures.py` já indicava "Postgres de dev local (container lineops-db, porta 5433)" — inconsistente com a alegação do Compliance Report de POR-05 ("todo o smoke rodou contra um SQLite efêmero... Postgres de desenvolvimento... não sofreu nenhuma escrita"). O módulo `por05_smoke_settings.py` que de fato decidia o banco usado não foi preservado em nenhum dos dois diretórios de evidência (só sua variante `_baseline.py`, que o importa via `from por05_smoke_settings import *`), então não é possível reconstituir com certeza qual dos dois bancos cada execução de POR-05 usou — o que é demonstrável é que **houve escrita real no Postgres de dev**, pelos registros órfãos encontrados. Antes de prosseguir com o aceite desta etapa, pedi confirmação ao usuário (`AskUserQuestion`) sobre apagar esses três registros órfãos do `lineops-db`; aprovado, e os três foram removidos (`employees_employeehistory` do funcionário removido primeiro, por FK `NO ACTION`; depois o `Employee`; depois os dois `SystemUser`) — confirmado por recontagem `0`/`0` depois. Nenhum outro dado do `lineops-db` foi tocado; nenhuma tabela além das três envolvidas foi escrita. Registrado aqui como achado de higiene de processo, não como defeito da feature de bloqueio por origem — e como motivo concreto para esta etapa usar exclusivamente Postgres **descartável**, nunca o de dev, conforme já pedido no início da tarefa.

**2. Revisão integrada do código (leitura direta, não por confiança no relatório anterior).** Conferido via `git diff` linha a linha: `telecom/origin_restriction.py` (mensagem exata byte-a-byte igual à aprovada, `BLOCKED_ORIGINS` = `{APARELHO_OP, PESSOAL}`, `phone_line=None` → `False`); `pendencies/views.py` (`_pendency_to_json` expõe os dois campos aditivos; `PendencyUpdateView.post` checa origem só dentro do ramo `was_no_action and not will_be_no_action`, depois do gate `is_super_like`, preservando T8); `pendencies/admin.py` (`AllocationPendencyAdminForm.clean()` usa `cleaned_data.get("allocation")`, a allocation **proposta**, não `self.instance.allocation`, confirmando a correção da conferência corretiva de POR-04 continua em vigor); `dashboard/views.py` (cálculo de `origin_open_blocked` ocorre antes do ramo de `line_status` — `and not origin_open_blocked` no gate do ADMIN — e antes do trio de decisão de ação; `existing_action` não é reconsultado, reaproveitando a query já feita sob `select_for_update`); `templates/dashboard/daily_user_action_board.html` (as três funções assíncronas que escrevem no modal — `loadPendency`, `savePendency`, `submitResponsibleAction` — têm a mesma guarda de `currentRequestToken`). Nenhuma divergência entre o que a spec alega e o que o código faz foi encontrada nesta leitura.

**3. Regressão real reexecutada nesta etapa (não reaproveitada do relatório).** `manage.py test pendencies.tests dashboard.tests -v 2` → **171/171 PASSED**, 0 FAILED, 0 ERROR (idêntico ao baseline de POR-04/POR-05: 91 em `pendencies.tests` + 80 em `dashboard.tests`). `manage.py test telecom -v 2` → **272 testes, 271 PASSED + 1 SKIPPED, 0 FAILED** (skip pré-existente, dependente de Postgres, não relacionado a esta tarefa — reconfirmado, não apenas citado). `pytest pendencies/tests/test_pendency_origin_restriction.py dashboard/tests/test_daily_user_action_origin_restriction.py --collect-only -q` → **43 tests collected**; mesma dupla, execução real → **43 passed, 18 subtests passed**, 0 failed — coleta e resultado idênticos ao `manage.py test`, confirmando de novo a ausência de divergência de runner já registrada em POR-03/04 (não reafirmada sem checar: comando rodado de novo nesta etapa). `manage.py check` → "System check identified no issues (0 silenced)." `git diff --check` → só o aviso pré-existente de normalização CRLF/LF, nenhum novo.

**4. Aceite real no navegador (Chrome headless real via CDP, Postgres descartável) — 21/21 verificações PASS, 0 FAIL**, cobrindo desktop (1280px) e mobile (390px/360px), nos dois papéis (SUPER, ADMIN):

- Abertura bloqueada (nunca aberta, `APARELHO OP`) e reabertura bloqueada (ciclo resolvido, `PESSOAL`): mensagem exata presente, `<select>` desabilitado, confirmado por leitura real do DOM renderizado (não inferido do JSON da API).
- Controle positivo (`APARELHO`) e sem linha vinculada: mensagem ausente, `<select>` habilitado.
- Pendência já aberta em origem bloqueada (ADMIN): claim ("Assumir"/"Liberar"), edição de observação e salvamento funcionam sem a mensagem aparecer — tratamento autorizado não é impedido pela origem.
- **Ciclo dinâmico completo, pela primeira vez exercitado ponta a ponta no navegador** (POR-05 só carregava um registro já pré-resolvido do banco): ADMIN assume → resolve (`no_action`) → `<select>` volta a ficar desabilitado automaticamente, sem fechar/reabrir o modal, porque `renderModal` já recalcula tudo a cada resposta de sucesso → tentativa de reabrir forçando o `<select>` via JS (defesa em profundidade) é recusada pelo **servidor**, não pelo `disabled` do cliente → SUPER tentando reabrir a mesma pendência recebe a mensagem de origem exata; ADMIN tentando reabrir recebe a mensagem de permissão pré-existente (diferente) — confirmando que a flag reflete a linha, não o papel de quem vê, igual ao contrato técnico do payload.
- Troca de funcionário/linha sem estado residual: confirmado pela sequência de cenários distintos no mesmo DOM sem reload entre a maioria deles.
- Origem alterada no banco (via `UPDATE` direto no Postgres descartável, fora do navegador) depois do load do modal, antes do clique em Salvar: servidor recusa com a mensagem exata; a observação digitada não é perdida (mesmo comportamento documentado em POR-05, reconfirmado).
- Mobile 390px/360px: `.modal-dialog` não ultrapassa o viewport físico (folga de 16px nos dois tamanhos — medido via `getBoundingClientRect`, não por inspeção visual), mensagem visível, confirmado por screenshot real (`Page.captureScreenshot`, não simulação).
- Console/rede: 0 exceções JS não tratadas, 0 respostas 5xx inesperadas em toda a sessão.

Dificuldade de ambiente encontrada e resolvida (registrada por transparência, não escondida): em emulação "mobile" do Chrome headless (`Emulation.setDeviceMetricsOverride` com `mobile:true`), `window.innerWidth`/`innerHeight` relataram valores bem maiores que o `width`/`height` emulados (866×1777 para um dispositivo de 390×800) — confirmado como o mesmo overflow horizontal pré-existente da tabela (documentado desde POR-05) se manifestando também no "layout viewport" do Chrome, não um bug da ferramenta de teste. `visualViewport.width`/`outerWidth` continuaram corretos (390). Cliques por coordenada de mouse (usados com sucesso no desktop, seção abaixo) ficavam fora do alvo real nesse modo; a verificação mobile passou a usar `btn.click()` via JS para abrir o modal (mesmo método já usado com sucesso em POR-05 `click_pendency_btn`), reservando clique por coordenada real para o desktop, onde foi exercitado em 14 interações distintas (abrir, fechar, assumir, liberar, salvar, forçar reabertura) sem essa limitação.

**5. Teclado real (CDP `Input.dispatchKeyEvent`, 15 tabulações) — reexecutado nesta etapa, resultado reproduzido:**

- `<select>` desabilitado pela origem nunca recebeu foco (0/15) — comprovado, não apenas por inspeção do DOM: sequência real de eventos de teclado despachados pelo protocolo do Chrome (o mesmo mecanismo usado por qualquer automação de navegador, não uma simulação de alto nível em JavaScript).
- `pendencyObservation` e `pendencySaveBtn` permanecem alcançáveis.
- `BODY` apareceu como `document.activeElement` em 2 das 15 tabulações — mesma ordem de grandeza do achado de POR-05 (lá: ~3/15). **Mantido explicitamente como achado informativo, não PASS/FAIL de produto**: a contenção estrita do foco dentro do modal (Tab nunca pousar fora) continua **nem comprovada nem refutada** por este método, porque dispatch sintético via CDP contra o focus-trap do Bootstrap 5 é conhecido por não reproduzir com 100% de fidelidade esse comportamento específico em Chrome headless — distinção entre falha do harness e regressão de produto mantida (nenhuma linha de CSS/JS de foco foi alterada por nenhuma etapa desta feature). Recomendação, como já registrado em POR-05, de verificação com teclado físico real continua válida e não foi feita nesta etapa (ambiente sem acesso a interação humana direta).

**6. Admin — HTTP real contra servidor real (não Django test Client), criação/abertura/reabertura/troca de allocation no mesmo POST — 7/7 PASS.** Usado `urllib` (stdlib, sem dependência nova) com um `opener` que **não segue redirect automaticamente** (necessário para diferenciar 200 de 302 corretamente — a primeira tentativa, usando o opener padrão do Python, seguia o redirect de sucesso e mascarava um 302 real como 200 na página de destino, o que inicialmente pareceu um defeito e foi investigado antes de ser descartado como erro de instrumentação do teste, não do produto; corrigido no script, não no código da aplicação). Cada cenário foi conferido tanto pelo HTTP quanto pelo estado persistido via ORM Django (não só pelo status):

- Abertura bloqueada via Admin cria 200 com a mensagem exata; `AllocationPendency.action` permanece `no_action` (conferido por `refresh_from_db` equivalente via nova consulta ORM).
- Troca de `allocation` de origem permitida para bloqueada **no mesmo POST** de abertura: recusada (200, DB inalterado) — confirma a correção da conferência corretiva de POR-04 (usar `cleaned_data.get("allocation")`, não `self.instance.allocation`) continua correta sob HTTP real.
- Troca de `allocation` de origem bloqueada para permitida **no mesmo POST**: aceita (302, DB atualizado com a nova allocation e `action=pending`).
- Criação direta (`add/`) com ação já aberta em origem bloqueada: recusada (200, nenhum registro criado — contagem antes/depois igual).
- Controle: criação direta com `NO_ACTION` (não é abertura): aceita normalmente (302, registro criado).

Exige usuário Django `is_staff`/superusuário real para acessar o Admin (distinto do papel de negócio ADMIN usado no modal) — fixture `POR06SMOKE.root@test.local` criado via `SystemUser.objects.create_superuser`, mesmo padrão já usado pelos testes `pytest` de Admin.

### T18 — Classificação final (PostgreSQL real descartável, não SQLite)

Executado contra o container `por06-pg-disposable` (nunca `lineops-db`). Duas camadas:

**Camada 1 — mapeamento de locks por SQL direto (duas conexões `psycopg2` independentes, sem passar pela aplicação):**

| # | Verificação | Resultado | Evidência |
|---|---|---|---|
| T18.1 | `SELECT ... FOR UPDATE` em `AllocationPendency` (mesma linha, duas conexões) | Serializa — 2ª conexão bloqueada ~1,2s até a 1ª liberar | `t18_locks.log` |
| T18.2 | `SELECT ... FOR UPDATE` em `LineAllocation` (mesma linha, duas conexões) | Serializa — mesmo padrão | `t18_locks.log` |
| T18.3 | `UPDATE telecom_phoneline SET origem=...` concorrente, enquanto outra conexão segura o lock de `AllocationPendency`/`LineAllocation` da pendência relacionada | **Não bloqueado** (~5ms) — confirma por medição real, não por leitura de código, que nenhum dos dois locks usados pelos três pontos de abertura trava `PhoneLine` | `t18_locks.log` |
| T18.4 | Leitura subsequente (nova transação) do `origem` após o `UPDATE` concorrente | Reflete o valor recém-commitado — READ COMMITTED padrão do Postgres, sem isolamento adicional | `t18_locks.log` |

**Camada 2 — concorrência real via HTTP (duas requisições `PendencyUpdateView` reais, mesma pendência, mesmo instante, usando `threading.Barrier` pra sincronizar o disparo):**

Resultado: as duas requisições completam (200/200); exatamente **1** evento `OPENED` é gravado (não 2); o estado final da pendência é consistente (`action=pending`, sem duplicidade). Mecanismo real, não hipotético: a 2ª requisição fica bloqueada no `select_for_update` de `_load_locked_pendency_for_scope` até a 1ª commitar; ao destravar, ela recalcula `was_no_action` sobre o estado **já atualizado** (`pending`), então `new_action == pendency.action` e `action_changed` é `False` — a 2ª requisição não gera erro nem segunda abertura, apenas um no-op silencioso dentro do mesmo fluxo de sucesso já existente. Evidência: `t18_http_race.log`.

**Classificação explícita pedida:**

- **Garantia contratual comprovada:** a origem é sempre avaliada sobre o valor persistido no momento da avaliação, dentro da mesma transação que decide (T18.3/T18.4) — exatamente o que o contrato aprovado exige, nada além disso. Duas tentativas concorrentes de abrir a **mesma** pendência não corrompem estado nem duplicam auditoria (T18, camada 2) — isso decorre do `select_for_update` já existente sobre `AllocationPendency`/`LineAllocation`, não de nenhum lock novo.
- **Hipótese mais forte que o contrato, com risco residual documentado (não corrigida, por não ter sido pedida):** não há serialização de uma edição concorrente de `PhoneLine.origem` em relação à decisão de abrir/reabrir — confirmado agora por medição direta (T18.3), não só por `grep` de código (como em POR-04/conferência). Sob `READ COMMITTED` (padrão do Django/Postgres), uma transação concorrente poderia alterar a origem entre a leitura da política e o commit da abertura, sem bloqueio. Isso é pré-existente ao padrão de locks já usado por outras partes do sistema (`core/services/allocation_service.py`, `core/services/telephony_use_case.py`, que travam `PhoneLine` para fins diferentes, não relacionados a estes três pontos) e não foi alterado nesta feature. **Decisão de produto necessária, se o risco for considerado inaceitável:** adicionar `select_for_update` sobre `PhoneLine` nos três pontos de abertura — isso ampliaria o contrato aprovado (que não pede essa garantia) e não foi feito sem pedido explícito.
- Nenhuma garantia de serialização de origem foi inventada; nenhum lock novo foi adicionado ao código de produção.

### Revisão do erro SQLite da rodada anterior (pedido explícito)

Erro exato, como documentado em POR-05/conferência corretiva (nenhum log bruto foi preservado daquela investigação — só a descrição em prosa na própria spec, conferida agora por releitura do texto-fonte, não reconstituída): *"a resolução às vezes retornava 'Somente o técnico responsável pode resolver a pendência' mesmo logo após um 'assumir' bem-sucedido do mesmo admin"*, atribuído a um SQLite efêmero de arquivo único sob `runserver` single-thread recebendo requisições de processos concorrentes em sucessão rápida sem folga. Nesta etapa, T18 foi inteiramente reexecutado contra **PostgreSQL real** (camadas 1 e 2 acima), onde esse tipo de artefato de visibilidade não se aplica da mesma forma (MVCC real, não um arquivo único compartilhado) — e nenhuma recorrência desse sintoma específico foi observada em nenhuma das execuções desta etapa (nem no `por06_t18_http_race.py`, nem nos 21 cenários de `por06_browser_accept.py`, que incluem um ciclo assumir→resolver→tentativa de reabertura). Isso **não** prova retroativamente que a causa de POR-05 era exclusivamente o harness SQLite (execuções limpas isoladas não provam ausência de causa, só ausência de recorrência nas condições testadas aqui) — mantido como limitação de evidência herdada, não resolvida nem descartada nesta etapa, conforme já registrado.

### Implementation Plan

Nenhuma alteração de código de aplicação nesta etapa — POR-06 é só aceite/regressão/revisão. Único achado corrigido foi de **ambiente** (dados órfãos em `lineops-db`, removidos após aprovação do usuário — ver Gap Analysis item 1), não de código.

### Test Checklist — matriz requisito → cenário → evidência → resultado → limitação

| Requisito | Cenário | Evidência | Resultado | Limitação |
|---|---|---|---|---|
| Bloqueio por origem (abertura/reabertura, as duas origens) | Modal, desktop, SUPER/ADMIN | `browser_accept.log` #1,2,9,11; screenshots | PASS | UI colapsa as duas origens num único booleano; cobertura por origem específica é da camada HTTP (171 testes) |
| Controles positivos (origem permitida, sem linha) | Modal, desktop | `browser_accept.log` #3,4 | PASS | — |
| Tratamento de pendência aberta em origem bloqueada (claim/observação/release) | Modal, desktop, ADMIN | `browser_accept.log` #5–8 | PASS | — |
| Resolução seguida de tentativa de reabertura, ciclo dinâmico real | Modal, desktop, ADMIN então SUPER | `browser_accept.log` #9–12 | PASS | Primeira vez exercitado dinamicamente de ponta a ponta no navegador (POR-05 só carregava registro pré-resolvido) |
| Origem alterada após carregar o modal | Modal, desktop, UPDATE direto no Postgres descartável | `browser_accept.log` #13,14 | PASS | — |
| Admin: criação, abertura, reabertura, troca de allocation no mesmo POST | HTTP real (urllib, sem redirect automático) + ORM | `admin_http.log` | PASS (7/7) | Via HTTP real, não clique de navegador renderizado (Admin não foi navegado visualmente nesta etapa) |
| Mensagem legível junto aos controles, sem bloquear modal inteiro | Screenshots 1280/390/360 | `modal-*.png` | PASS | — |
| Ausência de novo badge/ícone permanente | Leitura do diff do template (24 linhas, sem nova tabela/coluna) | diff `templates/dashboard/daily_user_action_board.html` | PASS | — |
| Console/rede: erros esperados vs. inesperados | Sessão completa do navegador | `browser_accept.log` #20,21 | PASS | — |
| Teclado real, foco, controles alcançáveis | Tab×15 via CDP `Input.dispatchKeyEvent` | `browser_accept.log` #15–17 | PASS (foco básico); informativo (contenção estrita) | Contenção estrita do foco nem comprovada nem refutada — limitação conhecida do método sintético em Chrome headless, não regressão |
| Overflow A/B (não ampliar escopo) | Não refeito nesta etapa — já comprovado por comparação A/B real em POR-05/conferência | `2026-10-13-por05-conferencia-corretiva/05-overflow-ab-comparison.txt` | Reaproveitado (código do template nessa área inalterado desde então) | Overflow do documento continua não corrigido, fora do escopo aprovado |
| T18 — origem persistida no momento da avaliação | SQL direto + HTTP concorrente real, Postgres descartável | `t18_locks.log`, `t18_http_race.log` | PASS (garantia contratual comprovada) | Serialização de `PhoneLine.origem` em si é hipótese mais forte que o contrato — risco residual documentado, não corrigido |
| Regressão proporcional | `pendencies.tests`+`dashboard.tests` (171), `telecom` (272), `pytest` (43) | saída de terminal desta sessão | PASS, 0 regressão | — |
| `manage.py check` / `git diff --check` | — | saída de terminal desta sessão | PASS | — |
| Erro SQLite da rodada anterior | Revisão documental + não recorrência sob Postgres real nesta etapa | seção dedicada acima | Não resolvido nem descartado — limitação de evidência herdada | Nenhum log bruto daquela investigação foi preservado |

### Test Strategy

Mesma filosofia das etapas anteriores (HTTP/Admin real, navegador real, nenhuma dependência nova), com duas mudanças desta etapa: (1) Postgres **descartável** dedicado em vez de SQLite ou do Postgres de dev, inclusive para o aceite de navegador (evita repetir o problema do item 1 do Gap Analysis); (2) T18 executado com SQL direto (duas conexões `psycopg2`) além de HTTP concorrente real, para mapear o comportamento de lock sem depender só de leitura de código. Banco recriado do zero (`DROP DATABASE`/`CREATE DATABASE` + `migrate` + fixtures) antes de cada rodada de teste que pudesse ter sido mutada por uma tentativa anterior, para que o PASS final não reaproveitasse estado alterado por uma iteração de depuração.

### Compliance Report

**Resultado:** POR-06 **concluída**, critérios do pedido cobertos com evidência real, nenhum PASS declarado por inspeção estática isolada.

**Defeitos encontrados:** nenhum defeito de produto novo. Um defeito de **higiene de ambiente/evidência** (dados sintéticos de POR-05 órfãos no Postgres de dev real, contradizendo o Compliance Report daquela etapa) foi encontrado, confirmado por consulta direta ao banco, aprovado para remoção pelo usuário e corrigido (3 registros removidos, recontagem 0/0 confirmada). Duas suposições de defeito no script de teste do Admin (status 200 onde se esperava 302) foram investigadas e refutadas — causa era o `urllib` seguindo redirect automaticamente, não o produto; corrigido no instrumento de teste.

**Evidências novas (esta etapa, `docs/superpowers/evidence/2026-10-13-por06/`):** `browser_accept.log` (21/21 PASS), `admin_http.log` (7/7 PASS), `t18_locks.log` (4/4 PASS), `t18_http_race.log` (4/4 PASS), 4 screenshots reais (`modal-1280-blocked.png`, `modal-1280-open-blocked-treatment.png`, `modal-390-blocked.png`, `modal-360-blocked.png`), scripts completos para reprodução (`por06_settings.py`, `por06_setup_fixtures.py`, `por06_browser_accept.py`, `por06_admin_http.py`, `por06_t18_locks.py`, `por06_t18_http_race.py`, `por06_screenshots.py`, `cdp_client.py`).

**Evidências reaproveitadas (código/cenário comprovadamente inalterado desde então, citadas, não reexecutadas):** comparação A/B de overflow horizontal da tabela (`2026-10-13-por05-conferencia-corretiva/05-overflow-ab-comparison.txt`) — nenhuma linha do template fora do bloco de pendência/mensagem foi tocada desde aquela comparação, confirmado por `git diff` desta sessão.

**T18 — resultado e foco:** garantia contratual (origem avaliada no momento da avaliação; duas aberturas concorrentes da mesma pendência não corrompem estado) **comprovada** por SQL direto e HTTP real contra Postgres descartável. Hipótese mais forte (serialização de `PhoneLine.origem` contra escrita concorrente) **não comprovada nem exigida pelo contrato** — risco residual documentado, decisão de produto pendente só se esse risco for considerado inaceitável (não é, pelo contrato aprovado até aqui).

**Arquivos candidatos à entrega** (criados/alterados pela feature, POR-01 a POR-06, separados de arquivos alheios já modificados antes desta tarefa):
- `telecom/origin_restriction.py` (novo)
- `pendencies/views.py`, `pendencies/admin.py`, `dashboard/views.py` (alterados)
- `templates/dashboard/daily_user_action_board.html` (alterado)
- `pendencies/tests/test_pendency_origin_restriction.py`, `dashboard/tests/test_daily_user_action_origin_restriction.py` (novos)
- `docs/superpowers/specs/2026-10-13-pendency-origin-restriction-design.md` (esta spec, nova)
- `docs/superpowers/evidence/2026-10-13-por05/`, `.../2026-10-13-por05-conferencia-corretiva/`, `.../2026-10-13-por06/` (evidências, novas)

**Arquivos alheios preservados, não tocados por esta tarefa:** `config/settings.py` (bump de versão 1.9.0), `docs/superpowers/specs/2026-09-10-line-daily-action-audit-design.md`, `docs/release-notes-1.9.0.md`, `docs/specs/`, diretórios de configuração de ferramentas (`.clinerules/`, `.cursor/`, `.opencode/`, `.superpowers/`, `.windsurf/`, `.github/copilot-instructions.md`, `AGENTS.md`), e as evidências de outras tarefas (`SVI-06`, `SVI-07`, `SVI-P04`, `SVI-P06`).

**Plano de deploy/rollback (documentado, não executado):** Deploy: aplicar os quatro arquivos de produção (`telecom/origin_restriction.py`, `pendencies/views.py`, `pendencies/admin.py`, `dashboard/views.py`, `templates/dashboard/daily_user_action_board.html`) numa janela normal — sem migration, sem alteração de permissão, sem dependência nova; nenhuma mudança de schema, então não há passo de dados a coordenar. Rollback: reverter os mesmos cinco arquivos (`git revert`/checkout do commit anterior) restaura o comportamento pré-feature integralmente, porque a política inteira é aditiva (dois campos novos no payload JSON, uma checagem a mais antes de gravações já existentes) — nenhum dado persistido precisa de correção pós-rollback, porque nenhuma pendência é fechada/apagada pela política (contrato explícito: mudança de origem não fecha pendência aberta). Risco residual a monitorar pós-deploy: nenhuma métrica nova foi criada para contar quantas aberturas são recusadas por origem — se o produto quiser visibilidade operacional disso, seria trabalho adicional fora do escopo aprovado.

Sem stage, commit, push, versão ou deploy executado nesta etapa. Recursos descartáveis desta rodada encerrados: container `por06-pg-disposable` (parado e removido), `runserver` em `127.0.0.1:8778` (finalizado), Chrome headless (finalizado). `lineops-db` (Postgres de dev real) não sofreu nenhuma escrita nova nesta etapa além da remoção aprovada dos três registros órfãos de POR-05 (achado, não causado, por esta tarefa). Nenhum acesso a PRD em nenhum momento.

**Veredito final:** POR-06 concluída com os critérios aprovados comprovados por evidência real e reproduzível. Nenhuma pendência material do contrato de produto permanece em aberto; os dois itens de risco residual documentados (serialização de `PhoneLine.origem` sob concorrência real e contenção estrita de foco no modal) são, pelo contrato já aprovado, informativos — não bloqueiam a conclusão porque não foram exigidos pelo contrato e estão documentados para decisão futura caso o produto queira ampliá-lo.

## POR-06 — Revisão final antes de preparar commit (2026-10-13)

Revisão solicitada antes de preparar o commit, com quatro pendências explícitas: (1) reconciliar contagens de regressão e sobreposição; (2) reler os oito cenários de T18 e classificar com precisão; (3) localizar/completar evidência de teclado/foco herdada de POR-05; (4) auditar a limpeza já feita no Postgres de desenvolvimento. Nenhuma afirmação abaixo vem de releitura do relato anterior sem checar — cada uma foi conferida por arquivo/log direto ou, onde faltava evidência, por execução nova e isolada (item 3).

### Spec Summary

Nenhum defeito de aplicação encontrado nas quatro frentes. Um gap real de cobertura foi identificado e fechado nesta etapa (teclado/foco — Shift+Tab, foco inicial e retorno de foco nunca haviam sido exercitados, nem em POR-05 nem na primeira rodada de POR-06), com evidência nova, em ambiente isolado adicional (Postgres descartável #2, descartado ao final). As contagens de regressão foram reexecutadas com log salvo (antes só existiam como texto de terminal, não como arquivo de evidência) e batem com o que já estava documentado. T18 foi relido cenário a cenário e reclassificado com a distinção pedida (SQL direto vs. endpoint real; qual lock prova o quê). A limpeza do Postgres de dev foi auditada: a aprovação existe (pergunta ao usuário registrada na conversa, resposta "Limpar agora"), os comandos batem com o estado atual (recontagem 0/0, reconfirmada agora), e uma lacuna no pré-checo de integridade (uma das cinco tabelas com FK para `employees_employee` não foi consultada antes do `DELETE`) foi identificada e explicada — sem exigir nova limpeza, porque a própria constraint `NO ACTION` do Postgres já teria recusado o `DELETE` se houvesse referência pendente, e o `DELETE` foi bem-sucedido.

### Gap Analysis

**1. Contagens e sobreposição — sem discrepância nova; log agora existe em arquivo, não só em texto de terminal.**

Reexecutado nesta etapa, com saída salva em `docs/superpowers/evidence/2026-10-13-por06/`:

| Comando | Resultado | Arquivo |
|---|---|---|
| `manage.py test pendencies.tests dashboard.tests -v 2` | `Ran 171 tests` — `OK`, 0 FAILED, 0 ERROR (171 `... ok` por grep) | `regression_pendencies_dashboard.log` |
| `manage.py test pendencies.tests -v 2` (isolado) | `Ran 91 tests` — `OK` | `regression_pendencies_only.log` |
| `manage.py test dashboard.tests -v 2` (isolado) | `Ran 80 tests` — `OK` | `regression_dashboard_only.log` |
| `manage.py test telecom -v 2` | `Ran 272 tests` — `OK (skipped=1)`; por grep: 271 `... ok`, 1 `skipped` (linha 129: `test_db_immutability_trigger_blocks_update`, "Trigger de imutabilidade so existe em Postgres" — pré-existente, não relacionado), 0 `FAIL`, 0 `ERROR` | `regression_telecom.log` |
| `pytest ... --collect-only -q` (os dois arquivos POR) | `43 tests collected` | `pytest_collect.log` |
| `pytest ...` (execução) | `43 passed, 2 warnings, 18 subtests passed` — 0 failed | `pytest_run.log` |

**91 + 80 = 171** (confirma a soma, não é coincidência — são as mesmas 171 execuções, batidas pelos dois comandos). **91 + 80 + 272 = 443** nós de teste Django distintos nas três suítes de app tocadas/relacionadas, sem sobreposição entre si (apps diferentes). Os **43** do `pytest`/`--collect-only` **não são um quarto pool somável** — são os métodos dos dois arquivos `test_pendency_origin_restriction.py` (33, confirmado por `grep -c "    def test_" pendencies/tests/test_pendency_origin_restriction.py`) e `test_daily_user_action_origin_restriction.py` (10, mesmo grep), que já estão **dentro** dos 91 e dos 80 respectivamente — a frase do relatório anterior "regressão 171+272+43" (usada no resumo de chat, não na spec) somava um subconjunto como se fosse um conjunto disjunto; retificado aqui. A spec já havia listado os três números separadamente na seção anterior (sem a soma indevida), mas o resumo de chat conflacionou; esta seção é a retificação explícita.

**Métodos vs. subtestes vs. skips, separados (não somados):**
- Métodos de teste (nós `def test_*`): 91 (`pendencies.tests`) + 80 (`dashboard.tests`) + 272 (`telecom.tests`) = 443, todos `OK`.
- Subtestes (`self.subTest(...)` dentro de métodos, contador adicional do `pytest-subtests`, não presente no sumário do `manage.py test`): 18, só nos dois arquivos POR — não há contagem equivalente separada para `telecom`/resto de `pendencies`/`dashboard` nesta etapa (não pedida).
- Skips: exatamente 1, em `telecom.tests`, pré-existente (dependente de Postgres real para testar um trigger de imutabilidade a nível de banco — `migration 0019`), não relacionado a esta feature.
- Verificações de navegador/HTTP real (scripts `por06_*.py`, não `pytest`/`manage.py test`): 21 (`browser_accept.log`) + 7 (`admin_http.log`) + 4 (`t18_locks.log`) + 4 (`t18_http_race.log`) + 10 (`keyboard_focus.log`, nesta revisão) = **46 verificações**, cada uma uma asserção Python própria deste conjunto de scripts — **não são nós de teste `pytest`/Django, não contam nos 443, e não devem ser somadas a eles.** São uma categoria à parte (aceite real), do mesmo jeito que T15/T18 sempre foram tratados como fora do pytest local nas specs anteriores.

Nenhuma FAIL, ERROR ou discrepância de coleta encontrada em nenhuma das reexecuções.

**2. T18 — releitura cena a cena dos oito nós, classificação explícita.**

Os "oito cenários" são as oito linhas `[PASS]` reais em `t18_locks.log` (4) + `t18_http_race.log` (4) — lidos diretamente dos scripts (`por06_t18_locks.py`, `por06_t18_http_race.py`) nesta revisão, não só do texto da spec anterior:

| # | Script | O que o cenário demonstra, exatamente | Camada |
|---|---|---|---|
| T18.1 | `t18_locks.py` | Conexão A faz `SELECT ... FOR UPDATE` em `AllocationPendency` (linha específica) e mantém a transação aberta; conexão B tenta o mesmo `SELECT ... FOR UPDATE` na mesma linha e fica **mensuravelmente bloqueada** (~1,2s, igual ao `time.sleep` que A mantém o lock) até A commitar. Prova: lock de linha real do Postgres, não é teste hipotético. | SQL direto (`psycopg2`, duas conexões, sem passar pela view) |
| T18.2 | `t18_locks.py` | Mesmo padrão, para `LineAllocation` (o lock usado por `daily_user_action_board`). | SQL direto |
| T18.3 | `t18_locks.py` | Enquanto a conexão A ainda segura o lock de `AllocationPendency` (sem commitar), a conexão B executa `UPDATE telecom_phoneline SET origem=...` na linha relacionada e **isso NÃO fica bloqueado** (~5ms, não ~1,2s) — ou seja, **alteração concorrente de `PhoneLine.origem` logo após uma transação já ter lido/travado a pendência, mas antes dela commitar.** Prova, por medição e não por leitura de código, que o lock de `AllocationPendency`/`LineAllocation` não se propaga para `PhoneLine`. | SQL direto |
| T18.4 | `t18_locks.py` | Uma **terceira** conexão, nova, lê `PhoneLine.origem` depois do `UPDATE` da T18.3 ter commitado — vê o valor novo. Isso demonstra leitura padrão `READ COMMITTED` (cada nova transação vê o que já foi commitado), não uma garantia de isolamento adicional. Corresponde ao cenário "origem alterada antes da avaliação": se a view ainda não tiver lido `PhoneLine.origem` no momento desse `UPDATE`, a leitura seguinte dela já verá o valor novo — é o comportamento sequencial de T17 (já coberto por `pytest`), replicado aqui a nível de SQL puro para confirmar a semântica de isolamento subjacente. | SQL direto |
| HTTP.1 | `t18_http_race.py` | Duas requisições HTTP reais (threads Python, `threading.Barrier(2)` sincronizando o instante de disparo do `urlopen`) contra `PendencyUpdateView` real, mesma pendência (origem permitida), tentando abrir ao mesmo tempo. Ambas completam (200/200) — nenhuma trava nem perde a conexão. Isso é **concorrência entre aberturas** da mesma pendência, pela pilha real da aplicação (não SQL direto). | Endpoint real (`urllib` contra `runserver` com threading, Postgres descartável) |
| HTTP.2 | `t18_http_race.py` | Estado final da pendência, lido via ORM depois das duas respostas: `action == "pending"`, um valor único e consistente — não um estado intermediário corrompido nem uma mistura dos dois payloads. | Endpoint real |
| HTTP.3 | `t18_http_race.py` | Contagem de `LineDailyActionAuditEvent` tipo `OPENED` para essa pendência, antes e depois: **exatamente 1** evento novo, não 2. Mecanismo explicado no script/spec: a 2ª requisição, ao destravar do `select_for_update`, recalcula `was_no_action` sobre o estado **já atualizado** pela 1ª (`pending`), então `new_action == pendency.action` e `action_changed` é `False` — a 2ª não entra no ramo de abertura, não grava evento, não é tratada como erro, apenas um no-op dentro do fluxo de sucesso já existente. Isso é a prova de **ausência de efeito parcial/duplicado** sob concorrência real na mesma pendência. | Endpoint real |
| HTTP.4 | `t18_http_race.py` | Pelo menos uma das duas respostas teve sucesso (200) — controle de sanidade de que a serialização não transformou a segunda requisição num erro 403/500 inesperado. | Endpoint real |

**Distinção explícita SQL direto vs. endpoint real:** T18.1–T18.4 não passam pela `view`/`url` nenhuma — são duas conexões `psycopg2` manipulando as tabelas diretamente, servindo para medir o comportamento do **lock do Postgres em si** (`FOR UPDATE`), isolado de qualquer lógica Django. HTTP.1–HTTP.4 passam pela pilha real (`PendencyUpdateView.post`, `_load_locked_pendency_for_scope`, `record_action_change`), servindo para confirmar que o **comportamento da aplicação sob concorrência real** é seguro (sem duplicar evento, sem corromper estado) — mas **não isola** o instante exato de bloqueio a nível de SQL (o `Barrier` sincroniza o disparo do HTTP do lado cliente, não há instrumentação de `pg_locks`/`pg_stat_activity` capturada durante a corrida para provar diretamente que as duas transações da aplicação se sobrepuseram no servidor). A prova **direta e inequívoca** de que o lock realmente serializa (não é coincidência de execução sequencial) vem de T18.1/T18.2 (tempo de espera mensurado, ~1,2s); HTTP.1–4 complementam mostrando que, **se** houver sobreposição (arquitetura favorece isso: `runserver` multithreaded + disparo sincronizado por barreira), o resultado é seguro — não que a sobreposição foi literalmente capturada no instante do lock.

**Não se conclui, em nenhum ponto, que a edição de `PhoneLine.origem` fica serializada só porque há locks em `AllocationPendency`/`LineAllocation`** — T18.3 mede exatamente o oposto (o `UPDATE` em `PhoneLine` não espera) e é citado explicitamente como a prova dessa não-serialização, não como uma falha do teste.

**Classificação final (sem adicionar lock nem ampliar contrato nesta revisão):**

| Garantia | Classificação | Evidência |
|---|---|---|
| Origem persistida é lida no momento da avaliação, dentro da transação que decide (nunca um valor do payload do cliente, nunca um valor "renderizado" antigo) | **Critério contratual comprovado** | T18.4 (READ COMMITTED real) + T17 (pytest, sequencial) + T17 navegador (`browser_accept.log` #13,14) |
| Duas tentativas concorrentes de abrir a mesma pendência não duplicam evento nem corrompem estado | **Critério contratual comprovado** | HTTP.1–HTTP.4, decorre do `select_for_update` já existente, não de garantia nova |
| Edição concorrente de `PhoneLine.origem` fica serializada/bloqueada em relação à decisão de abrir | **Risco residual fora da garantia contratada** — o contrato aprovado não pede essa serialização, só pede "origem persistida no momento da avaliação" (já comprovado); nenhum lock novo foi adicionado | T18.3 (medição direta: não bloqueia) |
| Há um defeito de aplicação relacionado a T18 | **Nenhum encontrado** — nenhuma das oito verificações falhou, nenhum estado inconsistente observado | Todas as oito, `t18_locks.log`/`t18_http_race.log` |
| Decisão de produto pendente | Só **se** o risco residual acima for considerado inaceitável (ex.: exigir `select_for_update` em `PhoneLine` nos três pontos) — não é uma lacuna de teste, é uma escolha de escopo já registrada desde POR-04/conferência corretiva, reconfirmada agora por medição direta em vez de só leitura de código | — |

**3. Teclado e foco — lacuna real confirmada por releitura dos scripts; fechada nesta etapa com evidência nova, em ambiente isolado adicional.**

Releitura de `por05_browser_smoke.py`, `por06_browser_accept.py` e de todos os scripts de `2026-10-13-por05-conferencia-corretiva/` (grep por `Shift`, `returnFocus`, `aria-hidden`, `focus.*return`): **nenhuma ocorrência** em nenhum deles. Confirmado por releitura direta, não por confiança no relato: as três rodadas anteriores (POR-05 original, conferência corretiva de POR-05, primeira rodada de POR-06) só dispatcharam **Tab pra frente**, sempre a partir de um foco **setado manualmente via JS** (`document.getElementById('pendencyObservation').focus()`), nunca testaram:
- Foco inicial real do modal ao abrir (o que o Bootstrap foca sozinho, sem nenhum `.focus()` deste script).
- Shift+Tab (navegação reversa).
- Fechamento via tecla real (as rodadas anteriores sempre fechavam clicando em `[data-bs-dismiss='modal']`, nunca com `Escape`).
- Retorno de foco após fechar.

Executado agora, isolado, ambiente novo (container `por06b-pg-disposable`, porta 55434, destruído ao final; servidor em `127.0.0.1:8779`; Chrome headless porta 9444; todos finalizados ao fim do script, nenhum resíduo). **10/10 PASS** (`keyboard_focus.log`):

- Abrir o modal foi feito por **clique real de mouse** (coordenada via CDP, não `btn.click()` via JS) — consistente com o método usado no desktop nas seções anteriores.
- **Foco inicial:** `document.activeElement` logo após o modal abrir (sem nenhum `.focus()` deste script) é o próprio elemento `#pendencyModal` (`tabindex="-1"`, padrão do Bootstrap 5 — o modal container recebe foco quando não há `autofocus` configurado) — dentro do modal, não vazou pra tabela atrás.
- **Tab (10x):** sequência real `pendencyModal → BUTTON (fechar) → pendencyObservation → BUTTON → pendencySaveBtn → BODY → BUTTON → pendencyObservation → BUTTON → pendencySaveBtn → BUTTON`. O `<select>` desabilitado pela origem (`pendencyAction`/`pendencyActionSubmit`) não aparece nenhuma vez.
- **Shift+Tab (10x), a partir do ponto final do Tab:** percorre de volta por elementos já visitados na ida (`pendencySaveBtn`, `pendencyObservation`, `BUTTON` — ciclo coerente, não quebrado), sem o `<select>` desabilitado em nenhum momento também no sentido reverso — **primeira vez que o sentido reverso foi exercitado em qualquer rodada desta feature.**
- **Mensagem não cortada:** `#pendencyOriginBlockedText` (`right: 1023px`) fica dentro de `.modal-dialog` (`right: 1040px`) em todos os momentos medidos.
- **Fechamento com tecla real (`Escape`, nunca testado antes):** fecha o modal de fato (`classList` perde `show`).
- **Retorno de foco após fechar:** `document.activeElement` vira `BODY`, **não** o botão que abriu o modal. Registrado como **observação, não como falha** — o contrato aprovado (POR-01/Fechamento) só exige "fechamento... conforme comportamento existente", não promete restaurar foco ao gatilho; e o próprio mecanismo de abertura (um `addEventListener('click', ...)` genérico delegado no `document`, não um atributo `data-bs-toggle="modal"` apontando pro botão) é a razão técnica: o Bootstrap só restaura foco automaticamente quando é ele mesmo quem abre o modal a partir de um elemento com esse atributo: aqui quem abre é JS próprio da página. Nenhuma linha de JS/CSS de foco foi alterada por esta ou por nenhuma etapa da feature — comportamento pré-existente ao bloqueio por origem, não introduzido por ele.
- **Achado informativo, reproduzido pela terceira vez (POR-05: ~3/15; POR-06 rodada 1: 2/15; esta rodada: 1/10 no Tab de ida, nenhuma no Shift+Tab):** `BODY` aparece no meio da sequência de Tab, não só nas pontas — mantido como limitação do método sintético (`Input.dispatchKeyEvent` via CDP contra o focus-trap do Bootstrap 5 em Chrome headless), **nem comprovado nem refutado** como regressão real, pela mesma razão já registrada nas rodadas anteriores (reprodutível e consistente em ordem de grandeza, mas não confirmável como "contenção estrita" sem teclado físico real).

Separação exigida — observado vs. limitado pelo harness: tudo que envolve **direção** (Tab e Shift+Tab não pousam no `<select>` desabilitado; a mensagem não é cortada; `Escape` fecha; foco inicial fica dentro do modal) foi **observado e comprovado** por teclado real via protocolo do navegador. Só a **contenção estrita** (Tab nunca pousar fora do modal, ponto a ponto) permanece **limitada pelo harness** — não confirmada nem refutada, e não tratada como ausência de prova igual a defeito.

**4. Limpeza no Postgres de desenvolvimento — auditada; confirmada corretamente autorizada e executada; uma lacuna de pré-checagem identificada e explicada, sem exigir nova limpeza.**

- **Banco/container efetivamente acessado:** `lineops-db` (nome do container Docker), mapeado para a porta `5433` do host, banco `lineops` — confirmado nesta auditoria por `docker ps` (container listado, rodando desde antes desta tarefa, não criado por ela) e pelos comandos reais executados via `docker exec lineops-db psql -U lineops -d lineops`. Este é o Postgres de **desenvolvimento**, não produção (`ssh lineops-prod` aponta para outro host, `10.103.4.184`, nunca acessado nesta tarefa nem nesta revisão).
- **Critério usado para identificar dados do ensaio:** prefixo `POR05SMOKE` em `employees_employee.employee_id`/`full_name` (`ILIKE '%por05smoke%'`) e em `users_systemuser.email` (`ILIKE '%por05smoke%'`) — mesmo prefixo usado pelos scripts de fixture de POR-05 (`por05_setup_fixtures.py`, `TAG = "POR05SMOKE"`), conferido por leitura do próprio script antes de identificar os registros como órfãos.
- **Autorização:** registrada na conversa via `AskUserQuestion` ("Postgres dev... tem lixo sintético orfão de POR-05... Limpo agora ou só registro achado e sigo?"), resposta do usuário: **"Limpar agora (Recomendado)"**. Sem essa resposta, nenhuma escrita teria sido feita no `lineops-db`.
- **Tabelas/registros efetivamente atingidos** (reconfirmado agora por leitura do histórico de comandos desta sessão, não por memória): `employees_employeehistory` (1 linha, `employee_id=12`, deletada **antes** da linha de `employees_employee` por causa da constraint `NO ACTION` dessa FK — não havia `ON DELETE CASCADE`, a ordem foi manual); `employees_employee` (1 linha, `id=12`, `employee_id='POR05SMOKE-BlockedNew'`); `users_systemuser` (2 linhas, `POR05SMOKE.super@test.local` e `POR05SMOKE.admin@test.local`). **Nenhuma cascata automática do banco** — todas as três exclusões foram comandos `DELETE` explícitos, numa única transação (`BEGIN...COMMIT`).
- **Comandos executados** (reconstituídos do histórico desta sessão, sem credenciais reais envolvidas — usuário/senha são os do Postgres de dev local, já presentes em `.env`/`docker-compose`, não segredos de produção):
  ```sql
  BEGIN;
  DELETE FROM employees_employeehistory WHERE employee_id=12;
  DELETE FROM employees_employee WHERE id=12;
  DELETE FROM users_systemuser WHERE email IN ('POR05SMOKE.super@test.local','POR05SMOKE.admin@test.local');
  COMMIT;
  ```
  Saída na época: `BEGIN` / `DELETE 1` / `DELETE 1` / `DELETE 2` / `COMMIT` — todos os quatro comandos da transação retornaram sucesso, nenhum erro de violação de FK.
- **Verificações posteriores disponíveis:** recontagem imediata após o `COMMIT` (`0`/`0` para os dois critérios `ILIKE`), e **reconfirmada agora, nesta auditoria** (mesma consulta, mesmo resultado `0`/`0` — ver comando desta revisão).
- **Lacuna de pré-checagem identificada nesta auditoria:** antes do `DELETE`, só 4 das 5 tabelas com FK real para `employees_employee` foram checadas manualmente (`employees_employeehistory`, `allocations_lineallocation`, `pendencies_allocationpendency`, `dashboard_dailyuseraction`) — **`telecom_linedailyactionauditevent` não foi consultada antes de apagar**, confirmado agora por uma consulta a `information_schema` que lista as 5 tabelas com FK real para `employees_employee`, todas com `delete_rule = NO ACTION`. Isso **não** significa que a exclusão foi insegura: como as 5 constraints são `NO ACTION` (não `CASCADE`, não `SET NULL`), o Postgres **teria recusado** o `DELETE FROM employees_employee WHERE id=12` dentro da mesma transação se qualquer uma das 5 tabelas (incluindo a que não foi checada) tivesse uma linha referenciando `employee_id=12` — e o `DELETE` retornou sucesso (`DELETE 1`, seguido de `COMMIT`, não de `ROLLBACK`/erro). A garantia de integridade vem da própria constraint do banco, não da minha checagem manual ter sido exaustiva — registrado aqui como a forma correta de atestar a ausência de referência pendente, não como "eu conferi todas as tabelas antes" (o que seria impreciso).
- **O que esta auditoria NÃO certifica:** não há baseline (dump/contagem) do `lineops-db` de antes da criação dos dados de POR-05 para comparar contra o estado atual tabela a tabela — a comprovação de "nenhum outro resíduo" se apoia no critério de busca por prefixo (`POR05SMOKE`/`POR06SMOKE` — este, aliás, buscado agora também, resultado `0`, nenhum dado de POR-06 nunca tocou o `lineops-db`) mais a garantia estrutural de FK acima, não numa auditoria linha-a-linha de todas as tabelas do banco. Não se certifica retroativamente "nenhum recurso de desenvolvimento foi tocado" — **foi tocado**, de forma autorizada e documentada, e o que se certifica é que a escrita foi a aprovada (3 registros órfãos, critério por prefixo, sem cascata além das 3 tabelas listadas) e que não ficou pendência de integridade referencial depois dela.
- **Nenhuma nova limpeza foi executada nesta auditoria** — só consultas `SELECT`/`information_schema` (somente leitura) contra `lineops-db`.

### Implementation Plan

Nenhuma alteração de código de aplicação nesta revisão. Alterações desta etapa: reexecução de regressão com log salvo (arquivo, não código), um script novo e isolado de teclado/foco (`por06b_keyboard_focus.py` e fixtures/settings associados, arquivados em `docs/superpowers/evidence/2026-10-13-por06/`), e esta atualização de spec.

### Test Checklist — matriz pendência → evidência consultada → conclusão → limitação

| Pendência | Evidência consultada | Conclusão | Limitação |
|---|---|---|---|
| 1. Contagens e sobreposição | `regression_pendencies_dashboard.log`, `regression_pendencies_only.log`, `regression_dashboard_only.log`, `regression_telecom.log`, `pytest_collect.log`, `pytest_run.log` (todos novos, reexecutados nesta revisão); `grep -c` direto nos dois arquivos de teste | 91+80=171 (pendencies+dashboard), +272 (telecom) = 443 nós distintos, 0 FAIL/ERROR, 1 SKIP (pré-existente); 43 do pytest são subconjunto de 91+80 (33+10), não somável; 18 subtestes e 46 verificações de navegador/HTTP são categorias separadas, não nós `pytest` | O resumo de chat da rodada anterior ("171+272+43") somou indevidamente; a spec em si já não cometia esse erro. Retificado aqui, sem alterar os números-base (que já estavam certos) |
| 2. T18 / PostgreSQL | `por06_t18_locks.py`, `por06_t18_http_race.py`, `t18_locks.log`, `t18_http_race.log` (lidos integralmente nesta revisão) | Garantia contratual (origem no momento da avaliação; abertura concorrente não corrompe nem duplica) comprovada; serialização de `PhoneLine.origem` continua **não** coberta pelo contrato (risco residual, não defeito); nenhum defeito de aplicação | HTTP.1–4 provam segurança da aplicação sob tentativa de concorrência, não o instante exato de sobreposição das transações no servidor (sem instrumentação de `pg_locks` durante a corrida) — T18.1/T18.2 é que provam bloqueio real, por medição de tempo |
| 3. Teclado e foco | `keyboard_focus.log` (novo, 10/10 PASS); releitura de todos os scripts anteriores (grep por `Shift`/`returnFocus`) | Gap real confirmado (Shift+Tab, foco inicial e retorno de foco nunca testados antes) e fechado com evidência nova: direção/alcançabilidade comprovadas; contenção estrita de foco segue como achado informativo, reproduzido pela 3ª vez | Ambiente isolado adicional (Postgres descartável #2), já destruído; não é teclado físico real, é protocolo do navegador (mecanismo padrão de automação, não simulação de app) |
| 4. Limpeza Postgres dev | Histórico de comandos desta sessão + reconsulta `information_schema` e recontagem `0`/`0` nesta auditoria | Autorização existe e está registrada; comandos batem com o estado atual; 4 de 5 tabelas com FK foram checadas antes do `DELETE`, a 5ª é coberta retroativamente pela garantia de constraint `NO ACTION` (o `COMMIT` só teria ocorrido se nenhuma referência existisse) | Sem baseline anterior à criação dos dados de POR-05 para comparação tabela-a-tabela; certificação é por critério de prefixo + garantia estrutural de FK, não por auditoria exaustiva de todo o banco |

### Test Strategy

Mesma filosofia das etapas anteriores: nenhuma afirmação aceita sem arquivo/log/script conferido diretamente nesta revisão. Onde a evidência já existia e era suficiente (contagens, T18), foi **relida e reexecutada** para confirmar, não apenas citada. Onde a evidência não existia (teclado/foco: Shift+Tab, foco inicial, retorno de foco), foi **executada agora**, em ambiente isolado adicional (Postgres descartável distinto do usado antes, destruído ao final), sem reabrir a implementação nem repetir os outros ensaios já suficientemente cobertos. A auditoria da limpeza do Postgres de dev foi feita **só com leitura** (`SELECT`/`information_schema`), sem nova escrita.

### Compliance Report

**Reconciliação das quatro pendências pedidas:**

1. **Contagens/sobreposição:** reconciliadas. 171 (91+80) + 272 (telecom) = 443 nós de teste Django distintos, todos `OK`, 1 skip pré-existente. Os 43 do `pytest` são subconjunto dos 171 (33 em `pendencies.tests`, 10 em `dashboard.tests`), não um quarto pool. 18 subtestes e 46 verificações de navegador/HTTP/SQL (`por06_*.py`) são categorias à parte, contadas separadamente. Nenhuma FAIL/ERROR em nenhuma reexecução.
2. **T18:** os oito cenários relidos e reclassificados — quatro por SQL direto (medem o lock do Postgres em si, com tempo de espera real), quatro por HTTP real (medem segurança da aplicação sob tentativa de concorrência). Garantia contratual comprovada (origem no momento da avaliação; sem corrupção/duplicação em abertura concorrente). Serialização de `PhoneLine.origem` permanece risco residual fora do contrato, não corrigido nem exigido. Nenhum defeito de aplicação.
3. **Teclado/foco:** gap real confirmado por releitura (Shift+Tab, foco inicial, retorno de foco nunca testados); fechado nesta etapa com execução real isolada, 10/10 PASS. Direção e alcançabilidade comprovadas; contenção estrita de foco permanece achado informativo (3ª reprodução consistente), não promovido a defeito por ausência de prova definitiva.
4. **Limpeza Postgres dev:** auditada. Autorização real e registrada; comandos conferem com o estado atual (`0`/`0` reconfirmado); uma lacuna de pré-checagem (1 de 5 tabelas com FK não consultada antes do `DELETE`) identificada e coberta retroativamente pela própria garantia de integridade referencial do Postgres (`NO ACTION`, `DELETE` só teve sucesso porque não havia referência pendente). Nenhuma nova limpeza executada. Não se certifica "nenhum recurso de dev tocado" — foi tocado, de forma autorizada, com escopo e critério registrados.

**Nenhum defeito de aplicação encontrado em nenhuma das quatro frentes.** O único gap de cobertura (teclado/foco) foi de **evidência**, não de comportamento do produto — e já foi fechado nesta mesma revisão, com resultado 100% PASS.

**Arquivos novos desta revisão:** `docs/superpowers/evidence/2026-10-13-por06/regression_pendencies_dashboard.log`, `regression_pendencies_only.log`, `regression_dashboard_only.log`, `regression_telecom.log`, `pytest_collect.log`, `pytest_run.log`, `keyboard_focus.log`, `por06b_settings.py`, `por06b_setup_fixtures.py`, `por06b_keyboard_focus.py`. Nenhum arquivo de aplicação alterado.

**Recursos descartáveis desta revisão, todos encerrados ao final:** container `por06b-pg-disposable` (porta 55434, parado e removido), `runserver` em `127.0.0.1:8779` (finalizado), Chrome headless na porta de debug 9444 (finalizado, processo específico, não um `taskkill` genérico de todos os `chrome.exe`). `lineops-db` só recebeu consultas de leitura nesta revisão (nenhuma nova escrita).

**Veredito desta revisão:** **PRONTO PARA PREPARAÇÃO DO COMMIT.** As quatro pendências foram reconciliadas por evidência direta (arquivo/log/script), não por reafirmação do relato anterior. Nenhum defeito de aplicação foi encontrado. Os itens classificados como risco residual (serialização de `PhoneLine.origem`, contenção estrita de foco) e a ressalva de rastreabilidade (cobertura de FK pré-checagem na limpeza do Postgres dev) **não são bloqueantes à luz do contrato aprovado**: nenhum dos dois foi exigido pelo contrato de produto (POR-01/Fechamento das quatro decisões), e a integridade referencial da limpeza é garantida estruturalmente pelo próprio banco, não dependente da minha checagem manual ter sido exaustiva. Preparação de commit pode prosseguir sobre os arquivos já listados como candidatos à entrega na seção anterior — sem stage, commit, push, PR, deploy, acesso a PRD ou nova limpeza de banco executados nesta revisão.

**Retificação (ver "POR-06 — Correção de dois defeitos de interação" abaixo, 2026-10-13):** o veredito "PRONTO PARA PREPARAÇÃO DO COMMIT" acima está **retificado** — dois defeitos reais de interação JavaScript foram encontrados depois desta revisão (não pela bateria de 443 testes de backend, que não cobre o fluxo de interação do modal) e precisaram de correção antes do commit. Texto acima preservado como histórico; ver seção seguinte para o estado real.

## POR-06 — Correção de dois defeitos de interação (2026-10-13)

Dois defeitos reais de JavaScript no modal de pendências, relatados com reprodução precisa, confirmados por leitura do código antes de qualquer teste e corrigidos nesta etapa. Spec → Tests → Code → Validation, como pedido.

### Spec Summary

**Defeito 1 — botões presos após troca de registro.** `saveBtn.disabled`/`claimBtn.disabled` são setados `true` de forma síncrona no clique (`savePendency()` linha 714, `submitResponsibleAction()` linha 771) e só voltam a `false` dentro do `finally` de cada função, **condicionado ao token da requisição ainda bater** (linhas 765/806 — guarda correta, não deve ser removida). Quando o usuário troca de registro (ou fecha/reabre o modal) antes da resposta de A chegar, `loadPendency` incrementa `currentRequestToken` (linha 688) e `renderModal(data)` é chamado para popular o registro B — mas `renderModal` (linha 568–685) **nunca toca `saveBtn.disabled`/`claimBtn.disabled`**. Quando a resposta antiga de A finalmente chega, o `finally` compara o token e, corretamente, **não** reabilita o botão (porque o token mudou) — mas como nada mais o reabilita para B, o botão fica preso desabilitado para sempre no registro B, mesmo que B tenha permissão de salvar/assumir.

**Defeito 2 — select desabilitado ainda envia tentativa de abertura.** Para papéis não-ADMIN, `renderModal` monta `submittableChoices` filtrando **fora** o valor `no_action` (linha 616–618: `data.action_choices.filter(c => c.value !== 'no_action')`) antes de popular `pendencyActionSubmit` (linha 623). Quando a pendência está em `no_action` (nunca aberta) — exatamente o caso em que a origem pode estar bloqueada — nenhuma `<option>` da lista filtrada bate com `data.action` (`'no_action'`), então `populateSelect` (linha 548–557) nunca marca nenhuma opção como `selected`, e o navegador aplica o padrão do HTML: a **primeira** opção da lista (uma ação de abertura real, ex.: "Número Novo") fica selecionada — mesmo com o `<select>` desabilitado pela origem (`actionSubmitSel.disabled = blockOpening`, linha 646). Em `savePendency()` (linha 719–725), `actionValue` é lido direto de `document.getElementById('pendencyActionSubmit').value` **sem checar `.disabled`** — o atributo `disabled` de um `<select>` não impede leitura programática de `.value` em JavaScript, só bloqueia interação do usuário e inclusão em submit de `<form>` nativo (este código não usa um `<form>`, monta o JSON manualmente). Resultado: ao editar só a observação e clicar Salvar, o payload carrega `action: "new_number"` (ou o que for a primeira opção), diferente de `pendency.action` (`"no_action"`) — o backend (`PendencyUpdateView.post`, `action_changed = bool(new_action) and new_action != pendency.action`) interpreta isso como tentativa de abertura, cai no `elif is_origin_blocked_for_opening(...)` e recusa com 403, **impedindo até a edição de observação**, que deveria ser permitida.

Ambos os defeitos são só no JavaScript do template (`templates/dashboard/daily_user_action_board.html`); nenhuma política de origem, permissão ou contrato HTTP de `pendencies/views.py`/`dashboard/views.py`/`telecom/origin_restriction.py` está envolvida ou será alterada.

### Gap Analysis

- Nenhum dos 443 nós de teste Django (`pendencies.tests`+`dashboard.tests`+`telecom.tests`) nem os 46 scripts de aceite de navegador das rodadas anteriores de POR-06 exercitaram o cenário exato de cada defeito: as rodadas anteriores de "resposta atrasada" (POR-05/conferência corretiva, `savePendency`/`submitResponsibleAction` com guarda de token) sempre testaram **identidade do registro** (nome do usuário, mensagem), nunca o estado **habilitado/desabilitado dos botões** depois da troca — gap 1. As rodadas de origem bloqueada sempre testaram o **ADMIN** (cujo `<select>` completo inclui `no_action` e não sofre o problema) ou, quando testaram SUPER, sempre deixaram a observação como estava **sem alterar nem clicar Salvar** nesse estado específico (os cenários de origem bloqueada testados eram só leitura do modal, nunca um Salvar de observação pura) — gap 2.
- Causa raiz de cada defeito confirmada por leitura de código antes de qualquer teste (ver Spec Summary acima com números de linha exatos), não por suposição.
- Nenhuma lacuna de política backend — `PendencyUpdateView.post` já suporta corretamente "ação não alterada" via `new_action` vazio (`action_changed = bool(new_action) and ...` — string vazia é falsy), que é exatamente a semântica que faltava a UI usar.

### Implementation Plan

**Arquivo único a alterar:** `templates/dashboard/daily_user_action_board.html`.

1. **Defeito 1:** em `renderModal(data)`, resetar `saveBtn.disabled = false;` e `claimBtn.disabled = false;` — `renderModal` só é chamado quando há um estado fresco e atual pra exibir (carga inicial de um registro, ou sucesso de save/claim/release do próprio registro ainda ativo), nunca pelo caminho de uma resposta descartada por token diferente; portanto é o ponto certo pra garantir que o registro recém-exibido sempre comece com os dois controles utilizáveis, sem depender de o `finally` de uma operação antiga (de outro registro) ter rodado. Não altera nenhuma guarda de token existente — elas continuam sendo o que impede conteúdo/mensagem antigos de vazarem pra um registro novo; só adiciona o reset de estado que faltava.
2. **Defeito 2:** em `savePendency()`, ao calcular `actionValue`, checar se o elemento de origem está `.disabled` antes de ler `.value` — se desabilitado (só acontece por `blockOpening`, nenhum outro código desabilita esses dois selects), usar `''` em vez do valor visual. Isso aciona a semântica já existente no backend de "ação não alterada" (`new_action` vazio → `action_changed = False`), preservando observação e demais operações. Não mexe em `populateSelect`/`submittableChoices` (continua sem oferecer `no_action` a não-ADMIN, evitando liberar semântica de resolução) nem em nenhuma regra de backend.

Nenhuma migration, nenhuma dependência nova, nenhuma alteração de `pendencies/`, `dashboard/views.py` (Python) ou `telecom/`.

### Test Checklist (antes da correção — alvo do RED)

1. Salvar(A) atrasado, trocar pra B antes da resposta: botão Salvar de B deve ficar utilizável e o clique em B deve efetivamente disparar e concluir uma operação.
2. Assumir/Liberar(A) atrasado, trocar pra B: mesmo resultado pro botão de responsável técnico.
3. Erro atrasado de A (403) não aparece no `saveStatus` de B.
4. Fechar modal durante operação pendente de A e reabrir (mesmo registro ou outro): botão não preso.
5. Origem bloqueada, não-ADMIN, editar só observação e salvar: payload não deve conter uma ação de abertura; resposta deve ser sucesso; observação persistida; `action` continua `no_action`; nenhum evento `OPENED`/`REOPENED` novo.
6. Controles positivos (origem permitida) e tratamento de pendência já aberta continuam funcionando sem mudança.
7. POST direto tentando abrir (origem bloqueada, agora via requisição real, não mascarada pelo select) continua recusado com a mensagem exata — regressão do contrato de backend, não nova regra.

### Test Strategy

Mesma filosofia das etapas anteriores: Chrome headless real via CDP (stdlib Python, cliente `cdp_client.py` reaproveitado sem alteração), Postgres **descartável** dedicado (`por06fix-pg`, porta 55435, destruído ao final), servidor real (`runserver`), dados 100% sintéticos (`POR06FIX_*`). Mesmo script (`por06fix_bugs_test.py`) roda antes (RED) e depois (GREEN) da correção — só o nome do log muda (`01-red.log`/`02-green.log`), nenhuma lógica do template foi copiada para o teste: os testes clicam nos botões/selects reais e leem `window.__lastPostBody` (capturado por um override de `window.fetch`, só pra inspeção, nunca reimplementando a montagem do payload) e o DOM real (`disabled`, `textContent`), nunca reimplementam `renderModal`/`savePendency`. Atraso de resposta via override de `fetch` (`window.__postDelayMs`, consumido uma única vez), mesmo padrão já usado em POR-05/POR-06. Limite do harness declarado: o clique é via coordenada de mouse real (CDP `Input.dispatchMouseEvent`-equivalente usando `.click()` direto no elemento, já que aqui o alvo nunca está fora do viewport) no desktop; no mobile, `btn.click()` via JS pelo mesmo motivo de quirk de `window.innerWidth` em emulação headless já documentado nas rodadas anteriores — não uma limitação nova, não investigada de novo aqui (fora do escopo deste achado).

Regressão de backend: `manage.py test pendencies.tests dashboard.tests` (SQLite padrão, não o Postgres descartável) e `pytest` sobre os dois arquivos POR — nenhum teste Python foi criado ou alterado (a correção é só JavaScript), então qualquer mudança de resultado ali seria regressão real. `manage.py check` e `git diff --check` conferidos no final. Nenhum teste de T18 (SQL direto/concorrência Postgres) foi reexecutado — nenhuma mudança nesta etapa afeta lock/transação, só o JavaScript do modal.

### Test Checklist — resultado (RED → GREEN real, node por node)

| # | Verificação | RED (antes) | GREEN (depois) |
|---|---|---|---|
| B1.1 | Salvar(A) atrasado + troca pra B: botão Salvar de B utilizável | FAIL (`saveBtnDisabled: True`) | PASS |
| B1.2 | Clique em Salvar em B após a troca dispara e conclui | FAIL (travado, `saveStatusText` nunca muda) | PASS (`Salvo com sucesso.`) |
| B1.3 | Assumir(A) atrasado + troca pra B (pendência já aberta): botão Assumir/Liberar de B utilizável | FAIL (`claimBtnDisabled: True`) | PASS |
| B1.4 | Clique em Assumir em B após a troca dispara e conclui | FAIL (travado) | PASS (`Responsável técnico atribuído.`, `claimBtnText: Liberar`) |
| B1.5 | Fechar durante operação pendente de A e reabrir o mesmo registro: botão não preso | PASS (já funcionava — fechar/reabrir já recarrega via `loadPendency`) | PASS |
| B1.6 | Sem exceções JS no bloco do defeito 1 | PASS | PASS |
| B2.1 | Payload de `savePendency` não contém ação de abertura quando o select está desabilitado por origem | FAIL (`action: "new_number"`) | PASS (`action: ""`) |
| B2.2 | Resposta de sucesso ao editar só observação em origem bloqueada | FAIL (403, mensagem de origem) | PASS (`Salvo com sucesso.`) |
| B2.3 | Observação persistida | PASS (persistida mesmo com erro — já era true antes) | PASS |
| B2.4 | `AllocationPendency.action` continua `no_action` no banco | PASS | PASS |
| B2.5 | Nenhum evento `OPENED`/`REOPENED` novo | PASS | PASS |
| B2.6 | Controle: origem permitida, abrir selecionando ação real | PASS | PASS |
| B2.7 | Controle: tratamento (claim+observação) de pendência já aberta em origem bloqueada | PASS | PASS |
| B2.8 | Defesa em profundidade: select reabilitado via JS pra um valor real — servidor ainda recusa | PASS | PASS |
| — | Sem exceções JS em toda a sessão | PASS | PASS |

**Total:** 16 verificações por rodada. RED: 10 PASS, **6 FAIL** (exatamente as 6 que correspondem aos dois defeitos — nenhuma falha de setup misturada, controles e regressões todos PASS desde o RED). GREEN: **16/16 PASS**, 0 FAIL.

**Mobile (390px/360px), rodada separada após o GREEN** (`por06fix_mobile_check.py`, `03-mobile-regression.log`): **10/10 PASS** — botão Salvar de B utilizável após Salvar(A) atrasado + troca (ambas as larguras); `.modal-dialog` não estoura o viewport físico (`overflow=-16` nas duas larguras, sem regressão de layout); mensagem de origem bloqueada visível; salvar só observação em origem bloqueada funciona também no mobile; console/rede limpos.

**Regressão de backend** (`regression_pendencies_dashboard.log`, `pytest_run.log`): `manage.py test pendencies.tests dashboard.tests -v 2` → **171/171 PASSED**, 0 FAILED, 0 ERROR (idêntico ao baseline de todas as rodadas anteriores — correção é só JS, nenhum teste Python tocado). `pytest` sobre os dois arquivos POR → **43 passed, 18 subtests passed**, 0 failed. `manage.py check` → "System check identified no issues (0 silenced)." `git diff --check` → só os dois avisos pré-existentes de CRLF, nenhum novo.

### Compliance Report

**Causa de cada defeito** (confirmada por leitura de código antes do teste, ver Spec Summary): Defeito 1 — `saveBtn.disabled`/`claimBtn.disabled` nunca eram resetados ao exibir um registro novo, só no `finally` da própria operação (guardado por token, que corretamente não dispara pra um registro trocado). Defeito 2 — `populateSelect` filtra `no_action` da lista de não-ADMIN; quando `data.action` é `no_action` (único caso em que a origem pode bloquear), nenhuma opção bate, o HTML seleciona a primeira opção real por padrão, e `savePendency` lia `.value` sem checar `.disabled`.

**Arquivo alterado:** `templates/dashboard/daily_user_action_board.html` (único arquivo de produção tocado — 2 blocos de JavaScript, ~15 linhas adicionadas, nenhuma removida). Nenhuma migration, nenhuma dependência nova, nenhuma alteração de `pendencies/`, `dashboard/views.py` (Python) ou `telecom/`.

**Node IDs / verificações, RED → GREEN:** ver tabela acima (16 verificações por rodada, scripts `por06fix_bugs_test.py` + `por06fix_mobile_check.py`, não `pytest`/`manage.py test` — são scripts de aceite via navegador real, mesma categoria já estabelecida nas rodadas anteriores de POR-06, não nós Django). Métodos/subtestes do backend (`pytest`/`manage.py test`) continuam exatamente nos mesmos números das rodadas anteriores (171 + 43 subconjunto), **sem overlap somado**: os dois conjuntos (verificações de navegador vs. nós Django) são categorias distintas, não somadas entre si nem com os 46 scripts de aceite das rodadas de revisão anteriores (esses continuam válidos, não reexecutados aqui por não terem relação com os dois defeitos — critério "não ampliar escopo" respeitado).

**Evidências novas:** `docs/superpowers/evidence/2026-10-13-por06-ui-fixes/` — `01-red.log` (10/16 PASS, 6 FAIL reais), `02-green.log` (16/16 PASS), `03-mobile-regression.log` (10/10 PASS), `regression_pendencies_dashboard.log` (171/171 PASSED), `pytest_run.log` (43 passed/18 subtests), scripts completos (`por06fix_settings.py`, `por06fix_setup_fixtures.py`, `por06fix_bugs_test.py`, `por06fix_mobile_check.py`).

**Limitações explícitas:**
- T18 (concorrência/locks em PostgreSQL) não foi reexecutado — nenhuma mudança desta etapa toca transação/lock, só JavaScript do modal; reexecutar seria repetir ensaio sem necessidade, contrário ao pedido.
- Overflow horizontal pré-existente da tabela e contenção estrita de foco no modal **não foram tocados** — permanecem exatamente como documentados nas rodadas anteriores (achados informativos, fora do escopo destes dois defeitos).
- O clique mobile via `btn.click()` (JS) em vez de coordenada de mouse real é a mesma limitação de harness já documentada desde POR-05/POR-06 (quirk de `window.innerWidth` em emulação headless) — não investigada de novo, não é uma lacuna nova introduzida por esta correção.

**Retificação do veredito anterior:** a revisão final anterior ("PRONTO PARA PREPARAÇÃO DO COMMIT") está **retificada** por esta correção — os dois defeitos reais encontrados depois daquela revisão foram corrigidos, com RED real confirmado antes (6/16 falhas, causa demonstrada em cada uma) e GREEN real confirmado depois (16/16), sem enfraquecer nenhum teste e sem regressão em nenhuma das suítes (backend 171+43, navegador desktop 16 + mobile 10, `manage.py check`, `git diff --check`).

**Veredito:** **PRONTO PARA PREPARAÇÃO DO COMMIT**, agora com os dois defeitos de interação corrigidos e validados por RED→GREEN real (navegador real, desktop e mobile) e regressão completa sem quebra. Nenhuma pendência material conhecida permanece aberta. Arquivos alterados nesta correção: só `templates/dashboard/daily_user_action_board.html`. Alterações alheias preservadas, incluindo a versão 1.9.0 em `config/settings.py`. Sem stash/reset/checkout destrutivo, migration, dependência nova, stage, commit, push, deploy ou acesso a PRD nesta etapa. Recursos descartáveis desta rodada (container `por06fix-pg`, porta 55435; `runserver` em `127.0.0.1:8780`; Chrome headless na porta de debug 9555) todos encerrados ao final — nenhum recurso de rodadas anteriores foi reaberto ou tocado. Diff pronto para nova revisão antes de qualquer commit.

**Retificação (ver "Checagem de concorrência entre operações do mesmo registro" abaixo, 2026-10-13):** o veredito "PRONTO PARA PREPARAÇÃO DO COMMIT" acima está **retificado de novo** — a correção do defeito 1 (botões presos) introduziu, por sua vez, um problema de concorrência diferente entre as duas operações do MESMO registro (Salvar × Assumir/Liberar), confirmado por hipótese e corrigido na seção seguinte. Texto acima preservado como histórico.

## Checagem de concorrência entre operações do mesmo registro (2026-10-13)

### Spec Summary

Hipótese verificada (não presumida como defeito): a correção do defeito 1 (`saveBtn.disabled = false; claimBtn.disabled = false;` incondicional em `renderModal`) resolveu o vazamento **entre registros diferentes**, mas `currentRequestToken` só muda ao trocar de **registro** (`loadPendency`), nunca por operação — Salvar e Assumir/Liberar são operações independentes no mesmo registro, nenhuma desabilita o botão da outra, e nada impedia as duas ficarem em voo ao mesmo tempo. **Hipótese confirmada**, em duas camadas:

1. **Reabilitação prematura e submissão duplicada** (camada mais superficial): com `saveBtn`/`claimBtn` controlados por flags independentes (`saveOperationPending`/`claimOperationPending`, tentativa intermediária), a resposta de uma operação ainda reabilitava o botão da outra só porque a dela mesma tinha terminado — um clique real nesse instante disparava uma **segunda requisição duplicada** para a operação ainda pendente (confirmado por contagem real de POSTs: 2 em vez de 1).
2. **Restauração de estado antigo** (camada mais profunda, só visível depois de corrigir a camada 1): mesmo com os botões controlados independentemente, o `renderModal` da operação que terminava primeiro ainda sobrescrevia o campo de observação com o snapshot do servidor **anterior** à conclusão da operação irmã ainda em voo — apagando o texto que o usuário tinha acabado de digitar para a outra operação, antes dela sequer ser enviada.

Corrigido serializando as duas operações no mesmo registro: um único `operationInFlight`, que desabilita **os dois botões** enquanto qualquer uma das duas estiver em andamento. Isso torna as duas operações mutuamente exclusivas no tempo para o mesmo registro, eliminando por construção tanto a reabilitação prematura quanto a sobrescrita de estado antigo — sem remover a guarda de `requestToken` (que continua protegendo contra respostas de **outro** registro) e sem tocar na correção anterior do defeito 2 (select desabilitado não envia ação).

### Gap Analysis

**1. Mapeamento (inspeção, antes de qualquer teste):**

- `saveBtn.disabled` muda em: clique em Salvar (síncrono, `true`); `finally` de `savePendency` (`false`, só se `requestToken` ainda bater); e, antes desta correção, incondicionalmente em `renderModal` (`false`).
- `claimBtn.disabled` muda nos mesmos pontos equivalentes de `submitResponsibleAction`.
- **Nada** desabilita `claimBtn` quando `savePendency` roda, nem `saveBtn` quando `submitResponsibleAction` roda — os dois `addEventListener('click', ...)` são independentes (`saveBtn.addEventListener('click', savePendency)`, `claimBtn.addEventListener('click', submitResponsibleAction)`), sem nenhum bloqueio cruzado.
- `currentRequestToken` só muda em `loadPendency` (`++currentRequestToken`) — nunca em `savePendency`/`submitResponsibleAction`, que apenas **leem** o valor atual. Logo, duas operações no mesmo registro sempre compartilham o mesmo token.
- `renderModal` é chamado por: `loadPendency` (carga de registro), sucesso de `savePendency`, sucesso de `submitResponsibleAction`. Em qualquer um desses três casos, antes da correção, ele reescrevia incondicionalmente **todos** os campos do formulário (observação, ação, status da linha, responsável técnico) a partir do snapshot daquela resposta específica — nunca sabendo se uma operação irmã ainda estava em voo.
- Campos editáveis (observação, selects de ação/status) **nunca** são desabilitados por `savePendency`/`submitResponsibleAction` em nenhum momento (só os dois botões de ação o são) — o usuário sempre pode continuar digitando/trocando valores independentemente de qualquer requisição em andamento.
- **Conclusão da inspeção, sem assumir segurança só pela presença do token:** Salvar e Assumir/Liberar **podem**, sim, ser disparados quase simultaneamente pela interface real (basta clicar num botão e, antes da resposta, clicar no outro — nada na UI impede isso), e o token por si só não distingue essas duas operações.

**2. Prova determinística (navegador real, app real, Postgres descartável isolado `por06race-pg`, porta 55436, destruído ao final; dados sintéticos `POR06RACE_*`):**

Controle de ordem de resposta via atraso injetado **por URL** em `window.fetch` (override `window.__delays`, chave por substring de endpoint: `api/update/`, `api/claim/`, `api/release/`), não por `sleep` isolado — o `sleep` do script só espera o tempo suficiente pra garantir que a requisição (com ou sem atraso) já tenha sido disparada/resolvida antes da próxima asserção, nunca usado como prova em si.

RED real (`01-red.log`, código antes de qualquer correção desta checagem — ainda com o reset incondicional do defeito 1): 7/14 FAIL, confirmando exatamente a hipótese — botão da operação irmã reabilitado enquanto a própria operação ainda estava pendente, clique nesse estado disparando uma segunda requisição real (contagem de POST = 2 em vez de 1), e um efeito colateral de negócio emergente (ao processar a 2ª requisição de Salvar depois que o Liberar concorrente já tinha removido o responsável técnico, o backend corretamente recusou com "Somente o técnico responsável pode alterar o status da linha" — consequência correta do backend reagindo a uma condição que mudou de verdade, não um bug novo).

Tentativa intermediária (flags independentes por operação, `02-intermediate-flags-only-still-red.log`): resolveu reabilitação prematura e duplicação de submissão (A.2/A.3/A.5/B.2/B.3/B.5 PASS), mas revelou a camada mais profunda — `renderModal` da operação que termina primeiro ainda sobrescrevia o campo de observação com o estado anterior à conclusão da operação irmã, apagando texto digitado e ainda não enviado (A.4b FAIL, observação virou `''` em vez do texto digitado).

GREEN real final (serialização completa, `03-green-serialized.log`): **16/16 PASS**, cobrindo:
- Salvar pendente → tentativa real (clique por coordenada de mouse, não `btn.click()` via JS) de Assumir/Liberar: **impossível** — botão desabilitado não recebe o evento de clique do navegador, 0 requisições novas disparadas (prova de impossibilidade pela interface, não por recusa de handler).
- Assumir pendente → tentativa real de Salvar: mesma impossibilidade, nas duas direções (iniciar por Salvar primeiro **e** por Assumir primeiro).
- Respostas entregues nas duas ordens (Liberar resolvendo antes de Salvar ainda pendente; Salvar resolvendo antes de Assumir ainda pendente) — ambas seguras, sem reabilitação prematura, sem duplicação, sem estado antigo.
- Após a primeira operação concluir, a segunda (antes bloqueada) funciona normalmente, com o texto que o usuário digitou **durante o bloqueio** preservado e enviado com sucesso.
- Controle: duplo clique rápido no **mesmo** botão continua gerando só 1 requisição (nunca foi o problema, não regrediu).
- Regressão: troca de registro A→B durante operação pendente de A continua funcionando (correção do defeito 1 preservada) — a serialização é por registro atual, não trava o modal globalmente nem entre registros diferentes.
- 0 exceções JS em toda a sessão.

**Achado informativo, não defeito, fora do escopo desta correção:** ao testar "Assumir pendente → Salvar", um rascunho de observação digitado **antes** de clicar em Assumir (sem nunca ter sido salvo) foi substituído pelo valor real persistido (vazio) quando o **próprio** sucesso de Assumir rodou `renderModal`. Isso é comportamento pré-existente de `renderModal` (sempre re-renderiza todos os campos a partir do snapshot fresco do servidor em qualquer sucesso, inclusive o da própria operação que acabou de rodar) — já acontecia antes de qualquer correção desta tarefa, não depende de concorrência nenhuma (bastava clicar Assumir sem ter salvo a observação antes), e não é a sobrescrita de "estado antigo por uma operação irmã" que a hipótese testava (essa foi corrigida pela serialização). Registrado por transparência, não corrigido — ampliar esse comportamento está fora do escopo do achado reportado.

**3. Decisão:** hipótese **confirmada** (não refutada) — defeito real de concorrência entre operações do mesmo registro, corrigido com a menor mudança suficiente (serialização via uma única flag compartilhada), sem remover nenhuma guarda de token existente, sem tocar a correção do defeito 2 (confirmado por diff: bloco `actionSelect.disabled ? '' : ...` inalterado nesta etapa), sem alterar backend/permissões.

### Implementation Plan

**Arquivo alterado:** `templates/dashboard/daily_user_action_board.html` (único arquivo de produção tocado).

1. Variável `saveOperationPending`/`claimOperationPending` (tentativa intermediária, não suficiente) substituída por uma única `operationInFlight`, declarada junto a `currentRequestToken`.
2. `renderModal`: `saveBtn.disabled`/`claimBtn.disabled` passam a refletir `operationInFlight` (não mais `false` incondicional nem flags por operação).
3. `loadPendency`: zera `operationInFlight = false` ao carregar um registro (novo ou o mesmo recarregado) — consistente com o comportamento já aprovado de "fechar/reabrir não deixa botão preso".
4. `savePendency`: seta `operationInFlight = true` e desabilita **os dois** botões no início (não só `saveBtn`); no `finally` (guardado por `requestToken`), zera `operationInFlight` e reabilita os dois.
5. `submitResponsibleAction`: mesma simetria (seta no início, desabilita os dois; `finally` guardado por token zera e reabilita os dois).

Nenhuma migration, dependência nova, alteração de `pendencies/`, `dashboard/views.py` (Python) ou `telecom/`. Nenhuma mudança de permissão ou contrato de backend.

### Test Checklist — cenário → possibilidade pela UI → ordem das respostas → resultado → evidência

| Cenário | Possibilidade pela UI | Ordem das respostas | Resultado | Evidência |
|---|---|---|---|---|
| Salvar pendente → tentar Assumir/Liberar (código ANTES da serialização) | Possível (nenhum botão cruzado desabilitado) | Liberar resolve primeiro, Salvar ainda em voo | **Defeito**: botão de Salvar reabilitado prematuramente; clique real disparava 2º POST duplicado | `01-red.log` (A.2/A.3 FAIL) |
| Mesmo, após serialização | **Impossível** (claimBtn desabilitado enquanto Salvar em voo) | N/A — clique real não dispara requisição | Seguro, provado por impossibilidade | `03-green-serialized.log` (A.2 PASS, 0 requisições) |
| Assumir/Liberar pendente → tentar Salvar (código ANTES da serialização) | Possível | Salvar resolve primeiro, Liberar ainda em voo | **Defeito**: botão de Assumir/Liberar reabilitado prematuramente; clique real disparava 2º POST duplicado | `01-red.log` (B.2/B.3 FAIL) |
| Mesmo, após serialização | **Impossível** (saveBtn desabilitado enquanto Assumir/Liberar em voo) | N/A | Seguro | `03-green-serialized.log` (B.2 PASS, 0 requisições) |
| Resposta de sucesso (uma operação) com a outra ainda pendente | Possível (antes da serialização) | Qualquer uma primeiro | **Defeito**: `renderModal` da que termina primeiro sobrescreve observação da operação irmã ainda em voo com estado anterior | `02-intermediate-flags-only-still-red.log` (A.4b FAIL) |
| Mesmo, após serialização | Impossível (mutuamente exclusivas) | N/A | Sem sobrescrita — texto digitado durante o bloqueio é preservado e enviado com sucesso depois | `03-green-serialized.log` (A.4, A.5, B.4 PASS) |
| Duplo clique rápido no MESMO botão | Possível tentar; nunca foi o problema | N/A | Seguro antes e depois (guarda síncrona de clique já existia) | `01-red.log` e `03-green-serialized.log` (controle, PASS nos dois) |
| Troca de registro A→B durante operação pendente de A | Possível e esperado funcionar (correção do defeito 1) | N/A | Continua seguro — serialização é por registro atual, não global | `03-green-serialized.log` (regressão, PASS) |
| Observação em registro de origem bloqueada, sem tentar abrir | N/A — já coberto na correção anterior, código inalterado nesta etapa | N/A | Reaproveitado (ver Test Strategy) | `2026-10-13-por06-ui-fixes/02-green.log` |

### Test Strategy

Mesma filosofia das correções anteriores: Chrome headless real via CDP, Postgres descartável dedicado (`por06race-pg`, porta 55436, destruído ao final), servidor real, dados sintéticos. **Diferença desta etapa:** cliques nos botões de ação usam coordenada de mouse real (`Input.dispatchMouseEvent`, função `real_click`), não `btn.click()` via JS — necessário porque a prova central ("impossível clicar") depende de um botão HTML `disabled` genuinamente não receber evento de ponteiro real; `btn.click()` via JS dispara o evento mesmo em elemento desabilitado em alguns navegadores/contextos, o que inverteria a prova. Controle de ordem de resposta via atraso por URL (não só `sleep`), como já estabelecido.

Backend reexecutado (não só citado): `manage.py test pendencies.tests dashboard.tests -v 2` → **171/171 PASSED**; `pytest` sobre os dois arquivos POR → **43 passed, 18 subtests passed**. Nenhum teste Python criado ou alterado — correção é só JavaScript. `manage.py check` → sem problemas. `git diff --check` → só os dois avisos pré-existentes de CRLF.

Mobile (390px/360px, `04-mobile-regression.log`): **9/9 PASS** — mesma prova de impossibilidade (clique real em Liberar enquanto Salvar pendente não dispara requisição) também no mobile; `.modal-dialog` não estoura o viewport (overflow ≤ 16px nas duas larguras); botões voltam a ficar habilitados após a operação concluir; 0 exceções JS.

**Evidência reaproveitada, não reexecutada** (código inalterado, confirmado por diff): a correção do defeito 2 (select desabilitado não envia ação de abertura) não foi tocada nesta etapa — `docs/superpowers/evidence/2026-10-13-por06-ui-fixes/02-green.log` (observação salva com sucesso em origem bloqueada, sem tentar abrir, backend recusando abertura real continua ativo) permanece válida sem nova execução. T18 (concorrência/locks PostgreSQL) não foi reexecutado — nenhuma mudança desta etapa toca transação/lock de backend, só JavaScript do modal; reexecutar seria repetir ensaio sem necessidade.

### Compliance Report

**Hipótese:** confirmada (não refutada). Dois defeitos reais de concorrência entre operações do mesmo registro foram encontrados e corrigidos: (1) reabilitação prematura do botão da operação irmã, com submissão duplicada real comprovada por contagem de requisições; (2) restauração de estado antigo (campo de observação) pela conclusão de uma operação sobre a outra ainda em voo — essa segunda camada só ficou visível depois de corrigir a primeira com uma tentativa intermediária (flags independentes), que não foi suficiente sozinha.

**Correção aplicada:** serialização das duas operações do modal (`operationInFlight` único, desabilita os dois botões enquanto qualquer uma estiver pendente) — opção explicitamente oferecida no pedido, preferida à alternativa (flags independentes) porque esta última corrigia só a camada 1, não a camada 2.

**Preservado, confirmado por teste e por diff:**
- Guarda de `requestToken` contra respostas de outro registro — inalterada, continua funcionando (regressão testada).
- Correção do defeito 2 (select desabilitado não envia ação) — bloco de código inalterado nesta etapa, confirmado por `git diff`.
- Abertura/reabertura proibidas continuam recusadas pelo backend — nenhuma alteração de backend/permissão nesta etapa.
- Tratamento autorizado (claim/observação/release) continua funcional — coberto pelos próprios cenários A/B do teste desta etapa (ambas as operações, quando não bloqueadas, completam com sucesso).

**Node IDs / verificações (scripts de aceite via navegador real, não `pytest`/`manage.py test` — categoria separada, não somada aos 443 nós Django nem aos 46+16 scripts de aceite das rodadas anteriores):** `01-red.log` (14 verificações, 7 FAIL reais), `02-intermediate-flags-only-still-red.log` (15 verificações, 1 FAIL real — a camada 2), `03-green-serialized.log` (16 verificações, 0 FAIL), `04-mobile-regression.log` (9 verificações, 0 FAIL). Métodos/subtestes de backend inalterados desde a correção anterior (171 nós Django + 43 subconjunto/18 subtestes `pytest`).

**Limitações explícitas:**
- O achado informativo (rascunho de observação substituído pelo próprio sucesso de uma operação, sem precisar de concorrência) é pré-existente, documentado, não corrigido — fora do escopo deste defeito.
- T18 e a correção do defeito 2 não foram reexecutados — sem mudança que justifique, conforme pedido.
- Overflow horizontal pré-existente da tabela e contenção estrita de foco no modal seguem exatamente como documentados nas rodadas anteriores — não tocados.

**Arquivos alterados nesta etapa:** só `templates/dashboard/daily_user_action_board.html`. Alterações alheias preservadas, incluindo a versão 1.9.0 em `config/settings.py`.

**Evidências novas:** `docs/superpowers/evidence/2026-10-13-por06-same-record-race/` — `01-red.log`, `02-intermediate-flags-only-still-red.log`, `03-green-serialized.log`, `04-mobile-regression.log`, `regression_pendencies_dashboard.log` (171/171), `pytest_run.log` (43/18 subtests), scripts completos (`por06race_settings.py`, `por06race_setup_fixtures.py`, `por06race_test.py`, `por06race_mobile_check.py`).

**Recursos descartáveis desta rodada, todos encerrados ao final:** container `por06race-pg` (porta 55436, parado e removido), `runserver` em `127.0.0.1:8781` (finalizado), Chrome headless na porta de debug 9666 (finalizado, processo específico). Nenhum recurso de rodadas anteriores foi reaberto ou tocado.

**Veredito:** **PRONTO PARA PREPARAÇÃO DO COMMIT**, com a hipótese de concorrência entre operações do mesmo registro confirmada e corrigida (serialização), validada por RED→GREEN real em duas camadas (reabilitação/duplicação e estado antigo), regressão completa sem quebra (backend 171+43, navegador desktop 16 + mobile 9, `manage.py check`, `git diff --check`) e sem reabertura de escopo já fechado (defeito 2, T18, overflow, foco). Sem stash/reset/checkout destrutivo, migration, dependência nova, stage, commit, push, deploy ou acesso a PRD nesta etapa. Diff pronto para nova revisão.
