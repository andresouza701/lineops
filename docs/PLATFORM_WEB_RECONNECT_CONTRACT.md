# Contrato da Plataforma Web para Reconnect via Mongo

Este documento descreve exatamente o que a plataforma web precisa fazer para
integrar com o fluxo de reconnect do RPA usando a collection
`RPA.reconnect_sessions`.

O contrato abaixo reflete o comportamento atual homologado entre LineOps e RPA.

## Visao geral

A plataforma web fala diretamente com o MongoDB.

Fluxo:

1. A plataforma cria uma sessao em `reconnect_sessions` com `status=QUEUED`.
2. O RPA do servidor correto faz claim da sessao e muda para `EMULATOR_STARTING`.
3. Quando o WhatsApp estiver pronto para receber codigo, o RPA muda a sessao para `WAITING_FOR_CODE`.
4. Se o fluxo disponivel no app for por QR, o RPA muda a sessao para `WAITING_FOR_QR_SCAN` e publica o QR no documento.
5. A plataforma mostra ao usuario que ja pode informar o codigo ou escanear o QR, conforme o status.
6. A plataforma grava o codigo no Mongo quando a sessao estiver em `WAITING_FOR_CODE`.
7. O RPA consome o codigo, envia para o WhatsApp e muda a sessao para `SUBMITTING_CODE`.
8. Se tudo der certo, o RPA finaliza em `CONNECTED`.
9. Se houver falha, timeout, restricao, restauracao ou banimento, o RPA finaliza em `FAILED`.
10. Se a plataforma cancelar:
   - uma sessao ainda em `QUEUED` pode ser finalizada imediatamente pela propria plataforma em `CANCELLED`
   - uma sessao ja em andamento depende do RPA para finalizar em `CANCELLED`

## Banco e collection

- Banco: `RPA`
- Collection: `reconnect_sessions`

### Indice operacional obrigatorio

Para garantir que nao existam duas sessoes ativas concorrentes para o mesmo
telefone, o ambiente precisa ter um indice unico parcial na collection:

```javascript
db.reconnect_sessions.createIndex(
  { phone_number: 1 },
  {
    unique: true,
    partialFilterExpression: { active_lock: true }
  }
)
```

Sem esse indice, a plataforma nao consegue confiar no fluxo de reaproveitamento
por conflito de chave unica descrito neste contrato.

## Campos obrigatorios na criacao da sessao

A plataforma deve criar o documento com estes campos:

```json
{
  "_id": "manual_reconnect_3b661385ece0406692038881b283bd13",
  "phone_number": "19910001737",
  "vm_name": "19910001737",
  "target_server": "rafael",
  "assigned_server": null,
  "status": "QUEUED",
  "attempt": 0,
  "active_lock": true,
  "device_name": "Rafael Gomes",
  "created_at": "2026-04-10T14:24:32.035Z",
  "updated_at": "2026-04-10T14:24:32.035Z"
}
```

### Regras desses campos

- `_id`
  - obrigatorio
  - a plataforma define
  - precisa ser unico por sessao

- `phone_number`
  - obrigatorio
  - usado no lock de sessao ativa
  - nao pode existir outra sessao ativa do mesmo telefone com `active_lock=true`

- `vm_name`
  - obrigatorio na pratica
  - se nao vier, o RPA cai para `phone_number`, mas a plataforma deve mandar `vm_name`
  - deve ser o identificador da VM MEmu

- `target_server`
  - obrigatorio
  - e a fonte de verdade de roteamento
  - deve vir ja resolvido pela plataforma
  - usar hostname curto, por exemplo `rafael`

- `device_name`
  - obrigatorio
  - e o nome que o RPA vai escrever na tela `Nome do dispositivo`
  - o RPA corta para no maximo 50 caracteres

- `status`
  - sempre iniciar com `QUEUED`

- `attempt`
  - sempre iniciar com `0`

- `active_lock`
  - sempre iniciar com `true`

- `assigned_server`
  - sempre iniciar com `null`

