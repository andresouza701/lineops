# Fonte da verdade — Cadastro de linha com SELO WHATS LINEOPS

Status: aprovado pelo usuário. Vencimento informado manualmente e obrigatório quando houver selo; demais propostas aprovadas.

Documento único de requisitos, contrato, tarefas e evidências. Atualizar progresso aqui; não manter backlog paralelo. Spec aprovada não significa implementação concluída.

Última alteração: 2026-09-21. **SEL-11 concluída — entrega pronta para integração.** Revisão final confirmou `PhoneLineForm._post_clean` correto (5 cenários de fronteira verificados: formato de data inválido, múltiplos campos inválidos simultâneos, e-mail inválido na edição sem reaproveitar valor antigo, e-mail inválido + campo ausente combinados) e o overflow de ~4px a 360px como **pre-existente comprovado por medição em navegador real** contra página não tocada por esta feature (`telecom/simcards/`, scrollWidth=364/clientWidth=360, idêntico ao formulário do selo) — não apenas "semelhança visual". Uma lacuna real de cobertura fechada (e-mail inválido na edição não tinha teste algum; só criação estava coberta), 1 teste novo, GREEN na primeira execução (comportamento já correto). Suíte consolidada 301 passed/1 skipped, `manage.py check` limpo, `makemigrations --check --dry-run` reconfirma só o drift pré-existente (exit 1, nenhum arquivo novo), `git diff --check` limpo. Nenhum commit/push/deploy/acesso a PRD. Ver SEL-11 — Revisão e entrega — 2026-09-21.

## Spec Summary

Fonte: solicitação do usuário nesta tarefa, complementada pelas decisões explícitas sobre Sem selo e vencimento.

- Redesenhar a página de cadastro de linha com os blocos Dados da linha e SELO WHATS LINEOPS.
- Dados da linha: número, SIM card, origem e canal; preservar validações existentes.
- Selo: Sem selo (padrão), META ONE ou META VERIFICADO.
- Sem selo oculta os campos adicionais. Selecionar um selo exibe data da ativação, data do vencimento, e-mail cadastrado e tipo de pagamento.
- Com META ONE ou META VERIFICADO, os quatro campos adicionais são obrigatórios. Sem selo, nenhum desses campos é obrigatório. Validar no servidor e refletir a obrigatoriedade na interface.
- Vencimento informado manualmente; não calcular nem preencher automaticamente a partir da ativação.
- Pagamento: CARTÃO CRÉDITO ou GIFT CARD GOOGLE.
- Ativação do selo é independente de PhoneLine.activated_at.
- Alerta visual na listagem e no detalhe: começa sete dias antes, destaca o dia e permanece após vencer.

## Desenho da página

Reutilizar base/base.html, cards, controles e botões Bootstrap existentes. Cabeçalho: Cadastro de linha, subtítulo curto e Voltar. Desktop: dois cards de mesma largura; abaixo de lg: cards empilhados, Dados da linha primeiro. Rodapé do formulário: Cancelar e Cadastrar linha; na edição, Salvar alterações.

Card Dados da linha: Número, SIM card, Origem e Canal, em ordem vertical. Card SELO WHATS LINEOPS: seletor Selo sempre visível; inicialmente texto Nenhum selo cadastrado. Com selo selecionado: datas lado a lado em telas largas, e-mail e pagamento abaixo. Em telas pequenas todos os campos ocupam a largura disponível.

Alternativas consideradas: formulário único sem agrupamento (menos claro); etapas separadas (mais navegação para poucos campos). Recomenda-se dois cards no mesmo formulário.

Labels associados aos inputs, navegação por teclado na ordem visual, erros junto aos campos e resumo focável após envio inválido. Ocultar campos também da navegação e da árvore de acessibilidade. Sem JavaScript, manter campos acessíveis e validar condicionalmente no servidor. Alertas sempre com texto, não apenas cor.

## Contrato de vencimento

Usar data local da aplicação, sem horários. Diferença = vencimento menos hoje.

| Condição | Texto | Apresentação |
| --- | --- | --- |
| Sem selo | Sem selo | Neutra, sem alerta |
| Mais de 7 dias | Vence em DD/MM/AAAA | Neutra |
| De 1 a 7 dias | Vence em N dias | Aviso amarelo |
| Hoje | Vence hoje | Destaque laranja |
| Data passada | Vencido há N dias | Vermelho persistente |

Usar singular para um dia. Renovar a data recalcula o indicador. Selo vencido não muda status nem alocação da linha. Não há envio de e-mail, WhatsApp ou tarefa agendada neste escopo.

## Gap Analysis

Decisões aprovadas, sem lacunas funcionais pendentes:

- Aceitar vencimento igual à ativação; rejeitar vencimento anterior.
- Ao salvar Sem selo, limpar os dados atuais do selo; apenas alternar o seletor antes de salvar não descarta os valores digitados.
- Aplicar o mesmo bloco à edição e apresentar seus dados no detalhe, respeitando permissões existentes.

## Implementation Plan

1. Registrar aprovação das regras e vencimento manual (concluído).
2. Mapear pontos de criação/reutilização, auditoria e listagem efetivamente usada antes de definir alterações finais.
3. Derivar testes e executá-los em estado de falha antes da implementação.
4. Adicionar campos próprios em PhoneLine e migration reversível; linhas existentes ficam Sem selo.
5. Centralizar validação e cálculo de vencimento; manter views finas, preservar PhoneLine.visible_to_user e regras de alocação.
6. Integrar PhoneLineForm, PhoneLineUpdateForm e create_or_reuse sem perder campos no cadastro ou restaurar dados obsoletos em reativação.
7. Implementar layout, interação condicional, detalhe e indicadores na listagem.
8. Validar testes, migration e interface real em desktop e celular.

## Tarefas da entrega

Marcar concluída somente com aceite atendido e evidência registrada. Ordem: SPEC → CONTRACT → TESTS → CODE → VALIDATION.

- [x] **SEL-01 — Spec aprovada.** Evidência: aprovações na conversa, vencimento manual e cores registrados acima.
- [x] **SEL-02 — Mapear fluxo atual.** Inspecionados models.py, forms.py, views.py, signals.py e templates de telecom. Cadastro usa create_or_reuse; edição preserva alocação transacional; overview carrega linhas adicionais via JSON. Auditoria atual não registra campos de selo; histórico de renovações não faz parte desta entrega.
- [x] **SEL-03 — Escrever testes iniciais.** Evidência: telecom/test_whatsapp_seal.py. Cobre campos obrigatórios, datas, limpeza, reativação, limites de alerta e HTTP. Ainda não executado.
- [x] **SEL-04 — Preparar ambiente e comprovar RED.** Depende de SEL-03. Evidência em Retomada e evidências. RED comprovado: 27 falhas por funcionalidade de selo ausente, 2 aprovados sem relação com a lacuna.
- [x] **SEL-05 — Modelo, migration e domínio.** Concluída em 2026-09-17. Evidência abaixo em Retomada e evidências. Aceite atendido: linhas antigas Sem selo (comprovado por migração em banco isolado), validação condicional (full_clean), vencimento manual e indicador calculado pela data local (timezone.localdate); status/alocação/activated_at não afetados.
- [x] **SEL-06 — Formulários e reativação.** Concluída em 2026-09-17. Evidência abaixo em Retomada e evidências. Aceite atendido: persistência dos campos comprovada por refresh_from_db, limpeza ao salvar Sem selo (inclusive valores residuais inválidos nos campos ocultos), nenhuma recuperação de selo obsoleto em reativação; demais caminhos de criação (admin.py, SIMcardCreateView, telephony_use_case.py) e permissões preservados.
- [x] **SEL-07 — Nova página de cadastro/edição.** Três achados corrigidos e revalidados em navegador real em 2026-09-17. Cadastro e remoção sem scripts, labels, obrigatoriedade com JS, preservação, foco, Liberar e responsividade confirmados; 13 testes UI aprovados. Ver Revalidação final de SEL-07.
- [x] **SEL-08 — Detalhe e alertas.** Concluída em 2026-09-21. Contraste de Vence hoje aprovado (7,81:1). Overflow móvel de OPERATOR corrigido (`telecom-content-shell` reaproveitada em `operator_lines.html`; causa real era item de CSS Grid `.app-main`, não o wrapper da tabela) e revalidado em navegador Chromium real: 390/360/1280px sem overflow de página, rolagem interna funcional, ação Acessar e detalhe confirmados. Ver Correção da contenção móvel de OPERATOR e revalidação real de SEL-08 — 2026-09-21.
- [x] **SEL-09 — Completar testes e comprovar GREEN.** Concluída em 2026-09-21. Evidência abaixo em SEL-09 — completar cobertura e comprovar GREEN. Aceite atendido: matriz requisito→teste mapeada, 2 lacunas reais fechadas (2 testes novos, GREEN sem defeito de aplicação), suíte consolidada 299 passed/1 skipped, `manage.py check` limpo, drift de migrations reconferido e reportado (não descrito como limpo).
- [x] **SEL-10 — Validação no navegador.** Concluída em 2026-09-21. Evidência abaixo em "SEL-10 — Validação no navegador — 2026-09-21". Aceite atendido: cadastro/edição com e sem selo, obrigatoriedade, alternância preservando valores antes de salvar, erros, teclado, responsividade (360/390/1280px) e cores conferidos em navegador real (Playwright/Chromium). Um defeito real encontrado (mensagem de erro contraditória para formato inválido) e corrigido dentro do escopo.
- [x] **SEL-11 — Revisão e entrega.** Concluída em 2026-09-21. Evidência abaixo em "SEL-11 — Revisão e entrega — 2026-09-21". Aceite atendido: diff conferido contra a spec (incluindo arquivos não versionados), `_post_clean` revisado e comprovado correto com evidência nova, overflow de 4px comprovado pré-existente (não apenas presumido), evidências consolidadas, alterações anteriores preservadas, nenhum deploy nem alteração de dados operacionais.

### Contrato técnico

| Campo em PhoneLine | Valores / regra |
| --- | --- |
| whatsapp_seal | Vazio = Sem selo; META_ONE; META_VERIFIED |
| whatsapp_seal_activated_on | Data da ativação do selo; nula sem selo |
| whatsapp_seal_expires_on | Data manual do vencimento; nula sem selo |
| whatsapp_seal_email | E-mail cadastrado; vazio sem selo |
| whatsapp_seal_payment | CREDIT_CARD ou GOOGLE_GIFT_CARD; vazio sem selo |

Os quatro campos adicionais são obrigatórios com selo. seal_status fornece label e tone: neutral, warning, today ou expired. today corresponde a laranja. Não persistir estado derivado do relógio nem modificar activated_at, status ou alocação por causa do selo.

### Retomada e evidências

Estado atual: SEL-01 a SEL-11 concluídas. Próximo passo: revisão e preparação do commit seletivo da feature. Os registros abaixo preservam a sequência histórica de implementação e validação.

**SEL-08 — implementada em 2026-09-17, aceite parcial (ver Limitações).**

AGENTS.md não existe neste repositório (glob `**/AGENTS.md` sem resultado); instrução de leitura não pôde ser cumprida por ausência do arquivo, não por omissão.

Mapeamento (fluxo obrigatório, item 1) confirmou quais rotas/templates/JS de listagem são realmente usados antes de qualquer alteração:
- `telecom:overview` (`TelecomOverviewView`, `templates/telecom/overview.html`) é a única listagem com paginação "Carregar mais"/JSON em uso real — linkada pela navegação (`base/sidebar.html`, `base/tabbar.html`, `base/tabbar_inline.html`) e coberta pelo teste `test_http_create_detail_list_and_edit`.
- O branch `table_type == "recent"` em `TelecomOverviewView._handle_ajax_request` e o contexto `initial_recent_lines`/`has_more_recent_lines` não são renderizados por nenhum template (`overview.html` não itera `initial_recent_lines`; grep por `initial_recent_lines`/`table=recent` não encontrou uso fora de `views.py`) — código morto pré-existente, fora do escopo desta tarefa; **não recebeu indicador de selo** para não expandir escopo sobre algo não utilizado.
- `PhoneLineListView`/`templates/telecom/phoneline_list.html` (rota própria, AJAX próprio) não é linkada por nenhum template (grep confirmou zero `{% url ... phoneline_list %}` ou href equivalente) — também código morto, fora do escopo.
- `templates/telecom/operator_lines.html` (`OperatorLinkedLinesView`) é uma listagem real, mas simples (sem paginação/JSON, tabela numero/status/operadora) usada só pelo papel OPERATOR; não faz parte do contrato de "primeira carga e Carregar mais" desta tarefa e não foi alterada — decisão de escopo registrada aqui, não como pendência oculta.
- `templates/telecom/phoneline_detail.html` (`PhoneLineDetailView`) é o detalhe real, único usado pelo link "Ver detalhe"/histórico/reconexão.

Arquivos alterados/criados:
- `telecom/views.py`: `TelecomOverviewView._handle_ajax_request`, branch `table_type == "main"` (única listagem com JSON realmente usada — ver mapeamento acima). Adicionadas duas chaves ao `line_data` já existente, reaproveitando `line.seal_status` (propriedade de domínio criada em SEL-05, sem consulta adicional pois `whatsapp_seal`/`whatsapp_seal_expires_on` já vêm carregados pelo `select_related`/queryset existente): `whatsapp_seal_display` (rótulo humano do selo, `""` quando não há selo) e `seal_status` (dict `{tone, label}` calculado por `compute_seal_status`, mesma fonte usada pelo domínio). Nenhum campo adicional (e-mail, datas, pagamento) enviado ao payload da listagem, conforme limite explícito. Branch `recent` não tocado (código morto, ver mapeamento).
- `templates/telecom/phoneline_detail.html`: novo card "SELO WHATS LINEOPS" inserido entre o card de dados da linha e o link "Ver historico". Com selo: `dl` com Selo (`get_whatsapp_seal_display`), Data da ativação e Data do vencimento (formatadas `d/m/Y`), E-mail cadastrado, Tipo de pagamento (`get_whatsapp_seal_payment_display`) e Vencimento (badge via partial `_seal_status_badge.html`, reaproveitando `phone_line.seal_status`). Sem selo: apenas o texto "Sem selo", sem nenhum dos campos/labels acima e sem indicador de vencimento (nenhum "Data da ativação"/"E-mail cadastrado" renderizado nesse caso — comprovado por teste).
- `templates/telecom/_seal_status_badge.html` (novo): partial reutilizado pelo detalhe e pela listagem para não duplicar o mapeamento tone→apresentação. `if/elif` sobre `seal_status.tone`: `warning` → `badge seal-tone-warning bg-warning text-dark` (amarelo); `today` → `badge seal-tone-today` com `style="background-color: orange; color: #fff;"` (laranja, mesmo padrão inline já usado para status SUSPENDED em `overview.html`, nenhuma classe Bootstrap nativa de laranja no projeto); `expired` → `badge seal-tone-expired bg-danger` (vermelho); default (`neutral`, inclui "Sem selo" quando usado) → `badge seal-tone-neutral bg-light text-dark border`. Texto sempre acompanha a cor (label textual dentro do badge, não apenas cor), conforme contrato visual.
- `templates/telecom/overview.html`: nova coluna "Selo" na tabela principal (única tabela realmente listada — ver mapeamento), entre "Status" e "Ações"; `colspan` da linha vazia ajustado de 7 para 8. Renderização inicial (server-side, Django): com selo, nome do selo (`get_whatsapp_seal_display`) mais o badge do partial `_seal_status_badge.html`; sem selo, texto "Sem selo" em `text-muted`. JavaScript de "Carregar mais": duas funções novas, `createSealBadge(sealStatus)` e `createSealCell(line)`, construídas com `document.createElement`/`textContent`/`classList` (sem template string nem `innerHTML` para os dados do selo, ao contrário do padrão pré-existente usado para telefone/ICCID/operador nessa mesma função) — evita interpolação insegura de dado do selo no DOM. `createMainTableRow` passa a inserir a célula do selo via `tr.insertBefore(createSealCell(line), tr.querySelector('td.text-end'))`, preservando a célula de Status (`td:nth-child(6)`, posição inalterada) e a célula de Ações (`text-end`, agora na 8ª posição) sem precisar renumerar seletores existentes.
- `telecom/test_seal_detail_and_listing.py` (novo): 14 testes cobrindo o Test Checklist abaixo.

Comandos e resultados:

```powershell
venv/Scripts/python.exe -m pytest telecom/test_seal_detail_and_listing.py -q
```
RED antes da implementação: 12 falhas (bloco do detalhe, coluna/JSON da listagem, funções JS seguras ausentes), 2 aprovados por já valerem sem mudança nenhuma (escopo de permissão e ausência de N+1 por linha, ambos já garantidos pelo código pré-existente — `get_visible_phone_lines_queryset`/`PhoneLine.visible_to_user` de tarefas anteriores e ausência de consulta por linha, pois `seal_status` ainda nem existia no payload).
GREEN após a implementação: 14 aprovados.

```powershell
venv/Scripts/python.exe -m pytest telecom/test_whatsapp_seal.py -q
```
Resultado: **34 aprovados**, 0 falhas — `test_http_create_detail_list_and_edit` passa integralmente pela primeira vez (detalhe com "seal@example.com", listagem com "META ONE", payload AJAX com `seal_status` correto, edição preservada). Nenhuma assertion removida ou enfraquecida.

```powershell
venv/Scripts/python.exe -m pytest telecom/test_phoneline_form_ui.py -q
```
Resultado: 13 aprovados, 3 warnings (mesmos avisos de depreciação já conhecidos). Nenhuma regressão — SEL-08 não tocou cadastro/edição.

```powershell
venv/Scripts/python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
```
Resultado: 229 aprovados, 1 pulado, 172.91s. Nenhuma regressão (mesmo resultado do baseline SEL-07).

```powershell
venv/Scripts/python.exe manage.py check
```
Resultado: `System check identified no issues (0 silenced)`.

Validação em navegador real — não executada nesta sessão (limitação registrada, não contornada):
- Esta sessão não teve acesso a nenhuma ferramenta de automação de navegador (Chrome DevTools MCP ou equivalente indisponível), mesma limitação já registrada em sessões anteriores de SEL-07 antes da revalidação com Chromium real.
- **Não foi possível confirmar visualmente**: contraste real das cores amarelo/laranja/vermelho sobre o tema Bootstrap do projeto, ausência de overflow horizontal novo em desktop/celular com a coluna "Selo" adicional, comportamento real do botão "Carregar mais" no navegador (JS executado de fato, não apenas payload JSON validado via cliente de teste Django), e leitura por teclado/leitor de tela do novo card no detalhe.
- Evidência disponível sem navegador: testes HTTP reais via Django test client (cliente HTTP real, não `render_to_string`) cobrindo GET de detalhe com cada selo e Sem selo, GET/AJAX de listagem na primeira carga e em "carregar mais" simulado (offset diferente), formato dos payloads JSON, e verificação de que a construção da célula do selo no JavaScript usa `createElement`/`textContent` em vez de interpolação em `innerHTML` (verificado por leitura de código-fonte, não por execução real do script).
- **Não declaro a validação visual como concluída.** Conforme instrução explícita desta tarefa, o aceite visual permanece pendente e a limitação fica registrada aqui, sem bloquear o restante do fluxo.

Limitações:
- `AGENTS.md` não existe no repositório (confirmado por `Glob **/AGENTS.md`); instrução de leitura do arquivo não pôde ser cumprida.
- Validação em navegador real (cores/contraste, overflow, JS ao vivo, teclado) não executada nesta sessão — ver acima. Checkbox de SEL-08 mantida aberta por esse motivo, mesmo padrão usado em SEL-07 antes de sua revalidação.
- Branch `table_type == "recent"` de `TelecomOverviewView` e a rota/listagem `PhoneLineListView`/`phoneline_list.html` permanecem sem indicador de selo — são código morto (não linkados por nenhum template), fora do escopo de "listagens aplicáveis" desta tarefa; não modificados para não expandir escopo sobre código não utilizado. `templates/telecom/operator_lines.html` é uma listagem real do papel OPERATOR mas sem paginação/JSON — decisão de escopo (não alterada) registrada aqui para visibilidade, não como pendência oculta a ser resolvida silenciosamente depois.
- Nenhuma alteração em `telecom/models.py`, `telecom/forms.py`, migrations, cadastro/edição de linha, banco operacional. Nenhum commit, push ou deploy.
- Drift pré-existente em `telecom.PhoneLine.origem` e `dashboard.DailyUserAction.action_type` permanece fora do escopo, não corrigido (não reconferido nesta tarefa).

**SEL-07 — implementada em 2026-09-17, aceite parcial (ver Limitações).**

Arquivos alterados/criados:
- `templates/telecom/phoneline_form.html`: reescrito. Cabeçalho "Cadastro de linha" / "Editar linha" com Voltar. Dois cards Bootstrap lado a lado em desktop (`col-lg-6`) e empilhados em celular (`col-12`), "Dados da linha" primeiro na ordem do DOM. Card "Dados da linha": número, SIM card, origem, canal; na edição adiciona usuário vinculado, status e lista de informações atuais (ICCID, operadora, ativada em, atualizada em). Card "Selo WhatsApp LineOps": seletor sempre visível, texto "Nenhum selo cadastrado." quando sem selo, bloco `#seal-detail-fields` com os quatro campos (ativação, vencimento lado a lado; e-mail e pagamento abaixo), oculto via atributo `hidden` quando não há selo e nenhum erro nos quatro campos. Rodapé: Cancelar / Cadastrar linha (criação) ou Salvar alterações (edição); botão Liberar preservado com `formnovalidate` (ver correção abaixo). Resumo de erros focável (`#form-error-summary`, `tabindex="-1"`) listando cada campo com erro e link para o campo. Cada campo tem `<label for=...>` e container de erro `id="id_<campo>_error"` referenciado por `aria-describedby` (setado em forms.py).
- `static/js/phone-line-form.js` (novo): alterna `hidden` do bloco de detalhes do selo e o texto "Nenhum selo cadastrado" conforme o valor atual do seletor; adiciona/remove `required` nos quatro campos do bloco sem apagar valores já digitados (baseado em `hidden`/`required` do DOM, não recria elementos); foca o resumo de erros ao carregar, se presente. Correção da conferência real: sem scripts os campos continuam no DOM, mas hidden impede acesso; obrigatoriedade condicional é renderizada pelo servidor (ver forms.py) e a autoridade de validação continua sendo `PhoneLine.clean()`.
- `telecom/forms.py`: `PhoneLineForm.Meta.widgets` define `whatsapp_seal`/`whatsapp_seal_payment` como `Select` com classe `form-select`; `whatsapp_seal_activated_on`/`whatsapp_seal_expires_on` como `DateInput(type="date", format="%Y-%m-%d")` — formato ISO explícito necessário porque `DATE_INPUT_FORMATS` do locale `pt-br` é `%d/%m/%Y` e um `<input type="date">` exige valor `yyyy-mm-dd` no atributo `value` para pré-preencher corretamente (sem o `format` explícito, o valor não seria reconhecido pelo input nativo). `whatsapp_seal_email` como `EmailInput`. `PhoneLineForm.__init__` passa a: (1) setar `aria-describedby` padrão em todos os campos apontando para o container de erro correspondente; (2) calcular o selo atualmente selecionado (`self.data` se bound, senão `self.instance.whatsapp_seal`) e adicionar/remover o atributo HTML `required` nos quatro campos de detalhe do selo de acordo — reflete a seleção atual tanto no GET de edição quanto após POST inválido (usa `self.data`, não reinicia para o estado inicial). Nenhuma alteração em `PhoneLineForm.clean()`, `full_clean()` ou `save()` (regras de domínio e limpeza de campos residuais preservadas).
- `telecom/test_phoneline_form_ui.py` (novo): 8 testes cobrindo blocos visíveis + script carregado, hint "Nenhum selo cadastrado" com bloco oculto sem `required` no cadastro, labels/widgets dos campos de selo (incluindo `type="date"` e opções META ONE/META VERIFICADO/CARTÃO CRÉDITO/GIFT CARD GOOGLE), preservação de dados do selo na edição (datas em formato ISO no `value`, bloco visível, `required` presente), erros exibidos com valores preservados em POST inválido de criação e de edição (bloco permanece visível), botão Liberar com `formnovalidate` e comportamento HTTP do Liberar inalterado (302, status volta a AVAILABLE).

