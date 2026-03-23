# Release Notes 1.1.0

Data: 2026-03-23

## Resumo

Esta versao introduz novas capacidades operacionais no upload e no dashboard, melhora a prontidao de producao e consolida a preservacao historica dos indicadores diarios sem quebrar contratos existentes. Por isso, o versionamento adequado desta entrega e `MINOR`, evoluindo de `1.0.5` para `1.1.0`.

## Melhorias

- Ajustada a regra central de alocacao para permitir ate 4 linhas ativas por usuario, com alinhamento entre servicos, formularios e testes.
- Adicionado suporte de upload para cadastrar linhas ja vinculadas a usuarios existentes quando o arquivo informar `full_name` e `status=ALLOCATED`.
- Adicionada exportacao do snapshot diario dos indicadores com filtro por data para gerar relatorio do dia selecionado.
- O dashboard passou a preservar snapshots diarios para a tabela `Indicadores Diarios`, mantendo historico estavel para dias fechados.

## Correcoes

- Corrigido o bootstrap de producao para forcar `APP_ENV=prod` antes da carga das configuracoes base.
- Corrigido o parser de upload para aceitar arquivos CSV em `utf-8-sig`, `cp1252` e `latin-1`, evitando erro `500` em arquivos gerados por Excel/Windows.
- Corrigido o CSV exportado do dashboard para abrir sem mojibake em Excel, com cabecalhos como `Numeros Disponiveis` e `Numeros Entregues`.
- Corrigido o fluxo de exportacao do dashboard para nao deixar a tela presa em overlay de carregamento apos o download.
- Corrigida a preservacao historica dos indicadores diarios quando usuarios ou dados de telefonia sao removidos ou alterados depois da data analisada.

## Qualidade

- Adicionados testes para upload com arquivos Windows-encoded e para o tratamento controlado de falha de leitura na view.
- Adicionados testes de regressao para preservacao historica da tabela `Indicadores Diarios`.
- Adicionados testes para exportacao do snapshot diario com filtro de data, validando conteudo e encoding do CSV.
- Validacoes direcionadas executadas em `dashboard.tests`, `core.tests.test_upload_service` e `config.tests.test_upload_view`.

## Compatibilidade

- Esta versao e retrocompativel no comportamento externo esperado pelo sistema; nao ha indicio de quebra intencional de contrato para usuarios ou integracoes.
- Ha mudanca de schema introduzida pela migration `dashboard/migrations/0007_dashboarddailysnapshot.py`, necessaria para a preservacao dos snapshots diarios.
- Ambientes de producao devem aplicar as migrations pendentes antes do deploy completo desta versao.
