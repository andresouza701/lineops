# Especificacao Tecnica Complementar - Reconexao Web no LineOps

## Fonte de verdade

- Contrato principal: `docs/PLATFORM_WEB_RECONNECT_CONTRACT.md`
- Esta especificacao complementa o contrato para fechar lacunas de implementacao no LineOps.
- Regra de prioridade: contrato > esta especificacao > testes > codigo

## Objetivo

Implementar no LineOps um fluxo web de reconexao em que a aplicacao:

1. registra no Mongo a intencao de reconectar uma linha
2. mostra ao usuario em que estado a sessao de reconexao se encontra
3. aceita o codigo informado pelo usuario quando a sessao estiver pronta
4. grava esse codigo no mesmo documento da collection `RPA.reconnect_sessions`
5. permite cancelar a sessao enquanto ela nao estiver finalizada

O LineOps nao abre MEmu, nao abre WhatsApp e nao digita o codigo.
Essas etapas continuam sendo responsabilidade exclusiva do RPA.

## Escopo funcional

### Fluxo web

O fluxo ficara na area `telecom`, associado a uma `PhoneLine`.

O usuario podera:

1. abrir o detalhe da linha
2. iniciar a reconexao
3. acompanhar o status por polling
4. informar o codigo quando o status for `WAITING_FOR_CODE`
5. visualizar o QR de conexao quando o status for `WAITING_FOR_QR_SCAN`
6. cancelar a sessao enquanto ela estiver ativa

### Fora de escopo

- Persistir a sessao de reconexao em modelos Django locais
- Espelhar estados do RPA em `PhoneLine.status`
- Automatizar qualquer interacao com MEmu ou WhatsApp

## Premissas obrigatorias de implementacao

### Resolucao de `phone_number`

- O LineOps armazenara e consultara `PhoneLine.phone_number` como hoje.
- Para o documento Mongo, `phone_number` sera sempre enviado somente com digitos.
- Exemplo:
  - `+5511999990001` no Django
  - `5511999990001` no Mongo

### Resolucao de `vm_name`

- Enquanto o dominio local nao tiver um campo proprio para o identificador da VM MEmu, `vm_name` sera igual ao `phone_number` normalizado em digitos.
- Essa decisao segue o comportamento descrito no contrato e o exemplo fornecido.

### Resolucao de `target_server`

- `target_server` sera resolvido a partir de `PhoneLine.origem`.
- Apenas linhas com origem `SRVMEMU-*` sao elegiveis para reconexao via RPA.
- O mapeamento de origem para hostname curto sera configurado via settings.
- Mesmo que o settings contenha outras chaves, o LineOps deve bloquear o inicio da reconexao para origens fora de `SRVMEMU-*`.
- Se a linha nao tiver origem elegivel ou nao houver mapeamento configurado, o LineOps deve bloquear o inicio da reconexao com erro de regra de negocio.

### Resolucao de `device_name`

- `device_name` sera resolvido na seguinte ordem:
  1. nome do usuario da alocacao ativa da linha
  2. `phone_number` normalizado em digitos
- O valor final sera truncado para no maximo 50 caracteres antes de ser salvo no Mongo.

### Politica de sessao ativa

- Se ja existir uma sessao ativa para o mesmo telefone com `active_lock=true`, o LineOps deve reaproveitar a sessao existente.
- O LineOps nao abrira uma nova sessao concorrente para o mesmo telefone.

### Politica de visibilidade e acao

- Os mesmos papeis que podem acessar o detalhe da linha podem visualizar o status da reconexao daquela linha.
- Os mesmos papeis que podem visualizar o detalhe da linha podem iniciar a reconexao, enviar codigo e cancelar, respeitando a visibilidade da linha ja aplicada no dominio atual.

### Politica de persistencia local

- O estado da reconexao nao sera salvo em tabelas Django.
- O LineOps sempre buscara o estado atual diretamente no Mongo.
- A tela deve conseguir reencontrar a sessao ativa da linha pelo telefone quando ainda nao conhecer um `session_id`.
- Depois que a UI receber um `session_id`, o polling deve continuar consultando essa mesma sessao por `_id`, inclusive se ela ja tiver ficado terminal.

### Politica de polling

