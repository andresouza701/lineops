# Runbook de QA - Reconexao Web WhatsApp

## Fonte de verdade

- Contrato principal: `docs/PLATFORM_WEB_RECONNECT_CONTRACT.md`
- Especificacao complementar: `docs/PLATFORM_WEB_RECONNECT_IMPLEMENTATION_SPEC.md`
- Implementacao web:
  - `telecom/views.py`
  - `telecom/services/reconnect_service.py`
  - `telecom/repositories/reconnect_sessions.py`

## Objetivo

Validar em QA o fluxo ponta a ponta em que:

1. o usuario inicia a reconexao no LineOps
2. o LineOps cria ou reaproveita a sessao no Mongo
3. o RPA processa a sessao na collection `RPA.reconnect_sessions`
4. o usuario informa o codigo no LineOps quando a sessao estiver em `WAITING_FOR_CODE`
5. o RPA consome o codigo e conclui a sessao

O LineOps nao abre MEmu e nao interage diretamente com o WhatsApp.

## Escopo do teste

### Em escopo

- criacao da sessao no Mongo
- polling de status na tela da linha
- envio do codigo de conexao
- cancelamento de sessao nao terminal
- integracao indireta com o RPA por meio da mesma collection Mongo

### Fora de escopo

- automacao do MEmu pelo LineOps
- mudanca de `PhoneLine.status`
- persistencia local da sessao de reconexao em tabelas Django

## Pre-condicoes de QA

### Aplicacao

- build de QA publicada com a implementacao da reconexao
- dependencia `pymongo==4.10.1` disponivel no ambiente
- migracoes aplicadas
- assets publicados com `collectstatic`
- aplicacao reiniciada apos configuracao das variaveis

### Configuracao

As variaveis abaixo devem estar definidas no ambiente de QA:

```env
RECONNECT_ENABLED=True
RECONNECT_MONGO_URI=mongodb://<host-qa>:27017/
RECONNECT_MONGO_DATABASE=RPA
RECONNECT_MONGO_COLLECTION=reconnect_sessions
RECONNECT_POLL_INTERVAL_MS=1000
RECONNECT_TARGET_SERVER_MAP={"SRVMEMU-01":"<srv01>","SRVMEMU-02":"<srv02>","SRVMEMU-03":"<srv03>","SRVMEMU-04":"<srv04>","SRVMEMU-05":"<srv05>","SRVMEMU-06":"<srv06>"}
```

### Infraestrutura

- a aplicacao web de QA consegue conectar no Mongo configurado
- o RPA de QA le a mesma database e a mesma collection
- a collection `RPA.reconnect_sessions` possui indice unico parcial por `phone_number` com `active_lock=true`
- existe pelo menos uma linha de teste elegivel com origem `SRVMEMU-*`
- o usuario de QA usado no teste tem permissao para visualizar o detalhe da linha

Validacao recomendada do indice antes do teste:

```javascript
db.reconnect_sessions.getIndexes()
```

Deve existir um indice equivalente a:

```javascript
db.reconnect_sessions.createIndex(
  { phone_number: 1 },
  {
    unique: true,
    partialFilterExpression: { active_lock: true }
  }
)
```

### Dados recomendados da linha de teste

- `PhoneLine.phone_number` valido
- `PhoneLine.origem` em `SRVMEMU-01` a `SRVMEMU-06`
- `PhoneLine.canal` preenchido
- alocacao ativa opcional, mas recomendada para o `device_name`

## Comandos de deploy e sanity check

Executar no deploy de QA:

```powershell
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

Sanity checks recomendados apos o restart:

```powershell
python manage.py check
```

```text
GET /health/ -> 200
GET /accounts/login/ -> 200
```

## Rotas relevantes

### UI

- `GET /telecom/phonelines/<id>/`

### Endpoints JSON do fluxo

- `GET /telecom/phonelines/<id>/reconnect/status/`
- `POST /telecom/phonelines/<id>/reconnect/start/`
- `POST /telecom/phonelines/<id>/reconnect/code/`
- `POST /telecom/phonelines/<id>/reconnect/cancel/`

## Papeis autorizados

O fluxo de reconexao fica disponivel para os mesmos papeis configurados no detalhe da linha:

- `admin`
- `super`
- `backoffice`
- `gerente`

O usuario tambem precisa enxergar a linha dentro das regras de visibilidade ja existentes no dominio.

## Roteiro de execucao em QA

### 1. Abrir a linha de teste

1. Fazer login no LineOps QA.
2. Abrir o detalhe da linha de teste em `Telecom > Detalhe da Linha`.
3. Confirmar a presenca do card `Reconexao WhatsApp`.

Resultado esperado:

- a tela mostra o card de reconexao
- o estado inicial aparece como `Sem sessao ativa`
- o botao `Iniciar reconexao` fica visivel

### 2. Iniciar a reconexao

1. Clicar em `Iniciar reconexao`.
2. Acompanhar a mudanca de status na tela.
3. Validar no Mongo a criacao ou reutilizacao do documento.

Resultado esperado no LineOps:

- a tela deixa de mostrar `Sem sessao ativa`
- um `session_id` aparece
- o status inicial esperado e `QUEUED`, salvo se uma sessao ativa ja existir e for reaproveitada

Resultado esperado no Mongo:

```javascript
db.reconnect_sessions.find(
  { phone_number: "<telefone_so_com_digitos>" },
  {
    _id: 1,
    phone_number: 1,
    vm_name: 1,
    target_server: 1,
    assigned_server: 1,
    status: 1,
    attempt: 1,
    active_lock: 1,
    device_name: 1,
    created_at: 1,
    updated_at: 1
  }
).sort({ created_at: -1 }).limit(1)
```

Campos esperados no documento criado:

- `_id` iniciado por `manual_reconnect_`
- `phone_number` somente com digitos
- `vm_name` igual ao telefone normalizado
- `target_server` resolvido a partir de `PhoneLine.origem`
- `assigned_server` inicialmente `null`
- `status` inicialmente `QUEUED`
- `attempt` inicialmente `0`
- `active_lock` igual a `true`
- `device_name` preenchido

### 3. Validar o polling e a evolucao do RPA

1. Aguardar o RPA processar a sessao.
2. Confirmar que a tela atualiza automaticamente sem refresh manual.
3. Observar a evolucao de status ate `WAITING_FOR_CODE`.

Status esperados durante o fluxo:

- `QUEUED`
- `EMULATOR_STARTING`
- `WAITING_FOR_CODE`
- `SUBMITTING_CODE`
- `CONNECTED`
- `FAILED`
- `CANCELLED`

Resultado esperado:

- enquanto a sessao nao for terminal, o LineOps continua atualizando o estado
- ao entrar em `WAITING_FOR_CODE`, o formulario `Codigo de conexao` fica visivel

### 4. Enviar o codigo de conexao

1. Quando a sessao estiver em `WAITING_FOR_CODE`, digitar o codigo no campo `Codigo de conexao`.
2. Clicar em `Enviar codigo`.
3. Confirmar no Mongo que o codigo foi salvo no mesmo documento.

Resultado esperado no LineOps:

- a submissao nao retorna erro
- o campo pode desaparecer depois que o status sair de `WAITING_FOR_CODE`
- o status pode evoluir para `SUBMITTING_CODE`

Resultado esperado no Mongo:

```javascript
db.reconnect_sessions.find(
  { _id: "<session_id>" },
  {
    pair_code: 1,
    pair_code_attempt: 1,
    pair_code_submitted_at: 1,
    last_pair_code: 1,
    last_pair_code_attempt: 1,
    last_pair_code_submitted_at: 1,
    status: 1,
    attempt: 1
  }
)
```

Campos esperados apos o envio:

- `pair_code` preenchido
- `pair_code_attempt` igual ao `attempt` atual
- `pair_code_submitted_at` preenchido
- `last_pair_code` preenchido
- `last_pair_code_attempt` preenchido
- `last_pair_code_submitted_at` preenchido

Observacao:

- o LineOps envia o codigo em maiusculo
- o LineOps nao sobrescreve `pair_code` se o documento ja tiver um valor preenchido para a mesma tentativa

### 5. Validar a conclusao da sessao

1. Aguardar o RPA consumir o codigo.
2. Acompanhar a sessao ate um estado terminal.

Resultado esperado:

- sucesso: `CONNECTED`
- falha: `FAILED`
- cancelamento: `CANCELLED`

Ao final:

- o polling para automaticamente
- o botao `Iniciar reconexao` volta a ficar disponivel
- a tela nao altera `PhoneLine.status`

### 6. Validar o cancelamento

Executar um segundo ciclo ou usar uma sessao ainda nao terminal.

1. Iniciar a reconexao.
2. Antes do estado terminal, clicar em `Cancelar sessao`.
3. Confirmar a marcacao de cancelamento no Mongo.
4. Validar a resposta do RPA para a sessao.

Resultado esperado no Mongo:

```javascript
db.reconnect_sessions.find(
  { _id: "<session_id>" },
  {
    cancel_requested_at: 1,
    status: 1,
    updated_at: 1
  }
)
```

Resultado esperado:

- se a sessao ainda estiver em `QUEUED`, o LineOps pode encerrar imediatamente em `CANCELLED`
- se a sessao ja estiver em andamento, `cancel_requested_at` fica preenchido e a UI passa a exibir `CANCEL_REQUESTED`
- com o RPA novo, a sessao deve evoluir depois para `CANCELLED`
- com RPA antigo, a sessao pode permanecer em `CANCEL_REQUESTED` ate encerramento manual no Mongo

## Evidencias minimas para aceite

- screenshot da tela antes de iniciar a sessao
- screenshot da tela com `WAITING_FOR_CODE`
- screenshot da tela em estado terminal
- snapshot do documento Mongo apos a criacao
- snapshot do documento Mongo apos o envio do codigo
- snapshot do documento Mongo ao final da sessao
- horario do teste
- identificacao da linha testada
- identificacao do `session_id`

## Checklist de aceite

- o card `Reconexao WhatsApp` aparece para o usuario autorizado
- a sessao e criada ou reaproveitada corretamente no Mongo
- o status mostrado na tela acompanha o documento da collection
- o formulario de codigo so fica disponivel em `WAITING_FOR_CODE`
- o codigo e salvo no mesmo documento da sessao
- o cancelamento marca o documento corretamente
- o estado final do RPA aparece na tela
- `PhoneLine.status` nao e alterado pela reconexao

## Troubleshooting

### O card de reconexao nao aparece

Verificar:

- `RECONNECT_ENABLED=True`
- usuario com papel autorizado
- usuario com acesso a essa linha

### O clique em iniciar retorna erro de regra de negocio

Verificar:

- origem da linha em `SRVMEMU-*`
- `RECONNECT_TARGET_SERVER_MAP` contendo a origem da linha
- indice unico parcial da collection para `phone_number` com `active_lock=true`

### O documento nao aparece no Mongo

Verificar:

- `RECONNECT_MONGO_URI`
- acesso de rede do LineOps ao Mongo
- database `RPA`
- collection `reconnect_sessions`
- logs da aplicacao no momento do clique

### O RPA nao pega a sessao

Verificar:

- se o RPA esta lendo a mesma collection
- se o `target_server` gerado e o esperado pelo RPA
- se o documento ficou em `QUEUED` sem atualizacao posterior

### O campo de codigo nao aparece

Verificar:

- se o RPA realmente levou a sessao para `WAITING_FOR_CODE`
- se a tela continua fazendo polling
- se o status endpoint retorna o estado correto

### O front de QA ficou sem estilo

Verificar:

- `python manage.py collectstatic --noinput`
- restart da aplicacao apos o deploy
- configuracao de static no servidor de QA

## Riscos residuais

- para sessoes ja em andamento, o comportamento final de `CANCELLED` depende de o RPA respeitar `cancel_requested_at`
- a garantia forte contra sessao ativa duplicada para o mesmo telefone depende de o indice unico parcial estar presente e saudavel no Mongo do ambiente
- o `target_server` precisa refletir o mapeamento real dos servidores de QA