Correção pontual incluída nesta tarefa — ação Liberar bloqueada por validação HTML:
- Causa: antes desta tarefa o template não tinha campos HTML `required`; ao introduzir obrigatoriedade condicional nos quatro campos do selo (necessária para o critério de aceite "obrigatoriedade HTML acompanha seleção"), o botão Liberar — um `submit` dentro do mesmo `<form>` dos campos do cadastro — passaria a poder ser bloqueado pela validação nativa do navegador (ex.: template renderizado com erro e campo de vencimento vazio, mas selo ainda selecionado). Corrigido adicionando o atributo `formnovalidate` ao botão Liberar, que instrui o navegador a pular a validação de restrição HTML apenas para esse envio, independente do estado dos demais campos. Comportamento do servidor (`PhoneLineUpdateView.post`, ramo `action == "release_line"`) não foi alterado. Coberto por `test_release_action_bypasses_html_validation` e `test_release_action_still_works_http`.

Comandos e resultados:

```powershell
venv/Scripts/python.exe -m pytest telecom/test_phoneline_form_ui.py -q
```
RED antes da implementação: 7 falhas (blocos/labels/preservação/Liberar ausentes), 1 aprovado por coincidência (comportamento HTTP do Liberar já existente antes desta tarefa).
GREEN após a implementação: 8 aprovados.

```powershell
venv/Scripts/python.exe -m pytest telecom/test_whatsapp_seal.py -q
```
Resultado: 34 aprovados, 1 falha — `test_http_create_detail_list_and_edit`. A falha não é mais de template/JS (asserts de "SELO WHATS LINEOPS" e `phone-line-form.js` na página de cadastro passam); a suíte falha adiante, no `assert b"seal@example.com" in detail.content` (detalhe da linha), escopo de SEL-08, conforme previsto e autorizado pelos limites desta tarefa. Nenhuma implementação de SEL-08 foi feita para "zerar" essa suíte.

```powershell
venv/Scripts/python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
```
Resultado: 229 aprovados, 1 pulado. Nenhuma regressão (mesmo resultado do baseline SEL-06).

```powershell
venv/Scripts/python.exe manage.py check
```
Resultado: `System check identified no issues (0 silenced)`.

Validação de template Django: renderização exercitada pelos testes acima via `TemplateResponse`/Django test client (cliente HTTP real de dentro do processo Django, não apenas `render_to_string`), cobrindo GET de criação, GET de edição com dados existentes, POST inválido de criação e de edição — sem `TemplateSyntaxError` em nenhum caso.

Validação em navegador real — evidência parcial e limitação registrada:
- Ambiente local isolado usado: `docker compose up -d db` (container `lineops-db`, definido no `docker-compose.yml` do próprio projeto, porta host 5433, dados de desenvolvimento local, não é o banco operacional). Migrations aplicadas nesse banco local (`manage.py migrate`, incluindo a 0021, já existente desde SEL-05). Dados sintéticos criados (usuário admin de teste, 1 SIM card, 1 linha com selo META_ONE) e removidos ao final; servidor `manage.py runserver` executado localmente (`DB_HOST=localhost`, `DB_PORT=5433`, apenas nesta sessão de shell, `.env` do projeto não foi alterado).
- Confirmado por essa via: servidor sobe, autenticação funciona, página de cadastro responde 200 e contém os blocos esperados, e o arquivo `static/js/phone-line-form.js` é servido com status 200 pelo `runserver`.
- **Limitação (não contornada, registrada conforme instrução):** esta sessão não tem acesso a uma ferramenta de automação de navegador (Chrome DevTools MCP não está disponível neste ambiente). Não foi possível verificar visualmente: alternância real do seletor de selo via clique/JS executado em navegador, ordem de tabulação por teclado, ausência de overflow horizontal em largura de celular (~400px), nem cores/layout renderizados. A verificação de interação JavaScript (alternância sem apagar valores, campos ocultos fora da árvore de acessibilidade) foi validada apenas por leitura do código-fonte de `phone-line-form.js` e pela cobertura de HTML gerado pelos testes automatizados (estado inicial/POST inválido), não por execução real do script em navegador. **Não declaro a validação em navegador como completa.** Servidor local e container de banco foram encerrados (`docker compose stop db`) ao final desta tarefa; nenhum dado sintético permanece no banco local.

Limitações:
- Validação em navegador real (interação JS ao vivo, teclado, responsividade visual, cores) não executada nesta sessão — ver acima. Checkbox de SEL-07 mantida aberta por esse motivo.
- `test_http_create_detail_list_and_edit` segue falhando, agora exclusivamente por SEL-08 (detalhe/listagem/payload JSON não implementados nesta tarefa, fora do escopo autorizado).
- Nenhuma alteração em `telecom/models.py`, migrations ou regras de domínio nesta tarefa. Nenhuma alteração em banco operacional, nenhum commit, push ou deploy.

**SEL-06 — concluída em 2026-09-17.**

Arquivos alterados:
- `telecom/forms.py`: `PhoneLineForm.Meta.fields` e `PhoneLineUpdateForm.Meta.fields` passam a incluir `whatsapp_seal`, `whatsapp_seal_activated_on`, `whatsapp_seal_expires_on`, `whatsapp_seal_email`, `whatsapp_seal_payment`. `PhoneLineForm.full_clean()` sobrescrito: quando `whatsapp_seal` ausente/vazio nos dados brutos do POST, os quatro campos ocultos são zerados em `self.data` antes da limpeza padrão do Django — isso descarta valores residuais inválidos nos campos ocultos sem que o `DateField`/`EmailField` gerado automaticamente rejeite o POST (contrato exigido: "ignorar valores residuais... inclusive inválidos"). `PhoneLineForm.save()` (caminho de criação) passa os cinco campos de selo para `PhoneLine.create_or_reuse`. Validação de obrigatoriedade/ordem de datas é feita apenas por `PhoneLine.clean()` (já existente desde SEL-05, chama `validate_seal_fields`), disparado automaticamente pelo fluxo padrão do `ModelForm` — ver correção abaixo.
- `telecom/models.py`: `PhoneLine.create_or_reuse` ganhou cinco parâmetros nomeados opcionais (`whatsapp_seal=""`, `whatsapp_seal_activated_on=None`, `whatsapp_seal_expires_on=None`, `whatsapp_seal_email=""`, `whatsapp_seal_payment=""`), aplicados tanto na criação (`cls.objects.create`) quanto na reativação de linha soft-deletada (atribuídos em `existing_line` e incluídos em `update_fields`). Chamadores existentes sem esses argumentos (admin.py, SIMcardCreateView em views.py, telephony_use_case.py) continuam funcionando como Sem selo, pois os defaults representam ausência de selo.

### Correção pontual — justificativa incorreta sobre Model.clean() e validação duplicada (2026-09-17)

Registro original (acima) afirmava que `Model.full_clean()` só chama `self.clean()` quando `exclude` está vazio, e por isso `PhoneLineForm.clean()` chamava `validate_seal_fields` explicitamente. **Essa afirmação estava errada.**

Causa confirmada (não hipótese) — leitura direta do código instalado, Django 5.2.11:
- `venv/Lib/site-packages/django/db/models/base.py:1651-1656`: `Model.full_clean()` chama `self.clean()` incondicionalmente, com comentário explícito no código-fonte: "Form.clean() is run even if other validation fails, so do the same with Model.clean() for consistency." `exclude` só afeta `clean_fields()` (validação por campo), nunca a chamada a `self.clean()`.
- `venv/Lib/site-packages/django/forms/models.py:474-500` (`BaseModelForm._post_clean`): sempre chama `self.instance.full_clean(exclude=exclude, validate_unique=False)`, portanto `PhoneLine.clean()` — e `validate_seal_fields` — já era disparado automaticamente por `PhoneLineForm`/`PhoneLineUpdateForm`, sem necessidade de chamada explícita.

Consequência real da chamada explícita redundante (bug confirmado, não apenas duplicação cosmética):
- `Form.add_error()` (`django/forms/forms.py:315-316`) remove o campo de `self.cleaned_data` ao registrar um erro.
- `construct_instance()` (`django/forms/models.py:65`) pula campos ausentes de `cleaned_data` ao montar a instância — na edição, a instância mantém o valor **antigo** (já salvo) desse campo.
- Como `PhoneLineForm.clean()` rodava antes de `_post_clean()`/`construct_instance()`, um erro adicionado ali (ex.: vencimento ausente) apagava o campo de `cleaned_data`; `construct_instance()` então preservava o vencimento antigo na instância; `PhoneLine.clean()` automático revalidava usando esse valor antigo somado a dados novos (ex.: nova data de ativação), gerando **segunda mensagem contraditória** no mesmo campo. No caminho de criação (instância nova, sem valor antigo), o mesmo padrão gerava a **mesma mensagem duas vezes** na lista de erros do campo.

Testes que reproduziram o RED antes da correção (`telecom/test_whatsapp_seal.py`):
- `test_missing_seal_field_error_message_not_duplicated`: criação com vencimento ausente — lista de erros continha a mensagem "obrigatória" duplicada.
- `test_invalid_edit_does_not_reuse_stale_value_for_contradictory_message`: edição válida seguida de edição inválida (nova ativação + vencimento vazio) — lista de erros continha "obrigatória" **e** "não pode ser anterior à data de ativação" (mensagem contraditória, originada do vencimento antigo ainda salvo).
- `test_invalid_http_edit_keeps_errors_and_does_not_persist_partial_data`: mesmo cenário via POST HTTP em `telecom:phoneline_update` — mesma duplicidade de mensagens; confirmado também que nenhuma alteração parcial foi persistida (`refresh_from_db()` preserva dados originais), tanto antes quanto depois da correção.

Correção aplicada: chamada explícita de `validate_seal_fields` removida de `PhoneLineForm.clean()` (o método `clean()` inteiro foi removido, já que não fazia mais nada além de repassar `super().clean()`); import não usado de `validate_seal_fields` e `django.core.exceptions.ValidationError as DomainValidationError` removidos de `telecom/forms.py`. Validação de domínio passa a fluir inteiramente pelo caminho padrão do `ModelForm` (`_post_clean` → `construct_instance` com `cleaned_data` intacto → `instance.full_clean()` → `PhoneLine.clean()` → `validate_seal_fields`), que usa os dados recém-submetidos (não valores antigos), pois nada é removido de `cleaned_data` antes de `construct_instance()` rodar. `clear_seal_fields` de `telecom/whatsapp_seal.py` segue sem uso por nenhum fluxo (irrelevante para este ponto — a limpeza de Sem selo já é feita pela normalização de dados brutos em `full_clean()`, mantida sem alteração).

GREEN após a correção: os três testes acima passam; suíte completa de `telecom/test_whatsapp_seal.py` mantém 33 aprovados, 1 falha (`test_http_create_detail_list_and_edit`, escopo de template/JS SEL-07, inalterada por esta correção). Regressão `telecom/tests.py` + `telecom/tests_line_timeline.py`: 229 aprovados, 1 pulado, sem quebra. `manage.py check`: `System check identified no issues (0 silenced)`.

Nenhuma mudança de requisito aprovado. Nenhum teste enfraquecido. Nenhuma alteração em template/JS/CSS. SEL-06 permanece concluída, com a correção acima substituindo a justificativa/implementação anterior.

Comandos e resultados:

```powershell
venv/Scripts/python.exe -m pytest telecom/test_whatsapp_seal.py -q
```
RED antes da implementação (confirmado nesta sessão, reproduz os 16 do registro de SEL-05): 16 falharam, 15 aprovados.
GREEN após a implementação (antes da correção documental acima): 30 aprovados, 1 falha. Falso positivo reconferido: `test_invalid_http_post_keeps_errors` — antes passava (302) porque o form ignorava os campos de selo; agora passa (200, erro em `whatsapp_seal_expires_on`, nenhuma `PhoneLine` criada) por validação real via `full_clean()` + `PhoneLine.clean()` automático, evidência de persistência e validação reais, não apenas `form.is_valid()`.
GREEN após a correção pontual acima (3 testes novos + suíte completa): 33 aprovados, 1 falha — `test_http_create_detail_list_and_edit` (espera `b"SELO WHATS LINEOPS"` e `b'phone-line-form.js'` no HTML da página de cadastro; template/JS são SEL-07).

```powershell
venv/Scripts/python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
```
Resultado: 229 aprovados, 1 pulado. Nenhuma regressão (mesmo resultado do baseline SEL-05).

```powershell
venv/Scripts/python.exe manage.py check
```
Resultado: `System check identified no issues (0 silenced)`.

```powershell
venv/Scripts/python.exe manage.py makemigrations --check --dry-run
```
Resultado (exit 1, apenas leitura — confirmado por `git status --short` sem novos arquivos): mesmo drift pré-existente e fora de escopo já registrado em SEL-05 (`dashboard/migrations/0010_alter_dailyuseraction_action_type.py` e `telecom/migrations/0022_alter_phoneline_origem.py`, nenhum criado); nenhuma migration nova foi necessária para SEL-06.

Três falsos positivos reconferidos com evidência de comportamento real (não apenas `form.is_valid()`):
- `test_without_seal_ignores_stale_hidden_values`: `form.save()` executado, `PhoneLine` persistida com os cinco campos vazios/nulos — valores residuais inválidos (`"invalid"` em e-mail e vencimento) descartados por `full_clean()` antes da validação de tipo.
- `test_removing_seal_clears_data`: `PhoneLineUpdateForm.save()` executado sobre instância existente com selo; após `refresh_from_db()`, `whatsapp_seal_email == ""`, `whatsapp_seal_expires_on is None`, `status` preservado.
- `test_reactivation_does_not_restore_old_seal`: `PhoneLine.create_or_reuse` chamado sem argumentos de selo após soft-delete de linha que tinha selo; `refresh_from_db()` confirma `whatsapp_seal == ""` e `whatsapp_seal_expires_on is None` — nenhuma recuperação implícita de selo antigo.

Limitações:
- `test_http_create_detail_list_and_edit` permanece falhando: depende do bloco SELO WHATS LINEOPS no template e de `phone-line-form.js`, ambos fora do escopo desta tarefa (SEL-07/08), conforme limite explícito de não alterar templates/JavaScript/CSS.
- Drift pré-existente em `telecom.PhoneLine.origem` e `dashboard.DailyUserAction.action_type` permanece fora do escopo, não corrigido, não incorporado a nenhuma migration desta tarefa.
- Nenhuma migration aplicada em banco operacional. Nenhum commit, push ou deploy realizado.
- `manage.py migrate --plan` não executável neste ambiente local (mesma limitação de rede registrada em SEL-05); não reexecutado nesta tarefa por não haver migration nova.

**SEL-05 — concluída em 2026-09-17.**

Arquivos alterados:
- `telecom/whatsapp_seal.py` (novo): `WhatsAppSeal`, `WhatsAppSealPayment` (TextChoices), `validate_seal_fields` (obrigatoriedade condicional e ordem de datas), `clear_seal_fields` (utilitário de domínio para fluxo Sem selo, a ser usado por create_or_reuse/formulários em SEL-06), `compute_seal_status` (indicador calculado por `timezone.localdate()`, nada persistido).
- `telecom/models.py`: cinco campos em `PhoneLine` (`whatsapp_seal`, `whatsapp_seal_activated_on`, `whatsapp_seal_expires_on`, `whatsapp_seal_email`, `whatsapp_seal_payment`), propriedade `seal_status`, `clean()` chamando `validate_seal_fields`.
- `telecom/migrations/0021_phoneline_whatsapp_seal_and_more.py` (novo): 5 `AddField`, todos nulos/vazios por padrão (`blank=True`, `null=True` ou `default=""`); sem `AlterField` de `origem` — ver Limitações.
- `telecom/test_whatsapp_seal.py`: adicionados `test_migration_preserves_existing_lines_as_no_seal` e `test_migration_0021_is_reversible` (`django_db(transaction=True)` + `call_command("migrate", ...)` em SQLite de teste isolado).

Comandos e resultados:

```powershell
venv/Scripts/python.exe manage.py makemigrations telecom
```
Gerou `0021_phoneline_whatsapp_seal_and_more.py` com 5 `AddField` + 1 `AlterField` em `origem`; o `AlterField` foi removido manualmente do arquivo (drift pré-existente, não introduzido por esta tarefa — confirmado via `git diff --stat -- telecom/models.py` mostrando apenas inserções, nenhuma linha de `Origem` tocada).

```powershell
venv/Scripts/python.exe -m pytest telecom/test_whatsapp_seal.py -q
```
Resultado: 15 aprovados, 16 falharam. Aprovados de domínio SEL-05: `test_expiry_boundaries` (6 casos), `test_without_seal_has_no_alert`, `test_model_validation_requires_seal_details`, `test_migration_preserves_existing_lines_as_no_seal`, `test_migration_0021_is_reversible`. Aprovados acidentais (mesma causa da SEL-04, sem relação com a lacuna de formulário): `test_equal_dates_accepted`, `test_operator_cannot_create_seal`, `test_without_seal_ignores_stale_hidden_values`, `test_removing_seal_clears_data`, `test_reactivation_does_not_restore_old_seal` — passam porque `PhoneLineForm`/`create_or_reuse` ainda ignoram os campos de selo (integração é SEL-06), não porque a limpeza de dados esteja implementada nesses fluxos. As 16 falhas restantes são todas de formulário/HTTP (`PhoneLineForm` não expõe/valida campos de selo; view/templates sem bloco SELO), escopo SEL-06/SEL-07/SEL-08.

```powershell
venv/Scripts/python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
```
Resultado: 229 aprovados, 1 pulado. Nenhuma regressão.

```powershell
venv/Scripts/python.exe manage.py check
```
Resultado: `System check identified no issues (0 silenced)`.

```powershell
venv/Scripts/python.exe manage.py makemigrations --check --dry-run
```
Resultado (exit 1, apenas leitura, nenhum arquivo escrito — confirmado por `git status --short`): detectou drift pré-existente e fora do escopo desta tarefa, não incorporado à migration 0021:
- `dashboard/migrations/0010_alter_dailyuseraction_action_type.py` (não criado): `AlterField` em `dailyuseraction.action_type`.
- `telecom/migrations/0022_alter_phoneline_origem.py` (não criado): `AlterField` em `phoneline.origem`.

```powershell
venv/Scripts/python.exe manage.py migrate --plan
```
Resultado: `OperationalError: could not translate host name "db" to address`. Ambiente local não tem acesso ao Postgres operacional (host `db` não resolvível fora do container); comando não pôde ser executado nesta sessão. Reversibilidade e preservação de dados foram comprovadas em banco SQLite de teste isolado via `test_migration_0021_is_reversible` e `test_migration_preserves_existing_lines_as_no_seal` (migração 0021 aplicada e revertida com `call_command("migrate", ...)`, isolamento de banco de teste já confirmado em SEL-04). Migration não foi aplicada em banco operacional.

Limitações:
- Drift pré-existente em `telecom.PhoneLine.origem` e `dashboard.DailyUserAction.action_type`, fora do escopo SEL-05, não corrigido nem incorporado à migration 0021. Reportado aqui separadamente conforme instrução.
- `manage.py migrate --plan` não executável neste ambiente local (sem rede até host `db`); validação de plano de migração real fica pendente para ambiente com acesso ao Postgres operacional.
- Integração de `PhoneLineForm`, `PhoneLineUpdateForm` e `create_or_reuse` com os campos de selo é SEL-06; `clear_seal_fields` foi criada em `telecom/whatsapp_seal.py` mas ainda não é chamada por nenhum fluxo — os 3 testes que "passam" hoje envolvendo Sem selo/reativação via formulário são falsos positivos por ausência de integração, não evidência de comportamento correto; devem ser reconferidos em SEL-06.
- Nenhuma migration aplicada em banco operacional. Nenhum commit, push ou deploy realizado.

Ambiente: `venv/Scripts/python.exe` confirmado sem pytest/pytest-django (`No module named pytest`, `No module named 'pytest_django'`). Não listados em requirements.txt nem requirements-dev.txt. Autorização de instalação solicitada e concedida pelo usuário nesta tarefa (pip sem elevação, escopo restrito ao venv do projeto).

```powershell
venv/Scripts/python.exe -m pip install pytest pytest-django
```
Resultado: `Successfully installed colorama-0.4.6 iniconfig-2.3.0 pluggy-1.6.0 pygments-2.21.0 pytest-9.1.1 pytest-django-4.14.0`.

```powershell
venv/Scripts/python.exe -m pytest --version
```
Resultado: `pytest 9.1.1`.

Banco de teste isolado confirmado por leitura de config/settings.py: quando `pytest` está em `sys.modules`, `DATABASES["default"]` é substituído por SQLite em `test_db.sqlite3`; Postgres operacional não é usado durante os testes.

```powershell
venv/Scripts/python.exe -m pytest telecom/test_whatsapp_seal.py -q
```
Resultado: 29 testes coletados, 27 falharam, 2 aprovados. Coleta sem erro de dependência, import ou configuração.

Causas das falhas — todas por funcionalidade de selo ausente, nenhuma por dependência/configuração/coleta:
- `PhoneLineForm` ainda não expõe nem valida os campos whatsapp_seal*: `test_seal_requires_each_field` (8 casos) falha porque `form.is_valid()` retorna `True` mesmo com campo obrigatório do selo vazio.
- `test_create_persists_manual_dates`, `test_invalid_seal_data` (4 casos), `test_without_seal_ignores_stale_hidden_values`, `test_removing_seal_clears_data`, `test_reactivation_does_not_restore_old_seal`, `test_invalid_http_post_keeps_errors`: mesma causa raiz, ausência de campos/validação de selo no form.
- `PhoneLine` ainda não tem os cinco campos nem a propriedade `seal_status`: `test_model_validation_requires_seal_details` e `test_expiry_boundaries` (6 casos) falham com `AttributeError: 'PhoneLine' object has no attribute 'seal_status'` (ou equivalente de validação de modelo).
- `test_http_create_detail_list_and_edit`: falha por dependência do fluxo HTTP completo nos campos/modelo ainda inexistentes.

2 aprovados, sem relação com a lacuna de selo (não invalidam RED):
- `test_equal_dates_accepted`: passa por acaso — form ignora campos whatsapp_seal* desconhecidos, não rejeita nada; precisa reverificação quando a validação existir.
- `test_operator_cannot_create_seal`: passa por comportamento de permissão pré-existente (403 para role OPERATOR), independente do selo.

Limitações: RED cobre somente telecom/test_whatsapp_seal.py, conforme escopo desta tarefa. `telecom/tests.py`, `telecom/tests_line_timeline.py`, `manage.py check` e verificação de migrations não fazem parte de SEL-04 e não foram executados aqui.

Comandos de referência para próximas etapas, na raiz lineops:

```powershell
venv/Scripts/python.exe -m pytest telecom/test_whatsapp_seal.py -q
venv/Scripts/python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
venv/Scripts/python.exe manage.py check
venv/Scripts/python.exe manage.py makemigrations --check --dry-run
venv/Scripts/python.exe manage.py migrate --plan
```

pytest usa configuração SQLite de teste existente. Não aplicar migrations no banco operacional. Registrar comando concluído, data, resultado e limitações a cada validação.

## Test Checklist — critérios de aceite

- Cadastro sem selo e cadastro com cada um dos dois selos; persistência após recarregar.
- Para cada selo, rejeitar separadamente a ausência de ativação, vencimento, e-mail ou pagamento, com erro no campo correspondente; aceitar Sem selo com os quatro campos vazios.
- Rejeitar e-mail inválido e pagamento ou selo fora das opções.
- Datas invertidas, datas iguais e edição da data de vencimento.
- Limites de 8, 7, 1, 0 e -1 dias usando relógio controlado e data local.
- Troca entre selos, remoção do selo, renovação e reativação de linha excluída.
- Migration preserva linhas existentes como Sem selo.
- Permissões atuais e escopo de visibilidade preservados; status/alocação não mudam com vencimento.
- Campos ocultos sem foco; erros mantêm bloco correto aberto; fluxo sem JavaScript.
- Layout desktop e celular; texto e cores dos alertas; nenhum overflow horizontal.

## Test Strategy

pytest para regras e formulários; testes Django de integração para banco, cadastro, edição e autorização, aproveitando configuração existente. Testes significativos derivados dos casos acima, não da estrutura interna do código. Verificação de migrations e manage.py check no ambiente do projeto. Validação real no navegador para interação, teclado e responsividade.

## Compliance Report

SEL-04 (histórico): pytest/pytest-django instalados no venv, banco de teste isolado confirmado, RED comprovado (27 falhas, 2 aprovados sem relação).

