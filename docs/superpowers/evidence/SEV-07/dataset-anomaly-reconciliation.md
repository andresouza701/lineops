# SEV-07 — Reconciliação da anomalia de dataset e da divergência S11

Data desta reconciliação: 2026-10-01 (mesma data do aceite original,
rodada de reconciliação solicitada após revisão documental).

Fonte dos dados históricos: `scratchpad/sev07_build_dataset.py`,
`scratchpad/sev07_fix_dataset.py` (ambos preservados na pasta de
scratchpad da sessão) e as saídas de execução desses scripts,
registradas na transcrição desta mesma sessão (não há log de arquivo
separado do `sev07_build_dataset.py` original — limitação explícita,
ver seção 4).

## 1. Inventário completo dos registros afetados (categoria/plano/valor)

Todos os `PhoneLine` criados via `PhoneLine.objects.create(...)` direto
no ORM em `sev07_build_dataset.py` **após** a classificação do legado
(ou seja, todas as linhas de 6 a 19, exceto a 7, que não tem selo)
tiveram `whatsapp_seal_category`, `whatsapp_seal_plan` e
`whatsapp_seal_monthly_value` persistidos vazios/nulos apesar de
passados explicitamente como argumentos ao `.create()`. A tabela abaixo
cruza o valor **pretendido** (lido do código-fonte de
`sev07_build_dataset.py`), o valor **observado antes da correção**
(capturado por consulta direta ao banco, registrado nesta mesma sessão
antes de qualquer `UPDATE`) e o valor **aplicado pela correção**
(`sev07_fix_dataset.py`):

| PK | Linha (variável no script) | Campo | Pretendido na criação | Observado antes do fix | Aplicado pelo fix | Corrigido? |
| --- | --- | --- | --- | --- | --- | --- |
| 6 | `deleted_line` | category/plan/value | PERSONAL_CREATOR / STANDARD / 59.90 | '' / '' / None | PERSONAL_CREATOR / STANDARD / 59.90 | Sim |
| 6 | `deleted_line` | activation_status | ACTIVE | ACTIVE | *(não tocado pelo fix)* | N/A — coincide com o pretendido, corrupção indetectável neste campo especificamente |
| 8 | `line_na_zero` | category/plan/value | CREATORS_BUSINESSES / ONE_ESSENTIAL / 0.00 | '' / '' / None | CREATORS_BUSINESSES / ONE_ESSENTIAL / 0.00 | Sim |
| 8 | `line_na_zero` | **activation_status** | **NOT_ACTIVATED** | **ACTIVE** | ***(não tocado pelo fix — permaneceu ACTIVE)*** | **Não** |
| 9 | `line_na_pos` | category/plan/value | BUSINESS_SME / BUSINESS_BASIC / 53.90 | '' / '' / None | BUSINESS_SME / BUSINESS_BASIC / 53.90 | Sim |
| 9 | `line_na_pos` | **activation_status** | **NOT_ACTIVATED** | **ACTIVE** | ***(não tocado pelo fix — permaneceu ACTIVE)*** | **Não** |
| 10 | `active_lines["mais8"]` | category/plan/value | CREATORS_BUSINESSES / ONE_ESSENTIAL / 59.00 | '' / '' / None | CREATORS_BUSINESSES / ONE_ESSENTIAL / 59.00 | Sim |
| 10 | idem | activation_status | ACTIVE | ACTIVE | *(não tocado)* | N/A — coincide com o pretendido |
| 11 | `active_lines["mais7"]` | category/plan/value | CREATORS_BUSINESSES / ONE_ESSENTIAL / 59.00 | '' / '' / None | *(não incluído no fix — selo já havia sido removido pelo cenário S8 antes da correção rodar)* | Não aplicável — selo removido torna os 3 campos irrelevantes |
| 12 | `active_lines["mais1"]` | category/plan/value | CREATORS_BUSINESSES / ONE_ESSENTIAL / 59.00 | '' / '' / None | CREATORS_BUSINESSES / ONE_ESSENTIAL / 59.00 | Sim |
| 13 | `active_lines["hoje"]` | category/plan/value | CREATORS_BUSINESSES / ONE_ESSENTIAL / 59.00 | '' / '' / None | CREATORS_BUSINESSES / ONE_ESSENTIAL / 59.00 | Sim |
| 14 | `active_lines["menos1"]` | category/plan/value | CREATORS_BUSINESSES / ONE_ESSENTIAL / 59.00 | '' / '' / None | CREATORS_BUSINESSES / ONE_ESSENTIAL / 59.00 | Sim |
| 15 | combo META_VERIFIED/PERSONAL_CREATOR | category/plan/value | PERSONAL_CREATOR / STANDARD / 53.90 | '' / '' / None | PERSONAL_CREATOR / STANDARD / 53.90 | Sim |
| 16 | combo META_VERIFIED/BUSINESS_SME | category/plan/value | BUSINESS_SME / BUSINESS_BASIC / 53.90 | '' / '' / None | BUSINESS_SME / BUSINESS_BASIC / 53.90 | Sim |
| 17 | combo META_VERIFIED/BUSINESS | category/plan/value | BUSINESS / BUSINESS_PLUS / 109.00 | '' / '' / None | BUSINESS / BUSINESS_PLUS / 109.00 | Sim |
| 18 | `allocated_line` | category/plan/value | CREATORS_BUSINESSES / ONE_ESSENTIAL / 59.00 | '' / '' / None | CREATORS_BUSINESSES / ONE_ESSENTIAL / 59.00 | Sim |
| 18 | idem | activation_status | ACTIVE | ACTIVE | *(não tocado)* | N/A — coincide com o pretendido |
| 19 | `other_allocated_line` | category/plan/value | BUSINESS_SME / BUSINESS_BASIC / 0.00 | '' / '' / None | BUSINESS_SME / BUSINESS_BASIC / 0.00 | Sim |
| 19 | `other_allocated_line` | **activation_status** | **NOT_ACTIVATED** | **ACTIVE** | ***(não tocado pelo fix — permaneceu ACTIVE)*** | **Não** |

