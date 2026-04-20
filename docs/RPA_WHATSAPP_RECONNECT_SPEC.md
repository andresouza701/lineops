# Especificacao da Reconexao de Numeros WhatsApp no RPA

Este documento descreve o que foi implementado no RPA para fazer a reconexao
de numeros do WhatsApp Business usando MongoDB como fila logica e fonte unica
de estado.

Este arquivo documenta o comportamento do RPA.
O contrato da plataforma web continua descrito em
`PLATFORM_WEB_RECONNECT_CONTRACT.md`.

## Objetivo

Implementar uma reconexao prioritaria de numeros WhatsApp com estas regras:

- a plataforma cria a sessao direto no Mongo
- o servidor alvo vem da plataforma em `target_server`
- o RPA do servidor correto faz claim da sessao
- o RPA abre o WhatsApp, navega ate o pareamento por numero e espera o codigo
- o codigo vem da plataforma pelo Mongo, nao por SQS
- reconexoes tem prioridade sobre novos pulls da SQS
- contas restritas, restauradas ou banidas sao detectadas automaticamente
- apos parear, o RPA escreve o nome do dispositivo, salva e remove o primeiro
  dispositivo conectado da lista

## Arquitetura implementada

O fluxo foi implementado em cima de 4 blocos:

1. `reconnect_sessions` no MongoDB
   Guarda o estado da sessao, codigo, tentativas, roteamento, heartbeat e
   resultado final.

2. `ReconnectSessionService` / `ReconnectSessionCollection`
   Encapsulam claim atomico, heartbeat, lease, timeout, consumo atomico do
   codigo e finalizacao da sessao.

3. `ReconnectManager`
   Executa a navegacao dentro do WhatsApp Business no MEmu.

4. `orchestrator.py`
   Pausa a SQS enquanto houver backlog de reconexao do servidor atual e drena
   as sessoes pendentes antes de voltar para a fila.

## Arquivos principais

- `orchestrator.py`
  Faz o gate de prioridade, drena backlog e executa a sessao.

- `database/mongodb/collections/reconnect_sessions.py`
  Implementa a collection operacional e os updates atomicos.

- `database/services/reconnect_sessions.py`
  Encapsula regras de negocio da sessao.

- `core/whatsapp_automation/base_manager.py`
  Abre o app, faz dump da tela e detecta estados especiais da conta.

- `core/whatsapp_automation/reconnect_manager.py`
  Executa o fluxo de reconexao, envio do codigo e pos-pareamento.

- `utils/ui_locators.py`
  Registra os locators XML usados pelo fluxo.

- `utils/ui_automator.py`
  Faz clique por XML e digitacao exata para o nome do dispositivo.

- `test_reconnect_flow.py`
  Teste manual ponta a ponta simulando plataforma + RPA via Mongo.

## Modelo de dados

Collection:

- `RPA.reconnect_sessions`

Status ativos:

- `QUEUED`
- `EMULATOR_STARTING`
- `WAITING_FOR_CODE`
- `SUBMITTING_CODE`

Status terminais:

- `CONNECTED`
- `FAILED`
- `CANCELLED`

Campos de entrada esperados da plataforma:

- `_id`
- `phone_number`
- `vm_name`
- `target_server`
- `device_name`
- `status=QUEUED`
- `attempt=0`
- `active_lock=true`
- `assigned_server=null`
- `created_at`
- `updated_at`

Campos mantidos pelo RPA:

- `assigned_server`
- `worker_heartbeat_at`
- `lease_until`
- `session_deadline_at`
- `error_code`
- `error_message`
- `finished_at`
- `cancel_requested_at`
- `account_state`
- `needs_it_action`
- `needs_it_reason`
- `restriction_seconds_remaining`
- `restriction_until`
- `account_state_detected_at`
- `detected_screen_text`

Campos de codigo:

- `pair_code`
  Campo operacional temporario. O RPA consome e remove do documento.

- `pair_code_attempt`
- `pair_code_submitted_at`
- `pair_code_consumed_at`

- `last_pair_code`
  Historico do ultimo codigo enviado pela plataforma.

- `last_pair_code_attempt`
- `last_pair_code_submitted_at`
- `last_pair_code_consumed_at`

