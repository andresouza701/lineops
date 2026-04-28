# Release Notes 1.6.0

Data: 2026-04-27

## Resumo

Esta versao expande a visibilidade operacional do LineOps com duas novas funcionalidades: posicao na fila de execucao da reconexao WhatsApp e pagina de metricas de pendencias por responsavel tecnico. Inclui tambem correcoes de consistencia entre superficies da interface, ajuste de regras de criticidade e ordenacao de portfolios. Por adicionar funcionalidades novas de forma retrocompativel e sem migrations, o versionamento adequado e `MINOR`, evoluindo de `1.5.0` para `1.6.0`.

---

## Novas Funcionalidades

### Posicao na Fila de Reconexao WhatsApp

- A tela de detalhe da linha passou a exibir a posicao da conta na fila de execucao enquanto o status da sessao for `QUEUED`.
- A posicao e calculada via contagem de sessoes ativas e enfileiradas no mesmo servidor-alvo com data de criacao anterior, garantindo ordenacao deterministica por `created_at` e `_id`.
- Exibicao simplificada: a hint de espera passa a mostrar apenas `Aguarde sua vez na fila de execucao.` sem repetir o numero de posicao no texto de apoio.
- O calculo e tolerante a falhas: caso o repositorio nao suporte a operacao ou ocorra erro, o campo retorna `null` sem interromper o polling.

### Pagina de Metricas de Pendencias

- Nova pagina em `/dashboard/metricas/` exclusiva para a role `admin`.
- Exibe um ranking de responsaveis tecnicos com contagem de pendencias por status de linha (`restrito`, `banido`, `em analise`, `aguardando operador`) e por acao (`numero novo`, `reconectar`, `pendencia`).
- Exibe tambem a data da pendencia mais antiga por responsavel para priorizar acompanhamento.
- Resumo agregado no topo: total aberto, assumidos, sem responsavel, restritos assumidos e banidos assumidos.
- Filtros disponiveis: status da linha, acao, responsavel tecnico e supervisor (este ultimo exclusivo para admin).
- Link de acesso adicionado na sidebar lateral, visivel apenas para admin.

---

## Correcoes

- **Responsavel tecnico no board Acoes do Dia**: a coluna `Resp. Tecnico` na tabela de acoes passou a exibir exatamente a mesma informacao mostrada no modal de status da pendencia, eliminando a divergencia causada por um fallback ao historico de alteracoes de linha.
- **Regras de criticidade no board Acoes do Dia**: ajustadas as condicoes que determinam o nivel de criticidade para refletir corretamente os cenarios operacionais cobertos.
- **Ordenacao de portfolios nos formularios**: a ordenacao dos portfolios em `EmployeeForm` e `CombinedRegistrationForm` foi corrigida para usar comparacao lexicografica padrao do Python, alinhando com o comportamento esperado e eliminando falhas nos testes de ordenacao.
- **Acesso a metricas restrito a admin**: a view e o link da sidebar de metricas de pendencias passaram a exigir `role=admin`, devolvendo 403 para qualquer outra role autenticada.

---

## Qualidade

- Adicionados testes de servico e de view para a pagina de metricas de pendencias, cobrindo: ranking correto por responsavel, exclusao de `no_action`, resolucao de `line_status` por alocacao e por colaborador, escopo por supervisor e aplicacao de filtros.
- Adicionados testes de repositorio e de servico para o calculo de posicao na fila de reconexao, incluindo cenarios de fallback e de posicao zero.
- Adicionado teste de view confirmando que roles nao-admin recebem 403 na pagina de metricas.

---

## Compatibilidade

- Retrocompativel: nenhuma migration nova, nenhuma quebra de contrato externo.
- O acesso a `/dashboard/metricas/` requer `role=admin`; roles anteriormente listadas em `DASHBOARD_ALLOWED_ROLES` (super, backoffice, gerente) nao tem acesso a esta rota.
- O campo `queue_position` e `queue_position_label` foram adicionados ao payload de status da sessao de reconexao; clientes que ignoram campos desconhecidos nao sao afetados.
- O deploy deve atualizar o codigo e configurar `APP_VERSION=1.6.0` nos ambientes que sobrescrevem essa variavel.
