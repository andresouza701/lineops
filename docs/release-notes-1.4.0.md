# Release Notes 1.4.0

Data: 2026-04-16

## Resumo

Esta versao entrega o historico de reconexao WhatsApp com rastreabilidade completa das sessoes por linha, corrige inconsistencias nos indicadores do dashboard relacionados a reconectados, fortalece a persistencia de dados historicos mesmo apos exclusao de linha ou inativacao de usuario, e expande o board `Acoes do Dia` com novas colunas e notificacoes operacionais. Como a entrega inclui novo modelo, migration e funcionalidades ineditas de forma retrocompativel, o versionamento e `MINOR`, evoluindo de `1.3.0` para `1.4.0`.

---

## Novas Funcionalidades

### Historico de Reconexao WhatsApp

- Novo modelo `WhatsappReconnectHistory` registrando cada sessao de reconexao com: `session_id`, resultado (`CONNECTED`, `FAILED`, `CANCELLED`), codigo de erro, mensagem de erro, contagem de tentativas, usuario que iniciou, timestamps de inicio e fim.
- Migration `telecom/0014` criando a tabela com indice em `(phone_line, -started_at)`.
- `WhatsappReconnectHistoryService` com operacoes `open` (idempotente por `session_id`) e `close` (idempotente por `outcome__isnull`).
- Endpoint `GET /telecom/phonelines/<pk>/reconnect/history/` retornando os ultimos 50 registros em JSON.
- Botao **Verificar status** na pagina de detalhe da linha: consulta e atualiza o widget de reconexao sem recarregar a pagina.
- Botao **Historico de reconexao** abre modal Bootstrap com tabela colorida por resultado (verde: conectado, vermelho: falha, cinza: cancelado, amarelo: em andamento) e carga automatica a cada abertura.

### Board Acoes do Dia

- Adicionada coluna **Status Pendencia** exibindo o status atual da pendencia de cada usuario.
- Adicionado **badge de notificacao por linha** no botao `Status Pendencia`, indicando pendencias abertas diretamente na interface.
- **Notificacao de observacao de pendencia** entre roles: supervisores e admins recebem indicacao visual quando ha observacao registrada em uma pendencia.
- Adicionada **ordenacao por coluna** na tabela de Acoes do Dia para a role admin.
- Substituicao da coluna `Ult.alt.status` pela coluna **Envio da pendencia**, exibindo a data e hora do ultimo envio.
- Campo **Supervisor** adicionado ao modal de Informacoes da Linha.
- Ajustes visuais nos cards e modal de pendencias.

---

## Correcoes

- **Reconectados mostrando 0 no dashboard**: corrigido o `select_related` para incluir `sim_card` e adicionado fallback de busca por `LineAllocation` quando a pendencia nao tem alocacao direta.
- **Reconectados/entregues sumindo ao excluir linha ou inativar usuario**: `phone_line_is_visible_for_day` agora usa sempre `phone_line_was_visible_at` no momento do evento, preservando dados historicos independente do estado atual da linha ou do usuario.
- **Dados historicos sumindo apos inativacao**: corrigida a visibilidade de eventos passados que deixavam de aparecer quando usuario era inativado ou linha excluida.
- **`resolved_at` nunca salvo e `last_submitted_action` nulo**: corrigido o fluxo de gravacao da data de resolucao e da ultima acao submetida em pendencias.
- **Reconexoes nao contabilizadas**: adicionado campo `last_submitted_action` em `AllocationPendency` e ajustada a contagem de reconexoes no dashboard.
- Corrigidos 3 problemas no modal de pendencia (exibicao, interacao e atualizacao de estado).
- Corrigido metodo Bootstrap `Modal.getOrCreateInstance` incorreto que impedia abertura do modal.
- Corrigido campo `Ult.alt.status` que nao atualizava apos salvar e `Resp. Tecnico` que nao mostrava `-` por padrao quando vazio.
- Corrigida deriva de indice no snapshot diario do dashboard.

---

## Qualidade

- Adicionados testes cobrindo: criacao e idempotencia do historico de reconexao, fechamento com resultado terminal, representacao textual do modelo, endpoint de historico (lista, vazio, desabilitado), integracao com `PhoneLineReconnectStartView` e `PhoneLineReconnectStatusView`.
- Data migration `backfill_resolved_at` aplicada para corrigir registros historicos de reconexao anteriores ao fix.

---

## Migrations

| App | Arquivo | Descricao |
|-----|---------|-----------|
| `telecom` | `0014_whatsappreconnecthistory` | Cria tabela `WhatsappReconnectHistory` com indice em `(phone_line, -started_at)` |
| `pendencies` | `0003_allocationpendency_last_submitted_action` | Adiciona campo `last_submitted_action` em `AllocationPendency` |

Ambientes de producao devem aplicar as migrations pendentes antes do deploy:

```bash
python manage.py migrate
```

---

## Compatibilidade

- Retrocompativel: nenhuma interface ou contrato externo foi alterado.
- O campo `last_submitted_action` e `null=True` e nao quebra registros existentes.
- O modelo `WhatsappReconnectHistory` e novo e nao afeta tabelas existentes.
- A variavel `RECONNECT_ENABLED` continua controlando a exibicao dos botoes de reconexao e do historico.
