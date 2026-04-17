# Guia Operacional - Reconnect WhatsApp

## Objetivo

Este guia descreve como operar o reconnect WhatsApp no LineOps com o RPA, com foco em:

- habilitacao de ambiente
- regra de cadastro da linha
- uso no front
- comportamento esperado de status
- cancelamento
- troubleshooting

Este documento e orientado a operacao. A fonte de verdade tecnica continua sendo:

- `docs/PLATFORM_WEB_RECONNECT_CONTRACT.md`
- `docs/PLATFORM_WEB_RECONNECT_IMPLEMENTATION_SPEC.md`
- `docs/PLATFORM_WEB_RECONNECT_QA_RUNBOOK.md`

## Onde a funcao aparece

No LineOps, o reconnect fica em dois pontos:

1. pagina `Telecom`
   - a coluna `Acoes` mostra o botao `Reconnect`
   - esse atalho leva ao detalhe da linha com a ancora `#reconnect-whatsapp`

2. detalhe da linha
   - o card `Reconexao WhatsApp` mostra status, servidor, erros, QR e acoes

## Quem pode usar

### No detalhe da linha e nos endpoints

Papeis autorizados:

- `admin`
- `super`
- `backoffice`
- `gerente`

O usuario tambem precisa enxergar a linha dentro das regras normais de visibilidade do dominio.

### No botao da pagina `Telecom`

O atalho da coluna `Acoes` hoje aparece apenas para `admin`.

## Regra para a linha nascer pronta para reconnect

Para uma linha estar apta ao reconnect no momento do cadastro, a regra principal e:

- `PhoneLine.origem` precisa ser uma origem `SRVMEMU-*`

Origens aceitas atualmente:

- `SRVMEMU-01`
- `SRVMEMU-02`
- `SRVMEMU-03`
- `SRVMEMU-04`
- `SRVMEMU-05`
- `SRVMEMU-06`

Se a linha for criada com outra origem, o LineOps bloqueia o inicio da reconexao.

## Regra de ambiente para essa linha funcionar

Nao basta a linha ser `SRVMEMU-*`. O ambiente tambem precisa mapear essa origem para o servidor correto do RPA.

Exemplo:

```env
RECONNECT_TARGET_SERVER_MAP={"SRVMEMU-01":"srvmemu01","SRVMEMU-02":"srvmemu02"}
```

Se a linha tiver `origem=SRVMEMU-01`, o LineOps vai criar a sessao com:

- `target_server=srvmemu01`

Sem esse mapeamento, o reconnect nao inicia.

## Pre-requisitos obrigatorios do LineOps

As variaveis abaixo precisam existir no ambiente:

```env
RECONNECT_ENABLED=True
RECONNECT_MONGO_URI=mongodb://<usuario>:<senha>@<host>:27017/...
RECONNECT_MONGO_DATABASE=RPA
RECONNECT_MONGO_COLLECTION=reconnect_sessions
RECONNECT_POLL_INTERVAL_MS=1000
RECONNECT_TARGET_SERVER_MAP={"SRVMEMU-01":"srvmemu01"}
```

Tambem e obrigatorio que a imagem do LineOps tenha a dependencia de runtime:

```txt
pymongo==4.10.1
```

Sem `pymongo`, o card do reconnect pode falhar no front com erro de JSON porque o backend devolve HTML de erro em vez de payload JSON.

## Pre-requisitos obrigatorios do Mongo

A collection `RPA.reconnect_sessions` precisa ter o indice unico parcial:

```javascript
db.reconnect_sessions.createIndex(
  { phone_number: 1 },
  {
    unique: true,
    partialFilterExpression: { active_lock: true }
  }
)
```

Sem esse indice, o LineOps bloqueia a abertura de novas sessoes.

## Fluxo normal

1. usuario clica em `Reconnect`
2. LineOps cria ou reaproveita uma sessao em `RPA.reconnect_sessions`
3. RPA faz claim da sessao
4. LineOps acompanha o status via polling
5. se o RPA entrar em `WAITING_FOR_CODE`, o usuario informa o codigo
6. a sessao termina em `CONNECTED`, `FAILED` ou `CANCELLED`

## Status que podem aparecer no card