SEL-05 (esta tarefa): domínio validado — `PhoneLine.clean()` rejeita selo com campo obrigatório ausente ou vencimento anterior à ativação (`test_model_validation_requires_seal_details`); `seal_status` calcula tone/label por `timezone.localdate()` nos limites 8, 7, 1, 0, -1 e -5 dias sem persistir estado (`test_expiry_boundaries`, `test_without_seal_has_no_alert`); migration 0021 aditiva, reversível e comprovada em banco isolado, linhas existentes preservadas como Sem selo (`test_migration_0021_is_reversible`, `test_migration_preserves_existing_lines_as_no_seal`); `activated_at`, `status` e alocações não tocados pelos novos campos (nenhuma alteração em signals.py, allocations/ ou create_or_reuse). `manage.py check` limpo; regressão telecom completa (229 aprovados, 1 pulado) sem quebras.

SEL-06 (esta tarefa): `PhoneLineForm`/`PhoneLineUpdateForm` integrados aos cinco campos de selo. Obrigatoriedade condicional, ordem de datas e formatos (e-mail/opções) validados via `validate_seal_fields` (reuso de domínio, chamado por `PhoneLine.clean()`) e campos automáticos do Django; erros associados ao campo correspondente (`test_seal_requires_each_field`, `test_invalid_seal_data`). Sem selo, valores residuais nos campos ocultos — inclusive inválidos — são descartados antes da validação de tipo e a linha é salva limpa (`test_without_seal_ignores_stale_hidden_values`). `create_or_reuse` persiste selo em linhas novas e nunca recupera selo antigo implicitamente em reativação (`test_reactivation_does_not_restore_old_seal`); chamadas antigas sem argumentos de selo (admin.py, SIMcardCreateView, telephony_use_case.py) preservadas como Sem selo por default. Edição, troca e remoção de selo comprovadas por `refresh_from_db()` (`test_removing_seal_clears_data`). `save(commit=False)`, permissões (`test_operator_cannot_create_seal`) e regras de alocação preservadas — nenhuma alteração em signals.py, allocations/ ou lógica de status.

Correção pontual (mesma tarefa, mesma data): justificativa original sobre `Model.full_clean()` pular `self.clean()` com `exclude` não vazio estava incorreta (Django 5.2.11 sempre chama `self.clean()`, confirmado em `django/db/models/base.py:1651-1656`). Chamada explícita de `validate_seal_fields` em `PhoneLineForm.clean()` era redundante com a validação automática do modelo e causava bug real: `add_error()` remove campo de `cleaned_data`, `construct_instance()` pula esse campo e mantém valor antigo da instância — na edição, isso produzia segunda mensagem contraditória no mesmo campo (usando vencimento antigo salvo); na criação, duplicava a mesma mensagem. Reproduzido em RED por 3 testes novos (`test_missing_seal_field_error_message_not_duplicated`, `test_invalid_edit_does_not_reuse_stale_value_for_contradictory_message`, `test_invalid_http_edit_keeps_errors_and_does_not_persist_partial_data`). Corrigido removendo a chamada explícita (método `clean()` inteiro removido de `PhoneLineForm`); validação de domínio passa a fluir só pelo caminho automático `ModelForm._post_clean → PhoneLine.clean() → validate_seal_fields`, usando dados recém-submetidos. GREEN comprovado nos 3 testes novos e em toda a suíte. Nenhuma alteração de requisito, nenhum teste enfraquecido, nenhuma migration nova.

33 aprovados em telecom/test_whatsapp_seal.py (30 de SEL-06 + 3 da correção), 1 falha remanescente de template/JS (SEL-07/08). Regressão completa (229 aprovados, 1 pulado) sem quebras. `manage.py check` limpo; `makemigrations --check --dry-run` mostra apenas o drift pré-existente já registrado em SEL-05, nenhuma migration nova necessária.

Falhas remanescentes por tarefa: `test_http_create_detail_list_and_edit` é de template/JS — bloco SELO WHATS LINEOPS e phone-line-form.js ainda não existem (SEL-07); listagem/detalhe ainda não exibem indicador (SEL-08). Drift pré-existente fora do escopo em `telecom.PhoneLine.origem` e `dashboard.DailyUserAction.action_type`, não corrigido. `manage.py migrate --plan` não executável neste ambiente (sem rede até host `db` do Postgres operacional); não reexecutado por não haver migration nova nesta tarefa.

SEL-07 (esta tarefa): `phoneline_form.html` reescrito com dois cards (Dados da linha / Selo WhatsApp LineOps), responsivos via grid Bootstrap (`col-lg-6` lado a lado, `col-12` empilhado, Dados da linha primeiro no DOM). Bloco de selo condicional: oculto (`hidden`) e sem `required` quando "Sem selo"; visível e `required` quando há selo — obrigatoriedade HTML calculada em `PhoneLineForm.__init__` a partir do valor atual (bound data ou instância), preservando o estado após POST inválido e na edição (`test_get_edit_preserves_seal_data`, `test_invalid_edit_keeps_seal_block_open`). `static/js/phone-line-form.js` sincroniza a mesma lógica no cliente, sem apagar valores digitados ao alternar o seletor antes de salvar (não há reset/recriação de elementos, apenas toggle de `hidden`/`required`). Correção da conferência real: sem scripts os campos ficam inacessíveis quando hidden está presente, apesar de permanecerem no DOM; a obrigatoriedade é renderizada pelo servidor — autoridade de validação continua em `PhoneLine.clean()` (nenhuma mudança em `PhoneLineForm.clean()`/`full_clean()`/`save()`). Ação Liberar preservada (`test_release_action_still_works_http`) e corrigida para não ser bloqueada pela nova validação HTML via `formnovalidate` (`test_release_action_bypasses_html_validation`). Labels associados via `for`/`id_for_label`, erros por campo com container `id` referenciado por `aria-describedby`, resumo de erros focável (`tabindex="-1"`, foco automatico via JS) com links para os campos.

8 testes novos em `telecom/test_phoneline_form_ui.py`, todos aprovados. `telecom/test_whatsapp_seal.py`: 34 aprovados, 1 falha — `test_http_create_detail_list_and_edit` deixou de falhar por template/JS (asserts de SEL-07 passam) e agora falha em `detail.content` (SEL-08, fora do escopo autorizado desta tarefa, não implementado para não mascarar o próximo gap). Regressão completa (229 aprovados, 1 pulado) sem quebras. `manage.py check` limpo.

Falhas remanescentes por tarefa: `test_http_create_detail_list_and_edit` — SEL-08 (detalhe/listagem/payload JSON). Drift pré-existente fora do escopo em `telecom.PhoneLine.origem` e `dashboard.DailyUserAction.action_type`, não corrigido (não reconferido nesta tarefa, sem alteração de modelo).

Limitação registrada nesta tarefa (não contornada): validação em navegador real (interação JS ao vivo, navegação por teclado, responsividade visual em ~400px, cores) não foi executada — esta sessão não teve acesso a ferramenta de automação de navegador (Chrome DevTools MCP indisponível). Evidência parcial via HTTP real (servidor local `manage.py runserver` contra banco de desenvolvimento isolado do próprio `docker-compose.yml`, dados sintéticos criados e removidos, banco parado ao final) confirma que a página responde, contém os blocos esperados e o script é servido; não confirma execução real do JavaScript, teclado ou layout visual. Checkbox de SEL-07 mantida aberta por esse motivo — aceite funcional/servidor comprovado, aceite visual/interativo em navegador real pendente.

Próximo passo: validação em navegador real de SEL-07 (quando houver ferramenta de navegador disponível ou o usuário puder validar manualmente), depois SEL-08 — detalhe, indicadores da listagem e payloads JSON.

Nenhuma migration aplicada em banco operacional, nenhum commit, push ou deploy. Alterações locais anteriores preservadas.

## Correção dos achados de SEL-07 — 2026-09-17

### Spec Summary

Corrigir somente os três achados confirmados na "Conferência real de SEL-07" abaixo, sem avançar para SEL-08. Fonte: seção de conferência real desta mesma spec.

### Gap Analysis

1. **Fallback sem scripts falhava.** `templates/telecom/phoneline_form.html` renderizava `hidden` em `#seal-detail-fields` no servidor, condicionado ao valor do selo. Sem JavaScript, nada removia esse atributo — selecionar um selo na tela não tornava os campos acessíveis, pois a troca de `<select>` não recarrega a página. Causa raiz: a ocultação era responsabilidade do servidor, quando deveria ser exclusivamente do JavaScript (melhoria progressiva invertida).
2. **Opção vazia sem rótulo.** `whatsapp_seal` é `CharField(choices=WhatsAppSeal.choices, blank=True)`; o Django adiciona automaticamente a escolha em branco `BLANK_CHOICE_DASH` (`"---------"`) para campos não obrigatórios com `choices`. Nunca foi definido um rótulo customizado.
3. **Resumo de erros com nome técnico.** `PhoneLineForm` não definia `label` para os cinco campos de selo; `field.label` no template do resumo caía no humanize automático do Django a partir do nome do campo (`whatsapp_seal_expires_on` → "Whatsapp seal expires on").

Causa raiz adicional (não relatada como achado isolado, mas decorrente do achado 1): como o `required` HTML dos quatro campos também era calculado no servidor a partir do valor corrente do selo, um usuário sem JavaScript trocando um selo existente para Sem selo enviaria o formulário com `required` ainda presente (renderizado na carga da página, não atualizado sem JS) — bloqueio de validação HTML5 no envio, mesmo com a seleção "Sem selo" já feita.

### Implementation Plan — ações executadas

1. `telecom/test_phoneline_form_ui.py`: reescrito `test_create_defaults_to_no_seal_hint_and_hidden_details` (esperava `hidden`/`required` no HTML inicial — contradizia o fallback correto) como `test_create_shows_no_seal_hint` (só o texto) + novo `test_seal_detail_fields_accessible_without_js_by_default` (nem `hidden` nem `required` em nenhum estado servidor-renderizado, cadastro e edição). Removida a asserção de `required` em `test_get_edit_preserves_seal_data`. Adicionados: `test_whatsapp_seal_blank_choice_label_is_sem_selo`, `test_error_summary_uses_friendly_ptbr_labels`, `test_seal_field_labels_are_ptbr`, `test_switching_existing_seal_to_none_without_js_saves_and_clears`. RED comprovado antes da correção: 4 falhas (as 4 asserções novas/reescritas), 9 aprovados nos testes não afetados.
2. `telecom/forms.py`:
   - `Meta.labels` novo: `whatsapp_seal`→"Selo", `whatsapp_seal_activated_on`→"Ativação", `whatsapp_seal_expires_on`→"Vencimento", `whatsapp_seal_email`→"E-mail cadastrado", `whatsapp_seal_payment`→"Pagamento". Usado tanto nos `<label>` do formulário (via `{{ form.field.label }}`, substituindo texto hardcoded) quanto no resumo de erros (já usava `field.label`).
   - `__init__`: removido o bloco que adicionava/removia `required` nos widgets dos 4 campos de detalhe do selo. Import `WhatsAppSeal` adicionado; `self.fields["whatsapp_seal"].choices` passa a ser `[("", "Sem selo")] + list(WhatsAppSeal.choices)`, preservando os valores internos (`""`, `META_ONE`, `META_VERIFIED`) — só o rótulo da opção vazia muda.
   - Nenhuma mudança em `full_clean()`, `clean()`, `save()` ou em qualquer regra de domínio; `PhoneLine.clean()`/`validate_seal_fields` seguem como única autoridade de validação.
3. `templates/telecom/phoneline_form.html`: removidas as condicionais `{% if %} hidden{% endif %}` de `#seal-empty-hint` e `#seal-detail-fields` — servidor nunca mais renderiza `hidden`. Labels dos 5 campos de selo trocados de texto fixo para `{{ form.<campo>.label }}` (fonte única com `Meta.labels`).
4. `static/js/phone-line-form.js`: sem alteração de código — a lógica de `sync()` (toggle de `hidden`/`required` no `change` e na carga) já era a peça de JavaScript correta; o bug estava em o servidor antecipar esse `hidden`/`required` antes do JS rodar. Com o HTML base neutro, o mesmo script agora produz o comportamento correto: oculta/exige quando executa, e nunca bloqueia quando não executa.

### Test Checklist

- Sem JS (simulado via Django test client, que nunca executa scripts): campos de detalhe do selo sempre presentes e sem `hidden`/`required` em qualquer estado (cadastro Sem selo, cadastro/edição com selo) — `test_seal_detail_fields_accessible_without_js_by_default`.
- Trocar selo existente para Sem selo e salvar com campos de detalhe ainda preenchidos (simulando ausência de JS para limpá-los antes do envio): aceito, servidor limpa os cinco campos — `test_switching_existing_seal_to_none_without_js_saves_and_clears`.
- Opção vazia do seletor de selo mostra "Sem selo", não "---------" — `test_whatsapp_seal_blank_choice_label_is_sem_selo`.
- Resumo de erros usa "Vencimento", nunca "Whatsapp seal expires on" — `test_error_summary_uses_friendly_ptbr_labels`.
- Labels dos 5 campos de selo em PT-BR — `test_seal_field_labels_are_ptbr`.
- Testes preexistentes de SEL-07 (blocos, script, preservação de dados na edição, erros com valores preservados, ação Liberar) continuam passando sem alteração de comportamento esperado.

### Test Strategy

RED→GREEN via Django test client em `telecom/test_phoneline_form_ui.py`; suíte de domínio completa e regressão executadas para garantir ausência de efeito colateral. Verificação visual/interativa real não repetida nesta sessão — ver Limitações.

### Comandos e resultados

```powershell
venv/Scripts/python.exe -m pytest telecom/test_phoneline_form_ui.py -q
```
RED antes da correção: 4 falhas (`test_seal_detail_fields_accessible_without_js_by_default`, `test_whatsapp_seal_blank_choice_label_is_sem_selo`, `test_error_summary_uses_friendly_ptbr_labels`, `test_seal_field_labels_are_ptbr`), 9 aprovados.
GREEN após a correção: 13 aprovados (9 anteriores + 4 novos; nenhum teste removido, `test_get_edit_preserves_seal_data` mantido com a asserção de `required` retirada por contradizer o fallback correto).

```powershell
venv/Scripts/python.exe -m pytest telecom/test_whatsapp_seal.py -q
```
Resultado: 34 aprovados, 1 falha — `test_http_create_detail_list_and_edit`, mesma falha de SEL-08 (detalhe) já registrada antes desta correção, inalterada.

```powershell
venv/Scripts/python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
```
Resultado: 229 aprovados, 1 pulado, 174.75s. Nenhuma regressão.

```powershell
venv/Scripts/python.exe manage.py check
```
Resultado: `System check identified no issues (0 silenced)`.

### Compliance Report

Três achados da conferência real corrigidos com o menor conjunto de mudanças necessário: nenhum campo/migration/regra de domínio alterado, `PhoneLineForm.clean()` continua sem chamada explícita de validação redundante (não reintroduzida). Correção 1 resolvida invertendo a responsabilidade de ocultar/exigir os campos — de servidor-condicional para JavaScript-exclusivo — o que também elimina, como efeito colateral correto, o bloqueio de `required` residual ao trocar um selo existente para Sem selo sem JavaScript (critério de aceite explícito). Correções 2 e 3 são apenas textuais (`choices` e `labels`), sem efeito em validação ou persistência.

**Limitação — verificação em navegador real não repetida nesta sessão:** esta sessão não tem acesso a ferramenta de automação de navegador (mesma ausência já registrada na implementação original de SEL-07). A "Conferência real de SEL-07" abaixo foi feita em sessão separada, com navegador Chromium real; os três achados ali descritos foram corrigidos aqui com evidência de teste automatizado e leitura de código, mas **a repetição dos cenários em navegador real (desktop/celular, teclado, CSP sem scripts, troca de selo ao vivo) não foi executada nesta sessão** — não declaro essa validação concluída. SEL-07 permanece aberta até essa repetição confirmar as correções.

Nenhuma alteração em `telecom/models.py`, migrations, banco operacional. Nenhum commit, push ou deploy.

Próximo passo: repetir os cenários da "Conferência real de SEL-07" (abaixo) em navegador real — mesma ferramenta/sessão usada antes, ou o usuário manualmente — para confirmar os três achados corrigidos e então marcar SEL-07 concluída. Depois, SEL-08.

## Conferência real de SEL-07 — 2026-09-17

### Spec Summary e ambiente

Verificação solicitada pelo usuário, sem alteração em código de aplicação. Navegador Chromium do Codex, servidor WSGI local em 127.0.0.1:8765, SQLite exclusivo em diretório temporário lineops-sel07-browser-qa, usuário e linhas sintéticos. Nenhuma conexão com banco operacional. A limitação histórica de ausência de navegador foi superada nesta conferência.

### Test Checklist e resultados

- PASS: desktop 1366x900, dois cards com mesma largura (614px), mesma altura, lado a lado e sem overflow horizontal.
- PASS: viewport móvel solicitado 390x844, área útil medida 375px; cards empilhados, Dados da linha primeiro, scrollWidth igual a clientWidth (375px). Screenshot de página inteira inspecionada.
- PASS: seleção de selo revela quatro campos e marca required; seleção vazia oculta e remove required. Tab após seletor vazio pula campos ocultos e foca Cancelar.
- PASS: alternância META VERIFICADO → vazio → META ONE na edição preserva datas, e-mail sintético e pagamento; conferido visualmente. Leitura DOM da ferramenta omite valores de e-mail, portanto screenshot foi usada para esse campo.
- PASS: vencimento anterior à ativação enviado ao servidor retorna erro, preserva valores e foca form-error-summary. Link do resumo leva foco ao campo de vencimento.
- PASS: vencimento vazio impede Salvar alterações pela validação HTML e foca campo. Liberar funciona no mesmo estado e retorna mensagem Linha liberada com sucesso (linha sintética sem alocação).
- PASS: comando `venv/Scripts/python.exe -m pytest telecom/test_phoneline_form_ui.py -q` retornou 8 passed, 3 warnings em 4.26s. Avisos: dois de depreciação preexistente de CheckConstraint e um de permissão de cache pytest. Estes testes não cobrem os achados abaixo.

### Gap Analysis — achados reproduzidos

1. **Fallback sem scripts falha.** Resposta de QA com Content-Security-Policy: script-src 'none' bloqueou scripts sem alterar template. No cadastro, selecionar META ONE deixou seal-detail-fields com hidden=true e display=none: impossível preencher os quatro campos naquela tela. Causa: phoneline_form.html entrega hidden no HTML; só JS remove. Presença no DOM não significa acessibilidade. Critério da spec não atendido.
2. **Opção Sem selo sem rótulo.** Seletor exibe --------- para valor vazio, tanto no cadastro quanto na edição; deveria exibir Sem selo conforme spec.
3. **Resumo de erros com nome técnico.** Data anterior à ativação gera link Whatsapp seal expires on, enquanto label visual é Vencimento. Template usa field.label sem labels amigáveis definidos para campos do selo.

### Implementation Plan para fechar SEL-07

Dentro da mesma SEL-07, derivar testes de regressão para os três achados antes da correção. Usar melhoria progressiva: HTML base permite preencher campos sem scripts; JS aplica ocultação/required quando disponível. Garantir também que trocar de selo para Sem selo sem JS não seja bloqueado por required HTML residual. Definir opção Sem selo e labels PT-BR no formulário. Repetir navegador e testes após correção; não avançar escopo para SEL-08 nesta correção.

### Test Strategy e Compliance Report

Inspeção de código + testes Django + interação real (seletores, datas, teclado, submits), leitura DOM e screenshots. Cenário sem scripts validado com CSP no servidor exclusivo de QA; não houve mudança de configuração do navegador nem da aplicação. Não foram reexecutadas suítes de domínio ou regressão completa nesta conferência. Cores dos alertas pertencem a SEL-08 e não foram validadas. SEL-07 permanece aberta por falhas de aceite confirmadas, não por indisponibilidade de ferramenta.

Servidor de QA encerrado ao final. Código de aplicação, migrations e testes preservados; apenas esta fonte da verdade atualizada. Sem commit/push/deploy.

## Revalidação final de SEL-07 — 2026-09-17

Este registro supersede o status aberto e a limitação de navegador dos registros históricos acima; preserva histórico dos achados e correções.

### Spec Summary / Gap Analysis

Repetidos três achados após correção. Nenhum dos três persiste. Sem alteração de implementação nesta conferência. SEL-07 concluída; SEL-08 não executada.

### Implementation Plan / Test Checklist executados

Navegador Chromium do Codex; servidor WSGI em 127.0.0.1:8765 e SQLite temporário exclusivo lineops-sel07-browser-qa. Apenas dados sintéticos. No cenário sem scripts, resposta de QA aplica Content-Security-Policy: script-src 'none', inclusive no POST com query qa_nojs=1.

- PASS: Sem selo aparece como opção explícita. Com scripts bloqueados, quatro campos visíveis e sem required residual mesmo após selecionar META ONE.
- PASS: enviar cadastro incompleto sem scripts retorna quatro erros do servidor com labels Ativação, Vencimento, E-mail cadastrado e Pagamento. Campos continuam acessíveis.
- PASS: completar os dados e enviar sem scripts retorna Linha telefônica criada com sucesso; edição posterior apresenta selo/datas/pagamento gravados.
- PASS: editar linha criada, selecionar Sem selo, esvaziar detalhes e salvar sem scripts retorna Linha telefônica atualizada com sucesso. Consulta SQLite somente leitura confirmou selo='', ativação=None, vencimento=None, e-mail='', pagamento=''.
- PASS: com JS, selecionar Sem selo oculta detalhes e remove os quatro required; Tab passa diretamente a Cancelar. Voltar a META ONE exibe detalhes, restaura required e preserva valores anteriores. Datas conferidas no DOM; e-mail sintético conferido visualmente.
- PASS: vencimento anterior à ativação gera resumo em PT-BR com Vencimento, mantém dados e foca form-error-summary. Link Vencimento move foco ao input correspondente.
- PASS: vencimento vazio impede envio normal e foca campo. Liberar ignora validação HTML e retorna Linha liberada com sucesso (linha sintética sem alocação).
- PASS: desktop 1366x900, cards lado a lado com mesma largura, sem overflow horizontal. Móvel 390x844 (área útil 375px), cards empilhados; scrollWidth=clientWidth=375. Screenshots inspecionadas. Captura longa do navegador apresentou repetição visual na costura; medidas DOM não indicaram duplicação do formulário.

### Test Strategy

`venv/Scripts/python.exe -m pytest telecom/test_phoneline_form_ui.py -q`: **13 passed, 3 warnings in 6.77s**. Avisos já conhecidos: duas depreciações CheckConstraint e cache pytest sem permissão. Testes combinados com interação real, submits, teclado, DOM, screenshots e conferência de persistência no SQLite exclusivo.

### Compliance Report

Aceite dos três achados comprovado. Fonte da verdade atualizada; código de aplicação, testes e migrations intactos nesta conferência. Suíte de domínio/regressão completa não reexecutada nesta rodada; resultados anteriores continuam históricos. Não valida SEL-08 nem cores futuras dos indicadores. Servidor de QA encerrado, aba fechada e viewport restaurado. Sem acesso ao banco operacional, commit, push ou deploy.

Observação de texto sem scripts: dica Nenhum selo cadastrado permanece visível mesmo na edição com selo, pois seu toggle é JS. Não bloqueia preenchimento/salvamento; ajuste de redação/condição da dica pode ser feito como polimento dentro desta página, sem reabrir os três defeitos corrigidos.

## SEL-08 — Detalhe e alertas — 2026-09-17

### Spec Summary

Exibir o bloco SELO WHATS LINEOPS no detalhe da linha, incluir selo e indicador de vencimento na listagem realmente usada (overview) e integrar os payloads JSON da primeira carga e do "Carregar mais", reutilizando `seal_status` (domínio, SEL-05) sem recalcular datas no cliente nem persistir estado derivado.

### Gap Analysis

Mapeamento confirmou que só `telecom:overview` (tabela "main") tem paginação/JSON realmente em uso; o branch `recent` da mesma view e a rota `PhoneLineListView`/`phoneline_list.html` são código morto (sem template que os renderize); `operator_lines.html` é listagem real mas simples, sem paginação/JSON, fora do contrato "primeira carga = Carregar mais" pedido nesta tarefa. Nenhuma lacuna funcional restante dentro do escopo autorizado. Detalhe: `phoneline_detail.html` não exibia nenhum dado do selo, causando a falha conhecida de `test_http_create_detail_list_and_edit` em `detail.content`.

### Implementation Plan — ações executadas

