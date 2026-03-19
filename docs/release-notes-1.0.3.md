# Release Notes 1.0.3

Data: 2026-03-19

## Resumo

Esta versao adiciona uma nova area de cadastro para configuracoes Blip, visivel apenas para usuarios com role `dev`, e formaliza o papel `dev` no modelo de usuarios do sistema.

## Melhorias

- Criada a tabela `BlipConfiguration` para armazenar `Blip ID`, `Tipo`, `Descricao`, `Numero Telefone`, `Chave` e `Valor`.
- Implementadas telas de listagem, cadastro e edicao para configuracoes Blip no modulo `telecom`.
- Adicionado item de navegacao exclusivo para usuarios com role `dev`.
- Registrado o novo cadastro no Django Admin para consulta e manutencao operacional.

## Permissoes

- O acesso a area de configuracoes Blip foi restrito ao role `dev`.
- O role `dev` passou a existir oficialmente nas choices de `SystemUser.role`.

## Schema

- Nova migracao: `telecom/migrations/0012_blipconfiguration.py`.
- Nova migracao: `users/migrations/0006_alter_systemuser_role.py`.

## Qualidade

- Adicionados testes cobrindo acesso do `dev`, bloqueio para usuarios sem permissao e criacao de configuracao Blip.
- Adicionado teste garantindo a disponibilidade do role `dev` nas choices de usuario.

## Compatibilidade

- Nao ha alteracao intencional em contratos externos de API.
- A feature depende da aplicacao das migracoes de `telecom` e `users` para funcionamento completo em ambiente.
