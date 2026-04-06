# Contrato DRF da Integracao WhatsApp

## Status

Documento complementar da trilha `SDD-008` e `SDD-009`.

Data de consolidacao: 2026-04-06.

## 1. Fonte de Verdade

Este contrato complementa:

- `docs/whatsapp-sdd-official-spec.md`
- `docs/meow-integration-high-level.md`

Em caso de conflito, prevalece a PRD e a especificacao oficial.

## 2. Decisoes Minimas de Contrato

### 2.1 Identificador do recurso

- o recurso DRF representa a conexao local `WhatsAppSession`
- o identificador exposto em rota e o `pk` local da sessao

### 2.2 Payload do `POST /api/integrations/whatsapp/`

- a entrada minima obrigatoria e `line_id`
- o ownership continua ancorado na `PhoneLine`

Exemplo:

```json
{
  "line_id": 123
}
```

### 2.3 Semantica do `correlation_id`

- o cabecalho oficial de rastreio e `X-Correlation-ID`
- se o cliente nao enviar esse cabecalho, o LineOps gera um novo identificador
- quando a chamada idempotente reaproveitar um job ativo ja existente, o
  `correlation_id` efetivo da resposta sera o do job reutilizado
- o `correlation_id` efetivo deve ser persistido em job e auditoria tecnica

## 3. Endpoints da Fase Atual

### `POST /api/integrations/whatsapp/`

Comportamento:

- cria ou reutiliza a conexao local de forma idempotente
- registra job de criacao quando necessario

Resposta:

- `201 Created` quando a conexao local for criada nesta chamada
- `200 OK` quando a conexao local ja existir

### `GET /api/integrations/whatsapp/`

Comportamento:

- lista conexoes locais persistidas

Resposta:

- `200 OK`

### `GET /api/integrations/whatsapp/{id}/`

Comportamento:

- retorna o resumo da conexao local

Resposta:

- `200 OK`
- `404 Not Found` quando a conexao local nao existir

### `GET /api/integrations/whatsapp/{id}/status/`

Comportamento:

- retorna apenas o ultimo estado local persistido
- nao chama o MEOW

Resposta:

- `200 OK`
- `404 Not Found` quando a conexao local nao existir

### `POST /api/integrations/whatsapp/{id}/generate-qr/`

Comportamento:

- reutiliza QR local valido quando existir
- caso contrario, registra job assicrono de geracao

Resposta:

- `200 OK` quando um QR local valido for devolvido
- `202 Accepted` quando a geracao assicrona for registrada
- `404 Not Found` quando a conexao local nao existir

### `DELETE /api/integrations/whatsapp/{id}/session/`

Comportamento:

- registra intencao local de encerramento
- enfileira cleanup remoto de forma assicrona e idempotente

Resposta:

- `202 Accepted` quando a intencao local for persistida
- `404 Not Found` quando a conexao local nao existir

## 4. Estrutura de Resposta

As respostas de recurso devem incluir pelo menos:

- `id`
- `line_id`
- `phone_number`
- `session_id`
- `status`
- `status_display`
- `version`
- `meow_instance`
- `connected`
- `has_qr`
- `qr_expires_at`
- `connected_at`
- `last_sync_at`
- `last_error`
- `is_active`
- `correlation_id`

Quando houver job associado a resposta, incluir:

- `job.id`
- `job.type`
- `job.status`
- `job.available_at`

Quando houver QR local valido retornado por `generate-qr`, incluir:

- `qr_code`

## 5. Permissao da Fase Atual

Para preservar compatibilidade com o escopo tecnico atual:

- somente usuarios `admin` acessam este contrato DRF nesta fase

Qualquer ampliacao de escopo deve ser tratada como decisao explicita de produto.