## Status usados pelo RPA

- `QUEUED`
  - sessao criada e aguardando claim do RPA

- `EMULATOR_STARTING`
  - o RPA ja pegou a sessao e esta abrindo ou preparando o emulador

- `WAITING_FOR_CODE`
  - o WhatsApp ja esta na tela pronta para receber o codigo
  - nesse momento a plataforma deve liberar a UI para o usuario informar o codigo

- `WAITING_FOR_QR_SCAN`
  - o WhatsApp entrou no fluxo de companion por QR
  - nesse momento a plataforma deve exibir o QR ao usuario e continuar acompanhando essa mesma sessao

- `SUBMITTING_CODE`
  - o RPA ja consumiu o codigo do Mongo e esta digitando ou processando no WhatsApp

- `CONNECTED`
  - sucesso final

- `FAILED`
  - falha final

- `CANCELLED`
  - sessao cancelada pela plataforma

## Campos que a plataforma deve ler

A plataforma deve acompanhar pelo menos:

- `_id`
- `status`
- `attempt`
- `assigned_server`
- `connection_mode`
- `error_code`
- `error_message`
- `session_deadline_at`
- `worker_heartbeat_at`
- `account_state`
- `needs_it_action`
- `needs_it_reason`
- `restriction_seconds_remaining`
- `restriction_until`
- `device_name`
- `qr_image_base64`
- `qr_image_mime_type`
- `qr_image_updated_at`
- `last_pair_code`
- `last_pair_code_attempt`
- `last_pair_code_submitted_at`
- `last_pair_code_consumed_at`

## Como a plataforma deve abrir o reconnect

### Passo 1: criar a sessao

A plataforma deve fazer `insertOne` com o documento inicial.

Se falhar por chave unica em `phone_number` com `active_lock=true`, significa
que ja existe um reconnect ativo para o telefone. Nesse caso a plataforma deve:

- reaproveitar a sessao ativa existente, ou
- bloquear a nova tentativa

### Passo 2: polling da sessao

Apos criar a sessao, a plataforma deve fazer polling do documento.

Intervalo recomendado:

- `1s`

Regra obrigatoria:

- assim que a plataforma conhecer o `_id` da sessao, o polling deve continuar lendo essa mesma sessao por `_id`
- a busca por sessao ativa do telefone deve ser usada apenas para descoberta inicial ou reaproveitamento
- isso evita perder o estado terminal quando o RPA finaliza a sessao de forma assincrona

### Passo 3: esperar `WAITING_FOR_CODE`

A plataforma so deve pedir o codigo ao usuario quando:

- `status == WAITING_FOR_CODE`

Tambem deve usar:

- `attempt`
- `session_deadline_at`

para saber qual tentativa esta aberta e ate quando o codigo pode ser enviado.

### Passo 3B: esperar `WAITING_FOR_QR_SCAN`

Se a sessao entrar em:

- `status == WAITING_FOR_QR_SCAN`

A plataforma deve:

- exibir o QR da sessao ao usuario
- continuar o polling dessa mesma sessao por `_id`
- tratar `CONNECTED`, `FAILED` ou `CANCELLED` como estados terminais dessa mesma sessao

## Como a plataforma deve enviar o codigo

Quando o usuario informar o codigo, a plataforma deve fazer um `updateOne`
condicional.

### Filtro do update

```json
{
  "_id": "manual_reconnect_3b661385ece0406692038881b283bd13",
  "status": "WAITING_FOR_CODE",
  "attempt": 1,
  "$or": [
    { "pair_code": { "$exists": false } },
    { "pair_code": null },
    { "pair_code": "" }
  ]
}
```

### Update correto

```json
{
  "$set": {
    "pair_code": "XBGWR7V6",
    "pair_code_attempt": 1,
    "pair_code_submitted_at": "2026-04-10T14:26:37Z",
    "last_pair_code": "XBGWR7V6",
    "last_pair_code_attempt": 1,
    "last_pair_code_submitted_at": "2026-04-10T14:26:37Z",
    "updated_at": "2026-04-10T14:26:37Z"
  }
}
```

