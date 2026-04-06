# Validacao PostgreSQL da Integracao WhatsApp

## Status

Documento operacional da trilha `SDD-011`.

Data de consolidacao: 2026-04-06.

## 1. Fonte de Verdade

Este procedimento complementa:

- `docs/whatsapp-sdd-official-spec.md`
- `docs/meow-integration-high-level.md`
- `docs/whatsapp-drf-contract.md`

## 2. Objetivo

Executar a trilha critica da integracao WhatsApp no banco alvo real
`PostgreSQL`, cobrindo:

- criacao concorrente de ownership local da sessao
- claim seguro de jobs
- competicao entre workers
- fluxo ponta a ponta da API assicrona com estado local

## 3. Pre-condicoes

- stack local ou QA com container `db` ativo
- migrations aplicadas
- `DJANGO_SETTINGS_MODULE=config.settings_test_postgres`
- `USE_SQLITE_TEST_DB=False`

## 4. Comandos

### Subir infraestrutura local

```bash
docker compose up -d db
```

### Executar somente a trilha critica em PostgreSQL

```bash
docker compose exec web python manage.py test whatsapp.test_postgres --settings=config.settings_test_postgres --verbosity 1
```

### Executar a trilha WhatsApp completa em PostgreSQL

```bash
docker compose exec web python manage.py test whatsapp --settings=config.settings_test_postgres --verbosity 1
```

## 5. Checklist de Aceite

- [ ] `get_or_create_session` retorna a mesma sessao em corrida concorrente
- [ ] apenas um worker consegue claim do mesmo job pendente
- [ ] dois workers concorrentes nao processam o mesmo job duas vezes
- [ ] fluxo `POST create -> worker -> status -> generate-qr -> delete -> worker`
      converge sem divergencia de estado
- [ ] nao ocorre erro `500` por duplicidade ou disputa de lock na trilha critica

## 6. Evidencia Esperada

Registrar em release note, ticket ou comentario de deploy:

- data/hora da execucao
- ambiente usado
- comando executado
- total de testes executados
- resultado final
- observacoes de lock, timeout ou comportamento inesperado
