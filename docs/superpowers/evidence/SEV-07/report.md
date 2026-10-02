# SEV-07 — Relatório de aceite real (visual e funcional)

Fonte da verdade: `docs/superpowers/specs/2026-09-30-whatsapp-seal-activation-value-design.md`

Data: 2026-10-01.

## 1. Ambiente

- **Backend de aplicação:** Postgres 15.8 em container Docker descartável
  `sev07-disposable-pg`, porta 55432, banco `sev07`, usuário `sev07`
  (credenciais descartáveis). Criado nesta task; separado dos recursos
  pré-existentes (`lineops-db` na porta 5433, `postgres`/pgvector na
  porta 5432), que não foram tocados.
- **Servidor da aplicação:** `manage.py runserver 127.0.0.1:8017
  --noreload`, `config.settings_dev`, variáveis de ambiente
  `DB_HOST=localhost DB_PORT=55432 DB_NAME=sev07 DB_USER=sev07
  DB_PASSWORD=sev07_disposable_pw APP_ENV=dev` passadas via processo
  (nenhum arquivo de configuração versionado alterado; `.env` não foi
  editado — as variáveis explícitas no processo têm precedência sobre
  `environ.Env.read_env`).
- **Django:** 5.2.11. **Python:** 3.14.3 (venv do projeto).
- **Navegador real:** Google Chrome 151.0.7922.109 instalado localmente,
  controlado via Playwright 1.63.0 (pacote npm global) em modo headless
  (`chromium.launch({channel: "chrome", headless: true})`). Node.js
  v24.14.0.