### Regras importantes

- a plataforma deve sempre enviar o codigo em maiusculo
- a plataforma deve sempre enviar o `attempt` atual da sessao
- a plataforma nao deve sobrescrever `pair_code` se ele ja existir
- se `modifiedCount == 0`, a plataforma deve reler a sessao e entender o motivo

### Importante sobre `pair_code`

O campo `pair_code` e temporario.

O RPA consome esse campo e o remove do documento quando comeca a usar o codigo.

Entao:

- `pair_code` = fila operacional temporaria
- `last_pair_code*` = historico ou auditoria

Se a plataforma quiser mostrar depois qual foi o codigo enviado, deve olhar:

- `last_pair_code`
- `last_pair_code_attempt`
- `last_pair_code_submitted_at`
- `last_pair_code_consumed_at`

## Como a plataforma deve reagir quando o codigo falhar

Se o WhatsApp rejeitar ou expirar o codigo, o RPA volta a sessao para:

- `status = WAITING_FOR_CODE`
- `attempt = attempt + 1`

E preenche:

- `error_code`
- `error_message`

Nessa situacao a plataforma deve:

1. reler a sessao
2. mostrar o novo `attempt`
3. pedir um novo codigo ao usuario
4. enviar o novo codigo usando o novo `attempt`

## Timeout de envio do codigo

Quando o RPA entra em `WAITING_FOR_CODE`, ele preenche:

- `session_deadline_at`

Esse e o prazo de 20 minutos para receber o codigo.

Se esse prazo expirar, o RPA finaliza com:

- `status = FAILED`
- `error_code = pair_code_timeout`

Nesse caso a plataforma deve tratar como falha terminal.

## Nome do dispositivo

A plataforma deve enviar o nome do dispositivo ja no momento de criacao da
sessao:

- campo `device_name`

Depois que o codigo e aceito, o RPA:

1. escreve esse nome na tela `Nome do dispositivo`
2. clica em `Salvar`
3. abre o primeiro dispositivo listado
4. entra em `Editar dispositivo`
5. clica em `Remover dispositivo`
6. confirma em `Remover`

Se `device_name` nao vier, a sessao falha com:

- `error_code = missing_device_name`

## Cancelamento pela plataforma

Se a plataforma quiser cancelar a sessao, deve fazer:

```json
{
  "$set": {
    "cancel_requested_at": "2026-04-10T14:30:00Z",
    "updated_at": "2026-04-10T14:30:00Z"
  }
}
```

Filtro:

```json
{
  "_id": "manual_reconnect_3b661385ece0406692038881b283bd13",
  "status": {
    "$nin": ["CONNECTED", "FAILED", "CANCELLED"]
  }
}
```

Quando o RPA perceber isso, ele finaliza em:

- `status = CANCELLED`
- `error_code = cancel_requested`

### Comportamento adicional da plataforma

O LineOps possui uma regra local para evitar sessao presa em fila:

- se a sessao ainda estiver em `QUEUED`, a propria plataforma pode finalizar imediatamente em `CANCELLED`
- se a sessao ja estiver em andamento, a plataforma serializa o estado web como `CANCEL_REQUESTED` ate o RPA concluir o encerramento

`CANCEL_REQUESTED` e um estado de payload web do LineOps, nao um status persistido do contrato Mongo.

## Casos especiais detectados pelo RPA

Toda vez que o WhatsApp e aberto, o RPA faz dump da tela e procura estados
especiais.

### Conta restrita

Se detectar restricao:

- `status = FAILED`
- `error_code = whatsapp_account_restricted`
- `account_state = RESTRICTED`
- `needs_it_action = false`
- `restriction_seconds_remaining`
- `restriction_until`
- `account_state_detected_at`
- `detected_screen_text`

### Conta restaurada

Se detectar tela de conta restaurada:

