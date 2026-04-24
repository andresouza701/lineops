# Release Notes 1.5.0

Data: 2026-04-23

## Resumo

Esta versao expande a operacao administrativa do LineOps com nova sinalizacao de criticidade no board `Acoes do Dia`, amplia o acesso controlado ao fluxo de reconexao WhatsApp para roles hierarquicas e melhora a experiencia operacional com novo timer de restricao, ajustes de pendencia e identidade visual da aplicacao. Como a entrega adiciona funcionalidades novas de forma retrocompativel e inclui migrations em `allocations`, `employees` e `dashboard`, o versionamento adequado e `MINOR`, evoluindo de `1.4.1` para `1.5.0`.

---

## Novas Funcionalidades

### Board Acoes do Dia

- Adicionada a coluna `Criticidade` para a role `admin`, com destaque visual por faixa lateral na tabela.
- A criticidade passa a considerar a situacao operacional do usuario no board: falta de linha ativa, pendencias associadas a status de linha e distribuicao de linhas ativas por colaborador.
- O destaque visual de criticidade fica restrito ao contexto administrativo, preservando a leitura das demais roles sem ruido adicional.

### Reconexao WhatsApp e Telecom

- Liberado o uso do fluxo de reconexao para `super`, `backoffice` e `gerente` dentro do mesmo escopo de visibilidade de telecom.
- Adicionado timer regressivo para contas em estado `RESTRICTED`, com fallback para sessoes sem estado ativo no polling.
- Simplificado o card de reconexao na tela de detalhe da linha para reduzir atrito operacional durante reenvio de codigo e acompanhamento do status.

### Operacao e Interface

- Novo status `waiting_operator` disponivel para `Employee.line_status` e `LineAllocation.line_status`.
- Adicionada identidade visual SVG do LineOps na sidebar, na tela de login e no favicon.

---

## Correcoes

- Reconexao WhatsApp: restringido o fluxo a linhas com origem `SRVMEMU-01`, alinhando a interface com a capacidade operacional atualmente suportada.
- Reconexao WhatsApp: removido loading global indevido no reenvio de codigo e evitado restart desnecessario do countdown timer a cada poll.
- Reconexao WhatsApp: ajustado fallback de status para contas antigas em `RESTRICTED`, evitando perda do temporizador quando nao ha sessao ativa.
- Pendencias: bloqueada a edicao de observacao enquanto a linha estiver `Em analise`.
- Pendencias: limpeza automatica de `technical_responsible` quando `admin` salva a pendencia com linha `Ativa` e acao `Sem Acao`.
- Pendencias: corrigida a persistencia do badge de notificacao ao abrir o modal.
- Dashboard: introduzido versionamento de calculo em snapshots diarios legados para permitir refresh consistente sem confundir dados historicos.

---

## Arquitetura e Observabilidade

- Melhorado o formatter de logs da aplicacao para dar mais contexto operacional aos fluxos de backend.
- Reforcada a observabilidade do processo de reconexao WhatsApp com instrumentacao mais consistente no caminho de execucao.

---

## Qualidade

- Adicionados e ajustados testes para criticidade no board `Acoes do Dia`, fluxo de notificacao de pendencias, formatter de logging e comportamento de reconexao.
- O destaque visual de criticidade recebeu cobertura especifica para diferenciar exibicao em `admin` e ocultacao nas demais roles.

---

## Migrations

| App | Arquivo | Descricao |
|-----|---------|-----------|
| `allocations` | `0007_alter_lineallocation_line_status` | Adiciona o status `waiting_operator` em `LineAllocation.line_status` |
| `employees` | `0017_alter_employee_line_status` | Adiciona o status `waiting_operator` em `Employee.line_status` |
| `dashboard` | `0009_dashboarddailysnapshot_calculation_version` | Adiciona `calculation_version` e marca snapshots existentes como legado |

Ambientes de producao devem aplicar as migrations pendentes antes do deploy:

```bash
python manage.py migrate
```

---

## Compatibilidade

- Retrocompativel: nao ha quebra de contratos externos nem alteracao obrigatoria de endpoints publicos.
- O acesso de roles hierarquicas ao fluxo de reconexao respeita o escopo de visibilidade ja aplicado em telecom.
- O deploy deve atualizar o codigo e configurar `APP_VERSION=1.5.0` nos ambientes que sobrescrevem essa variavel.