## Indices implementados

Na collection `reconnect_sessions` foram criados estes indices:

- indice unico parcial em `phone_number` com `active_lock=true`
- indice em `target_server + status + created_at`
- indice em `assigned_server + status`
- indice em `lease_until`

Objetivo:

- impedir duas reconexoes ativas para o mesmo telefone
- facilitar claim por servidor
- facilitar busca de backlog
- facilitar recuperacao de sessoes stale

## Roteamento por servidor

O servidor alvo da reconexao vem exclusivamente da plataforma:

- campo `target_server`

O fluxo de reconexao nao depende da collection `personas`.

O RPA aceita nome canonico ou alias configurado em:

- `OrchestratorConfig.SERVER_ALIAS_MAP`

Na pratica:

- a plataforma escolhe o servidor
- a sessao e criada com `target_server`
- somente o servidor compativel faz claim da sessao

## Regra de prioridade sobre a SQS

Reconexao tem prioridade sobre novos pulls da SQS.

Regra implementada:

1. se ja existe mensagem SQS em execucao, ela termina
2. antes de novo `receive_message`, o orquestrador consulta backlog de
   reconexao do servidor atual
3. se houver backlog, a SQS e pausada
4. o orquestrador drena todas as reconexoes pendentes do servidor atual
5. so depois volta a puxar mensagens da SQS

Se a reconexao entrar no meio de um lote SQS ja recebido:

- a mensagem atual termina
- as mensagens restantes do lote sao devolvidas para a fila usando
  `change_message_visibility`
- o orquestrador entra imediatamente no backlog de reconexao

O loop principal tambem usa sleep interruptivel para reagir rapido ao backlog.

## Recuperacao de sessoes stale

No boot do orquestrador e tambem durante a drenagem do backlog, o RPA tenta
recuperar sessoes cujo lease expirou.

Quando uma sessao fica stale:

- volta para `QUEUED`
- `assigned_server` e limpo
- `lease_until` e limpo
- `pair_code*` operacional e limpo
- `worker_heartbeat_at` e limpo
- `session_deadline_at` e limpo
- `error_code` vira `stale_session_requeued`

## Fluxo detalhado da reconexao

### 1. Criacao da sessao

A plataforma cria o documento em `RPA.reconnect_sessions` com `status=QUEUED`.

### 2. Claim atomico

O servidor atual faz claim atomico da proxima sessao `QUEUED` compatível com
seu `target_server`.

Ao claimar:

- `assigned_server` recebe o servidor atual
- `status` vira `EMULATOR_STARTING`
- `lease_until` e preenchido
- `worker_heartbeat_at` e preenchido

### 3. Preparacao do emulador

O orquestrador:

- abre a VM do MEmu
- prepara a tela inicial
- instancia o facade `WhatsApp`
- chama `run_reconnect_session(...)`

### 4. Abertura do WhatsApp e inspecao da tela

Toda vez que o WhatsApp e aberto, o `BaseManager.open_app()`:

- abre o app
- faz dump da UI atual
- extrai texto do XML
- classifica a tela

Estados possiveis:

- `NORMAL`
- `RESTRICTED`
- `RESTORED`
- `BANNED`

Prioridade da classificacao:

1. `BANNED`
2. `RESTORED`
3. `RESTRICTED`
4. `NORMAL`

Se a tela vier em estado especial, o RPA nao tenta clicar no botao de backup
e a reconexao termina imediatamente com `FAILED`.

### 5. Deteccao de conta restrita, restaurada e banida

Casos implementados:

- `RESTRICTED`
  - `error_code=whatsapp_account_restricted`
  - `account_state=RESTRICTED`
  - `needs_it_action=false`
  - tenta extrair contador em `HH:MM:SS` / `MM:SS` ou em texto (`1 hora 20 minutos`, `2 hours 5 minutes`)
  - preenche `restriction_seconds_remaining`
  - calcula `restriction_until`

- `RESTORED`
  - `error_code=whatsapp_account_restored_requires_it`
  - `account_state=RESTORED`
  - `needs_it_action=true`
  - `needs_it_reason=manual_reconnect_required`

