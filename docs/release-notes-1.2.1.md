# Release Notes 1.2.1

Data: 2026-03-29

## Resumo

Esta versao consolida correcoes operacionais e de escopo aplicadas apos a `1.2.0`. O foco foi corrigir visibilidade indevida de indicadores no dashboard principal para perfis hierarquicos e reduzir duplicidade de dados causada por variacoes de caixa, espacos e aliases em nomes, carteira, unidade e operadora. Como a entrega e majoritariamente corretiva e nao introduz mudanca de schema, o versionamento adequado desta entrega e `PATCH`, evoluindo de `1.2.0` para `1.2.1`.

## Correcoes

- Corrigido o dashboard principal para que `gerente` e `supervisor` vejam apenas metricas ligadas a `employee` e `allocation` das suas equipes subordinadas.
- Mantido o inventario global no dashboard para evitar mudanca indevida no comportamento dos cards de disponibilidade e estoque.
- Corrigida a consistencia de escopo entre dashboard principal, live refresh, detalhe diario e exportacao CSV.
- Corrigida a persistencia de dados textuais para normalizar nomes de usuario, carteira, unidade e operadora nos fluxos de model, form, admin e upload.
- Corrigida a busca de usuario no upload para considerar nome normalizado, evitando criacao de duplicados por diferencas de caixa e espacos.

## Melhorias Operacionais

- Adicionado o comando `python manage.py normalize_domain_data` para auditar a base existente em modo `dry-run`.
- Adicionado o modo `python manage.py normalize_domain_data --apply` para aplicar a normalizacao de forma controlada.
- Adicionada protecao para reportar e ignorar colisoes de nome apos normalizacao, preservando seguranca na limpeza da base.

## Qualidade

- Adicionados testes para o escopo hierarquico do dashboard principal, payload live e detalhe do dia.
- Adicionados testes para normalizacao em `Employee` e `SIMcard`, normalizacao do upload e comportamento do comando de saneamento.
- Validacoes direcionadas executadas em `dashboard.tests`, `employees.tests`, `telecom.tests`, `core.tests.test_upload_service`, `core.tests.test_normalization_command` e `allocations.tests.test_telephony_registration`.

## Compatibilidade

- Esta versao nao introduz migrations novas nem altera schema.
- O comportamento esperado para `admin` permanece global no dashboard; a mudanca de escopo afeta apenas perfis hierarquicos conforme a regra de negocio ja existente no dash gerencial.
- O comando de normalizacao deve ser executado primeiro sem `--apply` em ambientes de producao para revisar possiveis colisoes antes da aplicacao definitiva.