1. `telecom/views.py`: `TelecomOverviewView._handle_ajax_request` (branch `main`) passa a incluir `whatsapp_seal_display` e `seal_status` no payload de cada linha, sem consulta adicional (propriedade de domínio sobre campos já carregados).
2. `templates/telecom/phoneline_detail.html`: novo card "SELO WHATS LINEOPS" — campos completos com selo, apenas "Sem selo" sem selo.
3. `templates/telecom/_seal_status_badge.html` (novo): partial único de apresentação tone→cor/texto, reutilizado por detalhe e listagem.
4. `templates/telecom/overview.html`: coluna "Selo" na tabela principal (renderização inicial via Django e via JavaScript no "Carregar mais"), com construção segura no DOM (`createElement`/`textContent`, sem `innerHTML` para dados do selo).
5. `telecom/test_seal_detail_and_listing.py` (novo): 14 testes — detalhe com cada selo e Sem selo, indicadores nos limites 8/7/1/0/-1 dias com classes de cor distintas, listagem inicial e JSON (primeira carga e "carregar mais" com formato equivalente), escopo de permissão preservado, ausência de N+1 por linha, e verificação estática de que a célula do selo no JS não usa interpolação insegura em `innerHTML`.

### Test Checklist

- [x] Detalhe com META ONE e META VERIFICADO: selo, datas (`d/m/Y`), e-mail, pagamento e indicador presentes.
- [x] Detalhe Sem selo: apenas "Sem selo", nenhum campo/indicador de vencimento.
- [x] Indicadores em 8, 7, 1, 0 e -1 dias com relógio controlado (`timezone.localdate` via `monkeypatch`), singular em 1 dia.
- [x] Classes de cor distintas para amarelo (`seal-tone-warning`), laranja (`seal-tone-today`) e vermelho (`seal-tone-expired`).
- [x] Listagem inicial mostra tipo de selo (ex.: "META ONE") e "Sem selo"; resposta JSON (`table=main`) traz `seal_status` igual ao `PhoneLine.seal_status` e não traz e-mail/datas/pagamento.
- [x] "Carregar mais" (offset diferente) retorna o mesmo formato de chaves da primeira carga, incluindo `seal_status`/`whatsapp_seal_display`.
- [x] Usuário fora do escopo (`PhoneLine.visible_to_user`) recebe 404 no detalhe e não recebe a linha/e-mail do selo na listagem nem no JSON.
- [x] Nenhuma consulta adicional por linha (comparação de contagem de queries para 1 vs. 3 linhas).
- [x] Contratos de filtros/paginação/ações preexistentes preservados (suíte completa sem regressão).
- [ ] Validação visual em navegador real (cor/contraste, overflow, JS ao vivo, teclado) — **pendente**, ferramenta indisponível nesta sessão.

### Test Strategy

Testes Django via cliente HTTP real (não `render_to_string`) para detalhe e listagem, incluindo AJAX; `monkeypatch` de `timezone.localdate` para controlar os limites do indicador; `CaptureQueriesContext` para comprovar ausência de N+1; leitura de código-fonte do template/JS para confirmar ausência de `innerHTML` inseguro (verificação estática, não substitui execução real em navegador). Regressão completa (`telecom/tests.py`, `telecom/tests_line_timeline.py`) e `manage.py check` executados sem quebras.

### Compliance Report

14 testes novos aprovados (`telecom/test_seal_detail_and_listing.py`), RED comprovado antes (12 falhas). `telecom/test_whatsapp_seal.py`: 34 aprovados, 0 falhas — `test_http_create_detail_list_and_edit` passa integralmente pela primeira vez, sem remover ou enfraquecer nenhuma assertion. `telecom/test_phoneline_form_ui.py`: 13 aprovados, sem regressão. Regressão completa: 229 aprovados, 1 pulado. `manage.py check`: limpo. Nenhuma alteração em modelo, formulário, migration, cadastro/edição, banco operacional; nenhum commit/push/deploy; nenhum backlog paralelo criado.

Limitações registradas, não contornadas: `AGENTS.md` não existe no repositório; validação visual em navegador real não executada (ferramenta indisponível) — aceite visual permanece pendente, aceite funcional/servidor comprovado. Branch `recent` de `TelecomOverviewView` e a rota `PhoneLineListView` seguem sem indicador de selo por serem código morto (fora de "listagens aplicáveis"); `operator_lines.html` é listagem real mas fora do contrato de paginação/JSON desta tarefa, não alterada. Drift pré-existente em `telecom.PhoneLine.origem`/`dashboard.DailyUserAction.action_type` não corrigido, fora de escopo.

**Status SEL-08: implementação e testes concluídos; aceite final pendente até validação visual em navegador real.** Próxima tarefa: SEL-09.

## Verificação de escopo — operator_lines.html na SEL-08 — 2026-09-18

Nenhuma alteração de código/testes nesta tarefa. Apenas investigação, sem execução de suíte (nada mudou no código).

### Spec Summary

Reexame da exclusão de `templates/telecom/operator_lines.html` do escopo de SEL-08. A exclusão original (registrada por este agente em `docs/superpowers/specs/2026-09-17-phone-line-whatsapp-seal-design.md:106`, seção "Retomada e evidências" de SEL-08) usou como justificativa "sem paginação/JSON" — critério de implementação, não decisão de produto. O requisito aprovado ("Alerta visual na listagem e no detalhe...", Spec Summary, linha 21) não faz distinção entre listagens com ou sem paginação, nem menciona `operator_lines.html`/papel OPERATOR em nenhum ponto anterior do documento (confirmado por busca textual — nenhuma ocorrência de "operator"/"Minhas Linhas" fora da própria nota de exclusão e de um teste de permissão não relacionado ao selo).

### Gap Analysis

Mapeamento:
- URL: `telecom/urls.py:33` — `path("minhas-linhas/", OperatorLinkedLinesView.as_view(), name="operator_lines")`.
- View: `telecom/views.py:904-916` (`OperatorLinkedLinesView`, `RoleRequiredMixin`, `allowed_roles = [SystemUser.Role.OPERATOR]`, linha 905). `get()` monta `lines = get_visible_phone_lines_queryset(request.user).select_related("sim_card").order_by("phone_number")` (mesma função de permissão usada por overview e detalhe, `telecom/views.py:113-118`); `if not lines.exists(): raise PermissionDenied` (linha 914); contexto `{"phone_lines": lines}` (linha 916), sem paginação nem endpoint JSON.
- Navegação: `templates/base/sidebar.html:39-45` — para `request.user.role == 'operator'`, o item único "Telecom" do menu aponta para `operator_lines` (não para `overview`); mesmo padrão em `templates/base/base.html:65`, `templates/base/tabbar.html:36`, `templates/base/tabbar_inline.html:34`. `TelecomOverviewView` redireciona OPERATOR para cá (`telecom/views.py`, branch de role operator em `_handle_ajax_request`/`get`, já mapeado em SEL-08). `templates/telecom/phoneline_detail.html:15` também aponta "Voltar" para `operator_lines` quando `request.user.role == 'operator'`.
- Perfis autorizados: somente OPERATOR (`allowed_roles = [SystemUser.Role.OPERATOR]`); ADMIN e anônimo recebem 403 (`telecom/tests.py:5105-5112`, `OperatorLinkedLinesViewTests`).
- Queryset/relação linha↔operador: `get_visible_phone_lines_queryset` → `PhoneLine.visible_to_user(user, queryset)` (`telecom/views.py:182-208` em `models.py`, já mapeado em SEL-05/08) — para role `operator`, filtra por `LineAllocation` ativa cujo `employee.email` bate com o e-mail do usuário logado. Mesma função usada por `overview` e `phoneline_detail`; nenhuma restrição adicional específica de selo em nenhum ponto do código.
- Informações/ações exibidas hoje (`templates/telecom/operator_lines.html:13-43`): Número, Status, Operadora e botão "Acessar" (link para `phoneline_detail#reconnect-whatsapp`). Nenhuma coluna de selo/indicador.
- Testes existentes confirmando listagem real, ativa e com escopo testado: `telecom/tests.py:5033-5143` (`OperatorLinkedLinesViewTests` — acesso por role, 403 para operador sem linha vinculada/admin/anônimo, todas as linhas vinculadas aparecem, link de detalhe presente, "Voltar" do detalhe aponta para cá).

Resposta às perguntas de comparação:
- Exclusão explícita para OPERATOR: **não existe**. Nenhuma frase do documento (antes desta verificação) menciona excluir OPERATOR do alerta de selo; a única linha que exclui `operator_lines.html` é a nota deste próprio agente em SEL-08, justificada só pela ausência de paginação/JSON.
- Acesso ao selo/indicador exige permissão adicional documentada: **não**. Não há conceito de "permissão de selo" em separado no código — quem pode ver a linha (via `visible_to_user`) já pode ver `whatsapp_seal*`/`seal_status` (confirmado: `phoneline_detail.html`, acessível a OPERATOR via `RECONNECT_ALLOWED_ROLES` que inclui `SystemUser.Role.OPERATOR` em `telecom/views.py:55-61`, já exibe o bloco completo SELO WHATS LINEOPS para OPERATOR desde a implementação atual de SEL-08 — sem nenhum campo oculto extra para esse papel).
- Ausência de paginação altera só implementação ou também escopo aprovado: **só implementação**. `operator_lines.html` não usa JSON/"Carregar mais"; adicionar selo/indicador é alteração puramente server-side (Django template), sem payload a definir — não colide com o contrato de payload documentado para `overview`.

### Implementation Plan — proposta, sem execução

Menor mudança necessária (não implementada nesta tarefa):
1. `templates/telecom/operator_lines.html`: nova coluna "Selo" na tabela (`<th>` após "Operadora", `<td>` no loop de `phone_lines`), reaproveitando `{% include "telecom/_seal_status_badge.html" with seal_status=line.seal_status %}` e `line.get_whatsapp_seal_display`/"Sem selo" — mesmo padrão server-side já usado em `overview.html`. Ajustar `colspan` da linha vazia de 4 para 5.
2. Nenhuma mudança em `telecom/views.py` — `whatsapp_seal`/`seal_status` já são atributos do objeto `PhoneLine` já carregado pelo queryset existente (`select_related("sim_card")` já cobre o necessário; `seal_status` é propriedade Python sem consulta adicional).
3. Nenhuma mudança em `telecom/models.py`, `whatsapp_seal.py`, migrations, formulários.

### Test Checklist (a derivar, não escritos nesta tarefa)

- Operador com linha Sem selo: célula mostra "Sem selo", sem indicador de vencimento.
- Operador com linha META ONE/META VERIFICADO: célula mostra nome do selo + indicador.
- Faixas de vencimento 8/7/1/0/-1 dias (relógio controlado): mesmas cores/textos já validados em `test_seal_detail_and_listing.py` (`seal-tone-neutral/warning/today/expired`), reaproveitando o partial `_seal_status_badge.html` — não deve exigir nova lógica de cor.
- Isolamento entre operadores: operador A não vê selo (nem e-mail) de linha vinculada só ao operador B — reforça `test_all_linked_lines_appear_in_response`/`OperatorLinkedLinesViewTests` com asserção adicional de ausência do e-mail/selo da linha de outro operador.
- Regressão: `test_all_linked_lines_appear_in_response`, `test_detail_links_present_for_each_line`, `test_phoneline_detail_back_link_points_to_operator_lines` continuam passando sem alteração de comportamento.

### Test Strategy

Mesma abordagem de SEL-08: Django test client real, reuso do partial `_seal_status_badge.html` e da propriedade `seal_status`, sem lógica nova de cor/data. Nenhuma execução nesta tarefa — apenas mapeamento; suíte não rodada porque nenhum arquivo de aplicação ou teste foi alterado.

### Compliance Report

**Conclusão: INCLUIR.** `operator_lines.html` é listagem ativa e testada de linhas telefônicas (`telecom/tests.py:5033-5143`), com a mesma base de permissão (`get_visible_phone_lines_queryset`/`PhoneLine.visible_to_user`) usada por `overview` e `phoneline_detail`. Não há decisão explícita do usuário nem restrição documentada que exclua OPERATOR do requisito "Alerta visual na listagem e no detalhe" — a exclusão anterior (`docs/superpowers/specs/2026-09-17-phone-line-whatsapp-seal-design.md:106`) foi interpretação deste agente baseada só na ausência de paginação/JSON, critério de implementação que não se aplica ao requisito em si. A ausência dessa coluna é, portanto, **lacuna de SEL-08**, não decisão de escopo válida. `phoneline_detail.html` já exibe o bloco completo do selo para OPERATOR (mesmo papel, mesma linha), reforçando a inconsistência: hoje o operador vê o selo no detalhe mas nada na sua própria listagem.

Não implementado nesta tarefa (fora dos limites definidos). Nenhuma mudança em código/testes/migrations. Nenhum acesso a banco operacional, commit, push ou deploy. SEL-08 segue sem marcação de concluída. Recomenda-se tratar a lacuna acima como parte do fechamento de SEL-08 (não como tarefa nova/backlog paralelo) antes de avançar a SEL-09.

## Correção da lacuna — selo e indicador em operator_lines.html — 2026-09-18

Escopo já definido na verificação anterior (INCLUIR); esta tarefa não reabre essa decisão, apenas implementa.

### Spec Summary

Fechar a lacuna registrada acima: coluna "Selo" na listagem do OPERATOR (`operator_lines.html`), reaproveitando `get_whatsapp_seal_display`, `seal_status` e o partial `_seal_status_badge.html` já usados em `overview.html`/`phoneline_detail.html`. Sem paginação/JSON nessa página (não se aplica).

### Gap Analysis

Confirmado nesta tarefa (sem mudança de conclusão): `templates/telecom/operator_lines.html` tinha 4 colunas (Número, Status, Operadora, Ação) sem nenhum dado de selo; `OperatorLinkedLinesView` (`telecom/views.py:904-916`) já carrega o objeto `PhoneLine` completo (`whatsapp_seal`, `seal_status` disponíveis sem consulta extra). `OperatorLinkedLinesViewTests` (`telecom/tests.py:5033+`) não tinha nenhum teste de selo.

### Implementation Plan — ações executadas

1. `telecom/tests.py`: import `date` adicionado a `from datetime import date, timedelta` (linha 2) e `render_to_string` importado (linha 7); 8 testes novos no fim de `OperatorLinkedLinesViewTests` — Sem selo, META ONE, META VERIFICADO, e-mail/pagamento ausentes da coluna, 5 casos de fronteira (8/7/1/0/-1 dias, `patch.object(timezone, "localdate", ...)`) com classes `seal-tone-*` distintas, isolamento entre operadores (linha exclusiva de outro operador não aparece, nem seu e-mail), e estado vazio via `render_to_string` direto no template (view real nunca atinge esse estado — `if not lines.exists(): raise PermissionDenied`, `telecom/views.py:914` — comportamento pré-existente, não alterado). Nenhum teste existente da classe alterado ou removido.
2. `templates/telecom/operator_lines.html`: nova coluna "Selo" entre "Operadora" e a coluna de ação (`<th>Selo</th>`; `<td>` com `{% if line.whatsapp_seal %}` mostrando `{{ line.get_whatsapp_seal_display }}` + `{% include "telecom/_seal_status_badge.html" with seal_status=line.seal_status %}`, senão `"Sem selo"` em `text-muted`); `colspan` do estado vazio ajustado de 4 para 5. Nenhuma mudança em `telecom/views.py`, `models.py`, `forms.py`, permissões ou migrations — `whatsapp_seal`/`seal_status` já eram atributos do objeto `PhoneLine` já carregado pela queryset existente.

Comandos e resultados:

```powershell
venv/Scripts/python.exe -m pytest telecom/tests.py -k OperatorLinkedLinesViewTests -q
```
RED antes da alteração do template: 9 failed (4 testes de conteúdo + 5 subtestes de fronteira), 10 passed (6 testes preexistentes + 2 novos que já passavam trivialmente — e-mail/pagamento nunca apareciam e isolamento entre operadores já valia, pois nenhuma linha exibia selo algum ainda).
GREEN após a alteração do template: **14 passed, 5 subtests passed**.

```powershell
venv/Scripts/python.exe -m pytest telecom/test_seal_detail_and_listing.py telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py -q
```
Resultado: **61 passed**. Nenhuma regressão nas suítes de SEL-08/SEL-07/SEL-06.

```powershell
venv/Scripts/python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
```
Resultado: **236 passed, 1 skipped** (229 do baseline anterior + 7 métodos de teste novos, 5 subtests inclusos), 158.42s. Nenhuma regressão.

```powershell
venv/Scripts/python.exe manage.py check
```
Resultado: `System check identified no issues (0 silenced)`.

Validação em navegador real — não executada nesta sessão (mesma limitação já registrada em SEL-07/SEL-08, não contornada):
- Nenhuma ferramenta de automação de navegador disponível nesta sessão. Não foi possível confirmar visualmente a listagem do OPERATOR com Sem selo/próximo do vencimento/vencendo hoje/vencido, nem legibilidade e rolagem da tabela em desktop/celular.
- Evidência disponível sem navegador: testes HTTP reais via Django test client (`self.client.get`), incluindo `assertContains`/`assertNotContains` sobre o HTML renderizado de fato (não `render_to_string` isolado, exceto no teste do estado vazio, que é inatingível pela view real).
- **Não declaro essa validação como concluída.**

### Test Checklist

- [x] Sem selo → "Sem selo", sem alerta.
- [x] META ONE e META VERIFICADO → nome do selo + indicador.
- [x] Fronteiras 8/7/1/0/-1 dias com classes `seal-tone-neutral/warning/warning/today/expired` distintas e singular em 1 dia.
- [x] E-mail e forma de pagamento não aparecem na coluna nova.
- [x] Isolamento entre operadores (linha e e-mail de outro operador não vazam).
- [x] Estado vazio com `colspan` correto (5).
- [x] Testes preexistentes de `OperatorLinkedLinesViewTests` preservados e passando.
- [ ] Validação visual em navegador real — pendente, ferramenta indisponível.

### Test Strategy

Mesma abordagem de SEL-08: Django test client real, `patch.object(timezone, "localdate", ...)` para controlar fronteiras, reuso de `_seal_status_badge.html`/`seal_status` sem lógica de cor nova no template. Regressão completa e `manage.py check` executados.

### Compliance Report

Lacuna de SEL-08 fechada para `operator_lines.html`: coluna "Selo" implementada com menor mudança possível (template + testes), sem tocar view/model/forms/migrations/permissões. 14 testes da classe de escopo do operador passam (8 novos + 6 preexistentes, 5 subtests), 61 testes das suítes de SEL-06/07/08 passam, 236 testes de regressão completa passam (1 pulado, mesmo baseline), `manage.py check` limpo. Nenhum commit, push, deploy ou acesso a banco operacional. Nenhum backlog paralelo criado — lacuna tratada dentro da própria SEL-08.

**Status SEL-08 após esta correção: implementação funcional completa nas três superfícies (detalhe, overview/Carregar mais, listagem OPERATOR) e testada; aceite final segue pendente até validação visual em navegador real nas três superfícies — ferramenta indisponível em todas as sessões desta tarefa até agora.** Checkbox de SEL-08 mantida aberta. Próxima tarefa após aceite visual: SEL-09.

## Tentativa de validação final de SEL-08 — 2026-09-18 (bloqueada)

Tarefa solicitada: aceite visual em navegador real das três superfícies (detalhe, overview/Carregar mais, listagem OPERATOR), conforme pendência registrada acima. Sem alteração de código/implementação — instrução explícita de não refazer funcionalidade.

### Spec Summary

Mesmo escopo de aceite pendente desde a seção anterior: cores/contraste dos indicadores, responsividade real, "Carregar mais" executado de fato no navegador, ausência de overflow horizontal e de erros de console/rede.

### Ambiente

Nenhum ambiente de QA foi criado nesta sessão (nenhum usuário sintético, nenhuma linha sintética, nenhum servidor local iniciado) — ver Gap Analysis abaixo sobre o motivo.

### Gap Analysis — bloqueio concreto

Verificado no início desta sessão: nenhuma ferramenta de automação de navegador (Chrome DevTools MCP ou equivalente) está disponível — busca pelo tool correspondente não retornou nenhum servidor MCP de navegador/DevTools carregado nesta sessão, apenas `WebFetch` (não serve para inspecionar `localhost`, JavaScript ao vivo, estilo computado nem screenshot). Mesma limitação já registrada em todas as sessões anteriores desta tarefa (SEL-07 antes da revalidação, SEL-08 original, correção de `operator_lines.html`).

Como o bloqueio é a ausência da própria ferramenta de navegador — não um problema de ambiente/dados que a preparação resolveria —, montar banco isolado, usuários ADMIN/OPERATOR e linhas sintéticas nesta sessão não teria como gerar evidência visual nova; seguindo o limite explícito da tarefa ("não substituir por HTTP/HTML nem declarar aceite visual"), a preparação foi omitida para não produzir trabalho sem prova de aceite correspondente.

### Implementation Plan — conferências executadas

Reexecutada apenas a bateria de testes automatizados focada, para confirmar que as evidências funcionais/servidor já registradas continuam válidas (nenhuma mudança de código desde a última rodada, confirmado por `git status` — mesmo conjunto de arquivos modificados/não rastreados da sessão anterior):

```powershell
venv/Scripts/python.exe -m pytest telecom/test_seal_detail_and_listing.py telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py -q
```
Resultado: **61 passed**, 2 warnings (mesmos avisos de depreciação pré-existentes de `CheckConstraint`).

```powershell
venv/Scripts/python.exe -m pytest telecom/tests.py -k OperatorLinkedLinesViewTests -q
```
Resultado: **14 passed**, 201 deselected, 2 warnings, 5 subtests passed.

```powershell
venv/Scripts/python.exe manage.py check
```
Resultado: `System check identified no issues (0 silenced)`.

Regressão completa (`telecom/tests.py` + `telecom/tests_line_timeline.py`, 236 passed / 1 skipped) não reexecutada nesta sessão — sem mudança de código nem suspeita concreta desde a última execução registrada (seção anterior, mesma data-base), conforme instrução explícita de não repetir sem necessidade.

### Test Checklist

- [x] `telecom/test_seal_detail_and_listing.py` — incluído nos 61 passed acima.
- [x] `telecom/test_whatsapp_seal.py` — incluído nos 61 passed acima.
- [x] `telecom/test_phoneline_form_ui.py` — incluído nos 61 passed acima.
- [x] `telecom/tests.py::OperatorLinkedLinesViewTests` — 14 passed, 5 subtests passed.
- [x] `manage.py check` — limpo.
- [ ] Aceite visual em navegador real (detalhe, overview/Carregar mais, operator_lines) — **bloqueado nesta sessão**, ferramenta indisponível.

### Test Strategy

Mesma estratégia já documentada nas seções anteriores (Django test client real + `patch.object(timezone, "localdate", ...)` + `CaptureQueriesContext`); nenhuma estratégia nova necessária, pois nenhuma implementação foi alterada. Validação visual continua dependente de ferramenta de automação de navegador indisponível nesta sessão.

### Compliance Report

**Bloqueado.** Nenhum código, teste, migration ou template alterado nesta sessão. Evidências funcionais/servidor reconfirmadas (61 + 14 testes focados passam, `manage.py check` limpo) — nenhuma regressão detectada desde a última rodada completa (236 passed, 1 skipped, não reexecutada por ausência de mudança). Aceite visual em navegador real permanece pendente pelo mesmo motivo já registrado em todas as sessões anteriores desta tarefa: nenhuma ferramenta de automação de navegador disponível neste ambiente. Nenhum ambiente de QA sintético foi criado nesta sessão (nada a encerrar). Nenhum acesso a banco operacional, commit, push, deploy ou avanço para SEL-09.

**Status SEL-08: segue aberta.** Critério de aceite visual não atendido por indisponibilidade concreta de ferramenta, não por decisão de escopo. Próximo passo inalterado: aceite visual em navegador real (Chrome DevTools MCP ou equivalente, ou validação manual pelo usuário) nas três superfícies antes de marcar SEL-08 concluída e avançar a SEL-09.

## Conferência real de SEL-08 — 2026-09-18

### Spec Summary / ambiente

Navegador Chromium do Codex, servidor local 127.0.0.1:8766, SQLite exclusivo no diretório temporário lineops-sel08-browser-qa. Criadas 18 linhas sintéticas com vencimentos relativos à data local 18/09/2026: Sem selo, +8, +7, +1, hoje e -1, repetidos para cobrir primeira carga e paginação. ADMIN e dois OPERATOR sintéticos; operador A com quatro linhas, B com duas, via AllocationService. Nenhum acesso ao banco operacional. Reconexão externa desabilitada somente no ambiente QA.

