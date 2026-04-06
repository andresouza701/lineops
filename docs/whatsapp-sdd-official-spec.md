# Especificacao Oficial da Entrega WhatsApp SDD

## Status

Documento de decisao para orientar a execucao do backlog `SDD-000` a
`SDD-012`.

Data de consolidacao: 2026-04-06.

## 1. Hierarquia de Fonte de Verdade

### Fonte oficial da entrega

A partir deste backlog SDD, a fonte oficial da entrega passa a ser a PRD
[`docs/meow-integration-high-level.md`](/C:/Users/andre.souza/Desktop/reviewer/lineops/docs/meow-integration-high-level.md).

### Papel do runbook de QA

O documento
[`docs/qa-whatsapp-ops-runbook.md`](/C:/Users/andre.souza/Desktop/reviewer/lineops/docs/qa-whatsapp-ops-runbook.md)
permanece valido apenas como artefato operacional transitorio para o stack
atual de QA. Ele nao substitui a PRD em decisoes de dominio, contrato de API,
state machine ou semantica assicrona da integracao final.

### Regra de precedencia

Quando houver conflito entre a PRD e o runbook de QA:

1. prevalece a PRD
2. o runbook deve ser interpretado como compatibilidade temporaria
3. o codigo deve evoluir para o contrato da PRD

## 2. Escopo Oficial Desta Entrega

O alvo desta trilha SDD e a integracao completa descrita na PRD, com:

- persistencia local como fonte de verdade
- fila persistente de jobs
- worker dedicado fora do processo `web`
- leitura de status exclusivamente local
- state machine explicita
- observabilidade por `correlation_id`
- contrato DRF padronizado

Nao faz parte desta decisao tratar o estado atual de QA como entrega final.

## 3. Decisoes de Contrato Pendentes

### 3.1 Regra final de idempotencia do `POST /integrations/whatsapp`

Decisao:

- o `POST` e idempotente por ownership da conexao na `PhoneLine`
- deve existir no maximo uma conexao local por linha
- se a conexao ainda nao existir, o LineOps cria a conexao local e grava o job
  de criacao
- se a conexao ja existir, o `POST` devolve a mesma conexao local, sem criar
  duplicidade nem depender de estado remoto
- repeticao do `POST` nunca deve criar segunda sessao local nem segunda
  conexao para a mesma linha

Semantica de resposta:

- `201 Created` quando a conexao local for criada nesta chamada
- `200 OK` quando a conexao local ja existir e for reutilizada

Implicacoes de implementacao:

- unicidade local por linha permanece obrigatoria
- deduplicacao de job de criacao deve ocorrer por conexao e tipo de job
- indisponibilidade do MEOW nao altera a idempotencia do `POST`

### 3.2 Regra final de reuso e expiracao do QR

Decisao:

- `POST /integrations/whatsapp/{id}/generate-qr` e uma operacao assicrona
- se existir QR local ainda valido, o mesmo QR deve ser reutilizado
- se nao existir QR valido, o LineOps grava um job de geracao de QR
- a validade do QR deve ser determinada por `qr_expires_at` persistido
  localmente
- quando o provedor informar expiracao explicita, ela e a fonte principal
- quando o provedor nao informar expiracao, o QR deve ser tratado como de
  validade curta controlada por politica local configuravel

Politica de leitura:

- `GET status` nunca chama o MEOW para gerar ou renovar QR
- o cliente le apenas o ultimo QR persistido e seu estado local

Implicacoes de implementacao:

- o modelo local deve armazenar ao menos `qr_code`, `qr_generated_at` e
  `qr_expires_at`
- QR expirado nao pode ser retornado como valido
- polling do worker pode mover o estado de `QR_AVAILABLE` para
  `WAITING_SCAN`, `CONNECTED` ou `EXPIRED`

### 3.3 Semantica final do `DELETE /integrations/whatsapp/{id}/session`

Decisao:

- o `DELETE` e idempotente e assicrono
- a chamada registra intencao local e enfileira cleanup remoto quando
  necessario
- o retorno da API nao depende da resposta imediata do MEOW
- repeticao do `DELETE` para conexao ja encerrada nao e erro
- `404` remoto durante o cleanup e tratado como convergencia bem-sucedida para
  `DISCONNECTED`

Semantica de resposta:

- `202 Accepted` quando a intencao de encerramento for persistida
- `200 OK` ou `202 Accepted` continuam validos para repeticoes idempotentes,
  desde que a resposta reflita o estado local

Regra de convergencia:

- se a conexao local ja estiver em `DISCONNECTED`, o `DELETE` nao falha
- se o worker encontrar `404` remoto, a conexao local converge para
  `DISCONNECTED`
- `FAILED` fica reservado para falhas terminais que nao representem ausencia
  remota convergente

## 4. Diretrizes que Destravem o Backlog SDD

As seguintes regras devem ser consideradas obrigatorias nas proximas etapas:

- `connect`, `generate-qr` e `disconnect` nao executam I/O remoto no ciclo web
- `GET status` responde apenas do estado local persistido
- jobs devem sobreviver a restart de processo
- worker deve operar fora do `web`
- transicoes de estado devem ser centralizadas em servico
- erros `404` remotos devem seguir semantica de convergencia, nao de erro
  generico

## 5. Checklist de Decisao

- [x] Fonte oficial definida como PRD completa
- [x] Papel do runbook de QA rebaixado para compatibilidade operacional
- [x] Idempotencia final do `POST` definida
- [x] Regra de reuso e expiracao do QR definida
- [x] Semantica final do `DELETE` definida
- [x] Regra de tratamento para `404` remoto alinhada ao encerramento idempotente
- [x] Documento versionado em `docs/`

## 6. Impacto Imediato no Backlog

Este documento destrava diretamente:

- `SDD-001`
- `SDD-002`
- `SDD-003`
- `SDD-004`
- `SDD-005`
- `SDD-006`
- `SDD-007`

## 7. Itens Ainda Dependentes de Implementacao

Este documento nao implementa:

- a nova app `integrations_whatsapp`
- a fila persistente
- o worker dedicado
- a nova state machine no banco
- o contrato DRF final
- a trilha de testes PostgreSQL

Ele apenas fecha a especificacao oficial necessaria para orientar essas
implementacoes.