- Nenhuma ferramenta de navegador interativo (Chrome DevTools MCP) estava
  registrada nesta sessão; Playwright com o binário real do Chrome
  instalado foi usado conforme autorizado pelo pedido ("Playwright
  instalado"). Headless é uma limitação explícita: não há evidência de
  renderização visual *vista por um humano em tempo real*, mas o motor
  de renderização é o Chrome real (não um simulador), e todas as
  medidas de layout (scrollWidth/clientWidth, cor computada,
  posição de elementos) vêm do motor de renderização real.

## 2. Dataset

Construído em `scratchpad/sev07_build_dataset.py` contra o Postgres
descartável acima. Cenários cobertos (PKs de `telecom_phoneline`):

| PK | Cenário |
| --- | --- |
| 5 | Legado migrado (criado pré-migration com os 5 campos antigos, migration 0021→0022 real executada) — depois usado no cenário de edição S9 (preenchimento dos novos campos) |
| 6 | Registro logicamente excluído (`is_deleted=True`), com selo completo |
| 7 | Sem selo |
| 8 | Não ativado, valor zero |
| 9 | Não ativado, valor positivo |
| 10–14 | Ativo, vencimento +8/+7/+1/hoje/-1 dias |
| 15–17 | As 3 combinações restantes do catálogo (a 4ª é a de pk=10/META_ONE) |
| 18 | Linha alocada (operador 1) |
| 19 | Linha alocada a outro operador (para prova de escopo) |
| 20 | Segundo legado migrado (usado nos cenários de Liberar e remoção de selo) |
| 21–23, 25–31 (parcial), 2001–2015, 3001–3002 | Linhas criadas via navegador real durante os cenários de salvamento/monetário |

Usuários: `sev07-admin@example.invalid` (ADMIN), `sev07-operator@example.invalid`
e `sev07-outro-operador@example.invalid` (OPERATOR, cada um com um
Employee próprio e uma linha alocada distinta, para prova de escopo).

**Legado migrado:** criado com apenas os 5 campos antigos de selo
enquanto o schema estava no HEAD; em seguida `migrate telecom 0021`
(remove as 4 colunas novas do schema real) e `migrate telecom 0022`
(RunPython de backfill real) foram executados via `call_command`, não
substituídos por fixture ORM pós-migração. Repetido duas vezes (pk=5 e
pk=20) para ter dois registros legados independentes nos cenários de
edição e de Liberar.

## 3. Validação Postgres da migration — RESOLVIDA nesta task

Ver `migration-postgres.log` nesta mesma pasta. Forward, backfill
(incluindo excluídos logicamente e legado inconsistente) e reversão
foram exercitados em Postgres real e descartável, com 100% das
asserções passando. Isso resolve a pendência de Postgres deixada aberta
pelas rodadas anteriores de SEV-04 (que só haviam exercitado SQLite).

## 4. Anomalia observada na construção do dataset (causa não determinada — ver ressalva e reconciliação abaixo)

Durante a construção inicial do dataset (`sev07_build_dataset.py`),
diversas linhas criadas via `PhoneLine.objects.create(...)` direto no
ORM — **fora da aplicação**, sem passar por `PhoneLineForm`/
`create_or_reuse` — tiveram os campos `whatsapp_seal_category`,
`whatsapp_seal_plan` e `whatsapp_seal_monthly_value` persistidos vazios/
nulos apesar de passados explicitamente como argumentos, e 3 linhas
(`pk=8,9,19`) tiveram `whatsapp_seal_activation_status` forçado para
`ACTIVE` apesar de criadas com `NOT_ACTIVATED`.

Investigação realizada: múltiplas tentativas de reprodução isolada
(mesma sequência de `migrate` 0021→0022→HEAD seguida de `.create()` com
os mesmos campos, em processos novos e isolados) **não reproduziram** o
problema — os campos persistiram corretamente em todas as tentativas
isoladas. Buscas no código por `post_save`/`pre_save`/`save()` override/
`.update()` em massa sobre `PhoneLine` (`telecom/signals.py`,
`telecom/models.py`, grep global por `PhoneLine.objects.update(`) não
encontraram nenhum mecanismo de aplicação capaz de causar esse efeito —
os únicos usos de `.update()` em massa sobre `PhoneLine` existem em
arquivos de teste, não em código executado pelo servidor. A migration
0022 (`backfill_activation_status`) só poderia explicar o forçamento de
`ACTIVE`, nunca o esvaziamento de categoria/plano/valor (seu `.update()`
toca exclusivamente o campo de situação), e rodou comprovadamente uma
única vez, antes da criação das linhas afetadas.

**Conclusão:** não foi possível isolar a causa raiz com confiança
depois de investigação razoável. Dado que (a) o mecanismo não foi
encontrado no código de aplicação, (b) a reprodução isolada falhou
consistentemente, e (c) **todos os caminhos reais da aplicação**
exercitados nesta mesma task (formulário de cadastro via navegador —
cenários S1–S5, S9b, S10b, M01–M15 — e edição via navegador — S7_redo,
S11_redo) **persistiram corretamente** categoria/plano/valor e
preservaram a situação de ativação em 100% dos casos, este relatório
registra uma anomalia de preparação de dados com causa não determinada.
Esses fatos não comprovam origem na ferramenta nem excluem, por si sós,
um defeito de produto. As linhas afetadas foram corrigidas via `UPDATE` direto
(`scratchpad/sev07_fix_dataset.py`) antes da continuação dos testes de
aceite, documentado aqui para transparência. Nenhuma correção foi feita
em código de aplicação porque nenhum defeito de aplicação foi
confirmado.

Esta observação fica registrada como uma **limitação de investigação**,
não como uma pendência de produto: se o padrão se repetir em uma
rodada futura usando o ORM diretamente (fora dos formulários), vale a
pena investigar mais a fundo (por exemplo, isolando se dois processos
Django concorrentes contra o mesmo Postgres durante uma janela de
`migrate` down→up têm alguma interação de cache de schema).

## 5. Matriz requisito → cenário → evidência → resultado → limitação

### 5.1 Visual (larguras 1280/390/360, com/sem JS)

| Requisito | Cenário | Evidência | Resultado |
| --- | --- | --- | --- |
| Ordem Selo→Categoria→Plano→Situação→Valor | create, 3 larguras, JS on | `results_fase1a3.json` (`visual_field_order_*`), screenshots `create_w*_json.png` | PASS (9/9) |
| Sem overflow horizontal | create, 3 larguras × JS on/off | `results_fase1a3.json` (`visual_overflow_*`): clientWidth==scrollWidth em todos | PASS (6/6) |
| Fundo azul escuro | idem | `visual_dark_bg_*`: `rgb(2, 6, 23)` em todos | PASS (6/6) |
| Sem JS: controles acessíveis | create, 3 larguras, JS off | mesmos screenshots `create_w*_jsoff.png`; bloco de detalhes nunca fica oculto sem JS (confirmado por leitura do HTML/CSS — `hidden` só é setado por `phone-line-form.js`) | PASS |
| Detalhe do legado mostra "Não informado", nunca zero | GET `/telecom/phonelines/5/`, antes da edição S9 | `legacy_detail_nao_informado`, `legacy_detail_sem_zero_inventado` em `results_fase1a3.json`; screenshot `legacy_detail.png` | PASS |
| Catálogo filtra categoria/plano por selo | JS, selecionar META_ONE | `catalog_meta_one_category_filtered`, `catalog_meta_one_plan_filtered` | PASS |
| Referência de preço separada do valor efetivo | JS, selecionar plano | `catalog_price_reference_shown_and_separate`: referência mostrada, campo de valor continua vazio | PASS |
| Troca de tipo invalida só o incompatível, preserva valor digitado | JS, digitar 59,00 e trocar META_ONE→META_VERIFIED | `catalog_switch_type_invalidates_incompatible_keeps_value` | PASS |
| Não ativado oculta bloco de datas (JS) | JS | `catalog_not_activated_hides_dates_block_js` | PASS |

Screenshot adicional: `catalog_interaction.png`.

### 5.2 Salvamentos reais (seção 4 do pedido)

| Cenário | Evidência | Resultado |
| --- | --- | --- |
| A. Não ativado salva R$0,00 e valor positivo, datas nulas | S1/S2 em `results_saves.json` | PASS |
| B. Ativo: datas iguais aceitas, invertidas rejeitadas, zero rejeitado | S3/S4/S5 em `results_saves.json` | PASS |
| C. Não ativado→Ativo exige datas/valor | S6/S6_redo originais **invalidados na reconciliação** (pk=8 nunca teve `activation_status` corrigido para `NOT_ACTIVATED` — ver `dataset-anomaly-reconciliation.md`). **Substituído por reexecução em ambiente novo**, pk genuinamente `NOT_ACTIVATED` verificado: camada cliente (HTML5 bloqueia o submit) e camada servidor (JS desligado, POST real rejeitado com mensagem de negócio) comprovadas separadamente em `results_s6_s7_s11_reconciliation.json` + `results_s6_nojs_server_rejection.json` | PASS (reexecutado) |
| C. Ativo→Não ativado limpa datas, preserva resto | **S7_redo** em `results_saves_redo.json`: salva com sucesso; detalhe mostra "Não ativado", preserva valor (R$ 59,00) e categoria/plano (Criadores / Empresas, One Essencial) | PASS |
| C. Com selo→Sem selo limpa os 8 detalhes | S8 em `results_saves.json`: salva, detalhe mostra "Sem selo" | PASS |
| D. Legado: salvar com selo sem novos campos é rejeitado; preencher permite salvar | S9a/S9b em `results_saves.json` | PASS |
| E. Liberar linha legada não exige completar selo | S10a em `results_saves.json`: ação Liberar processada sem erro de validação do selo | PASS |
| D. Remover selo em legado permite salvar sem completar dados novos | S10b em `results_saves.json` | PASS |
| E. Editar somente selo em linha alocada preserva status/vínculo/activated_at | `S11_redo` original teve 1 assertion `ok:false` (`S11_redo_value_updated`) por expectativa de formato não respaldada pelo contrato — **reconciliado**: causa demonstrada (redisplay de `Decimal` via `str()`, "65.00" é equivalente válido a "65,00" pelo próprio contrato de entrada) e reexecutado em ambiente novo com `activated_at` de fixture **preenchido** (15/08/2026, não vazio→vazio): valor atualizado e confirmado por detalhe (`R$ 65,00`) e round-trip; `employee`, `status` (ALLOCATED) e `activated_at` idênticos antes/depois. Ver `report.md` seção "Reconciliação — rodada 2" e `results_s6_s7_s11_reconciliation.json` | PASS (reconciliado) |
| Reabrir a página confirma persistência | Todas as edições acima fazem GET pós-save (`getDetailText`/reload do form) antes de avaliar | PASS |

### 5.3 Validação monetária (seção 5 do pedido)

Todos os 15 casos (`results_monetary.json`, M01–M15) mais as 9
sub-checagens de preservação de entrada: **24/24 PASS**, cobrindo:
0,00 e 0,01 aceitos; 299,00 (vírgula e ponto) aceito; -0,01, -0,00,
299,01 rejeitados; separador de milhar (`1.000`, `1,000` ambíguo com 3
casas) rejeitado; símbolo de moeda rejeitado; notação científica
(`1e2`) rejeitada; `NaN`/`Infinity` rejeitados; ausência com selo
rejeitada; toda rejeição preserva a entrada digitada no campo para
revisão.

### 5.4 Sem JavaScript (seção 3, bloco "Sem JS")

| Cenário | Evidência | Resultado |
| --- | --- | --- |
| Combinação válida salva sem JS | `NOJS_valid_combo_saves` em `results_final_phases.json`; screenshot `nojs_valid_combo_result.png` | PASS |
| Combinação incompatível (META_ONE + Pessoa Física) rejeitada pelo servidor, sem JS | `NOJS_incompatible_combo_rejected` | PASS |
| Sem gravação parcial | `NOJS_no_partial_write` — resultado do script teve falso-positivo (o número digitado aparece ecoado no atributo `value` do campo de busca da listagem, não em uma linha real); **confirmado por consulta direta ao banco** (`PhoneLine.all_objects.filter(phone_number=...).exists() == False`) que a linha não foi gravada | PASS (confirmado por banco, não pelo texto da página) |

### 5.5 Consumidores (seção 6 do pedido)

| Cenário | Evidência | Resultado |
| --- | --- | --- |
| Overview distingue Não ativado de Sem selo | `overview_shows_nao_ativado_and_sem_selo_distinct` | PASS |
| Nenhum valor financeiro novo na listagem | `overview_no_financial_value_leak` (checagem por padrão `R$` seguido de dígito fora da referência de preço do formulário) | PASS |
| Carregar mais adiciona linhas reais | `overview_carregar_mais_adds_rows`: 10→20 linhas após clique real no botão | PASS |
| Escopo OPERATOR: cada operador só vê sua própria linha alocada | `operator1_sees_own_allocated_line`, `operator1_cannot_see_other_operator_line`, `operator2_sees_own_allocated_line`, `operator2_cannot_see_operator1_line` | PASS (4/4) |
| Hub de Relatórios ADMIN-only | `reports_hub_admin_allowed` (200), `reports_hub_operator_denied` (403) | PASS |
| Smoke relatório Selos: Não ativado fora do período de ativação | `reports_smoke_selo_excludes_not_activated` | PASS |
| Smoke relatório Selos: Ativo aparece no período | `reports_smoke_selo_includes_active` | PASS |
| Smoke Inventário: conta posse de selo independente de ativação | `reports_smoke_inventory_counts_not_activated_as_has_seal` | PASS |
| Sem nova coluna/total financeiro nos relatórios | `reports_smoke_selo_no_financial_column`, `reports_smoke_inventory_no_new_financial_column` | PASS |

## 6. Limitações explícitas (permanecem abertas)

1. **Navegador headless, não headed/interativo.** O Chrome real
   controlado via Playwright rodou em modo headless nesta sessão (sem
   interface gráfica disponível no ambiente de execução). A engine de
   renderização é real (Chrome 151), e todas as medições (layout,
   cores computadas, overflow) vêm dela — mas não houve observação
   visual humana em tempo real durante a execução. Screenshots PNG
   reais foram capturados e ficam disponíveis em `screenshots/` para
   inspeção visual humana posterior.
2. **Causa raiz da anomalia do dataset (§4) não isolada.** Não bloqueia
   o aceite (o caminho real da aplicação foi comprovado correto), mas
   fica registrada como limitação de investigação, não como pendência
   de produto resolvida com certeza sobre sua causa.
3. **Smoke de relatórios, não suíte completa.** A cobertura funcional
   completa de Selos/Inventário já está provada pelas 215 suítes
   pytest existentes (reaproveitadas, não reexecutadas nesta task por
   ausência de mudança de código nessas áreas); o navegador real aqui
   serviu para confirmar a integração ponta-a-ponta (HTML real, não
   apenas o serviço), não para re-provar cada regra já coberta.
4. **Export CSV/XLSX dos relatórios não exercitado nesta task** (fora
   do escopo explícito do pedido, que pede "smoke" dos relatórios, não
   das exportações).

## 7. Comandos de verificação executados nesta task

```
venv/Scripts/python.exe manage.py check --settings=config.settings_dev
  → System check identified no issues (0 silenced).

git diff --check
  → sem erro (avisos de LF/CRLF pré-existentes, mesmos arquivos já
    modificados por SEV-04/05/06)

git status --short
  → status relatado como equivalente, além da pasta nova de evidências.
    Isso não prova conteúdo inalterado: a spec também foi atualizada e
    arquivos já modificados/não rastreados podem manter o mesmo status.
```

Nenhuma suíte pytest foi reexecutada nesta task porque nenhum código de
aplicação foi alterado — a evidência GREEN de SEV-04/05/06 (516+ testes/
subtestes, registrada na fonte da verdade) permanece válida e não foi
reproduzida aqui por economia, conforme instrução de reaproveitamento
proporcional.

## 8. Limpeza

- Container `sev07-disposable-pg` (Postgres descartável): parado e
  removido ao final da task.
- Servidor de desenvolvimento (`runserver 127.0.0.1:8017`): encerrado
  ao final da task.
- Nenhum recurso pré-existente (`lineops-db`, `postgres`/pgvector,
  volumes, `.env`) foi tocado ou removido.


## Ressalvas documentais — 2026-10-01

- Anomalia de preparação com causa não determinada; classificação anterior como artefato da ferramenta retirada. Nenhuma reprodução nova nesta revisão.
- O relato identifica pk=8,9,19 para situação alterada, mas não fornece aqui inventário completo de todas as linhas/campos corrigidos por UPDATE. Não inferir que esses três IDs abrangem todos os ajustes. Complementar a rastreabilidade com o script/log de preparação disponível; se indisponível, declarar limitação.
- Reexecuções identificadas: S6_redo, S7_redo e S11_redo, em results_saves_redo.json. Isso não demonstra repetição de todos os cenários após todos os ajustes.
- Divergência encontrada por leitura direta: results_saves_redo.json contém S11_redo_value_updated com ok=false e detail="valor apos edicao=65.00". O texto do valor sozinho não autoriza converter a assertion em PASS. Conciliar esperado/assertion/resultado antes de considerar esse cenário aceito; não editar o JSON capturado para fazê-lo passar. Pode ser defeito do ensaio ou da aplicação, ainda não determinado nesta revisão.
- git status não comprova ausência de alterações de conteúdo. A spec foi atualizada e a pasta de evidências criada; ausência de mudança em código permanece relato do executor, sem comparação anterior/posterior de conteúdo nesta revisão.
- Até reconciliar a assertion S11 e o alcance das correções/reexecuções do dataset, o fechamento irrestrito de SEV-07 fica ressalvado. Resultados independentes, incluindo migration Postgres, não são invalidados automaticamente.

Revisão documental apenas: leitura de report.md, spec, results_saves_redo.json e git status. Nenhum teste/navegador reexecutado, nenhum artefato de resultado alterado, nenhum código/commit/push/deploy.

## Reconciliação — 2026-10-01 (rodada 2)

**Spec Summary.** Resolver, com evidência nova e identificada, as 5 ressalvas documentais acima: (1) divergência `S11_redo_value_updated`, (2) alcance real da correção de dataset (não presumir que pk=8,9,19 cobrem tudo), (3) proporção das reexecuções, (4) `git status` não é prova de conteúdo, (5) critério de fechamento. Nenhum JSON/log/screenshot antigo foi editado; todo resultado novo está em arquivo próprio e identificado.

**Preservação do estado.** `git status --short`/`git diff --stat` conferidos no início desta rodada (idênticos ao fim da rodada anterior, mais a pasta de evidências já existente). Nenhum `stash`/`reset`/`checkout` usado. Scripts históricos (`sev07_build_dataset.py`, `sev07_fix_dataset.py`, `sev07_saves_redo.js`) localizados intactos em `scratchpad/` (preservados pela sessão) e lidos, não editados.

### Divergência S11 — investigação concluída

Assertion original localizada em `scratchpad/sev07_saves_redo.js` linha 103:
`record("S11_redo_value_updated", valueAfter === "65,00", ...)`, onde `valueAfter = await page.inputValue("#id_whatsapp_seal_monthly_value")` lida **do formulário de edição** (GET pós-save, não do banco nem do detalhe).

- **Esperado pela assertion original:** string exata `"65,00"` (vírgula).
- **Obtido:** string `"65.00"` (ponto), tipo string (retorno de `inputValue`).
- **Origem:** campo de texto do formulário de edição, em uma releitura via GET após o salvamento — não o banco, não o detalhe.
- **Critério usado:** igualdade estrita de string.
- **Motivo concreto, demonstrado por leitura de código e confirmado por execução real nesta rodada:** `PhoneLineForm.Meta.fields` inclui `whatsapp_seal_monthly_value`; o form não declara `initial`/`prepare_value` customizado para esse campo na edição. Ao instanciar o form com `instance=`, o Django popula `self.initial` via `model_to_dict`, que lê o valor real do model (`DecimalField`) como objeto `Decimal`. Na renderização, o widget do `CharField` (`TextInput`) formata esse valor com `str(Decimal(...))`, que usa sempre ponto como separador decimal (comportamento padrão do Python, não localização do Django). **Isso não é um valor inválido nem corrompido**: a própria spec (seção "Entrada monetária") define `59,00` e `59.00` como formas de entrada igualmente válidas que resultam no mesmo `Decimal` exato — nenhuma cláusula do contrato exige que o campo de edição redisplay-e especificamente com vírgula; a exigência explícita de formato `R$ XX,XX` é para o **detalhe** (somente leitura), não para o campo editável.
- **Prova de round-trip (nova, nesta rodada):** resubmeter o formulário sem alterar o valor exibido (`"65.00"`) salvou com sucesso e preservou o mesmo `Decimal("65.00")` — confirmando que a string redisplay-ada é uma representação válida e equivalente, não um defeito. Evidência: `results_s6_s7_s11_reconciliation.json`, `S11_roundtrip_resubmit_unchanged_value_still_valid` (PASS).

**Classificação: divergência do script (assertion com expectativa não respaldada pelo contrato), não defeito de aplicação.** O `false` histórico de `S11_redo_value_updated` em `results_saves_redo.json` **foi preservado sem alteração** — não foi editado para virar PASS. O cenário real foi reexecutado em ambiente novo e identificado (`results_s6_s7_s11_reconciliation.json`), com asserções corrigidas que verificam o que o contrato de fato exige: valor persistido exato (via banco, round-trip de resubmissão) e exibição `R$ 65,00` no detalhe (contrato explícito) — ambos PASS.

Nenhum teste de regressão foi escrito para este item porque não há defeito de aplicação a regredir — a assertion do script é que foi corrigida, com a causa documentada acima.

### Dataset alterado por UPDATE — reconciliação completa

Ver `dataset-anomaly-reconciliation.md` (novo arquivo nesta pasta) para a tabela completa de 19 linhas cruzando pretendido/observado/corrigido por PK e campo, com fonte de cada valor.

**Achado principal desta reconciliação, não declarado antes:** `sev07_fix_dataset.py` corrigiu apenas categoria/plano/valor — **nunca** tocou `whatsapp_seal_activation_status`. As linhas pk=8, pk=9 e pk=19 (criadas como `NOT_ACTIVATED`, corrompidas para `ACTIVE`) **permaneceram `ACTIVE`** depois do "fix", contrariando a impressão anterior de que a correção havia restabelecido o dataset pretendido. Isso invalida especificamente os cenários S6 (original) e S6_redo, que dependiam de pk=8 estar genuinamente `NOT_ACTIVATED`. Nenhum outro cenário do aceite depende do `activation_status` de pk=8, pk=9 ou pk=19 (ver tabela de impacto em `dataset-anomaly-reconciliation.md` seção 2) — S7_redo (pk=10) e S11_redo (pk=18) usam PKs cujo `activation_status` nunca foi corrompido (apenas categoria/plano/valor, corrigidos antes dessas reexecuções rodarem).

A classificação da anomalia permanece **"causa não determinada"** — a rodada anterior já havia retirado a classificação "artefato da ferramenta" por falta de prova suficiente (ver "Ressalvas documentais" acima), e esta reconciliação não encontrou prova adicional que permita reclassificá-la em qualquer direção. Um dado novo, não conclusivo, foi registrado: a reconstrução do dataset mínimo desta rodada, feita **sem** o `runserver` ativo simultaneamente, não reproduziu a anomalia — consistente com, mas não demonstrativo de, uma hipótese de interação entre processos concorrentes contra o mesmo Postgres durante a janela de migração.

### Nova execução proporcional — S6, S7 e S11 reexecutados em ambiente novo

Ambiente: novo container Postgres descartável `sev07-recon-pg` (imagem postgres:15.8, porta 55433, banco `sev07recon`, distinto do container anterior já removido e dos recursos pré-existentes `lineops-db`/`postgres`), servidor em `127.0.0.1:8018`. Dataset mínimo (3 linhas + usuários/vínculo), cada registro **verificado imediatamente após a criação** por leitura real do banco antes de prosseguir (script `sev07recon_build_dataset.py`) — sem repetir a anomalia desta vez.

- **S6 (pk=1, estado inicial verificado `NOT_ACTIVATED`):** reexecutado com proteção dupla — camada cliente (JS ligado: `checkValidity()` bloqueia o submit nativamente, nenhum POST sai do navegador) e camada servidor (JS desligado: POST real chega ao servidor e é rejeitado com mensagem de negócio explícita: valor deve ser positivo, ativação e vencimento obrigatórios). DB confirmado inalterado após a tentativa. Evidências: `results_s6_s7_s11_reconciliation.json` (camada cliente, via submit com JS) e `results_s6_nojs_server_rejection.json` (camada servidor, prova definitiva da regra de domínio). **Isto substitui S6/S6_redo das rodadas anteriores, que — constatado nesta reconciliação — nunca geraram um POST real ao servidor (bloqueio client-side não distinguido do bloqueio de servidor no relato anterior).**
- **S7 (pk=2, estado inicial verificado `ACTIVE` com dados completos):** Ativo→Não ativado salvou com sucesso; datas confirmadas nulas por GET do formulário pós-save; categoria/plano/valor confirmados preservados no detalhe. Evidência: `results_s6_s7_s11_reconciliation.json` (nodes `S7_*`). Resultado consistente com `S7_redo` da rodada anterior (que já não estava contaminado pela lacuna do dataset) — reconfirmado em ambiente totalmente novo.
- **S11 (pk=3, estado inicial verificado: valor 59,00, alocada, `activated_at` de fixture preenchido em 15/08/2026 10:30, não vazio→vazio):** editado somente o valor para 65,00. Confirmado por banco (via detalhe, que lê o model real) e por GET do formulário: `employee` e `status` (ALLOCATED) idênticos antes/depois; `activated_at` idêntico e **preenchido** antes/depois (comprovação real de preservação, não trivial); detalhe exibe `R$ 65,00` (contrato explícito); round-trip de resubmissão sem alteração confirma que a representação redisplay-ada (`65.00`) é válida e equivalente. 18/19 asserções PASS nesta rodada; a única falha (`S6_error_mentions_date_or_value`) foi um problema de extração de texto do próprio script (captura vazia por timing), corrigido e reconfirmado em `results_s6_nojs_server_rejection.json` com o texto real do erro do servidor.

**Cenários não reexecutados nesta rodada (reaproveitados com justificativa, não por rotina):** S1–S5, S8, S9a/S9b, S10a/S10b, M01–M15, fases de consumidores/relatórios/sem-JS — nenhum depende de pk=8, pk=9 ou pk=19 (ver tabela de impacto), e nenhum teve sua própria assertion questionada nesta revisão. Não foram repetidos por não haver indício de contaminação nem de erro de assertion neles. A validação Postgres da migration (forward/backfill/reversão) também não foi reexecutada — é independente do dataset de aceite de navegador e não foi questionada nesta revisão.

### git status vs. conteúdo — reconciliado

A frase "git status idêntico, só evidências novas" da rodada original é, de fato, **apenas o relato do executor quanto a conteúdo** — procede, porém, quanto à **lista de caminhos**: o `git status --short` capturado automaticamente pelo ambiente no início da sessão (antes de qualquer ação desta task) lista exatamente os mesmos arquivos `M`/`??` de código de aplicação que o `git status --short` desta reconciliação, com a única adição de `docs/superpowers/evidence/SEV-07/` — essa comparação de caminhos **é verificável de forma independente** (a lista inicial não foi gerada por mim, veio do próprio ambiente). O que **não** é verificável de forma independente nesta revisão é se o **conteúdo byte-a-byte** de cada arquivo já listado como `M`/`??` mudou, porque nenhum `git diff --stat` ou hash de conteúdo foi capturado como linha de base antes do início de SEV-07 — apenas o `git diff --stat` desta própria sessão (768 inserções/48 deleções em 10 arquivos), que não tem com o que ser comparado retroativamente. Mantida, portanto, como relato do executor para o nível de conteúdo, e como fato verificado para o nível de lista de caminhos.

### Verificação e documentação desta rodada

```
venv/Scripts/python.exe manage.py check --settings=config.settings_dev
  → System check identified no issues (0 silenced).

git diff --check
  → sem erro (mesmos avisos informativos de LF/CRLF já presentes)

git status --short
  → lista de caminhos idêntica à capturada pelo ambiente no início da
    sessão, mais docs/superpowers/evidence/SEV-07/ (ver reconciliação
    acima sobre o alcance real desta comparação)
```

Nenhum código de aplicação foi alterado nesta reconciliação (apenas scripts de scratchpad novos e arquivos desta pasta de evidência); por isso nenhuma suíte pytest foi reexecutada — não há código novo para cobrir, e a reexecução de S6/S7/S11 via navegador real já fornece a prova funcional pedida.

### Compliance Report desta reconciliação

- **Divergência S11:** reconciliada. Causa demonstrada (redisplay de `Decimal` via `str()` no campo de edição, comportamento consistente com o contrato de entrada, que aceita ponto e vírgula como equivalentes). Classificada como ajuste de assertion do script, não defeito de aplicação. `false` histórico preservado; nova evidência com asserções corrigidas, incluindo prova de round-trip.
- **Dataset por UPDATE:** reconciliado por completo. Tabela de 19 linhas com pretendido/observado/corrigido. Lacuna real encontrada (activation_status de pk=8,9,19 nunca corrigido) e seu impacto delimitado (somente S6/S6_redo). S6 reexecutado com premissa genuinamente correta em ambiente novo.
- **Anomalia de dataset:** permanece "causa não determinada" — nenhuma prova nova suficiente para reclassificar. Um dado adicional não conclusivo foi registrado.
- **Prontidão de fechamento:** com a divergência S11 reconciliada, o impacto do UPDATE delimitado e S6 reexecutado com premissa válida (camada cliente e servidor comprovadas separadamente), **as três condições do critério de fechamento desta reconciliação estão atendidas**. SEV-07 pode ser considerada concluída, com as limitações explícitas abaixo mantidas abertas (não bloqueantes): causa raiz da anomalia de dataset não determinada; navegador headless; smoke (não suíte completa) de relatórios; exportações CSV/XLSX não exercitadas.
- Sem commit, push, deploy, acesso a PRD ou alteração de contrato nesta reconciliação.

### Limpeza desta rodada

- Container `sev07-recon-pg` e `runserver 127.0.0.1:8018`: criados nesta reconciliação, encerrados ao final.
- Container `sev07-disposable-pg` da rodada anterior: já havia sido removido antes desta reconciliação começar (confirmado por `docker ps -a` no início desta rodada).
- Recursos pré-existentes (`lineops-db`, `postgres`/pgvector): confirmados intactos por `docker ps -a` no início e no fim desta rodada.

Parado antes de SEV-08.
