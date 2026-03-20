# Release Notes 1.0.5

Data: 2026-03-19

## Resumo

Esta versao alinha o comportamento de soft delete entre o ORM, o Django Admin e o dashboard, reduzindo inconsistencias entre dados removidos logicamente e o que ainda aparecia nas telas operacionais e historicas.

## Melhorias

- Centralizada a regra de soft delete de `SIMcard` e `PhoneLine` para que o ORM e o admin sigam o mesmo fluxo de negocio.
- Ajustado o dashboard para manter pendencias visiveis em `Acoes do Dia` quando uma linha deixa de ser exibida por causa de soft delete.
- Separada a logica de visibilidade entre dia atual e dias historicos nos indicadores diarios.

## Correcoes

- `QuerySet.delete()` de `SIMcard` e `PhoneLine` agora respeita a regra de liberacao de alocacao antes do soft delete.
- Dias passados em `Resumo do dia` e `Listas detalhadas do dia` nao perdem mais eventos validos so porque o `SIMcard` foi removido depois.
- O dia atual continua ocultando linhas invalidas ou invisiveis no dashboard e no modulo `telecom`.

## Qualidade

- Adicionados testes para delete por ORM, preservacao de historico e manutencao de pendencias no board.
- Validacao executada com `python manage.py test telecom.tests --verbosity 1`.
- Validacao executada com `python manage.py test dashboard.tests --verbosity 1`.

## Compatibilidade

- Nao ha mudanca de schema ou migracao nesta versao.
- Nao ha alteracao intencional em contratos externos de API.
