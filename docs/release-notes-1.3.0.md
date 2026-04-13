# Release Notes 1.3.0

Data: 2026-04-13

## Resumo

Esta versao expande o fluxo operacional de `Acoes do Dia` com novas informacoes de acompanhamento para o time administrativo e melhora a usabilidade dos formularios com ordenacao alfabetica nas listas operacionais. Como a entrega adiciona funcionalidade nova de forma retrocompativel e inclui uma migration no app `dashboard`, o versionamento adequado desta entrega e `MINOR`, evoluindo de `1.2.1` para `1.3.0`.

## Melhorias

- Adicionada a coluna `Resp. Tecnico` no board `Acoes do Dia`, exibindo para as outras roles qual `admin` alterou o status da linha.
- Adicionada a coluna `Ult.alt.status` no board `Acoes do Dia`, mostrando a data e hora da ultima alteracao de status.
- Reorganizadas as colunas da tabela `Acoes do Dia` para refletir a ordem operacional solicitada.
- Adicionado filtro por `Resp. Tecnico` para a role `admin` no board `Acoes do Dia`.
- Adicionada a nova opcao `Pendencia` na coluna `Acao`.
- Ordenadas alfabeticamente as listas de `supervisor`, `gerente` e `carteira` nos formularios operacionais.

## Correcoes

- Ajustado o escopo do dashboard principal para que `backoffice` siga as mesmas regras de visibilidade do `supervisor`.
- Liberada a edicao do campo `canal` para a role `admin` no fluxo de edicao de linhas.

## Qualidade

- Adicionados testes cobrindo exibicao do responsavel tecnico, timestamp da ultima alteracao de status, filtro por responsavel tecnico, nova opcao `Pendencia` e ordenacao alfabetica das listas.
- Validacao de sintaxe executada com `python -m compileall dashboard employees`.

## Compatibilidade

- Esta versao permanece retrocompativel no comportamento externo esperado pelo sistema, com ampliacao de funcionalidades no board administrativo.
- Ha mudanca de schema introduzida pela migration `dashboard/migrations/0008_alter_dailyuseraction_action_type.py`, necessaria para registrar a nova opcao `Pendencia` em `DailyUserAction.action_type`.
- Ambientes de producao devem aplicar as migrations pendentes antes do deploy completo desta versao.