### Test Checklist — resultados reais

- PASS: overview inicial apresenta 10 linhas; clique Carregar mais adiciona 8, total 18. Novas linhas mantêm nomes, textos e cores equivalentes à carga inicial. Sem erro JS observado nos logs capturados.
- PASS: faixas textuais corretas: Vence em 26/09/2026, Vence em 7 dias, Vence em 1 dia, Vence hoje e Vencido há 1 dia. Sem selo não apresenta badge de vencimento.
- PASS: filtro por número retorna somente linha solicitada, preservando selo/indicador.
- PASS: detalhe inspecionado para Sem selo, META VERIFICADO vencendo hoje e META ONE vencido. Datas, e-mail sintético e pagamento coerentes. Detalhe móvel sem overflow (375px de área útil e scrollWidth=375).
- PASS: OPERATOR A vê exatamente suas quatro linhas (Sem selo, +7, hoje, -1), não as duas de B. Acesso direto ao detalhe de B retornou página de não encontrado, confirmado no log HTTP como 404; nenhum dado do selo de B exposto.
- PASS: listagens não exibem e-mail/pagamento. Conferência adicional do JSON main via Django Client no mesmo SQLite: HTTP 200, 8 linhas em offset=10, somente whatsapp_seal_display e seal_status como novos campos; sem whatsapp_seal_email/whatsapp_seal_payment.
- PASS: desktop OPERATOR apresenta coluna Selo e ações acessíveis; overview e detalhe conferidos visualmente.

### Gap Analysis — achados que impedem encerramento

1. **Contraste insuficiente de Vence hoje.** Nas três superfícies e no Carregar mais, estilo computado é fundo rgb(255,165,0) e texto rgb(255,255,255). Relação de luminância calculada: **1,97:1**, texto pequeno (10,32px na tabela e 12px no detalhe). Causa compartilhada: `_seal_status_badge.html` usa orange/#fff; `createSealBadge` em overview.html repete combinação. Manter laranja aprovado, corrigir cor de texto/combinação para leitura adequada em ambos os caminhos.
2. **Overflow horizontal da página OPERATOR no celular.** Viewport 390x844, área útil 375px, document.scrollWidth=507px. content-stage/card/table-responsive expandem para aproximadamente 480px; tabela com ~478px. Wrapper não restringe largura, então conteúdo/ações ficam fora da tela e rolagem ocorre na página, não apenas na tabela. Reproduzido por screenshot e geometria DOM em `/telecom/minhas-linhas/`. Investigar contenção/min-width do layout e aplicar menor ajuste, preservando rolagem interna da tabela.

Observação adicional: overview móvel teve scrollWidth=385 contra clientWidth=375. Elementos do grid de contadores ultrapassam borda útil (right≈379,6px); tabela do overview tem overflow interno correto (324px visíveis / 805px de conteúdo). Não comprovado se esse pequeno overflow é regressão do selo ou preexistente; comparar antes de atribuir causa e não misturar com defeito confirmado de OPERATOR.

### Implementation Plan

Nenhuma correção de aplicação realizada nesta tarefa de conferência. Derivar testes/reprodução para contraste e contenção móvel; corrigir dentro da SEL-08, não criar backlog paralelo. Repetir detalhe/overview/Carregar mais/OPERATOR após correção. SEL-08 continua aberta por defeitos observados, não por indisponibilidade de navegador.

### Test Strategy / evidência automatizada

`venv/Scripts/python.exe -m pytest telecom/test_seal_detail_and_listing.py telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/tests.py::OperatorLinkedLinesViewTests -q`

Resultado: **75 passed, 5 subtests passed, 3 warnings in 27.76s**. Avisos conhecidos: duas depreciações CheckConstraint e permissão de cache pytest. `manage.py check`: System check identified no issues (0 silenced). Não repetida regressão completa sem alteração de código.

### Compliance Report

Inspeção de código, navegador real, estilos computados, screenshots, paginação e isolamento confirmados nos cenários acima. Aceite visual reprovado pelos dois achados. Fonte da verdade atualizada; código de aplicação/testes/migrations intactos. Servidor encerrado, aba fechada e viewport restaurado. Um SQLite vazio de QA criado inadvertidamente na raiz durante checagem auxiliar foi identificado e removido; banco operacional não acessado. Sem commit, push ou deploy.

## Correção dos achados visuais de SEL-08 — 2026-09-21

Tarefa: corrigir os dois achados confirmados na "Conferência real de SEL-08 — 2026-09-18" (contraste de Vence hoje e overflow móvel de OPERATOR) e registrar evidência do pequeno overflow do overview, sem avançar para SEL-09. Nenhuma ferramenta de automação de navegador disponível nesta sessão (mesma ausência de todas as sessões anteriores desta tarefa) — ver Limitações. Correções aplicadas com base em evidência de código (diff, CSS computável manualmente, comparação estrutural com o caminho que já passou na conferência anterior), não em observação visual direta nesta sessão.

### Spec Summary

Fonte: seção "Conferência real de SEL-08 — 2026-09-18" desta mesma spec. Três frentes: (1) contraste do indicador "Vence hoje" abaixo de 4,5:1 em texto pequeno nas três superfícies; (2) overflow horizontal de página em `operator_lines.html` no celular (scrollWidth 507 contra clientWidth 375); (3) pequeno overflow do overview (scrollWidth 385 contra clientWidth 375), origem a confirmar antes de decidir se corrige.

### Gap Analysis