**Legenda de certeza:** "Observado antes do fix" vem de uma consulta real ao banco (`PhoneLine.all_objects.all()`), executada e impressa nesta mesma sessão antes de rodar `sev07_fix_dataset.py` — não é reconstrução por memória. "Pretendido" vem de leitura direta do código-fonte de `sev07_build_dataset.py` (arquivo preservado, não editado desde a criação). O "Aplicado pelo fix" vem da saída real de execução de `sev07_fix_dataset.py`, também capturada nesta sessão.

**Achado desta reconciliação, não registrado anteriormente:** `sev07_fix_dataset.py` corrigiu **apenas** `whatsapp_seal_category`, `whatsapp_seal_plan` e `whatsapp_seal_monthly_value` — o dicionário `fixes` do script **não contém a chave `whatsapp_seal_activation_status`** para nenhum PK. Como consequência, **pk=8, pk=9 e pk=19 permaneceram com `activation_status="ACTIVE"` mesmo depois da correção**, apesar de terem sido criados com `NOT_ACTIVATED`. Isso não foi declarado na rodada anterior (que mencionava "pk=8,9,19" apenas no contexto da classificação original, sem deixar explícito que o campo de situação desses três registros **não fazia parte** da correção aplicada).

## 2. Cenários potencialmente contaminados por essa lacuna

| Cenário | Usa PK afetado por status não corrigido? | Depende de `activation_status` desse PK? | Classificação |
| --- | --- | --- | --- |
| S6 (original) | pk=8 | Sim — pressupõe estado inicial NOT_ACTIVATED | **Contaminado — invalidado** |
| S6_redo | pk=8 | Sim — mesma premissa | **Contaminado — invalidado** |
| S7_redo | pk=10 | Não (pk=10 nunca teve o status corrompido — apenas categoria/plano/valor, corrigidos antes do S7_redo rodar) | Não contaminado |
| S11_redo | pk=18 | Não (pk=18 é ACTIVE em ambos os casos — pretendido e observado) | Não contaminado |
| Overview "Não ativado" distinto de "Sem selo" | Usa `+5511900001001`/`+5511900001002` (S1/S2, criados via navegador, independentes do dataset ORM) | Não | Não contaminado |
| Smoke relatório Selos (exclui Não ativado) | Usa `+5511900001001`/`+5511900001002` (idem) | Não | Não contaminado |
| Escopo OPERATOR (operador 2 vê pk=19) | pk=19 | Não — a checagem é de alocação/visibilidade, não de `activation_status` | Não contaminado |

**Conclusão:** apenas S6 e S6_redo foram efetivamente invalidados pela lacuna do fix. Nenhum outro cenário do aceite depende do campo `activation_status` desses três PKs especificamente.

