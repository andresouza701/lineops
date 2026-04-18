# Release Notes 1.4.1

Data: 2026-04-18

## Resumo

Esta versao consolida ajustes operacionais e de arquitetura aplicados apos a `1.4.0`, com foco em estabilidade de reconexao WhatsApp, consistencia de contadores no dashboard e higiene estrutural do backend Django. Como a entrega e predominantemente corretiva e retrocompativel, o versionamento adequado e `PATCH`, evoluindo de `1.4.0` para `1.4.1`.

---

## Melhorias

- Board `Acoes do Dia`: substituido o card `Status da Linha` por card `Total`, com calculo `Numero Novo + Reconexao Whats + Pendencia`.
- Dashboard principal: cards de pendencia (`Numero Novo` e `Reconexao Whats`) alinhados ao mesmo escopo de visibilidade usado na tela `Acoes do Dia`.
- Dashboard principal: card `Linhas bloqueadas` consolidado para contabilizar `SUSPENDED` e `CANCELLED`, com escopo por equipe para `supervisor`, `backoffice` e `gerente`.
- Fluxo de reconexao WhatsApp: removido o botao manual de verificacao de status para reduzir ambiguidades no fluxo de polling.

---

## Correcoes

- Reconexao WhatsApp: normalizacao de estados terminais (`SUCCESS`/`FAILED`) para evitar carregamento indefinido apos encerramento da sessao.
- Reconexao WhatsApp: melhorias de cancelamento para reduzir repeticao indevida de tentativa apos comando de cancelar.
- Dashboard: correcoes de divergencia entre contadores de cards e valores exibidos em `Acoes do Dia`.

---

## Arquitetura e Manutenibilidade

- PR1: invariantes de status de linha consolidados no use case de telefonia.
- PR2: desacoplamento do dashboard com extracao de queries/regras para `dashboard/services`.
- PR3: higiene estrutural com:
  - neutralizacao da duplicidade de `PhoneLineHistory` em `telecom/history.py`;
  - centralizacao de tratamento de `IntegrityError` em utilitario unico;
  - reducao de logica de negocio no middleware global.

---

## Qualidade

- Adicionados e ajustados testes para:
  - terminalizacao e historico de reconexao WhatsApp;
  - consistencia de contadores entre dashboard e board `Acoes do Dia`;
  - regras de escopo por role para cards do dashboard;
  - novo card `Total` no board `Acoes do Dia`.

---

## Compatibilidade

- Retrocompativel: sem quebra de contratos externos e sem novas migrations obrigatorias nesta versao.
- Deploy: basta atualizar codigo e configurar `APP_VERSION=1.4.1` nos ambientes.