- `BANNED`
  - `error_code=whatsapp_account_banned`
  - `account_state=BANNED`
  - `needs_it_action=true`
  - `needs_it_reason=account_banned`

Em qualquer um desses tres casos:

- a sessao termina em `FAILED`
- os metadados sao gravados no Mongo
- o emulador e fechado
- o orquestrador segue para a proxima reconexao pendente

### 6. Navegacao ate a tela de pareamento por numero

Quando a conta esta em estado `NORMAL`, o `ReconnectManager` navega por:

1. `Mais opcoes`
2. `Dispositivos conectados`
3. `Conectar dispositivo`
4. `Conectar com numero de telefone`

Os cliques usam localizadores XML cadastrados em `utils/ui_locators.py`.

### 7. Publicacao de `WAITING_FOR_CODE`

Quando a tela de codigo e atingida, a sessao muda para:

- `status=WAITING_FOR_CODE`
- `attempt=attempt+1`
- `session_deadline_at=agora+20min`
- `error_code=null`
- `error_message=null`

Tambem sao limpos:

- `pair_code`
- `pair_code_attempt`
- `pair_code_submitted_at`
- `pair_code_consumed_at`

### 8. Espera do codigo vindo da plataforma

Durante `WAITING_FOR_CODE`, o RPA:

- faz polling do Mongo
- renova lease e heartbeat
- verifica cancelamento
- verifica timeout da janela de codigo
- tenta consumir o codigo de forma atomica

Configuracoes atuais:

- `RECONNECT_SESSION_POLL_SECONDS=1`
- `RECONNECT_SESSION_LEASE_SECONDS=120`
- `RECONNECT_WAITING_CODE_TIMEOUT_SECONDS=1200`

Se a plataforma nao enviar o codigo em 20 minutos:

- a sessao termina em `FAILED`
- `error_code=pair_code_timeout`
- o emulador e fechado
- o orquestrador segue para a proxima reconexao

### 9. Consumo atomico do codigo

Quando a plataforma grava:

- `pair_code`
- `pair_code_attempt`
- `pair_code_submitted_at`
- `last_pair_code`
- `last_pair_code_attempt`
- `last_pair_code_submitted_at`

o RPA consome o codigo com `find_one_and_update`.

Ao consumir:

- `status` vira `SUBMITTING_CODE`
- `pair_code_consumed_at` e preenchido
- `last_pair_code_consumed_at` e preenchido
- `pair_code` e removido do documento

Importante:

- `pair_code` e volatil
- `last_pair_code*` permanece para auditoria

### 10. Submissao do codigo

O RPA:

- localiza o campo do codigo no XML
- toca no campo
- limpa caracteres anteriores
- digita o codigo em maiusculo
- tenta clicar em botao opcional de confirmacao se o build exigir

Depois aguarda um dos resultados:

- sucesso
- codigo expirado
- codigo invalido
- estado desconhecido

Configuracao atual:

- `RECONNECT_POST_SUBMIT_TIMEOUT_SECONDS=20`

### 11. Retry de codigo

Se o codigo for rejeitado ou expirar:

- a sessao volta para `WAITING_FOR_CODE`
- `attempt` e incrementado
- `session_deadline_at` reinicia para mais 20 minutos
- `error_code` e `error_message` sao atualizados
- os campos operacionais de `pair_code*` sao limpos

Erros de retry usados hoje:

- `pair_code_expired`
- `pair_code_invalid`
- `pair_code_not_accepted`
- `code_input_failed`

### 12. Pos-pareamento

Depois que o WhatsApp aceita o codigo, o RPA conclui o pos-pareamento antes de
marcar a sessao como conectada.

Fluxo implementado:

1. detectar a tela `Nome do dispositivo` ou a tela `Dispositivos conectados`
2. se estiver em `Nome do dispositivo`, preencher o nome vindo da plataforma
3. clicar em `Salvar`
4. voltar ou aguardar a tela `Dispositivos conectados`
5. abrir o primeiro dispositivo listado
6. abrir os tres pontinhos
7. clicar em `Remover dispositivo`
8. confirmar em `Remover`
9. aguardar a volta da tela `Dispositivos conectados`
10. concluir a sessao em `CONNECTED`