## 3. Nova execução: S6 reconciliado (ambiente novo, isolado)

Como o container descartável original (`sev07-disposable-pg`) já havia
sido removido ao final da task anterior, esta reconciliação usa um
**novo** container descartável, `sev07-recon-pg` (porta 55433, banco
`sev07recon`), com um **dataset mínimo novo e verificado
imediatamente após a criação** (script `sev07recon_build_dataset.py`,
cada linha criada é lida de volta do banco e comparada ao esperado
antes de prosseguir — ver saída real em `results_s6_s7_s11_reconciliation.json`
e nos logs desta sessão).

**Observação adicional (não conclusiva):** nesta rodada, o dataset foi
criado **sem** o `runserver` ativo simultaneamente (diferença
deliberada em relação à rodada anterior). As três linhas criadas via
ORM direto persistiram corretamente em todos os campos, sem reproduzir
a anomalia. Isso é um dado a mais, não uma prova — uma única repetição
sem o fator "processo concorrente" não isola a causa com certeza
estatística, mas é consistente com a hipótese (já registrada
anteriormente como não comprovada) de que a concorrência entre o
`runserver` e o script de setup teve algum papel. **A classificação
"causa não determinada" é mantida** — não há evidência suficiente
nesta reconciliação para reclassificar a anomalia como resolvida ou
como tendo uma causa raiz comprovada.

**Resultado do S6 reconciliado — duas camadas distintas, ambas comprovadas separadamente:**

1. **Camada cliente (JS ligado):** com o seletor de Situação alterado para `ACTIVE` em uma linha que começa genuinamente `NOT_ACTIVATED` (pk=1, verificado), o navegador bloqueia o `submit` via validação HTML5 nativa (`checkValidity()` reporta os campos de data como inválidos, mensagem "Preencha este campo.") — **nenhuma requisição POST chega ao servidor** nesse caminho. Evidência: `results_s6_nojs_server_rejection.json`, chave `clientSideValidityCheck`.
2. **Camada servidor (JS desligado, POST real):** com JavaScript desabilitado, o mesmo POST (situação=ACTIVE, sem datas, valor mantido em 0,00) **chega de fato ao servidor**, que rejeita com a mensagem real: *"Valor mensal (R$): Selo ativo exige valor mensal maior que zero. Ativação: Data de ativação do selo é obrigatória. Vencimento: Data de vencimento do selo é obrigatória."* — confirmando a regra de domínio ("Ativo exige datas e valor positivo") como validação de **servidor**, não apenas UX de JavaScript. Evidência: `results_s6_nojs_server_rejection.json`, chave `serverSideNoJsAttempt`. DB confirmado inalterado (`rejectedAtServer: true`, detalhe pós-tentativa ainda mostra "Não ativado").

**Achado de precisão desta reconciliação:** a tentativa original de S6 (e o S6_redo da rodada anterior) rodaram sempre com JavaScript ligado. Pela mecânica do formulário (`phone-line-form.js` marca os campos de data como `required` quando a situação selecionada é `ACTIVE`), **o clique no botão "Salvar alterações" nunca gerou um POST real para o servidor** nesses dois casos anteriores — o navegador bloqueou a submissão antes de qualquer requisição de rede. Isso não foi distinguido explicitamente no relato anterior, que tratou "ficou na mesma página" como prova de rejeição de servidor. Com a reconciliação desta rodada, a regra agora está comprovada nas duas camadas, separadamente.

## 4. Limitações explícitas desta reconciliação

- Não existe um arquivo de log persistido com a saída bruta e completa de `sev07_build_dataset.py` (rodada original) — apenas o código-fonte do script (preservado) e as saídas de verificação capturadas na transcrição desta mesma sessão (usadas como fonte nesta reconciliação, não inventadas retroativamente).
- O container Postgres descartável original (`sev07-disposable-pg`) foi removido antes desta reconciliação; não é possível consultar o estado exato do banco daquela rodada hoje. A tabela da seção 1 depende das saídas já capturadas nesta sessão antes da remoção, não de uma nova consulta ao banco antigo.
- A causa raiz da anomalia de categoria/plano/valor continua **não determinada**. Esta reconciliação acrescenta um dado (ausência de reprodução sem `runserver` concorrente) sem convertê-lo em prova de causa.
