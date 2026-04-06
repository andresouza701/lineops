# Plano de Migracao e Rollout da Integracao WhatsApp

## Status

Documento de rollout da trilha `SDD-012`.

Data de consolidacao: 2026-04-06.

## 1. Fonte de Verdade

Este plano complementa:

- `docs/whatsapp-sdd-official-spec.md`
- `docs/meow-integration-high-level.md`
- `docs/whatsapp-drf-contract.md`

## 2. Objetivo

Migrar a implementacao atual para o modelo final da integracao WhatsApp sem
perder sessoes locais, sem quebrar a leitura da UI e com rollback operacional
controlado.

## 3. Estrategia

### 3.1 Compatibilidade de leitura

- a UI continua lendo o mesmo recurso local `WhatsAppSession`
- o contrato HTML atual permanece ativo durante a transicao
- o contrato DRF novo entra em paralelo, sem desligar as telas existentes

### 3.2 Migracoes de banco em etapas curtas

1. adicionar novos campos compatveis
2. backfill de dados locais quando necessario
3. mover escritores para o novo contrato
4. remover dependencias legadas somente depois da validacao operacional

### 3.3 Fonte de verdade local preservada

- nenhuma etapa depende de leitura remota para reconstruir sessao local
- jobs e auditoria continuam persistidos no banco antes de qualquer I/O remoto

## 4. Etapas de Rollout

### Etapa A - Preparacao

- aplicar migrations de estado, job queue e `correlation_id`
- publicar worker dedicado
- validar `/readiness/`
- validar bootstrap de instancias Meow

### Etapa B - Escrita no novo fluxo

- manter `connect`, `generate-qr` e `delete` assicronos
- garantir que requests web e DRF escrevem no mesmo dominio local
- ativar logs estruturados por `correlation_id`

### Etapa C - Validacao operacional

- executar suite critica em PostgreSQL
- validar fluxo ponta a ponta em ambiente QA
- monitorar jobs `RETRY` e `FAILURE`
- monitorar sessoes em `FAILED`, `EXPIRED` e `DISCONNECTED`

### Etapa D - Consolidacao

- confirmar uso do contrato DRF pelos consumidores previstos
- revisar jobs presos ou stale
- congelar remocao de qualquer caminho legado ainda necessario para operacao

## 5. Rollback

### Rollback de aplicacao

- reverter deploy do codigo mantendo o banco intacto
- manter worker fora de rotacao se a falha estiver no processamento assicrono

### Rollback de banco

- migrations com adicao de campo podem permanecer aplicadas sem impacto
- reverter migration de status exige cuidado porque o mapeamento de estados e
  aproximado
- em rollback de estado, preservar leitura da UI antes de tentar reversao fisica

## 6. Checklist de Go-Live

- [ ] migrations aplicadas sem erro
- [ ] worker com heartbeat visivel
- [ ] suite critica em PostgreSQL executada
- [ ] fluxo create/status/qr/delete validado em QA
- [ ] observabilidade por `correlation_id` validada em logs e auditoria
- [ ] sem crescimento anormal de jobs em `RETRY` ou `FAILURE`

## 7. Riscos Residuais

- reversao de estados legados continua aproximada
- a validacao real de lock depende de PostgreSQL disponivel
- consumidores externos ainda precisam migrar para o namespace DRF novo
