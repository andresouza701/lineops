# Release Notes 1.2.0

Data: 2026-03-28

## Resumo

Esta versao expande o fluxo operacional de `Acoes do Dia` com filtros por usuario e linha, consulta rapida de detalhes da linha e o novo metadado `canal` no cadastro de telefonia. Como a entrega adiciona funcionalidade nova de forma retrocompativel e inclui uma migration de schema, o versionamento adequado desta entrega e `MINOR`, evoluindo de `1.1.0` para `1.2.0`.

## Melhorias

- Adicionados filtros por `usuario` e `linha` em `Acoes do Dia`, com preservacao desses parametros apos salvar uma acao.
- Adicionado modal de detalhes da linha no board diario com numero, ICCID, origem, canal, usuario, operadora e status.
- Adicionado campo opcional `canal` no cadastro e reuso de linhas, com suporte a `WEB` e `MyLoop` nos fluxos de `telecom`, `allocations` e Django Admin.
- Exibido o campo `canal` nas telas de cadastro e detalhe da linha para manter o dado visivel durante a operacao.

## Correcoes

- Ajustado o layout dos filtros do board para alinhamento a direita em desktop, preservando usabilidade em telas menores.
- Corrigido o contraste visual do modal de detalhes da linha para evitar perda de legibilidade.
- Simplificados os rotulos do popup de linha para `Usuario` e `Status`, mantendo consistencia com a operacao do board.

## Qualidade

- Adicionados testes para filtro por usuario e linha, preservacao dos filtros apos `POST` e renderizacao do modal de detalhes no dashboard.
- Adicionados testes para o novo campo `canal` cobrindo criacao, reuso de linha soft-deletada e exibicao no fluxo administrativo.
- Validacoes direcionadas executadas em `dashboard.tests` e `telecom.tests allocations.tests.test_telephony_registration`.

## Compatibilidade

- Esta versao e retrocompativel no comportamento externo esperado pelo sistema; nao ha indicio de quebra intencional de contrato para usuarios ou integracoes.
- Ha mudanca de schema introduzida pela migration `telecom/migrations/0013_phoneline_canal_alter_phoneline_origem.py`, necessaria para adicionar o campo `canal` e alinhar o estado do campo `origem`.
- Ambientes de producao devem aplicar as migrations pendentes antes do deploy completo desta versao.