- O cliente web fara polling de `1s` enquanto houver sessao conhecida nao terminal.
- Enquanto a UI ainda nao conhecer um `session_id`, ela pode descobrir a sessao atual da linha pela busca de sessao ativa por telefone.
- Depois que a UI conhecer um `session_id`, ela deve continuar consultando esse identificador para nao perder estados terminais que forem gravados de forma assincrona pelo RPA.
- Se a sessao receber `cancel_requested_at` mas ainda nao tiver ficado terminal, a UI pode representar esse estado como `CANCEL_REQUESTED` para deixar explicito que o pedido de cancelamento foi aceito e ainda depende do RPA.
- Estados terminais:
  - `CONNECTED`
  - `FAILED`
  - `CANCELLED`

## Contrato interno do LineOps

### Boundary de infraestrutura

Sera criada uma camada de repositorio para `RPA.reconnect_sessions`, isolando:

- `insertOne` da sessao inicial
- busca de sessao por `_id`
- busca de sessao ativa por telefone
- `updateOne` condicional para `pair_code`
- `updateOne` condicional para cancelamento

### Boundary de servico

Sera criado um servico de aplicacao responsavel por:

- validar se a linha pode ser reconectada
- resolver `phone_number`, `vm_name`, `target_server` e `device_name`
- reaproveitar sessao ativa quando existir conflito
- traduzir o documento Mongo para um DTO de UI
- aplicar regras de envio de codigo e cancelamento

### Boundary web

Serao expostos endpoints Django na app `telecom` para:

- iniciar reconexao
- consultar status atual
- enviar codigo
- cancelar sessao

As views devem permanecer finas e delegar a regra de negocio ao servico.

## Regras de dominio locais

- O fluxo de reconexao nao altera `PhoneLine.status`.
- Historico automatico de `PhoneLine` nao deve registrar estados operacionais do RPA.
- O fluxo usa a linha apenas como contexto de autorizacao e resolucao de metadados.

## Estrategia de testes

### Testes unitarios

- resolucao de payload inicial para o Mongo
- resolucao de `target_server`
- resolucao de `device_name`
- reaproveitamento de sessao ativa
- envio de codigo em maiusculo com `attempt` atual
- tratamento de falha de `modifiedCount == 0`
- cancelamento de sessao ativa

### Testes web

- renderizacao da area de reconexao no detalhe da linha
- inicio da reconexao via endpoint
- consulta de status da sessao via endpoint JSON
- consulta de status terminal por `session_id` via endpoint JSON
- envio de codigo permitido apenas em `WAITING_FOR_CODE`
- renderizacao do QR via `qr_image_data_url` sem duplicar `qr_image_base64` no payload web
- cancelamento de sessao via endpoint
- negacao de acesso quando o usuario nao pode ver a linha

## Dependencias e configuracao

Serao adicionadas configuracoes de ambiente para:

- habilitar o fluxo de reconexao
- definir conexao Mongo
- definir database e collection
- mapear `PhoneLine.origem` para `target_server`

Tambem e obrigatorio que a collection Mongo tenha um indice unico parcial em
`phone_number` com `partialFilterExpression: { active_lock: true }`.

Sem esse indice, o LineOps deve bloquear a abertura de novas sessoes para evitar
concorrencia inconsistente.

## Criterios de aceite

- o usuario consegue iniciar a reconexao a partir de uma linha elegivel
- o LineOps cria ou reaproveita a sessao correta no Mongo
- o estado exibido ao usuario acompanha o documento de `reconnect_sessions`
- o campo de codigo so fica operacional em `WAITING_FOR_CODE`
- o QR fica visivel ao usuario quando a sessao estiver em `WAITING_FOR_QR_SCAN`
- o polling preserva o ultimo estado da sessao quando a UI ja conhece o `session_id`
- o codigo e salvo corretamente com `attempt` e historico `last_pair_code*`
- o usuario consegue cancelar uma sessao nao terminal
- se a sessao ainda estiver `QUEUED`, o LineOps consegue encerra-la imediatamente em `CANCELLED`
- se a sessao ja estiver em andamento, a UI mostra `CANCEL_REQUESTED` ate o RPA concluir o encerramento
- o fluxo nao altera `PhoneLine.status`