Observacoes:

- o nome do dispositivo vem de `device_name`
- existe fallback para `linked_device_name`, `platform_device_name` e `name`
- o nome e truncado para 50 caracteres
- a digitacao do nome usa `type_text_exact()` em uma unica chamada ADB para
  evitar corrupcao de texto

### 13. Finalizacao

Casos finais:

- `CONNECTED`
  - sucesso completo
  - `active_lock=false`
  - `finished_at` preenchido

- `FAILED`
  - falha terminal
  - `active_lock=false`
  - `finished_at` preenchido

- `CANCELLED`
  - cancelamento pela plataforma
  - `active_lock=false`
  - `finished_at` preenchido

Ao finalizar, o RPA limpa:

- `lease_until`
- `pair_code`
- `pair_code_attempt`
- `pair_code_submitted_at`
- `pair_code_consumed_at`
- `session_deadline_at`

## Cancelamento pela plataforma

Se a plataforma preencher `cancel_requested_at`, o RPA encerra a sessao como:

- `status=CANCELLED`
- `error_code=cancel_requested`

## Relacao entre `CONNECTED` e proxima sessao

No fluxo real do `orchestrator.py`, depois de uma sessao terminar com
`CONNECTED`, `FAILED` ou `CANCELLED`, o processo continua drenando o backlog de
reconexao do servidor atual.

Ou seja:

- se houver outra sessao pendente para o mesmo servidor, o orquestrador pega a
  proxima
- a SQS so volta a ser consumida quando o backlog de reconexao zerar

## Teste manual implementado

O arquivo `test_reconnect_flow.py` simula a plataforma web e o RPA no mesmo
host.

Ele cobre:

- criacao da sessao no Mongo
- claim da sessao pelo `target_server`
- execucao do fluxo real do `ReconnectManager`
- polling do documento da sessao
- envio manual do codigo como se viesse da plataforma
- cancelamento da sessao
- exibicao dos campos principais, inclusive `last_pair_code*`

Observacao:

- o teste manual processa uma sessao por execucao
- o orquestrador real drena varias sessoes em sequencia

## Configuracoes relevantes

Configuracoes usadas pelo fluxo:

- `ORCHESTRATOR_SERVER_ALIASES`
- `RECONNECT_BACKLOG_POLL_SECONDS`
- `RECONNECT_SQS_REACTIVE_WAIT_SECONDS`
- `RECONNECT_SQS_PRIORITY_BACKOFF_SECONDS`
- `RECONNECT_SESSION_POLL_SECONDS`
- `RECONNECT_SESSION_LEASE_SECONDS`
- `RECONNECT_WAITING_CODE_TIMEOUT_SECONDS`
- `RECONNECT_POST_SUBMIT_TIMEOUT_SECONDS`

Defaults atuais observados no codigo:

- backlog poll: `1s`
- session poll: `1s`
- lease: `120s`
- timeout para receber codigo: `1200s`
- timeout para confirmar submit do codigo: `20s`

## Regras de negocio consolidadas

- reconexao nao usa SQS para receber o codigo
- reconexao usa `target_server` vindo da plataforma como fonte de verdade
- somente um telefone pode ter sessao ativa ao mesmo tempo
- o codigo so pode ser consumido para o `attempt` atual
- o RPA nao interrompe uma mensagem SQS ja em execucao
- o RPA para de puxar novas mensagens SQS enquanto houver backlog de reconexao
- estados especiais da conta sao detectados sempre que o WhatsApp e aberto
- o nome do dispositivo enviado pela plataforma e obrigatorio para o fluxo
  automatico completo

## Limitacoes atuais

- a deteccao de telas depende dos textos presentes no dump XML do build atual
  do WhatsApp Business
- o fluxo de abrir o primeiro dispositivo conectado depende da estrutura atual
  da tela `Dispositivos conectados`
- o teste manual ainda depende de input humano para digitar o codigo de
  pareamento

## Referencia complementar

Para a especificacao do que a plataforma web precisa gravar e ler no Mongo,
consultar:

- `PLATFORM_WEB_RECONNECT_CONTRACT.md`