- `QUEUED`
  - LineOps criou a sessao e aguarda claim do RPA

- `EMULATOR_STARTING`
  - o RPA pegou a sessao e esta preparando o emulador

- `WAITING_FOR_CODE`
  - o WhatsApp esta pronto para receber o codigo

- `SUBMITTING_CODE`
  - o RPA ja consumiu o codigo do Mongo

- `CONNECTED`
  - sucesso final

- `FAILED`
  - falha final

- `CANCEL_REQUESTED`
  - o usuario pediu cancelamento, mas a sessao ainda depende do RPA para encerrar

- `CANCELLED`
  - sessao encerrada

## Regra atual de cancelamento

O cancelamento depende do estado operacional da sessao.

### Quando a sessao ainda esta `QUEUED`

O proprio LineOps encerra a sessao imediatamente:

- `status = CANCELLED`
- `active_lock = false`

Esse caso nao depende do RPA.

### Quando a sessao ja esta em andamento

O LineOps grava:

- `cancel_requested_at`

E o card passa a exibir:

- `status = CANCEL_REQUESTED`

Nesse ponto, o encerramento final depende do RPA.

### Se o ambiente ainda estiver com RPA antigo

Se o RPA ainda nao estiver com a versao nova do reconnect, a sessao pode ficar parada em:

- `CANCEL_REQUESTED`

Nessa situacao, o encerramento precisa ser manual no Mongo.

## Como encerrar manualmente uma sessao presa em `CANCEL_REQUESTED`

Exemplo:

```javascript
use RPA

db.reconnect_sessions.updateOne(
  { _id: "manual_reconnect_xxx", active_lock: true },
  {
    $set: {
      status: "CANCELLED",
      finished_at: new Date(),
      active_lock: false,
      worker_heartbeat_at: new Date(),
      updated_at: new Date(),
      error_code: "cancel_requested",
      error_message: "Sessao cancelada manualmente pela plataforma"
    }
  }
)
```

Depois disso, o card do LineOps deve passar a mostrar `CANCELLED`.

## Checklist rapido de producao

### Para o botao aparecer

- `RECONNECT_ENABLED=True`
- usuario `admin`
- pagina `/telecom/`

### Para o card funcionar

- `RECONNECT_MONGO_URI` preenchido
- `pymongo==4.10.1` instalado na imagem
- imagem rebuildada
- container `web` recriado

### Para o reconnect iniciar

- linha com origem `SRVMEMU-*`
- `RECONNECT_TARGET_SERVER_MAP` com essa origem
- indice parcial da collection presente

### Para o reconnect concluir

- RPA lendo a mesma collection
- `target_server` coerente com o host do RPA
- worker do reconnect ativo

## Troubleshooting rapido

### O botao nao aparece

Verificar:

- `RECONNECT_ENABLED=True`
- usuario logado como `admin`
- pagina correta: `/telecom/`

### O card nao aparece no detalhe

Verificar:

- `RECONNECT_ENABLED=True`
- usuario com papel autorizado
- usuario com acesso a essa linha

### O card mostra `Unexpected token '<'`

Verificar:

- `pymongo` instalado na imagem do LineOps
- rebuild do container `web`
- logs do Django no momento da chamada

### O reconnect nao inicia

Verificar:

- `PhoneLine.origem` em `SRVMEMU-01..06`
- `RECONNECT_TARGET_SERVER_MAP` contendo a origem
- indice parcial no Mongo

### O cancelamento nao termina

Verificar:

- se a sessao ainda esta `QUEUED` ou ja foi pega pelo RPA
- se o RPA no ambiente ja e a versao nova
- se necessario, encerrar manualmente a sessao no Mongo

## Referencias cruzadas

- Contrato de integracao: `docs/PLATFORM_WEB_RECONNECT_CONTRACT.md`
- Spec de implementacao web: `docs/PLATFORM_WEB_RECONNECT_IMPLEMENTATION_SPEC.md`
- Runbook de QA: `docs/PLATFORM_WEB_RECONNECT_QA_RUNBOOK.md`
- Spec do RPA: `C:\Users\andre.souza\Desktop\lineops-main\rpa-whatsapp-git\docs\RPA_RECONNECT_SESSIONS_SPEC.md`
