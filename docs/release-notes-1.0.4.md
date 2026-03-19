# Release Notes 1.0.4

Data: 2026-03-19

## Resumo

Esta versao consolida ajustes no dashboard de excecoes para reconexoes do dia e simplifica a administracao do modulo `telecom`, removendo redundancia operacional no Django Admin.

## Melhorias

- Alinhada a contagem de `Reconectados` entre painel de excecoes, tabela de indicadores diarios e detalhamento do dia.
- Incluida no detalhamento do dia a listagem de numeros resolvidos via acao `Reconectar WhatsApp` quando a resolucao ocorre por usuario com role `ADMIN` no proprio dia.
- Consolidado o `/admin/` de `telecom` para usar `SIMcards` como ponto unico de manutencao, incorporando `Linha`, `Origem` e `Status da linha` no mesmo cadastro.

## Correcoes

- O painel `Reconectados hoje` passou a refletir apenas ocorrencias validas do dia atual, sem inflar a contagem com resolucoes fora da janela esperada.
- Corrigida a divergencia entre o card de excecoes e os dados exibidos em `Indicadores diarios` e `Detalhamento do dia > Reconectados`.
- Removida a duplicidade de manutencao entre `Phone lines` e `Simcards` no Django Admin do app `telecom`.

## Qualidade

- Ajustados testes de dashboard para cobrir o alinhamento entre card, indicador diario e detalhamento.
- Atualizados testes do admin de `telecom` para garantir que `PhoneLine` nao fique mais exposto como cadastro independente.

## Compatibilidade

- Nao ha mudanca de schema ou migracao nesta versao.
- Nao ha alteracao intencional em contratos externos de API.