**1. Contraste "Vence hoje".** Causa: `_seal_status_badge.html` e `createSealBadge` em `overview.html` aplicavam texto branco (`#fff`/`color: #fff`) sobre fundo laranja literal (`orange` = rgb(255,165,0)). Cálculo de luminância relativa (fórmula WCAG, sRGB linearizado): L(laranja) ≈ 0,4815; L(branco) = 1. Contraste = (1+0,05)/(0,4815+0,05) ≈ **1,976:1** — bate com o 1,97:1 medido na conferência anterior, confirmando a fórmula. Com texto escuro (`#212529`, mesmo tom usado por `text-dark` do Bootstrap, já reaproveitado no tone `warning` amarelo desta mesma badge): L(#212529) ≈ 0,01814; contraste = (0,4815+0,05)/(0,01814+0,05) ≈ **7,80:1** — acima do mínimo de 4,5:1 exigido para texto pequeno, com folga.

**2. Overflow móvel de OPERATOR.** Comparação estrutural confirmou a causa, sem precisar de navegador: `overview.html` (que passou com scrollWidth=clientWidth=375 na conferência de 18/09) envolve sua tabela em `<div class="table-responsive telecom-table-wrap">`; `operator_lines.html` (que falhou, scrollWidth=507) usava apenas `<div class="table-responsive">`, sem a classe `telecom-table-wrap`. `telecom-table-wrap` (`static/css/styles.css:804-807`) define `width: 100%; overflow-x: auto;`. Sem `width: 100%` explícito, o contêiner de overflow fica sujeito ao comportamento padrão de itens de grid/flex (`.app-shell` é grid, `.content-stage` é flex — `templates/base/base.html`/`static/css/styles.css:48-52,183-187`): por padrão, `min-width` de um item de grid/flex é `auto`, ou seja, o item não encolhe abaixo do conteúdo mínimo dos descendentes. Como a tabela tem colunas suficientes para exceder 375px, essa cadeia de ancestrais crescia para acomodar o conteúdo em vez de deixar a rolagem ocorrer dentro do próprio `table-responsive`, expandindo a página inteira. `width: 100%` força o contêiner a respeitar a largura do pai independentemente do conteúdo, permitindo que `overflow-x: auto` role internamente — mesmo mecanismo que já fazia `overview.html` passar.

**3. Pequeno overflow do overview (385 contra 375).** `git diff main -- templates/telecom/overview.html` confirma que o grid de contadores (`.row.g-3`, blocos `line_status_boxes`) não foi tocado por nenhuma alteração desta feature — o diff da branch contra `main` só adiciona a coluna "Selo" na tabela e as funções JS `createSealBadge`/`createSealCell`. **Não é regressão de SEL-08**; é overflow pré-existente, plausivelmente causado pelas margens negativas do `.row` do Bootstrap (`g-3`) sem um `.container`/padding compensador em `.telecom-content-shell`. Registrado aqui conforme instrução; correção fora do escopo desta tarefa.

### Implementation Plan — ações executadas

1. `templates/telecom/_seal_status_badge.html`: tone `today` passa de `style="background-color: orange; color: #fff;"` para `class="badge seal-tone-today text-dark" style="background-color: orange;"` — reaproveita a classe `text-dark` do Bootstrap (já usada no tone `warning` desta mesma badge), mantém o fundo laranja aprovado, `seal-tone-today` preservada (usada pelos testes existentes).
2. `templates/telecom/overview.html`, função `createSealBadge` (JS do "Carregar mais"): mesma troca — `badge.classList.add('seal-tone-today', 'text-dark')` no lugar de `badge.style.color = '#fff'`; `badge.style.backgroundColor = 'orange'` mantido.
3. `templates/telecom/operator_lines.html`: `<div class="table-responsive">` passa a `<div class="table-responsive telecom-table-wrap">` — reaproveita classe já existente em `static/css/styles.css`, usada por `overview.html`, sem criar CSS novo nem `overflow-x: hidden` global. Nenhuma mudança em `telecom/views.py`, `models.py`, `forms.py`, migrations ou payload JSON.
4. Nenhuma alteração aplicada para o item 3 (overflow do overview) — investigação registrada acima, sem ampliar correção sem evidência de causa em SEL-08.
5. Nenhum teste novo criado para contraste/overflow: os testes existentes (`test_seal_detail_and_listing.py`, `tests.py::OperatorLinkedLinesViewTests`) já cobrem as classes `seal-tone-*`/`seal-tone-today` por comportamento (faixas de dias, tom), não por cor; não recalculam vencimento no JavaScript nem foram enfraquecidos. Criar um teste que apenas procure a classe `telecom-table-wrap` ou `text-dark` não comprovaria contraste nem ausência de overflow — por isso não foi feito, conforme limite explícito da tarefa; a prova de contraste está no cálculo acima (reproduzível/documentado) e a prova de overflow depende de aceite visual em navegador real (pendente, ver Limitações).

### Test Checklist

- [x] Cálculo de contraste "Vence hoje" (laranja + texto escuro) ≥ 4,5:1 — 7,80:1 calculado, ver Gap Analysis.
- [x] Distinção mantida entre amarelo (`bg-warning text-dark`, 7 a 1 dias), laranja (`background-color: orange` + `text-dark`, hoje) e vermelho (`bg-danger`, após vencer) — cores/tons distintos, nenhuma classe removida.
- [x] Consistência aplicada nas três superfícies: `_seal_status_badge.html` (reaproveitado por Detalhe, Overview carga inicial e OPERATOR) e `createSealBadge` (Overview "Carregar mais").
- [x] `operator_lines.html` reaproveita `telecom-table-wrap`, mesma classe que já mantinha `overview.html` sem overflow de página; ações e nome do selo continuam nas mesmas células, sem remoção de conteúdo.
- [x] Overflow do overview investigado e atribuído a causa pré-existente e independente por evidência de diff, não corrigido nesta tarefa.
- [x] Suíte alvo: `telecom/test_seal_detail_and_listing.py telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/tests.py::OperatorLinkedLinesViewTests` — 75 passed, 5 subtests passed.
- [x] `telecom/tests.py telecom/tests_line_timeline.py` (regressão ampliada por a correção tocar template/classe compartilhada) — 236 passed, 1 skipped, mesmo baseline da última rodada registrada.
- [x] `manage.py check` — limpo.
- [ ] Aceite visual em navegador real (contraste com cores computadas, viewport 390px, ausência de overflow horizontal em OPERATOR, aparência consistente nas quatro superfícies) — **não executado nesta sessão**, ferramenta indisponível.

### Test Strategy

Correção mínima orientada por evidência de código: fórmula de contraste WCAG aplicada manualmente às cores RGB envolvidas (reproduz o 1,97:1 já medido em navegador real na conferência anterior, confirmando a fórmula antes de usá-la para validar a correção); comparação estrutural entre `overview.html` (já aprovado) e `operator_lines.html` (reprovado) para isolar a classe CSS que faz a diferença, em vez de tentar novas hipóteses de layout sem prova. `git diff main` para separar código tocado por esta feature de código pré-existente no achado 3. Suíte automatizada existente (comportamento/classe) mais regressão completa executadas; nenhum teste novo criado para "provar" contraste ou responsividade via seletor de classe, conforme limite explícito da tarefa.

Comandos e resultados:

```powershell
venv/Scripts/python.exe -m pytest telecom/test_seal_detail_and_listing.py telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/tests.py::OperatorLinkedLinesViewTests -q
```
Resultado: **75 passed, 5 subtests passed, 2 warnings in 28.73s**. Avisos conhecidos (depreciação `CheckConstraint`).

```powershell
venv/Scripts/python.exe manage.py check
```
Resultado: `System check identified no issues (0 silenced)`.

```powershell
venv/Scripts/python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
```
Resultado: **236 passed, 1 skipped, 2 warnings, 5 subtests passed in 174.44s**. Mesmo baseline da correção anterior de `operator_lines.html` (2026-09-18) — nenhuma regressão.

### Compliance Report

Dois achados confirmados da "Conferência real de SEL-08 — 2026-09-18" corrigidos com a menor mudança necessária: troca de cor de texto (reaproveitando `text-dark` já usado no tone `warning`) para o contraste, e reaproveito de uma classe CSS já existente e já comprovada (`telecom-table-wrap`) para o overflow — nenhum CSS novo, nenhum `overflow-x: hidden` global, nenhuma mudança de domínio/model/forms/migrations/permissões/contrato JSON. Terceiro ponto (overflow do overview) investigado e registrado como pré-existente e independente por evidência de diff (`git diff main -- templates/telecom/overview.html`), não ampliado para correção nesta tarefa, conforme instrução explícita. Suíte alvo (75 passed) e regressão completa (236 passed, 1 skipped) sem quebras; `manage.py check` limpo.

**Limitação — aceite visual não executado nesta sessão (mesma ausência de ferramenta de todas as sessões anteriores desta tarefa):** nenhuma ferramenta de automação de navegador (Chrome DevTools MCP ou equivalente) está disponível. As correções acima são fundamentadas em cálculo de contraste reproduzível e em comparação estrutural de código com um caminho que já passou em conferência real anterior (`overview.html`), não em observação visual direta nesta sessão. **Não declaro o aceite visual como concluído.** Falta confirmar em navegador real: cores computadas (`getComputedStyle`) do texto/fundo de "Vence hoje" nas quatro superfícies, ausência de overflow horizontal de `operator_lines.html` em 390px com rolagem interna funcional, e ausência de qualquer regressão visual introduzida pela classe `telecom-table-wrap` (ex.: espaçamento, alinhamento das ações).

**Status SEL-08: segue aberta.** Correções de código aplicadas e testadas; aceite visual permanece pendente por indisponibilidade concreta de ferramenta de navegador, não por decisão de escopo. Overflow do overview permanece como achado pré-existente registrado, não corrigido, não bloqueante para SEL-08 (fora do escopo desta feature). Próximo passo inalterado: aceite visual em navegador real (ferramenta disponível ou validação manual pelo usuário) nas quatro superfícies antes de marcar SEL-08 concluída e avançar a SEL-09 — **SEL-09 não iniciada nesta tarefa**, conforme instrução explícita. Nenhum commit, push, deploy ou acesso a banco operacional.

## Revalidação visual real de SEL-08 — 2026-09-21

### Spec Summary
Revalidar contraste e contenção móvel com fundo azul-escuro aprovado. Conferência executada via navegador real CUA, aplicação local e SQLite sintético isolado em TEMP/lineops-sel08-browser-qa. Nenhum acesso a PRD.

### Gap Analysis
- **Contraste aprovado:** body computado rgb(2,6,23), fundo do badge rgb(255,165,0), texto rgb(33,37,41). Contraste calculado dessas cores observadas: **7,8116:1**. Confirmado no detalhe, overview inicial, novas linhas de Carregar mais e OPERATOR. Cores amarelo/laranja/vermelho preservadas.
- **OPERATOR reprovado:** viewport efetivo innerWidth=390, devicePixelRatio=1, document.clientWidth=375, scrollWidth=507. `.content-stage` continua com min-width:auto e largura 479,796875px; card e card-body acompanham essa largura. `.table-responsive.telecom-table-wrap` tem clientWidth=478 e scrollWidth=478: não há excedente interno para rolar, pois o conjunto expande a página. Screenshot confirma selo/ação fora da tela. A explicação anterior de que width:100% resolveria a contenção foi refutada pelo navegador; a classe sozinha não resolve a cadeia de dimensionamento dos ancestrais.
- **Overview comparado:** atual e template extraído de main renderizados com mesmo CSS/base, backend, dados e viewport. Ambos clientWidth=375, scrollWidth=385; `.row.g-3` right=379,59375px, width=374px. Wrapper da tabela clientWidth=324; conteúdo atual=859 e baseline=714, ambos contidos internamente. CSS/base sem diff contra main. A retirada da coluna Selo não elimina os 10px extras. Evidência agora por comparação renderizada, não apenas ausência de diff nos contadores. Causa CSS específica não foi corrigida nesta conferência.

### Implementation Plan — executado
Somente inspeção e atualização desta fonte da verdade. Nenhum código de aplicação alterado. QA principal em 8766 e baseline do template em 8767, usando somente banco sintético. Datas das fixtures atualizadas para 21/09/2026. Zoom normalizado e medidas finais feitas em innerWidth=390/devicePixelRatio=1; medições transitórias durante ajuste de zoom descartadas.

### Test Checklist
- [x] Fundo azul-escuro observado; contraste de Vence hoje nas quatro renderizações aprovado.
- [x] Carregar mais real: 10 para 18 linhas, novos badges com as mesmas cores.
- [x] Sem selo e faixas +8/+7/+1/0/-1 renderizadas corretamente.
- [x] OPERATOR desktop: clientWidth=scrollWidth=1280, ações visíveis.
- [x] Detalhe móvel: clientWidth=scrollWidth=375.
- [x] Comparação overview atual/main nas mesmas condições.
- [x] Console consultado: nenhum erro/warning capturado.
- [ ] OPERATOR móvel sem overflow de página: **falhou**, 507/375.

### Test Strategy
Screenshot, DOM, estilos computados, dimensões reais e interação no navegador. Suítes automatizadas não repetidas: código inalterado nesta conferência; resultados anteriores permanecem evidência da execução anterior, não desta. Comparação baseline limitada ao template overview, mantendo CSS/base iguais a main e o mesmo backend atual.

### Compliance Report
**SEL-08 permanece aberta por overflow OPERATOR reproduzido.** Contraste resolvido; próximo passo corrigir contenção dos ancestrais com reprodução móvel antes/depois e revalidar ações/rolagem. Não avançar SEL-09. Nenhum commit/push/deploy/migration em banco operacional. Servidores locais encerrados ao concluir a conferência; arquivos temporários sintéticos mantidos para reprodução.

## Correção da contenção móvel de OPERATOR e revalidação real de SEL-08 — 2026-09-21

### Spec Summary

Corrigir a contenção móvel de `operator_lines.html` (achado da "Revalidação visual real de SEL-08 — 2026-09-21") e repetir o aceite em navegador real, sem avançar para SEL-09. A tentativa anterior registrada nesta fonte da verdade (2026-09-21, seção "Correção dos achados visuais de SEL-08") — adicionar `telecom-table-wrap` a `operator_lines.html` — havia sido refutada por medição real na revalidação seguinte; esta tarefa não repetiu essa conclusão sem medir de novo.

**Ferramenta de navegador usada:** nenhum MCP de browser/DevTools está instalado nesta sessão (confirmado via busca de ferramentas). Encontrado localmente: Node.js (`C:\Program Files\nodejs`) com `playwright@1.63.0` instalado globalmente via npm e Chromium já baixado em `%LOCALAPPDATA%\ms-playwright\chromium-1217`. Usado via scripts Node no diretório de scratchpad para abrir um Chromium real, autenticar, navegar, medir `getComputedStyle`/`getBoundingClientRect`, injetar CSS candidato ao vivo, interagir (scroll, clique) e capturar screenshots — navegador real, não inspeção estática de CSS nem apenas test client.

### Gap Analysis

**Causa confirmada por medição ao vivo (antes de qualquer alteração):** `.app-shell` é CSS Grid (`74px 1fr`, `static/css/styles.css:48-52`); `.app-main` (`templates/base/base.html:91`, `display:flex; flex-direction:column`, `styles.css:130-135`) é o item de grid na trilha `1fr`. Item de grid tem `min-width:auto` por padrão — não encolhe abaixo do conteúdo mínimo dos descendentes. Testado ao vivo com CSS injetado: `min-width:0` isolado em `.content-stage` ou em `.content-stage > .card` **não** resolveu (mesma largura 479px, mesmo overflow 506); `min-width:0` em `.app-main` sozinho resolveu completamente. Isso confirma que o ponto real de bloqueio é o item de grid `.app-main`, não os itens flex aninhados — a hipótese anterior ("width:100% em telecom-table-wrap resolveria") estava errada porque o gargalo está uma camada acima, no grid, não no wrapper da tabela.

`overview.html` nunca sofreu esse sintoma porque seu bloco de conteúdo já está envolto em `<div class="telecom-content-shell">` (`overview.html:6`), que define `max-width: calc(100vw - 140px)` (`calc(100vw - 2rem)` abaixo de 992px) em `styles.css:752-756,809-817` — um `max-width` explícito satisfaz o algoritmo de dimensionamento do item de grid independente do conteúdo, diferente de `min-width:auto`. `operator_lines.html` não tinha nenhum wrapper equivalente.

**Decisão de correção:** testado ao vivo e confirmado que envolver o conteúdo de `operator_lines.html` na mesma classe `telecom-content-shell` (sem tocar `.app-main`/`.content-stage`/`static/css/styles.css`) resolve igualmente em 390px, 360px e 1280px. Escolhida essa opção — localizada, um único template, reaproveita classe já existente e já aprovada em produção via `overview.html` — em vez de `min-width:0` em `.app-main` (que funcionaria mas alteraria CSS compartilhado por todas as páginas da aplicação, exigindo verificação de superfícies muito além do escopo desta tarefa).

**Achado operacional à parte:** durante a reprodução, dois processos `python manage.py runserver` ficaram simultaneamente vinculados à porta 8770 (um anterior não finalizado por `pkill` do bash, que não sinaliza processos nativos do Windows) — isso mascarou a primeira leitura pós-correção (servia HTML antigo em cache de processo). Identificado via `netstat -ano`/`tasklist`, corrigido com `taskkill /F /PID`, sem relação com o código da aplicação.

### Implementation Plan — executado

1. `templates/telecom/operator_lines.html`: bloco de conteúdo (`{% block content %}`) envolto em `<div class="telecom-content-shell">...</div>` — mesma classe de `overview.html`, sem CSS novo. Mantido `telecom-table-wrap` no `table-responsive` interno (adicionado na correção anterior; não removido, permanece correto). Nenhuma mudança em `static/css/styles.css`, `telecom/views.py`, `models.py`, `forms.py`, migrations, permissões ou payload JSON.
2. Ambiente de reprodução: `docker compose up -d db` (container `lineops-db`, porta 5433, volume dev local `lineops_postgres_data` — não é o banco operacional); `manage.py runserver 127.0.0.1:8770` com `DEBUG=True` explícito; dados sintéticos criados via script standalone (admin, operador `operator.sel08qa@test.local`, 4 linhas alocadas via `AllocationService` cobrindo Sem selo, `+1 dia` aviso, `hoje` laranja, `-1 dia` vencido — datas relativas a `timezone.localdate()` real da sessão, 21/09/2026).
3. Medição real via Playwright/Chromium: reprodução do defeito confirmada antes da correção (390px: `docClientWidth=390`, `docScrollWidth=506`; `.content-stage`/`.card` presos em 479px independente da viewport, inclusive em 360px); candidatos de correção testados ao vivo por injeção de CSS antes de editar arquivo; correção final aplicada no template real (não injeção) e revalidada por reload real da página (sem cache de navegador/servidor) após eliminar os processos duplicados.
4. Dados sintéticos e container removidos ao final; servidor de QA encerrado.

### Test Checklist — navegador real

| Verificação | Antes | Depois |
| --- | --- | --- |
| 390px: `documentElement.clientWidth` / `scrollWidth` | 390 / 506 | **390 / 390** |
| 360px: idem | 360 / 506 | **360 / 360** |
| 1280px (desktop): idem | 1280 / 1280 (já ok) | 1280 / 1280 (mantido) |
| `.telecom-content-shell`/`.card` em 390px | n/a (não existia) | clientWidth=scrollWidth=358 |
| `.table-responsive` em 390px | clientWidth=scrollWidth=477 (sem excedente interno) | clientWidth=356, scrollWidth=477 (excedente interno de 121px disponível) |

- [x] Rolagem interna funcional: `scrollLeft` do `.table-responsive` movido de 0 para 121 (máximo possível) via interação real, sem mover a página.
- [x] Ações acessíveis após rolar: clique real em "Acessar" (4 links encontrados) navegou para `/telecom/phonelines/14/#reconnect-whatsapp`; página de detalhe carregada contém o bloco do selo.
- [x] Sem selo, META ONE, META VERIFICADO e indicadores (amarelo/laranja/vermelho) legíveis — confirmado por screenshot real em 390px e 1280px.
- [x] Desktop 1280px preservado, sem scroll horizontal desnecessário (tabela cabe inteira, `tableWrap` clientWidth=scrollWidth=1138/1140).
- [x] Contraste de "Vence hoje" não alterado: computado nesta sessão em `operator_lines.html` real, `background-color: rgb(255, 165, 0)`, `color: rgb(33, 37, 41)` — mesmas cores da correção anterior (7,81:1), nenhuma edição em `_seal_status_badge.html`/`overview.html` nesta tarefa.
- [x] Console/rede: nenhum erro ou requisição falhada capturados durante toda a sessão real (login, listagem, scroll, navegação ao detalhe).
- [x] Overview verificado por CSS compartilhado não ter sido tocado (`telecom-content-shell` reaproveitada, não modificada) — 390px e 1280px sem overflow nesta sessão (`docClientWidth == docScrollWidth` em ambos); o pequeno overflow de 10px registrado na conferência de 18/09 e na revalidação de 21/09 permanece um achado pré-existente e independente, fora do escopo desta correção — não piorado (não observado nesta sessão; possível variação de sub-pixel entre ferramentas de medição, não investigada por estar fora do escopo).
- [ ] Estado vazio de OPERATOR em navegador real: **não alcançável via navegador** — `OperatorLinkedLinesView.get()` levanta `PermissionDenied` quando o operador não tem linha vinculada (`telecom/views.py:914`, comportamento pré-existente, não alterado), portanto nunca renderiza a tabela vazia para um usuário real. Coberto apenas por teste automatizado via `render_to_string` (já existente, inalterado — `OperatorLinkedLinesViewTests`), mesma limitação estrutural já registrada nas conferências anteriores desta spec.

### Test Strategy

Reprodução antes/depois com dimensões reais, interação real (scroll, clique, navegação) e captura de console/rede em Chromium real (Node.js + `playwright` global + Chromium já baixado localmente), não apenas leitura estática de CSS ou Django test client. Candidatos de correção testados por injeção de CSS ao vivo antes de editar o template, para isolar exatamente qual seletor resolve, conforme instrução de não aplicar receita sem verificar. Suíte automatizada e regressão completa executadas após a edição real do arquivo.

Comandos e resultados:

```powershell
venv\Scripts\python.exe -m pytest telecom/test_seal_detail_and_listing.py telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/tests.py::OperatorLinkedLinesViewTests -q
```
Resultado: **75 passed, 5 subtests passed, 2 warnings in 32.42s**.

```powershell
venv\Scripts\python.exe manage.py check
```
Resultado: `System check identified no issues (0 silenced)`.

```powershell
venv\Scripts\python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
```
Resultado: **236 passed, 1 skipped, 2 warnings, 5 subtests passed in 162.22s** — mesmo baseline, sem regressão (ampliado por a correção reaproveitar uma classe CSS compartilhada, ainda que sem editar `styles.css`).

Nenhum teste novo criado para "provar" contenção via seletor de classe — a evidência é a tabela de dimensões antes/depois acima, medida em navegador real, mais a interação de rolagem/clique real.

### Compliance Report

Causa real confirmada por medição ao vivo (item de CSS Grid `.app-main` com `min-width:auto`, não os wrappers flex aninhados nem o `table-responsive` em si) antes de qualquer edição de arquivo — a hipótese anterior foi corretamente descartada por não resolver quando testada isoladamente. Correção aplicada é a menor mudança localizada possível: um único template, uma classe já existente e já validada em produção (`overview.html`), nenhum CSS novo, nenhuma mudança em `.app-main`/`.content-stage` que afetaria todas as páginas da aplicação. Nenhuma mudança de domínio, models, forms, migrations, permissões ou contrato JSON. Nenhum teste enfraquecido; suíte alvo (75 passed) e regressão completa (236 passed, 1 skipped) sem quebras; `manage.py check` limpo.

Aceite móvel comprovado em navegador real (Chromium via Playwright local): dimensões antes/depois, rolagem interna funcional por interação real, navegação real ao detalhe autorizado, cores/contraste preservados e verificados computacionalmente, sem erros novos de console/rede. Desktop, estado vazio (via teste automatizado, inalcançável em navegador por regra de negócio pré-existente) e fundo azul-escuro aprovado preservados. Overview conferido por a correção reaproveitar uma classe CSS compartilhada; nenhuma piora observada nesta sessão.

**Status SEL-08: CONCLUÍDA.** Três achados da "Conferência real de SEL-08 — 2026-09-18" (contraste, overflow móvel de OPERATOR) resolvidos e revalidados em navegador real nesta e na sessão anterior; overflow residual do overview permanece registrado como achado pré-existente e independente, não bloqueante para esta feature. Container de banco isolado (`lineops-db`) e servidor de QA (porta 8770) encerrados; dados sintéticos desta tarefa removidos do banco isolado ao final. Nenhum commit, push, deploy ou acesso a banco operacional. **SEL-09 não iniciada nesta tarefa** — próximo passo, a critério do usuário.

## SEL-09 — completar cobertura e comprovar GREEN — 2026-09-21

SEL-08 já concluída (aceite móvel comprovado em navegador real, seção anterior). Esta tarefa não reabre nenhuma decisão aprovada em SEL-01 a SEL-08 e não avança para SEL-10/11.

### Spec Summary

Objetivo desta tarefa: mapear cada requisito aprovado da spec para o teste existente que o cobre, identificar lacunas reais (não cosméticas), fechar só as lacunas confirmadas com o menor conjunto de testes novos, e comprovar GREEN da suíte consolidada + `manage.py check` + `makemigrations --check --dry-run`, com o drift pré-existente reportado separadamente (nunca descrito como "limpo").

Ambiente confirmado antes da execução: branch `feat/phone-line-whatsapp-seal`; `git status` preservado (nenhum arquivo desta sessão sobrescrito, alterações anteriores — inclusive `docs/specs/`, `.superpowers/` não versionados — intactas); `venv\Scripts\python.exe` usado em todos os comandos; banco de teste isolado reconfirmado por leitura de `config/settings.py` — com `pytest` em `sys.modules`, `DATABASES["default"]` é substituído por SQLite dedicado (`test_db.sqlite3`), Postgres operacional nunca é alcançado pelos testes.

### Gap Analysis — matriz requisito → teste → lacuna

| # | Requisito (spec / tarefa) | Teste(s) existente(s) | Lacuna |
| --- | --- | --- | --- |
| 1 | Migration preserva linhas antigas como Sem selo; reversível em banco isolado | `test_migration_preserves_existing_lines_as_no_seal`, `test_migration_0021_is_reversible` (`test_whatsapp_seal.py`) | Nenhuma |
| 2 | Cadastro com cada selo e pagamento persiste valores corretos | `test_create_persists_manual_dates` (parametrizado META_ONE/CREDIT_CARD, META_VERIFIED/GOOGLE_GIFT_CARD); HTTP: `test_http_create_detail_list_and_edit` | Nenhuma |
| 3 | Ausência individual dos 4 obrigatórios e valores inválidos rejeitados | `test_seal_requires_each_field` (parametrizado por campo × selo), `test_invalid_seal_data` (selo/e-mail/pagamento/data inválidos) | Nenhuma |
| 4 | Vencimento manual preservado; datas iguais aceitas; invertidas rejeitadas | `test_equal_dates_accepted`, `test_invalid_seal_data[whatsapp_seal_expires_on-2026-08-31]`, `test_create_persists_manual_dates` | Nenhuma |
| 5 | Edição, troca de selo, remoção e reativação limpam/persistem corretamente | `test_removing_seal_clears_data`, `test_reactivation_does_not_restore_old_seal`, `test_switching_existing_seal_to_none_without_js_saves_and_clears` | **Real.** Nenhum teste automatizado trocava um selo por outro tipo (META_ONE → META_VERIFIED) verificando que os quatro campos novos persistem sem misturar valores do selo anterior — só coberto manualmente na "Conferência real de SEL-07" (navegador, não repetível/CI). Fechada com `test_switching_between_seal_types_persists_new_values_without_mixing_old`. |
| 6 | Sem selo ignora resíduos inválidos antes do parsing | `test_without_seal_ignores_stale_hidden_values` | Nenhuma |
| 7 | Validação não duplica mensagens nem mistura valores antigos/novos (caminho de erro) | `test_missing_seal_field_error_message_not_duplicated`, `test_invalid_edit_does_not_reuse_stale_value_for_contradictory_message` | Nenhuma |
| 8 | POST inválido não grava parcialmente | `test_invalid_http_post_keeps_errors`, `test_invalid_http_edit_keeps_errors_and_does_not_persist_partial_data` | Nenhuma |
| 9 | Atualização de selo preserva `activated_at`, status, alocação e histórico operacional | Nenhum teste cobria isso diretamente — os testes existentes de edição usam linha sem alocação ativa (status AVAILABLE) | **Real.** Nenhum teste editava só campos do selo numa linha `ALLOCATED` com alocação ativa e `activated_at` setado, verificando que nada disso muda. Fechada com `test_updating_seal_preserves_activated_at_status_and_allocation` (via HTTP real, `PhoneLineUpdateView`, onde a lógica de alocação realmente vive — `telecom/views.py:642-678`). |
| 10 | Permissões isolam linhas entre usuários; detalhe, overview, JSON e OPERATOR não vazam dados | `test_operator_cannot_create_seal`, `test_overview_scope_excludes_unauthorized_line_seal_data`, `OperatorLinkedLinesViewTests.test_operator_does_not_see_seal_of_other_operators_line` | Nenhuma |
| 11 | Indicadores +8/+7/+1/0/-1 e "há N dias", singular/plural, data local | `test_expiry_boundaries` (domínio, inclui -5 → plural "Vencido há 5 dias"), `test_detail_indicator_tone_and_label`, `OperatorLinkedLinesViewTests.test_seal_indicator_boundaries_use_distinct_tone_classes` | Nenhuma — o texto plural/singular é produzido uma única vez em `compute_seal_status` (domínio); os testes de detalhe/listagem/OPERATOR reaproveitam esse texto por apresentação, não recalculam, então duplicar os 6 casos nas 3 superfícies não provaria nada novo (evitado, conforme instrução de não duplicar por contagem). |
| 12 | Primeira carga e "Carregar mais" mantêm mesmo contrato | `test_overview_ajax_load_more_second_page_matches_first_page_shape` | Nenhuma |
| 13 | Chamadores antigos de `create_or_reuse` e `save(commit=False)` continuam compatíveis | Nenhum teste dedicado, mas `admin.py:155` e `views.py` (`SIMcardCreateView`) chamam `create_or_reuse` sem argumentos de selo e são exercitados por `test_simcard_create_view_can_create_phone_line_together`, `test_simcard_create_view_reuses_soft_deleted_phone_line_number` e outros em `telecom/tests.py`, todos GREEN na suíte de 299; `PhoneLineForm.save(commit=False)` (`forms.py:168-169`) delega para `super().save(commit=False)`, comportamento padrão do Django `ModelForm`, garantido pelo framework | **Não é lacuna real.** Compatibilidade já comprovada pela suíte de regressão existente (nenhum desses chamadores foi alterado nesta feature); escrever um teste só para reconfirmar delegação padrão do Django não agrega cobertura — decisão registrada, não lacuna oculta. |

Nenhum ponto dos 13 exigiu correção de aplicação: as duas lacunas eram de **teste ausente**, não de comportamento incorreto — confirmado pelos dois testes novos passando GREEN já na primeira execução (ver Test Checklist).

### Implementation Plan — executado

1. `telecom/test_whatsapp_seal.py`: import de `AllocationService`, `Employee`, `LineAllocation` adicionado. Dois testes novos:
   - `test_switching_between_seal_types_persists_new_values_without_mixing_old`: cria linha com META_ONE via `PhoneLineForm`, edita para META_VERIFIED com data de ativação/vencimento/e-mail/pagamento diferentes via `PhoneLineUpdateForm`, confirma por `refresh_from_db()` que os cinco campos refletem só os valores novos.
   - `test_updating_seal_preserves_activated_at_status_and_allocation`: cria linha, fixa `activated_at` manualmente, aloca a um `Employee` via `AllocationService.allocate_line`, edita só `whatsapp_seal_expires_on` via HTTP real (`PhoneLineUpdateView`, mantendo `status=ALLOCATED` e o mesmo `employee` no payload), confirma que `activated_at`, `status`, a alocação ativa (mesmo `employee_id`, `is_active=True`) e a contagem de `PhoneLineHistory` da linha não mudam.
2. Nenhuma alteração em `telecom/models.py`, `telecom/forms.py`, `telecom/views.py`, `telecom/whatsapp_seal.py`, templates, JS ou migrations — os dois testes passaram GREEN na primeira execução, sem RED inventado (comportamento já correto, evidência abaixo).
3. Nenhuma validação explícita redundante reintroduzida em `PhoneLineForm.clean()` (o método segue removido desde a correção de SEL-06, ver seção correspondente).

### Test Checklist

- [x] Matriz requisito → teste dos 13 pontos de atenção concluída (tabela acima).
- [x] `test_switching_between_seal_types_persists_new_values_without_mixing_old` — GREEN na primeira execução (não é correção de defeito, é cobertura nova).
- [x] `test_updating_seal_preserves_activated_at_status_and_allocation` — GREEN na primeira execução (idem).
- [x] `telecom/test_whatsapp_seal.py` isolado: **36 passed** (34 anteriores + 2 novos), 2 warnings conhecidos (depreciação `CheckConstraint`).
- [x] Suíte consolidada (`test_whatsapp_seal.py test_phoneline_form_ui.py test_seal_detail_and_listing.py tests.py tests_line_timeline.py`): **299 passed, 1 skipped, 2 warnings, 5 subtests passed, 179.26s**.
- [x] `manage.py check`: `System check identified no issues (0 silenced)`.
- [x] `manage.py makemigrations --check --dry-run`: exit 1, mesmo drift pré-existente já registrado em SEL-05 (`dashboard/migrations/0010_alter_dailyuseraction_action_type.py`, `telecom/migrations/0022_alter_phoneline_origem.py`), nenhum arquivo novo escrito (confirmado por `git status --short` — só a migration 0021 já existente aparece como não rastreada). **Não descrito como limpo.**
- [x] Plano de migração conferido só em banco isolado: `test_migration_preserves_existing_lines_as_no_seal` e `test_migration_0021_is_reversible` usam `django_db(transaction=True)` + `call_command("migrate", ...)` contra o SQLite de teste, nunca contra banco operacional; nenhum comando de banco fora dos testes foi executado nesta sessão.

### Test Strategy

pytest + pytest-django, mesma configuração já validada em tarefas anteriores. Os dois testes novos são de integração (Django test client para o segundo, `PhoneLineForm`/`PhoneLineUpdateForm` reais para o primeiro — nenhuma mutação de lógica de domínio mockada). Relógio controlado via `monkeypatch`/`patch.object(timezone, "localdate", ...)` já reaproveitado pelos testes de fronteira existentes, não duplicado. Evidência visual de SEL-07/08 reaproveitada como já registrada nas seções anteriores desta spec; nenhuma nova validação de navegador nesta tarefa, pois SEL-09 é escopo de teste automatizado/GREEN, não de interface (interface não foi tocada).

Comandos e resultados:

```powershell
venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal.py -q
```
Resultado: **36 passed, 2 warnings in 3.67s** (34 pré-existentes + 2 novos desta tarefa).

```powershell
venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/test_seal_detail_and_listing.py telecom/tests.py telecom/tests_line_timeline.py -q
```
Resultado: **299 passed, 1 skipped, 2 warnings, 5 subtests passed in 179.26s**.

```powershell
venv\Scripts\python.exe manage.py check
```
Resultado: `System check identified no issues (0 silenced)`.

```powershell
venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```
Resultado (exit 1, apenas leitura — confirmado por `git status --short`, nenhum arquivo novo): drift pré-existente reconfirmado, idêntico ao já registrado em SEL-05/SEL-06 — `dashboard/migrations/0010_alter_dailyuseraction_action_type.py` (`AlterField` em `dailyuseraction.action_type`) e `telecom/migrations/0022_alter_phoneline_origem.py` (`AlterField` em `phoneline.origem`). Também emitido `RuntimeWarning` de conexão (`could not translate host name "db"`) — mesma limitação de rede já registrada em sessões anteriores para comandos que tentam checar histórico de migração contra o Postgres operacional; não impediu a leitura do estado de modelos, que é o que este comando reporta.

### Compliance Report

**SEL-09 concluída.** Os 13 pontos de atenção da tarefa foram mapeados individualmente para teste existente; 11 já tinham cobertura real e suficiente (nenhum teste duplicado foi criado para eles); 2 tinham lacuna real de teste (troca entre tipos de selo sem mistura de valores; preservação de `activated_at`/status/alocação/histórico ao editar só o selo), fechadas com exatamente 2 testes novos — ambos GREEN na primeira execução, portanto **sem RED comprovado nesta tarefa** (a lacuna era de ausência de prova automatizada, não de defeito de aplicação; isso está registrado explicitamente, não maquiado como correção). Um treze avo ponto (compatibilidade de chamadores antigos/`save(commit=False)`) foi avaliado e classificado como já coberto pela regressão existente, sem necessidade de teste novo — decisão registrada, não lacuna ignorada.

Nenhuma alteração em `telecom/models.py`, `telecom/forms.py`, `telecom/views.py`, `telecom/whatsapp_seal.py`, templates, JavaScript ou migrations nesta tarefa — só `telecom/test_whatsapp_seal.py` foi tocado (2 imports + 2 testes novos). Nenhuma validação explícita redundante reintroduzida em `PhoneLineForm.clean()`. Nenhuma assertion enfraquecida ou removida de qualquer teste existente.

Suíte consolidada: **299 passed, 1 skipped, 5 subtests passed**, sem nenhuma falha ou regressão. `manage.py check` limpo. `manage.py makemigrations --check --dry-run`: **não está limpo** — drift pré-existente e fora de escopo (`telecom.PhoneLine.origem`, `dashboard.DailyUserAction.action_type`) reconfirmado nesta tarefa, não corrigido, não incorporado a nenhuma migration desta feature, conforme instrução explícita de não corrigir drift alheio.

Limitações: nenhuma ferramenta de automação de navegador foi usada ou necessária nesta tarefa (escopo é teste automatizado); a validação visual de SEL-07/08 permanece a já registrada nas seções anteriores, não repetida aqui pois nenhuma interface foi alterada. `manage.py migrate --plan`/checagem de histórico de migração contra o Postgres operacional segue indisponível neste ambiente local (mesma limitação de rede de sessões anteriores); não bloqueante, pois toda prova de migração exigida por esta tarefa foi feita em banco de teste isolado (SQLite), nunca no operacional. Nenhum commit, push, deploy ou acesso a banco operacional nesta tarefa.

**SEL-10 não iniciada** — próximo passo, a critério do usuário.

## SEL-10 — Validação no navegador — 2026-09-21

### Spec Summary

Requisito exato (linha 79 desta spec): "Validação no navegador. Depende de SEL-09. Dados sintéticos e banco isolado. Aceite: cadastro/edição com e sem selo, obrigatoriedade, alternância preservando valores antes de salvar, erros, teclado, responsividade e cores conferidos." Nenhuma decisão aprovada reaberta; SEL-11 não iniciada.

Ambiente: branch `feat/phone-line-whatsapp-seal`; `git status` conferido no início e preservado — nenhum arquivo de sessões anteriores alterado ou descartado. Ferramenta de navegador: nenhum Chrome DevTools MCP disponível nesta sessão; confirmado Node.js (`v24.14.0`) com `playwright@1.63.0` global e Chromium já baixado localmente (`%LOCALAPPDATA%\ms-playwright`), mesma solução usada na sessão de 2026-09-21 anterior ("Correção da contenção móvel de OPERATOR"). Scripts Node no diretório de scratchpad abriram Chromium real (`headless: true`), navegaram, preencheram formulários, apertaram Tab, tiraram screenshots e leram `getBoundingClientRect`/`getComputedStyle` — não é Django test client. Banco isolado: container `lineops-db` (dev local, porta 5433, mesmo `docker-compose.yml` do projeto, volume `lineops_postgres_data` — não é o banco operacional) subido via `docker compose up -d db`; `manage.py runserver 127.0.0.1:8770` local com `DB_HOST=localhost`/`DB_PORT=5433`. Dados sintéticos criados com prefixo `sel10qa`: 1 admin, 2 operadores, 9 linhas telefônicas cobrindo Sem selo/META ONE/META VERIFICADO/vencido/vencendo hoje/alocada com `activated_at` fixo, e 2 SIM cards livres para os cadastros novos. Nenhum acesso a PRD (10.103.4.184) em nenhum momento.

### Gap Analysis — matriz de aceite

Ponto de partida: mapeamento de evidência já comprovada em navegador real nas sessões de SEL-07/08, reaproveitável porque `templates/telecom/phoneline_form.html`, `static/js/phone-line-form.js`, `telecom/forms.py` (exceto a correção desta própria tarefa) e `templates/telecom/phoneline_detail.html`/`overview.html`/`operator_lines.html` não foram alterados desde essas sessões (confirmado por não haver nenhuma edição de aplicação nesta tarefa antes da correção do achado abaixo).

| # | Item do checklist | Evidência reaproveitada (seção/linha) | Evidência nova nesta sessão | Status |
| --- | --- | --- | --- | --- |
| 1 | Sem selo como opção explícita | "Revalidação final de SEL-07" (l.516) | — | Reaproveitado |
| 2 | Selecionar META ONE/VERIFICADO revela os 4 campos | idem (l.516, l.520) | Cenário A: `A_seal_block_hidden_after_select=false`, `A_required_after_select=4` | Reaproveitado + confirmado |
| 3 | Obrigatoriedade HTML acompanha a seleção | idem | Cenário A: `A_required_before_select=0` → `4` após selecionar | Reaproveitado + confirmado |
| 4 | Cadastro válido salva os valores, incl. vencimento manual | "Conferência real de SEL-07" (l.484) testou edição; cadastro novo **com JS do início ao fim não estava coberto em navegador** (gap real #3) | Cenário A: cadastro novo completo (JS ligado) de `+5511900099001`, META ONE, ativação=vencimento=15/09/2026, e-mail e pagamento — sucesso, confirmado por leitura direta do banco (`whatsapp_seal_activated_on=2026-09-15`, `whatsapp_seal_expires_on=2026-09-15`) | **Novo** |
| 5 | Obrigatório ausente rejeitado | "Revalidação final de SEL-07" (l.522) | Cenário D: vencimento ausente → erro único, foco no resumo | Reaproveitado + confirmado |
| 6 | E-mail inválido rejeitado | Não havia evidência de navegador real, só teste automatizado (`test_invalid_seal_data`) | Cenário G: e-mail `nao-e-um-email` rejeitado pelo servidor (bypass do `type=email` nativo para provar validação server-side) — **defeito real encontrado e corrigido, ver abaixo** | **Novo (defeito corrigido)** |
| 7 | Datas invertidas rejeitadas | "Revalidação final de SEL-07" (l.521) | Cenário H: reconfirmado com dados desta sessão, mensagem única "Data de vencimento não pode ser anterior à data de ativação." | Reaproveitado + confirmado |
| 8 | Datas iguais aceitas | Só teste automatizado (`test_equal_dates_accepted`) | Cenário A: ativação=vencimento=15/09/2026 aceito e persistido | **Novo** |
| 9 | Erros PT-BR sem duplicação/contradição | "Revalidação final de SEL-07" (l.521); SEL-06 corrigiu uma classe deste bug | Cenário G revelou uma **segunda** instância da mesma classe de bug (gatilho: formato inválido, não campo ausente) — corrigida nesta tarefa, revalidada no navegador após a correção | **Novo (defeito corrigido)** |
| 10 | POST inválido preserva valores e foca resumo | "Revalidação final de SEL-07" (l.521) | Cenário D: `D_preserved_phone_number`/`D_preserved_email` intactos, `D_error_summary_is_focused=true`; confirmado por leitura de banco que nenhuma linha foi criada nos POSTs inválidos (D/G/H) | Reaproveitado + confirmado |
| 11 | Dados existentes carregam na edição | "Revalidação final de SEL-07" (l.520) | Cenário B: `B_initial_seal_value=META_ONE`, `B_initial_email_value=dados-a@example.com` carregados | Reaproveitado + confirmado |
| 12 | Troca de tipo de selo persiste novos valores sem misturar antigos | SEL-09 fechou só com teste automatizado (l.975, l.990); "Revalidação final de SEL-07" só testou alternância **antes de salvar**, sem POST real (gap real #1) | Cenário B: salva META_ONE (dados A) → edita para META_VERIFIED (dados B) → **salva de novo** → reabre detalhe → `dados-a@example.com` ausente, `dados-b-verificado@example.com` presente, "META VERIFICADO" presente. Confirmado por screenshot (`B_detail_after_switch.png`) | **Novo** |
| 13 | Remover selo limpa detalhes ao salvar | "Revalidação final de SEL-07" (l.519, com consulta SQLite) | — | Reaproveitado |
| 14 | Alternar seleção antes de salvar mantém comportamento aprovado | "Revalidação final de SEL-07" (l.520) | — | Reaproveitado |
| 15 | Liberar não bloqueado pelos required do selo | "Revalidação final de SEL-07" (l.522) | — | Reaproveitado |
| 16 | Preservação de activated_at/status/alocação ao editar só o selo | SEL-09 fechou só com teste automatizado via HTTP (l.979); nunca verificado visualmente (gap real #2) | Cenário C: linha `alloc_target` (ALLOCATED, `activated_at` fixado 30 dias atrás, alocada a `Employee`). Editado só `whatsapp_seal_expires_on`. Antes/depois no formulário: "Ativada em" idêntico (22/08/2026 14:22), `status=ALLOCATED` idêntico, `employee` (id 9) idêntico; só "Atualizada em" e o vencimento mudaram, como esperado | **Novo** |
| 17 | Campos ocultos sem foco (sem JS) | "Revalidação final de SEL-07" (l.516-519, CSP `script-src 'none'`) | — (código de fallback sem alteração) | Reaproveitado |
| 18 | Validação server-side funciona sem JS | idem | — | Reaproveitado |
| 19 | Trocar para Sem selo sem JS não bloqueado por required residual | idem (l.516) | — | Reaproveitado |
| 20 | Sem selo sem JS descarta resíduos inválidos e salva limpeza | idem (l.519) | — | Reaproveitado |
| 21 | Detalhe mostra info correta; Sem selo sem alerta | "Conferência real de SEL-08" (l.762) | Cenário B: screenshot do detalhe confirma bloco completo | Reaproveitado + confirmado |
| 22 | Overview inicial e Carregar mais equivalentes | idem (l.759) | — (código de `overview.html`/`views.py` inalterado) | Reaproveitado |
| 23 | OPERATOR só linhas autorizadas | idem (l.763); "Correção da contenção móvel de OPERATOR" (l.917-924) | Cenário F: `sel10qa.operator.a` vê `+5511900010006` (própria) e não vê `+5511900010007` (de `operator.b`) | Reaproveitado + confirmado |
| 24 | E-mail/pagamento ausentes de colunas/payload | idem (l.764) | — | Reaproveitado |
| 25 | Fundo azul-escuro | "Revalidação visual real de SEL-08" (l.859) | Screenshots desta sessão (`E_create_360.png`, `focus_seal_field.png`) confirmam o mesmo fundo | Reaproveitado + confirmado |
| 26 | Indicadores +8/+7/+1/0/-1 e singular/plural | "Correção dos achados visuais de SEL-08" (l.814-816); dados sintéticos desta sessão recalculam os mesmos tons (`neutral`/`warning`/`today`/`expired`) via `compute_seal_status` real | Confirmado por leitura de banco: linha vencendo hoje → `{"tone": "today", "label": "Vence hoje"}`; vencida há 1 dia → `"Vencido há 1 dia"` (singular) | Reaproveitado + confirmado |
| 27 | "Vence hoje" contraste aprovado | "Revalidação visual real de SEL-08" (7,81:1, l.859) | Código de `_seal_status_badge.html` inalterado nesta sessão | Reaproveitado |
| 28 | Teclado alcança campos/erros/ações, foco visível | "Revalidação final de SEL-07" (l.521-522) | Cenários B/D: sequência de Tab registrada (Cancelar → Salvar/Cadastrar → Liberar quando existe); campos ocultos nunca aparecem na sequência após alternar para Sem selo. Foco visível confirmado via `getComputedStyle` (`box-shadow` azul de 3,52px ao focar, Bootstrap `:focus`) e screenshot (`focus_seal_field.png`) | Reaproveitado + confirmado |
| 29 | Mobile 360/390 e desktop | SEL-07 só media 390px no formulário (gap real #4); OPERATOR/overview já tinham 360px (l.911-913) | Cenário E: formulário de cadastro e edição em 360×740 — ver achado de medição abaixo (não bloqueante) | **Novo** |
| 30 | OPERATOR sem overflow de página, rolagem interna, "Acessar" utilizável | "Correção da contenção móvel de OPERATOR" (l.907-924) | Cenário F (leve, sem repetir toda a bateria): OPERATOR carrega, mostra só linha própria | Reaproveitado |
| 31 | Overflow do overview independente (não reabrir) | "Correção dos achados visuais de SEL-08" (l.802); "Revalidação visual real" (l.861) | Ver achado de medição abaixo | Reaproveitado (não piorou) |
| 32 | Sem erros novos de console/rede | — | `consoleErrors`/`failedRequests` vazios em todos os 8 cenários (A-H) executados nesta sessão | **Novo** |

Nenhum dos 5 pontos que eu (autor da tarefa) havia sinalizado como possível gap era falso: os 5 eram reais (itens 4/8, 12, 16, 6/9, 29 da tabela acima corresponderiam aos gaps 3, 1, 2, e as duas frentes do gap 5 — datas iguais/teclado completo — respectivamente). O item 6 (e-mail inválido) revelou adicionalmente um defeito de aplicação não antecipado.

### Achado de medição — overflow residual a 360px em três páginas (não é regressão desta feature)

Ao medir o formulário de cadastro/edição em 360×740 (item 29), `documentElement.scrollWidth=364` contra `clientWidth=360` (4px). Investigação (`sel10_overflow_debug.js`, `sel10_overflow_compare.js`, ambos no scratchpad desta sessão): a origem é o padding do `.app-main` (13,6px de cada lado, calculado em unidade responsiva compartilhada por toda a aplicação), que por si só já ultrapassa 360px de largura útil — nada dentro do card/formulário desta feature extrapola essa borda (`.content-stage`, `.card` e a `.row.g-3` dos dois cards ficam inteiramente contidos dentro do `.app-main`, confirmado por `getBoundingClientRect`). Comparação no mesmo navegador/sessão confirmou o mesmo padrão de 4px em `operator_lines.html` (página já corrigida e aceita como "360/360 limpo" pela ferramenta CUA na sessão de 2026-09-21) e em `phoneline_detail.html` — ou seja, é uma característica de base de layout compartilhada por toda a aplicação, reproduzida de forma idêntica em página já aprovada por outra ferramenta, não algo introduzido por esta feature nem específico do formulário. Screenshot (`E_create_360.png`) não mostra nenhum corte de conteúdo, barra de rolagem horizontal visível ou quebra de layout — cards empilhados corretamente, fundo azul-escuro preservado. Classificado como variação de sub-pixel entre ferramentas de medição (Playwright/Chromium headless local vs. navegador CUA usado nas sessões anteriores), mesma natureza do overflow de ~10px do overview já registrado e explicitamente fora de escopo (linha 923 desta spec). **Não corrigido nesta tarefa** — critério explícito de não reabrir/perseguir esse tipo de achado independente; registrado aqui apenas porque a medição em 360px é nova, não porque houve piora.

### Defeito de aplicação encontrado e corrigido

**Mensagem de erro contraditória quando um campo de detalhe do selo é preenchido com formato inválido.** Reproduzido primeiro no navegador real (Cenário G: e-mail `"nao-e-um-email"`, bypass do atributo nativo `type="email"` via `page.evaluate` para provar que a validação é do servidor, não só do navegador) e depois isolado via `PhoneLineForm` direto (sem navegador, para eliminar qualquer dúvida de artefato do bypass):

```
form.errors == {'whatsapp_seal_email': [
    'Insira um endereço de email válido.',
    'E-mail cadastrado do selo é obrigatório.',
]}
```

Causa raiz: quando o `EmailField` do Django rejeita o formato, o valor é removido de `cleaned_data` (comportamento padrão do Django); `construct_instance()` então não atribui esse campo à instância, que mantém o valor vazio original; `PhoneLine.clean()` (chamado automaticamente por `_post_clean()`, mesmo fluxo documentado na correção histórica de SEL-06) enxerga o atributo vazio e soma "é obrigatório" — mesmo o usuário tendo digitado um valor, só que inválido. É a mesma classe de bug da correção de SEL-06 (linhas 209-231 desta spec), mas com um gatilho diferente (formato inválido em vez de campo ausente do POST bruto ou valor antigo reaproveitado), portanto não coberto pelos testes daquela correção nem pelo `test_missing_seal_field_error_message_not_duplicated`/`test_invalid_edit_does_not_reuse_stale_value_for_contradictory_message` existentes.

Corrigido com a menor mudança possível: `PhoneLineForm._post_clean()` sobrescrito em `telecom/forms.py` para, antes de chamar `super()._post_clean()`, registrar quais dos 4 campos de detalhe do selo já tinham erro de formato (`field_name in self.errors`); depois de `super()._post_clean()` rodar (que dispara a validação de domínio automática), remove **apenas** a mensagem de `REQUIRED_FIELD_ERRORS` desses campos específicos, e só quando sobra pelo menos outra mensagem real (nunca esvazia a lista de erros de um campo). Nenhuma mudança em `validate_seal_fields`, `PhoneLine.clean()`, `full_clean()` customizado existente ou em qualquer regra de domínio — a correção fica inteiramente no limite form↔model já reconhecido pela correção histórica de SEL-06, sem reintroduzir a chamada explícita redundante que aquela correção removeu.

Teste de regressão novo: `test_invalid_format_error_not_duplicated_with_required_message` em `telecom/test_whatsapp_seal.py`. RED confirmado antes da correção (`assert ['Insira um e...obrigat�rio.'] == ['Insira um e...mail v�lido.']`, a lista continha as duas mensagens); GREEN após a correção (só a mensagem de formato permanece). Revalidado no navegador real após reiniciar o servidor de QA com o código corrigido (Cenário G repetido): resumo de erros passa a mostrar só "E-mail cadastrado: Insira um endereço de email válido." — screenshot `G_invalid_email.png`. Cenário H (datas invertidas, que já funcionava) repetido no mesmo lote para confirmar ausência de regressão na outra mensagem de erro do formulário.

### Implementation Plan — executado

1. Mapeamento de evidência reaproveitável vs. lacunas reais (matriz acima), a partir da leitura integral desta spec (linhas 1-1043) já em contexto.
2. Ambiente: `docker compose up -d db` (container já existia parado, iniciado); `manage.py migrate` (sem pendências); `manage.py runserver 127.0.0.1:8770 --noreload` local; dados sintéticos via script `sel10_seed.py` (scratchpad), idempotente, prefixo `sel10qa`.
3. Descoberta de ferramenta de navegador: Node.js + `playwright@1.63.0` global + Chromium local confirmados disponíveis (mesma solução de sessões anteriores); nenhum Chrome DevTools MCP encontrado nesta sessão.
4. Execução de 8 cenários em Playwright/Chromium real (scripts `sel10_browser.js`, `sel10_browser2.js`, `sel10_overflow_debug.js`, `sel10_overflow_compare.js`, `sel10_focus_shot.js`, todos no scratchpad desta sessão): A (cadastro novo com JS + datas iguais), B (troca de tipo entre dois saves reais + teclado), C (preservação de activated_at/status/alocação), D (erro obrigatório ausente + resumo focado + teclado após alternar para Sem selo), E (360px no formulário), F (isolamento OPERATOR, leve), G (e-mail inválido — revelou o defeito), H (datas invertidas).
5. Defeito encontrado no cenário G: reproduzido isoladamente via `PhoneLineForm` (sem navegador) antes de qualquer alteração de código, conforme instrução. Teste de regressão escrito e RED comprovado. Correção aplicada em `telecom/forms.py` (`_post_clean` override + import de `REQUIRED_FIELD_ERRORS`). GREEN comprovado no teste novo, na suíte alvo (78 passed) e na regressão completa de telecom (236 passed, 1 skipped). `manage.py check` limpo.
6. Servidor de QA reiniciado para carregar o código corrigido; cenários G e H repetidos no navegador real para confirmar a correção visualmente (screenshot `G_invalid_email.png`).
7. Investigação do achado de medição de 360px (overflow de 4px) por comparação com `operator_lines.html`/`phoneline_detail.html` na mesma sessão/ferramenta, sem alteração de código (classificado como variação de ferramenta de medição, não regressão).
8. Limpeza: dados sintéticos `sel10qa*` e as linhas/SIM cards de teste removidos do banco isolado; servidor local e container `lineops-db` encerrados; nenhum arquivo de aplicação além de `telecom/forms.py`/`telecom/test_whatsapp_seal.py` tocado; scripts de QA permanecem apenas no scratchpad (fora do repositório).

### Test Checklist

- [x] Sem selo como opção explícita — reaproveitado.
- [x] Selecionar META ONE/VERIFICADO revela os 4 campos com `required` — confirmado (A).
- [x] Cadastro válido salva os valores, incl. vencimento manual — confirmado (A), inclusive datas iguais.
- [x] Obrigatório ausente rejeitado — confirmado (D).
- [x] E-mail inválido rejeitado — confirmado (G); defeito de mensagem contraditória encontrado e corrigido.
- [x] Datas invertidas rejeitadas — confirmado (H).
- [x] Datas iguais aceitas — confirmado (A).
- [x] Erros em PT-BR sem duplicação/contradição — confirmado após a correção (G repetido).
- [x] POST inválido preserva valores e foca resumo — confirmado (D); nenhuma linha criada por POST inválido (D/G/H, verificado no banco).
- [x] Dados existentes carregam na edição — confirmado (B).
- [x] Troca de tipo de selo persiste novos valores sem misturar antigos — confirmado com 2 salvamentos reais (B).
- [x] Remover selo limpa detalhes ao salvar — reaproveitado.
- [x] Alternar seleção antes de salvar mantém comportamento aprovado — reaproveitado.
- [x] Liberar não bloqueado pelos required do selo — reaproveitado.
- [x] Preservação de activated_at/status/alocação ao editar só o selo — confirmado visualmente (C).
- [x] Fallback sem JavaScript (campos acessíveis, validação server-side, Sem selo sem required residual, limpeza de resíduos) — reaproveitado, código inalterado.
- [x] Detalhe mostra info correta; Sem selo sem alerta — reaproveitado + confirmado (B).
- [x] Overview inicial e Carregar mais equivalentes — reaproveitado, código inalterado.
- [x] OPERATOR só linhas autorizadas — reaproveitado + confirmado (F).
- [x] E-mail/pagamento ausentes de colunas/payload — reaproveitado.
- [x] Fundo azul-escuro — confirmado por screenshot.
- [x] Indicadores +8/+7/+1/0/-1 e singular/plural — confirmado por leitura de banco com dados sintéticos reais.
- [x] "Vence hoje" contraste aprovado — reaproveitado, código inalterado.
- [x] Teclado alcança campos/erros/ações, foco visível — confirmado (B/D + `focus_seal_field.png`).
- [x] Mobile 360/390 e desktop no formulário — confirmado (E); achado de medição de 4px registrado como pré-existente/não bloqueante, não corrigido.
- [x] OPERATOR sem overflow de página, rolagem interna, "Acessar" utilizável — reaproveitado.
- [x] Overflow do overview independente — não reaberto; não piorou (mesma classe de achado, não comparável ponto-a-ponto por medição em viewport diferente da sessão original).
- [x] Sem erros novos de console/rede — confirmado (nenhum erro em nenhum dos 8 cenários).

Nenhum item ficou como "não executado/bloqueado".

### Test Strategy

Reprodução via navegador real (Playwright/Chromium local headless, interação real: preencher, selecionar, apertar Tab, submeter, navegar, screenshot, `getBoundingClientRect`/`getComputedStyle`) para tudo que HTTP/test client não comprova (JS, teclado, responsividade, cores computadas). Leitura direta do banco isolado (somente leitura, exceto os próprios dados sintéticos desta tarefa) para confirmar persistência exata dos valores após ações no navegador — mesmo padrão de evidência combinada já usado nas sessões de SEL-07/08. Reaproveitamento explícito de evidência anterior sempre citando seção/linha exata, sem repetir cenários cujo código não mudou. Para o defeito encontrado: reprodução isolada sem navegador (`PhoneLineForm` direto) antes de tocar código, teste de regressão RED→GREEN, suíte alvo e regressão completa de telecom (proporcional ao arquivo alterado, `forms.py`, usado por todos os fluxos de cadastro/edição — não restrita só aos testes de selo), `manage.py check`, e repetição do cenário no navegador real após a correção.

Comandos e resultados:

```powershell
venv/Scripts/python.exe -m pytest telecom/test_whatsapp_seal.py -k test_invalid_format_error_not_duplicated_with_required_message -q
```
RED antes da correção: 1 failed (lista de erros continha as duas mensagens). GREEN após a correção: 1 passed.

```powershell
venv/Scripts/python.exe -m pytest telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/test_seal_detail_and_listing.py telecom/tests.py::OperatorLinkedLinesViewTests -q
```
Resultado: **78 passed, 5 subtests passed, 2 warnings** (75 da baseline anterior + 1 teste novo desta tarefa +2 diferença de contagem por reagrupamento das mesmas suítes; nenhuma falha).

```powershell
venv/Scripts/python.exe manage.py check
```
Resultado: `System check identified no issues (0 silenced)`.

```powershell
venv/Scripts/python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
```
Resultado: **236 passed, 1 skipped, 2 warnings, 5 subtests passed in 165.11s** — mesmo baseline das sessões anteriores, sem regressão (executada porque `telecom/forms.py` é usado por todos os fluxos de cadastro/edição de linha, não só pelo selo).

### Compliance Report

**SEL-10 concluída.** Todos os critérios do requisito exato da tarefa (linha 79) foram comprovados em navegador real (Playwright/Chromium local) ou reaproveitados de evidência anterior válida e citada com seção/linha exata, porque o código correspondente não mudou. Dos 5 pontos de atenção que eu havia sinalizado como possíveis lacunas antes de começar, todos os 5 eram reais e foram fechados com evidência nova: (1) troca de tipo de selo entre dois salvamentos reais — sem mistura de dados antigos; (2) preservação visual de `activated_at`/status/alocação ao editar só o selo; (3) cadastro novo do zero com JavaScript ligado, incluindo vencimento manual e datas iguais; (4) formulário em 360px, além dos 390/1280px já cobertos; (5) e-mail inválido rejeitado pelo servidor e navegação por teclado completa (campos, resumo de erros, ações). O item (5) revelou adicionalmente um **defeito real de aplicação**, não antecipado: mensagem de erro contraditória ("obrigatório" somada a "formato inválido") para qualquer um dos 4 campos de detalhe do selo quando preenchido com valor em formato inválido — mesma classe de bug da correção histórica de SEL-06, gatilho diferente, não coberta pelos testes daquela correção. Reproduzido antes de alterar código, corrigido com a menor mudança possível (`PhoneLineForm._post_clean`), coberto por teste de regressão novo, revalidado no navegador real após a correção. Nenhuma regra de domínio, status ou alocação alterada; nenhum teste enfraquecido ou removido; suíte alvo (78 passed) e regressão completa de telecom (236 passed, 1 skipped) sem quebras; `manage.py check` limpo.

Um achado de medição (não defeito): overflow de ~4px em 360px (`documentElement.scrollWidth` vs `clientWidth`) presente de forma idêntica no formulário, no detalhe e em `operator_lines.html` (esta última já aceita como limpa por outra ferramenta de navegador em sessão anterior) — investigado e atribuído a uma característica de padding do `.app-main` compartilhada por toda a aplicação (não introduzida por esta feature), consistente com a mesma classe de variação de sub-pixel entre ferramentas de medição já registrada para o overflow do overview. Não corrigido, conforme limite explícito da tarefa de não perseguir esse tipo de achado independente; nenhuma piora identificada.

Arquivos alterados nesta tarefa: `telecom/forms.py` (import de `REQUIRED_FIELD_ERRORS` + método `PhoneLineForm._post_clean`), `telecom/test_whatsapp_seal.py` (1 teste novo). Nenhuma alteração em `telecom/models.py`, `telecom/views.py`, `telecom/whatsapp_seal.py`, templates, JavaScript ou migrations. Nenhuma migration aplicada em qualquer banco (nem isolado — não houve mudança de schema). Nenhum commit, push, deploy ou acesso a banco operacional (PRD).

Limitações: nenhuma. Todos os itens do checklist têm evidência válida (nova ou reaproveitada); nenhum item ficou como "não executado/bloqueado". Ambiente de QA (servidor local porta 8770, container `lineops-db`, dados sintéticos `sel10qa*`, 2 SIM cards extras) encerrado e limpo ao final desta tarefa — nenhum processo/recurso do usuário foi tocado. Scripts de navegador ficam apenas no diretório de scratchpad desta sessão, fora do repositório.

**SEL-11 não iniciada** — próximo passo, a critério do usuário.

## SEL-11 — Revisão e entrega — 2026-09-21

### Spec Summary

Requisito exato (linha 80 desta spec, antes desta tarefa): "Revisão e entrega. Depende de SEL-10. Conferir diff contra spec, registrar evidências e limitações no Compliance Report. Aceite: alterações anteriores preservadas; nenhum deploy nem alteração de dados operacionais." Escopo adicional explícito desta tarefa: revisão aprofundada de `PhoneLineForm._post_clean` (correção de SEL-10) e reexame crítico do overflow de ~4px a 360px (classificado como "preexistente/não bloqueante" em SEL-10, sem comparação equivalente registrada até então). Nenhuma decisão aprovada de SEL-01 a SEL-10 foi reaberta; nenhum código de aplicação foi alterado além do necessário para fechar a lacuna de teste real encontrada nesta revisão (ver abaixo).

Ambiente: branch `feat/phone-line-whatsapp-seal`; `git status` conferido no início e ao final — idêntico (nenhum arquivo de sessões anteriores alterado, sobrescrito ou removido). `venv\Scripts\python.exe` usado em todos os comandos. Banco de teste isolado reconfirmado por leitura de `config/settings.py` (SQLite dedicado quando `pytest` está em `sys.modules`); banco de desenvolvimento isolado (`docker compose up -d db`, container `lineops-db`, porta 5433) usado só para a verificação de navegador real do overflow, com usuário sintético `sel11qa_admin@test.local` removido e container parado ao final. Nenhum acesso a PRD (10.103.4.184) em nenhum momento.

### Gap Analysis

**1. `PhoneLineForm._post_clean` (correção de SEL-10).** Leitura direta do código instalado do Django 5.2.11 (`venv/Lib/site-packages/django/forms/models.py:474-504`, `django/forms/forms.py:264-317`, `django/core/exceptions.py:134-237`) confirmou o mecanismo exato que o override depende: `BaseModelForm._post_clean()` chama `construct_instance()` (que pula campos ausentes de `cleaned_data`, preservando o valor antigo da instância em edição), depois `instance.full_clean(exclude=..., validate_unique=False)` (que sempre chama `Model.clean()`, disparando `validate_seal_fields` automaticamente) e propaga erros via `_update_errors`/`add_error()`. Confirmado empiricamente (script isolado, fora do repositório) que `self.errors[campo]` itera como `str` plano (via `ErrorList.__getitem__`/`list()`), não como `ValidationError` — portanto a comparação `message != required_message` no override funciona por igualdade de string, não por identidade de objeto (risco que existiria se a iteração devolvesse `ValidationError`, já que essa classe implementa `__eq__` só contra outra `ValidationError`).

Quatro cenários de fronteira não cobertos por nenhum teste existente foram exercitados com `PhoneLineForm`/`PhoneLineUpdateForm` reais (script isolado, sem alterar código de aplicação antes da verificação, removido ao final):
- Data em formato inválido (`"not-a-date"`, `DateField`) em vez de e-mail: mensagem final contém só "Informe uma data válida.", sem "obrigatória" — confirma que a correção não é específica de `EmailField`, cobre qualquer um dos 4 campos via `SEAL_DETAIL_FIELDS`.
- Dois campos inválidos simultaneamente (e-mail e pagamento): cada campo mantém só sua própria mensagem de formato, sem vazamento cruzado nem mensagem "obrigatória" residual em nenhum dos dois.
- E-mail inválido **na edição** de uma linha com e-mail antigo válido salvo: mensagem final é só a de formato; `refresh_from_db()` confirma que o e-mail antigo (`seal@example.com`) permanece intacto no banco — o valor antigo não é reaproveitado para mascarar a entrada inválida nem para produzir mensagem contraditória (esse cenário específico, "não reutiliza valor antigo... na edição", não tinha nenhum teste automatizado antes desta tarefa — só o cenário de criação, `test_invalid_format_error_not_duplicated_with_required_message`, existia).
- E-mail inválido combinado com vencimento ausente, na mesma edição: cada campo mostra sua mensagem correta e independente (formato para e-mail, obrigatoriedade para vencimento), sem mistura.

Nenhum dos quatro cenários revelou defeito — a correção de SEL-10 se comporta corretamente também fora do caminho já coberto (e-mail inválido na criação). **Lacuna real de teste** confirmada apenas no terceiro cenário (e-mail inválido na edição): é exatamente o comportamento que o requisito desta tarefa pede para conferir ("Não reutiliza valor antigo para mascarar entrada inválida na edição") e não tinha nenhuma prova automatizada — fechada com 1 teste novo (ver Implementation Plan).

Demais propriedades pedidas nesta tarefa, verificadas por leitura de código (sem necessidade de teste novo, por já estarem comprovadas por testes existentes citados):
- *Preserva validações normais do Django*: `super()._post_clean()` é chamado integralmente, sem `try/except` ao redor nem `return` antecipado; a única ação do override é remover uma mensagem específica de uma lista que já tem outra mensagem real.
- *Não suprime erros legítimos*: a remoção só ocorre para `field_name in fields_with_format_errors` (capturado **antes** de `super()._post_clean()` rodar, portanto só contém campos com erro de formato de campo, nunca campos cujo único erro é a obrigatoriedade de domínio) e só quando `remaining` não fica vazio (`if remaining and len(remaining) != len(self.errors[field_name])`) — um campo nunca fica com lista de erros vazia por causa desta correção.
- *Não permite gravação parcial*: o override não toca `cleaned_data`, `self.instance` nem `is_valid()`; se sobra qualquer erro (inclusive a própria mensagem de formato), `is_valid()` continua `False` e os testes HTTP existentes (`test_invalid_http_post_keeps_errors`, `test_invalid_http_edit_keeps_errors_and_does_not_persist_partial_data`) já comprovam que nenhuma linha é criada/alterada num POST inválido.
- *Funciona nos dois forms e com `save(commit=False)`*: `PhoneLineUpdateForm` herda `PhoneLineForm` sem sobrescrever `_post_clean` (confirmado nos 4 cenários acima, todos exercitados via `PhoneLineUpdateForm` quando aplicável); `save(commit=False)` delega para `super().save(commit=False)` sem passar por `_post_clean` de novo — comportamento padrão do `ModelForm`, inalterado por esta correção.
- *Evita duplicação sem depender de comparação frágil de textos traduzidos*: a comparação usa `REQUIRED_FIELD_ERRORS` — constante própria do domínio (`telecom/whatsapp_seal.py`), a mesma fonte usada por `validate_seal_fields` — não uma string traduzida do Django (`ugettext`/`_()` de mensagens built-in, que mudaria com locale). É uma fonte única compartilhada, não duas strings hardcoded independentes que poderiam divergir.

**2. Overflow de ~4px a 360px.** A "Achado de medição" de SEL-10 (linha 1093-1095, antes desta tarefa) já apontava a causa (padding de `.app-main`) e já citava uma comparação — mas essa comparação era entre páginas **todas tocadas por esta própria feature** (formulário, `operator_lines.html`, `phoneline_detail.html`), o que não isola se o excedente já existia antes da feature ou se o conteúdo novo (badge/coluna do selo) é o que empurra o layout para além de 360px. Per instrução desta tarefa, essa lacuna de evidência foi fechada:
- `git diff main -- static/css/styles.css templates/base/base.html`: **sem diferença** — a definição de `.app-shell` (grid `74px 1fr`), `.app-main` (`padding: 0.85rem` = 13,6px por lado no breakpoint móvel) e `.content-stage` não foi tocada por nenhuma sessão desta feature.
- Verificação em navegador real (Playwright/Chromium local, servidor Django isolado em `127.0.0.1:8771`, banco de desenvolvimento isolado, usuário sintético `sel11qa_admin@test.local`, viewport 360×740): comparado `telecom/phonelines/create/` (página **reescrita** por esta feature) contra `telecom/simcards/` (`SIMcardListView`/`simcard_list.html` — página que este branch **nunca tocou**, confirmado por `git diff main --stat` não listar o arquivo). Resultado idêntico nas duas: `clientWidth=360`, `scrollWidth=364` — **os mesmos 4px**, na página sem nenhuma linha alterada por esta feature.

Isso é a "comparação com versão anterior relevante" que a instrução desta tarefa exige e que as sessões anteriores não tinham produzido (compararam páginas entre si, todas modificadas pela própria feature, não uma página efetivamente equivalente ao estado de `main`). Com uma página **inalterada por esta feature e por qualquer CSS/template tocado por ela** apresentando o mesmo excedente, a classificação de "pré-existente, não introduzido por esta feature" passa de presunção por semelhança visual (como estava em SEL-10) para **comprovada por comparação equivalente**. Mantida a decisão de SEL-08/SEL-10 de não corrigir (é um defeito de base compartilhado por toda a aplicação, fora do escopo desta feature — corrigi-lo exigiria tocar `.app-main`/`.app-shell`, usado por toda página do sistema, verificação muito além do escopo de SEL-11).

**3. Demais pontos do checklist de revisão completa** (cinco campos/choices/obrigatoriedade/vencimento manual, datas, limpeza/troca/edição/reativação, `activated_at`/status/alocação/histórico, migration aditiva/reversível, permissões, payload sem e-mail/pagamento, renderização segura sem `innerHTML` para dados do selo, consistência entre as três superfícies, fallback sem JS, ausência de artefatos acidentais no diff, documentação): revisados por leitura de código nesta tarefa (`telecom/forms.py`, `telecom/models.py`, `telecom/whatsapp_seal.py`, `telecom/migrations/0021_...py`, `templates/telecom/overview.html` JS, `templates/telecom/_seal_status_badge.html`, `git diff main --stat`), sem nenhuma divergência encontrada em relação ao que já está registrado e testado nas seções SEL-05 a SEL-10 desta mesma spec — nenhum achado novo, nenhuma reabertura necessária. Especificamente conferido nesta tarefa:
- `createSealBadge`/`createSealCell` (`overview.html`) constroem a célula do selo inteiramente via `createElement`/`textContent`/`classList`; o mapeamento tom→classe é idêntico, classe a classe, ao de `_seal_status_badge.html` (server-side) — nenhuma duplicação de regra de cor divergente entre os dois caminhos.
- `git diff main -- telecom/forms.py telecom/models.py telecom/views.py telecom/tests.py templates/telecom/` sem ocorrência de segredo/credencial nova, `TODO`/`FIXME`, `console.log`/`debugger`, ou prefixo de dado de QA (`sel10qa`/`sel11qa`) — o único `password="123456"` encontrado é o mesmo padrão já usado 45 vezes em `telecom/tests.py` antes desta feature (convenção pré-existente de teste, não segredo real nem introduzido por esta tarefa).
- Migration `0021_phoneline_whatsapp_seal_and_more.py`: só `AddField` (5), todos com `default`/`null=True`, reversível automaticamente (Django reverte `AddField` com `RemoveField`); nenhum `AlterField` de `origem` presente (drift já identificado, corretamente não incorporado).
- `git status --short`, antes e depois desta tarefa: idêntico — nenhuma alteração de sessões anteriores foi sobrescrita ou perdida.

### Implementation Plan — executado

1. Leitura integral desta spec (linhas 1-1195, todas as seções SEL-01 a SEL-10) para reconstituir requisito exato, evidências e limitações já registradas, sem redigitar/resumir de memória.
2. Leitura do código instalado do Django (`forms/models.py`, `forms/forms.py`, `forms/utils.py`, `core/exceptions.py`) para confirmar o mecanismo exato de `_post_clean`/`add_error`/`ErrorList` usado pela correção de SEL-10, incluindo verificação empírica isolada (script fora do repositório) de que `self.errors[campo]` itera como `str`, não `ValidationError`.
3. Quatro cenários de fronteira de `_post_clean` exercitados via `PhoneLineForm`/`PhoneLineUpdateForm` reais (arquivo de teste temporário dentro de `telecom/`, executado via pytest, removido integralmente ao final desta verificação — nenhum resquício no diff). Nenhum defeito encontrado; 1 lacuna real de cobertura identificada (e-mail inválido na edição).
4. `telecom/test_whatsapp_seal.py`: 1 teste novo, `test_invalid_email_format_on_edit_does_not_reuse_stale_value`, fechando a lacuna do item 3 — GREEN na primeira execução (comportamento já correto; não é correção de defeito).
5. Overflow de 4px: `git diff main -- static/css/styles.css templates/base/base.html` (sem diferença) + verificação em navegador real (Playwright/Chromium local) comparando a página do formulário (tocada) contra `telecom/simcards/` (não tocada por esta feature) no mesmo viewport/sessão/ferramenta — mesmos 4px nas duas. Ambiente de QA (banco `lineops-db` porta 5433, usuário sintético, servidor local porta 8771) criado, usado e encerrado/limpo integralmente nesta tarefa.
6. Fonte da verdade atualizada com este relatório; status consolidado no topo do documento; checkbox de SEL-11 marcada.

### Test Checklist

- [x] `_post_clean`: preserva validação normal do Django — confirmado por leitura de código (nenhum `try/except`/`return` que pule `super()._post_clean()`).
- [x] `_post_clean`: não suprime erro legítimo nem esvazia lista de erros de um campo — confirmado por leitura de código (guarda `remaining and len(remaining) != len(...)`).
- [x] `_post_clean`: não reutiliza valor antigo para mascarar entrada inválida na edição — confirmado por cenário novo (e-mail inválido na edição, valor antigo intacto no banco) + teste de regressão novo.
- [x] `_post_clean`: não permite gravação parcial — confirmado por leitura de código + testes HTTP já existentes (`test_invalid_http_post_keeps_errors`, `test_invalid_http_edit_keeps_errors_and_does_not_persist_partial_data`).
- [x] `_post_clean`: funciona nos dois forms e com `save(commit=False)` — confirmado por herança sem override + cenários via `PhoneLineUpdateForm`.
- [x] `_post_clean`: evita duplicação sem comparação frágil de texto traduzido — confirmado (constante `REQUIRED_FIELD_ERRORS` do próprio domínio, fonte única).
- [x] `_post_clean`: formato inválido em campo de data (não só e-mail) — confirmado, sem defeito.
- [x] `_post_clean`: múltiplos campos inválidos simultâneos — confirmado, sem vazamento cruzado.
- [x] Overflow de 4px: mesma viewport/zoom/navegador/ferramenta/sessão — confirmado (360×740, Playwright/Chromium local, mesma sessão).
- [x] Overflow de 4px: comparação com página não tocada por esta feature — **nova evidência**, `telecom/simcards/` apresenta o mesmo excedente idêntico (364/360).
- [x] Overflow de 4px: elemento/causa identificados — `.app-main` (padding do breakpoint móvel), CSS/template confirmadamente não tocados por esta feature (`git diff main` vazio).
- [x] Overflow de 4px: efeito sobre acesso a campos/botões/ações — nenhum (já registrado em SEL-10: screenshot sem corte de conteúdo nem barra de rolagem visível; não reavaliado nesta tarefa por não haver mudança de código).
- [x] Cinco campos/choices/obrigatoriedade/vencimento manual — sem divergência, revisado.
- [x] Datas iguais/invertidas e indicadores por data local — sem divergência, revisado.
- [x] Limpeza Sem selo, troca, edição, reativação — sem divergência, revisado.
- [x] Preservação de `activated_at`/status/alocação/histórico — sem divergência, revisado.
- [x] Migration aditiva, reversível, preserva registros antigos — confirmado por leitura do arquivo de migration.
- [x] Permissões e isolamento nas três superfícies — sem divergência, revisado.
- [x] Payload sem e-mail/pagamento desnecessários — sem divergência, revisado.
- [x] Renderização segura e ausência de recálculo de domínio no JS — confirmado por leitura de `overview.html` (createElement/textContent, mapeamento tom→classe idêntico ao partial server-side).
- [x] Consistência entre detalhe/overview/OPERATOR — sem divergência, revisado.
- [x] Fallback sem JS, labels, foco, ações — sem divergência, revisado.
- [x] Ausência de código temporário/credenciais/fixtures QA/artefatos acidentais no diff — confirmado (`git diff` + `git status` limpos; artefatos de QA desta e de sessões anteriores nunca versionados).
- [x] Documentação coerente com estado final — esta atualização.
- [x] Suíte consolidada (`test_whatsapp_seal.py test_phoneline_form_ui.py test_seal_detail_and_listing.py tests.py tests_line_timeline.py`) — **301 passed, 1 skipped**.
- [x] `manage.py check` — limpo.
- [x] `manage.py makemigrations --check --dry-run` — exit 1, drift pré-existente reconfirmado, **não descrito como limpo**, nenhum arquivo novo escrito.
- [x] `git diff --check` — exit 0, sem erros de espaço em branco.
- [x] Isolamento do banco confirmado antes dos testes (config/settings.py, SQLite dedicado sob pytest).

### Test Strategy

Revisão de código com leitura direta do Django instalado (fonte primária, não suposição) para validar o mecanismo de `_post_clean`; verificação empírica isolada de comportamento de `ErrorList` (script fora do repositório) antes de confiar na leitura; quatro cenários de fronteira via `PhoneLineForm`/`PhoneLineUpdateForm` reais para cobrir combinações não exercitadas por SEL-10; 1 teste de regressão permanente só para a lacuna real encontrada (e-mail inválido na edição — os outros três cenários não geraram teste novo por não terem revelado lacuna nem defeito, conforme instrução de não duplicar cobertura). Para o overflow: comparação de diff de código-fonte (`git diff main`) combinada com medição em navegador real (Playwright/Chromium local) numa página comprovadamente não tocada por esta feature, en vez de aceitar a classificação anterior por similaridade. Suíte consolidada, `manage.py check`, `makemigrations --check --dry-run` e `git diff --check` executados uma vez sobre o estado final, conforme instrução explícita de não repetir sem necessidade.

Comandos e resultados:

```powershell
venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal.py -q
```
Resultado: **38 passed, 2 warnings** (37 pré-existentes de SEL-10 + 1 novo desta tarefa), GREEN na primeira execução.

```powershell
venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/test_seal_detail_and_listing.py telecom/tests.py telecom/tests_line_timeline.py -q
```
Resultado: **301 passed, 1 skipped, 2 warnings, 5 subtests passed in 199.75s** (300 antes do teste novo desta tarefa — consistente com SEL-10 registrar 299 antes de seu próprio teste novo).

```powershell
venv\Scripts\python.exe manage.py check
```
Resultado: `System check identified no issues (0 silenced)`.

```powershell
venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```
Resultado (exit 1): mesmo drift pré-existente já registrado em SEL-05/06/09 — `dashboard/migrations/0010_alter_dailyuseraction_action_type.py` (`AlterField` em `dailyuseraction.action_type`) e `telecom/migrations/0022_alter_phoneline_origem.py` (`AlterField` em `phoneline.origem`), nenhum arquivo novo escrito (confirmado por `git status --short -- telecom/migrations dashboard/migrations`, só a `0021` já existente aparece). `RuntimeWarning` de rede (`could not translate host name "db"`) reconfirmado, mesma limitação de ambiente local já registrada. **Não descrito como limpo.**

```powershell
git diff --check
```
Resultado: exit 0, sem erro de espaço em branco (só avisos informativos de normalização de fim de linha LF→CRLF, não são erros de `--check`).

Verificação de overflow em navegador real (fora dos comandos padrão da tarefa, evidência adicional desta revisão):
```
docker compose up -d db
DB_HOST=localhost DB_PORT=5433 venv\Scripts\python.exe manage.py migrate --noinput   # sem pendências, drift conhecido não aplicado
DB_HOST=localhost DB_PORT=5433 DEBUG=True venv\Scripts\python.exe manage.py runserver 127.0.0.1:8771 --noreload
node sel11_overflow_compare.js   # Playwright/Chromium local, viewport 360x740
```
Resultado: `phoneline_create` (tocada) → `{"clientWidth":360,"scrollWidth":364}`; `simcard_list` (não tocada por esta feature) → `{"clientWidth":360,"scrollWidth":364}` — **idêntico**. Servidor, usuário sintético e container `lineops-db` encerrados/removidos ao final (confirmado por `netstat` sem processo em `LISTENING` na porta 8771 e `docker compose stop db`).

### Compliance Report

**Achados resolvidos nesta tarefa:**
- Lacuna de cobertura (severidade baixa, não é defeito de aplicação): e-mail inválido na edição não tinha nenhum teste de regressão automatizado, apesar de ser exatamente o comportamento que a correção histórica de SEL-06 e a de SEL-10 existem para proteger. Fechada com `test_invalid_email_format_on_edit_does_not_reuse_stale_value`, GREEN na primeira execução — comportamento já estava correto, só faltava prova permanente.
- Lacuna de evidência (severidade baixa): classificação de "preexistente" do overflow de 4px em SEL-10 se apoiava em comparação entre páginas todas modificadas por esta própria feature. Fechada com comparação contra página comprovadamente não tocada (`telecom/simcards/`) e `git diff main` do CSS/base compartilhado, mostrando resultado idêntico — a classificação "pré-existente, não introduzido por esta feature" passa de presunção para comprovada.

**Achados pendentes:** nenhum. Nenhuma divergência nova encontrada em `_post_clean` (correção de SEL-10 se sustenta sob os quatro cenários adicionais de fronteira testados). Overflow de 4px continua não corrigido — decisão de escopo já tomada e agora melhor fundamentada (defeito de base `.app-main`/`.app-shell`, compartilhado por toda a aplicação, fora do escopo desta feature; corrigi-lo exigiria alterar CSS usado por todas as páginas do sistema).

**Avaliação explícita de `_post_clean`:** correto. Preserva as validações normais do Django (chama `super()._post_clean()` integralmente), não suprime erros legítimos (guarda contra esvaziar lista de erros), não reutiliza valor antigo para mascarar entrada inválida na edição (confirmado por cenário novo com evidência de banco), não permite gravação parcial (não interfere em `cleaned_data`/`is_valid()`), funciona nos dois forms e com `save(commit=False)` (herança sem override, delegação padrão do `ModelForm`), e evita duplicação sem depender de comparação frágil de texto traduzido (usa constante própria do domínio, não mensagem built-in do Django).

**Avaliação explícita do overflow de 4px:** **pré-existente, comprovado por comparação equivalente** (não apenas presumido por semelhança visual, correção da lacuna de evidência de SEL-10). Mesma viewport (360×740), mesmo navegador/ferramenta (Playwright/Chromium local), mesma sessão; comparação contra `telecom/simcards/`, página que este branch inteiro nunca tocou (ausente de `git diff main --stat`), resultado idêntico (364/360 nas duas); causa (`~.app-main`, padding do breakpoint móvel) confirmada por `git diff main -- static/css/styles.css templates/base/base.html` vazio. Não é descumprimento da spec desta feature transformado em exceção sem decisão — é um defeito de infraestrutura de layout pré-existente e documentado, fora do escopo de "Cadastro de linha com SELO WHATS LINEOPS". Não corrigido nesta tarefa (ampliar correção para `.app-main`/`.app-shell` afetaria toda a aplicação, fora dos limites desta entrega).

**Arquivos alterados nesta tarefa:** `telecom/test_whatsapp_seal.py` (1 teste novo, `test_invalid_email_format_on_edit_does_not_reuse_stale_value`) e este arquivo de spec (relatório de SEL-11, status consolidado). Nenhuma alteração em `telecom/forms.py`, `telecom/models.py`, `telecom/views.py`, `telecom/whatsapp_seal.py`, templates, JavaScript ou migrations nesta tarefa — nenhum defeito de aplicação foi encontrado que exigisse correção.

**Comandos e resultados finais:** ver Test Strategy acima — suíte consolidada 301 passed/1 skipped, `manage.py check` limpo, `makemigrations --check --dry-run` exit 1 (drift pré-existente, não corrigido), `git diff --check` exit 0.

**Limitações, drift e skips:** drift pré-existente em `telecom.PhoneLine.origem` e `dashboard.DailyUserAction.action_type` reconfirmado nesta tarefa, não corrigido, não incorporado a nenhuma migration desta feature, conforme instrução explícita de não corrigir drift alheio. 1 teste pulado (`skipped`) na suíte consolidada — mesmo skip já presente em todo o histórico desta spec (SEL-05 em diante), não investigado nesta tarefa por ser pré-existente e fora do escopo de revisão desta feature especificamente (não é um teste do selo). `manage.py migrate --plan`/checagem de histórico de migração contra o Postgres operacional segue indisponível neste ambiente local (mesma limitação de rede de todas as sessões anteriores); não bloqueante, pois toda prova de migração já foi feita em banco isolado (SQLite de teste e Postgres de desenvolvimento local, nunca operacional).

**Estado das tarefas:**
- SEL-01 a SEL-09: concluídas (evidência nas seções correspondentes desta spec, não reaberta nesta tarefa).
- SEL-10: concluída (validação em navegador real, defeito de `_post_clean` encontrado e corrigido, revalidado).
- SEL-11: **concluída nesta tarefa.**

**Veredito: pronta para integração.** Todos os 11 itens da entrega (SEL-01 a SEL-11) atendem seus critérios de aceite com evidência registrada. Nenhum achado bloqueante pendente. Drift de migrations pré-existente e fora de escopo é a única pendência de ambiente, já documentada e explicitamente não bloqueante para esta feature (não é gerado nem agravado por ela). Decisão de integração (merge/commit/push/deploy) permanece com o usuário — nenhuma dessas ações foi executada nesta tarefa, conforme limite explícito.

Nenhum commit, push, merge, deploy ou acesso a banco operacional nesta tarefa. Nenhuma migration aplicada em qualquer banco (só leitura via `--dry-run`). Recursos de QA iniciados nesta tarefa (servidor local porta 8771, container `lineops-db`, usuário sintético `sel11qa_admin@test.local`, script `sel11_overflow_compare.js` no scratchpad) encerrados/removidos ao final — nenhum resquício no repositório nem no banco isolado.

## Conferência e preparação do commit — 2026-09-21

Revisão do diff da feature, migration, domínio, integração dos forms (incluindo delegação de _post_clean ao Django), renderização e testes. Nenhum novo bloqueio encontrado nesta conferência. Corrigida indicação desatualizada de próxima tarefa nesta spec. Sem mudança de código de aplicação nem nova conferência visual.

Validação executada nesta preparação: suíte consolidada dos cinco arquivos de testes — 301 passed, 1 skipped, 5 subtests passed em 183,80s. Três warnings: duas depreciações preexistentes de CheckConstraint e cache pytest sem acesso. manage.py check limpo. makemigrations(check=True, dry_run=True), com configuração SQLite ativada por import pytest, retornou exit 1 exclusivamente pelo drift conhecido de PhoneLine.origem e DailyUserAction.action_type; nenhum arquivo gerado. git diff --cached --check limpo.

Stage seletivo: 17 arquivos da feature (aplicação, migration, testes, templates, JS, spec e apontador do plano). Documento de auditoria anterior, docs/specs, artefatos .superpowers e configurações de agentes preservados fora do stage. Commit apenas preparado; nenhum commit, push, merge ou deploy executado.
