# Release Notes 1.0.2

Data: 2026-03-19

## Resumo

Esta versao foca em reforco de permissao, consistencia de dados e estabilidade operacional nos fluxos de dashboard, alocacao, usuarios e telefonia.

## Melhorias

- Restringido o acesso as rotas sensiveis de indicadores e "Acoes do Dia" por papel de usuario.
- Endurecido o parsing de parametros de paginacao para evitar erro `500` com `offset` e `limit` invalidos.
- Desativada a edicao manual perigosa de alocacoes, preservando as invariantes do dominio.
- Ajustado o fluxo de liberacao de alocacao para operadores, com redirecionamento correto de volta ao hub de cadastro.

## Correcoes

- Desativacao de usuario agora libera alocacoes ativas antes do soft delete.
- Exclusao de linha agora libera alocacoes ativas antes do soft delete.
- Corrigidos problemas de lint remanescentes em `users` e no servico de upload.

## Qualidade

- Cobertura de testes ampliada para permissao de dashboard, integridade de alocacao, soft delete com liberacao e redirect de operador.
- Validacao final executada com `ruff check .` e `pytest -q`.

## Compatibilidade

- Nao ha mudanca de schema ou migracao nesta versao.
- Nao ha alteracao intencional em contratos externos de API.