- `status = FAILED`
- `error_code = whatsapp_account_restored_requires_it`
- `account_state = RESTORED`
- `needs_it_action = true`
- `needs_it_reason = manual_reconnect_required`

### Conta banida

Se detectar banimento:

- `status = FAILED`
- `error_code = whatsapp_account_banned`
- `account_state = BANNED`
- `needs_it_action = true`
- `needs_it_reason = account_banned`

## Como a plataforma deve interpretar o final da sessao

### Sucesso

Se:

- `status = CONNECTED`

Entao o reconnect terminou com sucesso e o RPA real pode seguir para a proxima
sessao pendente do mesmo servidor.

### Falha terminal

Se:

- `status = FAILED`

A plataforma deve olhar:

- `error_code`
- `error_message`
- `account_state`
- `needs_it_action`
- `needs_it_reason`

### Cancelada

Se:

- `status = CANCELLED`

A plataforma deve tratar como encerrada pela acao do usuario ou sistema.

## Ordem esperada dos principais status

Fluxo normal com codigo:

1. `QUEUED`
2. `EMULATOR_STARTING`
3. `WAITING_FOR_CODE`
4. `SUBMITTING_CODE`
5. `CONNECTED`

Fluxo normal com QR:

1. `QUEUED`
2. `EMULATOR_STARTING`
3. `WAITING_FOR_QR_SCAN`
4. `CONNECTED`

Fluxo com retry de codigo:

1. `QUEUED`
2. `EMULATOR_STARTING`
3. `WAITING_FOR_CODE` com `attempt=1`
4. `SUBMITTING_CODE`
5. `WAITING_FOR_CODE` com `attempt=2`
6. `SUBMITTING_CODE`
7. `CONNECTED`

Fluxo com falha:

1. `QUEUED`
2. `EMULATOR_STARTING`
3. `WAITING_FOR_CODE` ou `WAITING_FOR_QR_SCAN`
4. `FAILED`

## Regras obrigatorias para a plataforma web

- sempre gravar em `RPA.reconnect_sessions`
- sempre criar a sessao com `target_server` ja resolvido
- sempre mandar `device_name`
- sempre esperar `WAITING_FOR_CODE` antes de enviar o codigo
- sempre usar o `attempt` atual ao enviar o codigo
- sempre gravar `last_pair_code*` junto com `pair_code*`
- sempre reler a sessao se o update do codigo falhar
- sempre tratar `FAILED` olhando `error_code`, `account_state`, `needs_it_action` e `needs_it_reason`
- sempre tratar `CONNECTED` como final de sucesso
- sempre continuar o polling da sessao conhecida por `_id` para preservar o estado terminal

## Exemplo minimo de ciclo completo

### Criacao

```json
{
  "_id": "reconnect_001",
  "phone_number": "19910001737",
  "vm_name": "19910001737",
  "target_server": "rafael",
  "assigned_server": null,
  "status": "QUEUED",
  "attempt": 0,
  "active_lock": true,
  "device_name": "Rafael Gomes",
  "created_at": "2026-04-10T14:24:32Z",
  "updated_at": "2026-04-10T14:24:32Z"
}
```

### Quando o RPA ficar pronto para codigo

```json
{
  "status": "WAITING_FOR_CODE",
  "attempt": 1,
  "session_deadline_at": "2026-04-10T14:45:57Z"
}
```

### Quando o RPA ficar pronto para QR

```json
{
  "status": "WAITING_FOR_QR_SCAN",
  "connection_mode": "QR_CODE",
  "qr_image_base64": "<base64>",
  "qr_image_mime_type": "image/png",
  "qr_image_updated_at": "2026-04-11T15:16:57Z"
}
```

### Envio do codigo pela plataforma

```json
{
  "pair_code": "XBGWR7V6",
  "pair_code_attempt": 1,
  "pair_code_submitted_at": "2026-04-10T14:26:37Z",
  "last_pair_code": "XBGWR7V6",
  "last_pair_code_attempt": 1,
  "last_pair_code_submitted_at": "2026-04-10T14:26:37Z"
}
```
