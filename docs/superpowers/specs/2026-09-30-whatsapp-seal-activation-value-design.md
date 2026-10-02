# Fonte da verdade — Ativação, categoria, plano e valor mensal do selo

Data: 2026-09-30. Identificador: SEV.

Atualização de escopo: 2026-10-01 — categoria e plano solicitados pelo usuário, com catálogo de valores de referência abaixo.

Status: SEV-02 concluída em 01/10/2026. SEV-03 (testes RED) concluída em 01/10/2026. SEV-04 (modelo, domínio e migration) concluída em 01/10/2026, retificada em 01/10/2026 (dois desvios de contrato encontrados e corrigidos). SEV-05 (formulários e salvamento) concluída em 01/10/2026. SEV-06 (interface e consumidores) concluída em 01/10/2026. SEV-07 (aceite real em navegador) concluída em 01/10/2026, reconciliada em 01/10/2026 (revisão documental identificou divergência não resolvida em `S11_redo_value_updated` e alcance incompleto da correção de dataset; ambas reconciliadas com evidência nova — ver `docs/superpowers/evidence/SEV-07/report.md` seção "Reconciliação — rodada 2" e `dataset-anomaly-reconciliation.md`). **SEV-08 (revisão final e preparação de entrega) concluída em 01/10/2026 — veredito: pronto para integração, com limitações não bloqueantes explícitas (navegador headless, causa da anomalia de dataset não determinada, exportações de relatório não exercitadas, recuperação do stash histórico não certificável retroativamente); sem commit/push/versão/deploy.** Registros anteriores de pendência são históricos. **Estado de implantação: domínio/migração/formulário/salvamento/interface/aceite visual e funcional em navegador real (Chrome 151, headless, via Playwright) e validação Postgres real da migration 0022 (forward/backfill/reversão) concluídos e GREEN, sem crash, sem portão, sem gravação parcial, sem regressão. Revisão de diff completo e matriz requisito→teste→evidência consolidada em SEV-08, 691 testes aprovados, 1 skipped e 30 subtestes aprovados (8 deselected separados), 0 failed.**

Este documento concentra contrato, tasks, decisões e evidências desta evolução. Não criar backlog paralelo. Evolui [SEL](2026-09-17-phone-line-whatsapp-seal-design.md); os demais requisitos de SEL continuam válidos. O [contrato dos relatórios](2026-09-22-reports-hub-design.md) permanece vigente salvo alteração explicitamente aprovada.

## Spec Summary

Permitir identificar linhas que possuem selo ainda não ativado e cadastrar o valor mensal de cada selo em reais. Usar o bloco SELO WHATS LINEOPS existente, preservando layout, permissões e dados operacionais da linha.

### Aprovações do usuário

1. Selo não ativado: sem data de ativação, sem vencimento e sem alerta.
2. Valor mensal em R$ por linha, editável e obrigatório com selo, inclusive não ativado.
3. Selos existentes considerados ativos, preservando datas.
4. Valor legado fica vazio na migração, sem valor inventado; preenchimento obrigatório na próxima edição.
5. Incluir categoria e plano do selo, conforme catálogo informado em 01/10/2026.
6. Aprovação adicional em 01/10/2026: categoria e plano obrigatórios com selo, inclusive Não ativado; legados ficam vazios, com preenchimento obrigatório na próxima edição; preços apresentados apenas como referência e valor efetivo preenchido manualmente.

### Categoria, plano e valor — adendo de 01/10/2026

Fonte dos preços: tabela fornecida pelo usuário, sem verificação externa de preços comerciais. Tratar como referência de cadastro, não como garantia de preço atual da Meta nem como restrição automática sobre o valor efetivo da linha.

| Selo | Categoria | Plano | Referência mensal informada |
| --- | --- | --- | --- |
| META ONE | Criadores / Empresas | One Essencial | R$ 59,00 |
| META VERIFICADO | Pessoa Física (Uso Pessoal / Criador) | Standard | R$ 53,90 a R$ 69,90 (varia por app/iOS/web) |
| META VERIFICADO | Pessoa Jurídica (Empresas / PMEs) | Business Básico | R$ 53,90 |
| META VERIFICADO | Pessoa Jurídica (Empresas) | Business Plus | R$ 109,00 a R$ 120,90 |

- Tipo, categoria e plano são conceitos distintos. Manter as quatro combinações acima, sem fundir as duas categorias de Pessoa Jurídica silenciosamente.
- Valor mensal efetivo continua sendo um único Decimal editável por linha. Faixa não cabe no campo monetário; não usar média, mínimo ou máximo como valor contratado presumido.
- A referência não sobrescreve valores já salvos e não autoriza backfill financeiro de legados. Exibir referência separadamente do valor efetivo.
- Proposta de interface: ordem Selo → Categoria → Plano → Situação → Valor mensal (R$), seguida dos detalhes existentes. Opções dependentes da combinação; validar também no servidor, com/sem JS. Categoria/plano devem aparecer no detalhe ao lado dos dados do selo.
- Ao remover selo, categoria/plano também deixam de se aplicar. Ao trocar tipo/categoria, não salvar combinação incompatível nem substituir valor editado silenciosamente.
- Aprovado em 01/10/2026: categoria/plano obrigatórios com selo; legados vazios até a próxima edição, quando o preenchimento será exigido; valor efetivo manual, inclusive nos planos com preço fixo de referência. Trocas invalidam seleção incompatível e preservam o valor digitado, conforme aprovação de fechamento SEV-02.
- Nenhuma nova coluna/filtro de relatório foi solicitada neste adendo; manter os limites da seção de relatórios.

### Matriz de estados

| Estado | Tipo de selo | Datas do selo | Valor mensal | Indicador |
| --- | --- | --- | --- | --- |
| Sem selo | Vazio | Vazias | Vazio | Sem selo |
| Não ativado | META ONE ou META VERIFICADO | Vazias | Obrigatório | Não ativado, neutro |
| Ativo | META ONE ou META VERIFICADO | Ativação e vencimento obrigatórios; vencimento manual >= ativação | Obrigatório | Regra atual de vencimento |
| Ativo legado, antes da primeira edição | Tipo preservado | Datas preservadas | Vazio permitido apenas como estado legado persistido | Regra atual de vencimento |

Ativo significa que o selo foi ativado, não que está dentro da validade: selo vencido continua ativo quanto à ativação, com alerta vermelho. Não confundir essa situação com PhoneLine.status nem PhoneLine.activated_at.

E-mail e pagamento continuam obrigatórios quando há selo, conforme SEL: não foi aprovada flexibilização desses campos. Tipos de selo e pagamento atuais permanecem iguais.

### Fluxos e validação

- Aplicar o mesmo contrato nos formulários de cadastro e edição, que compartilham implementação. Não introduzir cadastro capaz de criar dados incompatíveis com a edição.
- Ativar exige datas válidas e valor. Não calcular vencimento nem valor a partir do tipo ou de outro registro.
- Ao salvar Sem selo, limpar dados próprios do selo, incluindo situação e valor; não recuperar dados antigos em reativação da linha.
- Ao salvar Não ativado, as datas devem ficar nulas e não gerar alerta. Ativo → Não ativado é permitido: limpar datas ao salvar, preservando tipo, categoria, plano, valor, e-mail e pagamento.
- Alternar seletores antes de salvar não deve destruir valores digitados; normalização ocorre no salvamento conforme o estado final.
- Valor ausente em legado não impede abrir a página nem consultar listagens. Salvar a edição da linha com selo exige valor; remover o selo permite salvar sem ele.
- Não aplicar essa exigência indiscriminadamente a ações independentes como Liberar/alocar/cancelar: preservar seus contratos atuais e testar os caminhos reais.
- Dados inválidos retornam erro de campo compreensível, preservam entradas aplicáveis e não geram gravação parcial ou mensagens contraditórias.
- Valor usa Decimal/DecimalField, nunca float. Exibir moeda brasileira. Não converter ausência em R$ 0,00.
- Limites aprovados em 01/10/2026: Não ativado aceita valor de R$ 0,00 a R$ 299,00, inclusive; Ativo exige valor maior que zero e no máximo R$ 299,00. Rejeitar negativos em ambos. Selo ativo vencido também exige valor positivo; vencimento não significa Não ativado.
- Ativar selo com valor zero exige informar valor positivo antes de salvar; não ajustar preço automaticamente. Valor ausente continua inválido no salvamento com selo, inclusive Não ativado.
- Não alterar histórico, status, activated_at, vínculo ou alocação por editar somente dados do selo.

### Interface e superfícies consumidoras

- Manter seletor de tipo de selo; acrescentar categoria, plano, situação de ativação e Valor mensal (R$) dentro do mesmo bloco, conforme adendo e decisões SEV-02.
- Com selo: mostrar categoria, plano, situação, referência de preço, valor efetivo, e-mail e pagamento. Datas aplicáveis somente a Ativo.
- Sem JavaScript: todos os controles necessários permanecem acessíveis; validação condicional no servidor. Com JavaScript: sincronizar visibilidade/required sem bloquear transições com campos inaplicáveis.
- Detalhe: mostrar situação e valor; ausência legada identificada como Não informado, nunca zero.
- Overview, Carregar mais e listagem OPERATOR: distinguir selo Não ativado de Sem selo, usando o indicador centralizado. Não adicionar valor financeiro a essas listagens nesta entrega.
- Preservar fundo azul escuro, contraste, teclado, resumo de erros, contenção móvel e ação Liberar.
- Permissões atuais de cadastro/edição/detalhe/listagens permanecem; a exclusividade ADMIN do hub de Relatórios não deve ser aplicada acidentalmente à navegação Telecom.

### Relatórios: limite desta evolução

O relatório Selos WhatsApp hoje filtra por whatsapp_seal_activated_on. Não ativados, sem essa data, não atendem a um período de ativação e ficam fora do relatório e de sua exportação. Isso é consequência do contrato atual, não licença para inventar data substituta.

Nesta entrega não incluir coluna de valor, total financeiro, novo filtro ou mudança de período nos relatórios. Testar compatibilidade de Selos e Inventário, inclusive com/sem selo: possuir selo não depende de estar ativado. Se o usuário desejar relatório dos não ativados ou custos, registrar aprovação e adendo neste documento antes de alterar contratos de relatório.

## Gap Analysis

### Mapeamento verificado em 30/09/2026

| Caminho | Situação atual / impacto |
| --- | --- |
| telecom/whatsapp_seal.py | validate_seal_fields exige quatro detalhes; compute_seal_status trata ausência de vencimento como Sem selo; clear_seal_fields limpa cinco campos |
| telecom/models.py | PhoneLine tem cinco campos de selo; clean/seal_status/create_or_reuse precisam integrar novos dados |
| telecom/forms.py | PhoneLineForm/PhoneLineUpdateForm compartilham campos; full_clean normaliza Sem selo; _post_clean evita erro obrigatório contraditório após erro de formato |
| static/js/phone-line-form.js | Atualmente exige todos os detalhes quando há selo; precisa distinguir datas condicionais |
| templates/telecom/phoneline_form.html | Bloco compartilhado de cadastro/edição |
| templates/telecom/phoneline_detail.html | Detalhes do selo e badge |
| templates/telecom/_seal_status_badge.html | Apresentação compartilhada de situação |
| templates/telecom/overview.html e telecom/views.py | Render inicial e payload main/Carregar mais consomem seal_status |
| templates/telecom/operator_lines.html | Listagem real que também consome seal_status |
| core/services/whatsapp_seal_report_service.py | Período por ativação; não ativados naturalmente excluídos |
| telecom/migrations/0021_phoneline_whatsapp_seal_and_more.py | Migração original; criar sucessora conforme grafo atual, sem editar a antiga |

### Decisões complementares, sem aprovação inventada

Decisões consolidadas em SEV-02 (01/10/2026):

1. **Resolvido — aprovado em 01/10/2026:** zero permitido somente para Não ativado; Ativo exige valor positivo. Negativos rejeitados; ausência não equivale a zero.
2. **Resolvido:** máximo R$ 299,00 aprovado. Decisão técnica: DecimalField(max_digits=5, decimal_places=2), validador de máximo Decimal("299.00") e parsing definido abaixo, sem arredondamento silencioso.
3. **Aprovado:** permitir Ativo → Não ativado, limpar datas somente ao salvar e preservar tipo/categoria/plano/valor/e-mail/pagamento.
4. **Aprovado:** novo selo inicia Não ativado. Chamadores sem selo continuam Sem selo. O default é aplicado à apresentação de formulário novo; POST com selo sem situação explícita é inválido, não deve converter edição de ativo silenciosamente.
5. **Resolvido — aprovado em 01/10/2026:** categoria/plano obrigatórios com selo, inclusive Não ativado; legados vazios, exigidos na próxima edição. Não inferir plano histórico pelo tipo do selo.
6. **Resolvido — aprovado em 01/10/2026:** preço exibido como referência; valor efetivo preenchido manualmente, inclusive para preços fixos. Sem preenchimento automático, escolha de valor de faixa ou sobrescrita de edição manual.
7. **Aprovado:** ao trocar tipo/categoria, invalidar categoria/plano incompatíveis e exigir seleção válida, preservando valor digitado para revisão. Sem JS, POST incompatível retorna erro, sem gravação parcial; com JS, remover apenas seleções incompatíveis. Não há gestão de catálogo nesta entrega.

Nenhuma decisão de produto impeditiva restante. Detalhes técnicos abaixo são decisões de implementação, não declarações de aprovação literal do usuário.

## Contrato técnico e persistência

### Campos e tokens — decisão técnica SEV-02

Persistir em PhoneLine:

| Campo | Tipo / valores |
| --- | --- |
| whatsapp_seal_activation_status | CharField: vazio sem selo; NOT_ACTIVATED (Não ativado); ACTIVE (Ativo) |
| whatsapp_seal_category | CharField: vazio no legado/sem selo; tokens do catálogo abaixo |
| whatsapp_seal_plan | CharField: vazio no legado/sem selo; tokens do catálogo abaixo |
| whatsapp_seal_monthly_value | DecimalField(max_digits=5, decimal_places=2), null para legado/sem selo; limite validado 299,00 |

Catálogo centralizado em telecom/whatsapp_seal.py; códigos estáveis, rótulos preservados da tabela do usuário:

| Selo | Token categoria | Token plano |
| --- | --- | --- |
| META_ONE | CREATORS_BUSINESSES | ONE_ESSENTIAL |
| META_VERIFIED | PERSONAL_CREATOR | STANDARD |
| META_VERIFIED | BUSINESS_SME | BUSINESS_BASIC |
| META_VERIFIED | BUSINESS | BUSINESS_PLUS |

Categoria/plano obrigatórios em qualquer novo salvamento com selo. Legados permanecem vazios até edição, sem inferência automática mesmo onde só exista uma opção. Referências de preço são ajuda visual, não limite mínimo/máximo por plano; somente os limites monetários globais aprovados são impostos. Manter seal_status calculado; não persistir estado de vencimento.

### Entrada monetária — decisão técnica SEV-02

Aceitar dígitos com zero, uma ou duas casas decimais, separador vírgula ou ponto, espaços externos removidos: 59, 59,0, 59,00, 59.00. Interpretar como Decimal exato; exibir R$ 59,00. Rejeitar símbolo monetário no input, separadores de milhar, separadores misturados, notação científica, NaN/Infinity e mais de duas casas (inclusive 1,000); não arredondar. Rejeitar qualquer sinal negativo, inclusive -0,00. Usar controle compatível com vírgula e teclado decimal, não depender da validação nativa de input number para aceitar formato brasileiro. Mensagem de ajuda deve explicar formato sem separador de milhar.

Ativo: 0,01–299,00; Não ativado: 0,00–299,00. Ausência é inválida para ambos no salvamento. Sem selo normaliza todos os dados próprios para vazio/null antes do parsing; Não ativado normaliza apenas datas inaplicáveis, preservando campos obrigatórios. Não alterar valor ao escolher plano.

### Compatibilidade de serviço — decisão técnica SEV-02

create_or_reuse recebe quatro kwargs novos opcionais para não quebrar chamadas Sem selo existentes. Se o chamador informar selo, exigir situação/categoria/plano/valor válidos via domínio; não presumir ACTIVE nem usar default para mascarar argumentos ausentes. Preservar API save(commit=False) sem escrita; form válido entrega os campos normalizados na instância. Migração usa modelos históricos sem a validação nova. Não adicionar full_clean ao save global da linha: operações independentes e dados legados não devem ser bloqueados por exigências do formulário.

Migração aditiva: classificar registros com selo existente como ativos e sem selo como ausência; valor null em todos os legados; preservar datas, inclusive inconsistências anteriores, sem backfill inventado. Usar modelos históricos da migração e incluir linhas excluídas logicamente. Não chamar full_clean em massa para corrigir dados antigos.

Novos salvamentos de cadastro/edição aplicam obrigatoriedade; null de compatibilidade no banco não torna valor opcional na interface. Avaliar constraints compatíveis com o legado; não adicionar constraint que inviabilize o backfill.

Testar reversão em banco descartável: dados anteriores à feature preservados. Reverter campos novos perde situação/valor novos; rollback operacional preferirá imagem anterior com colunas mantidas. Código antigo pode interpretar Não ativado incorretamente ou exigir datas: registrar essa limitação antes do deploy, sem prometer rollback funcional transparente.

Não gerar migration de drift alheio (PhoneLine.origem/DailyUserAction.action_type). Não aplicar migrations em PRD nesta etapa.

## Implementation Plan — tasks

Executar sequencialmente via executing-plans, uma task por vez. Atualizar evidências aqui; nenhum commit/push/deploy implícito. Prefixo SEV evita confusão com SEL e REL concluídas.

- [x] **SEV-01 — Fonte da verdade e levantamento inicial.** Registrar aprovações, matriz, impactos, lacunas e tasks. Saída: este arquivo; apenas documentação.
- [x] **SEV-02 — Fechar contrato complementar.** Concluída em 01/10/2026: decisões de produto aprovadas, tokens/parsing/defaults definidos, chamadores e Liberar inspecionados. Nenhum código de aplicação alterado.
- [x] **SEV-03 — Testes RED.** Concluída em 01/10/2026, corrigida em 01/10/2026 (retificação de qualidade: removidos 1 placeholder `pytest.fail` incondicional de T10 e 1 teste de símbolo inventado de T17). Criado telecom/test_whatsapp_seal_activation_value.py (75 nodes); telecom/test_phoneline_form_ui.py não precisou de ampliação. Ver Registro de execução.
- [x] **SEV-04 — Modelo, domínio e migration.** Concluída em 01/10/2026, **retificada em 01/10/2026**. Alterados telecom/models.py e telecom/whatsapp_seal.py; migration 0022 com backfill e testes reais de reversão em banco isolado (T10). A primeira rodada introduziu dois desvios de contrato (portão de validação e fallback de save() que inferia situação) para evitar um crash de fronteira com o ModelForm atual; ambos foram **removidos** nesta retificação, restabelecendo obrigatoriedade incondicional. O crash de fronteira (`ValueError` em `ModelForm._post_clean`) é real, confirmado no Django instalado, e permanece **sem solução nesta task** — não foi mascarado, é uma dependência explícita de SEV-05. create_or_reuse não foi alterado (fora de escopo). Ver Registro de execução (retificação) para o relatório de conformidade completo e o estado real de implantação.
- [x] **SEV-05 — Formulários e salvamento.** Concluída em 01/10/2026. Integrados telecom/forms.py e create_or_reuse; _post_clean reutilizado sem duplicar validação de Model.clean. Provados Decimal, limpeza condicional, legado, save(commit=False), atualização real via refresh_from_db e ações independentes preservadas. GREEN em todos os cenários de form/HTTP alcançáveis sem template novo (3 nodes de template/HTML ficam RED, explicitamente atribuídos a SEV-06 — ver Registro de execução).
- [x] **SEV-06 — Interface e consumidores.** Concluída em 01/10/2026. Alterados templates/telecom/phoneline_form.html, static/js/phone-line-form.js, templates/telecom/phoneline_detail.html; telecom/models.py (property de apresentação), telecom/whatsapp_seal.py (catálogo serializável) e telecom/views.py (contexto do catálogo). Overview/Carregar mais/OPERATOR já reutilizavam seal_status/badge compartilhado desde SEV-04 — confirmado, não alterado. Ver Registro de execução para o relatório de conformidade completo.
- [x] **SEV-07 — Aceite real.** Concluída em 01/10/2026. Ambiente Postgres descartável (Docker), dataset legado migrado + novos registros, navegador real (Chrome 151 via Playwright) em 1280/390/360, com/sem JS. Salvar/ativar/editar/remover, valor inválido, datas, consumidores e relatórios comprovados via navegador — não fechada por HTML de test client. Validação Postgres real da migration 0022 (forward/backfill/reversão) também concluída nesta task. Artefatos em `docs/superpowers/evidence/SEV-07/`. Ver Registro de execução para o relatório de conformidade completo e limitações explícitas (headless, não headed).
- [x] **SEV-08 — Revisão e preparação de entrega.** Concluída em 01/10/2026. Diff completo revisado por arquivo; matriz T01–T23 consolidada com 691 testes aprovados, 1 skipped e 30 subtestes aprovados (8 deselected separados) (0 failed); evidências de SEV-07 auditadas diretamente; plano de migration/rollback preparado (não executado); lista exata de arquivos de integração produzida. Veredito: pronto para integração, com limitações não bloqueantes explícitas. Ver Registro de execução.

Ampliação transversal das tasks pelo adendo: SEV-03 deriva também T17–T23; SEV-04 inclui catálogo e persistência de categoria/plano; SEV-05 integra salvamento e validação das combinações; SEV-06 implementa seletores e referências no formulário/detalhe; SEV-07 verifica as quatro combinações com/sem JS; SEV-08 confere ausência de valor/plano inventado em legados. Nenhuma task de implementação foi iniciada por esse adendo.

## Test Checklist

| ID | Cenário obrigatório | Task de implementação |
| --- | --- | --- |
| T01 | Sem selo salva sem campos extras; limpa valores/datas/situação residuais, inclusive inválidos | SEV-04/05 |
| T02 | Cada tipo não ativado salva valor/e-mail/pagamento e datas nulas; indicador Não ativado | SEV-04/05 |
| T03 | Ativo exige cada data e valor; datas iguais aceitas, invertidas rejeitadas | SEV-04/05 |
| T04 | Ativação de Não ativado preserva tipo/valor e não modifica status/activated_at/vínculo/histórico operacional | SEV-04/05 |
| T05 | Legado migrado ativo, datas idênticas, valor null; GET funciona, edição sem valor rejeitada, com valor persiste | SEV-04/05 |
| T06 | Valor válido persiste exato; ausente/formato inválido/negativo/zero/limite/excesso de casas conforme SEV-02 | SEV-04/05 |
| T07 | Erro de valor ou e-mail não gera mensagem obrigatória contraditória, não escreve parcialmente | SEV-05 |
| T08 | Reactivação/create_or_reuse/save(commit=False) não perdem novos campos nem recuperam selo antigo | SEV-05 |
| T09 | Edição de linha alocada e ações Liberar/alocar/cancelar preservam contratos, inclusive legado sem valor | SEV-05 |
| T10 | Migração inclui excluídos; forward/reverse preservam campos antigos, sem drift alheio | SEV-04 |
| T11 | Ativo mantém alertas 8/7/1/0/-1; Não ativado jamais alerta mesmo com entrada residual de data | SEV-04/06 |
| T12 | Detalhe/overview/Carregar mais/OPERATOR distinguem Não ativado e Sem selo, sem N+1 e sem ampliar permissões | SEV-06 |
| T13 | Relatório de Selos mantém período por ativação; não ativados excluídos; Inventário conta posse de selo corretamente | SEV-06 |
| T14 | JS e ausência de JS: required/visibilidade, transições, foco/erros, vírgula monetária, datas manuais | SEV-06/07 |
| T15 | Restrição de acesso/escopo e POST inválido permanecem; valor só nas superfícies definidas | SEV-05/06 |
| T16 | Regra final de Ativo→Não ativado e default de novos selos conforme contrato fechado em SEV-02 | SEV-04/05/07 |
| T17 | Quatro combinações do catálogo salvam/reabrem com categoria/plano corretos; combinação cruzada ou token desconhecido rejeitado no servidor | SEV-04/05/06 |
| T18 | Referência fixa/faixa separada do valor efetivo; valor editado preservado, sem escolher preço de faixa ou sobrescrever no GET | SEV-05/06/07 |
| T19 | Remoção/troca de selo/categoria/plano e obrigatoriedade conforme SEV-02, com e sem JS e POST inválido sem gravação parcial | SEV-05/06/07 |
| T20 | Legados não recebem categoria/plano/valor inferidos; migração e próxima edição seguem decisão explícita SEV-02 | SEV-04/05 |
| T21 | Não ativado: 0,00 aceito; Ativo: 0,00 rejeitado e 0,01 aceito. Ambos: -0,01 e 299,01 rejeitados; 299,00 aceito; ausência rejeitada ao salvar. Ativar com zero exige correção e não grava parcialmente | SEV-04/05/07 |

| T22 | Parsing aceita 59/59,0/59,00/59.00 e espaços externos; rejeita 1,000, 1.000, R$ 59,00, 1e2, NaN, Infinity, -0,00 e separadores misturados | SEV-04/05 |
| T23 | Form novo apresenta Não ativado; POST com selo sem situação rejeitado; serviço com selo e argumentos novos ausentes rejeitado; chamadores Sem selo continuam válidos | SEV-04/05 |

## Test Strategy

Domínio via pytest; ORM/form/HTTP com persistência real em banco isolado. Congelar somente data local para limites de vencimento; não mockar validador ou serviço sob teste. Fixtures legadas precisam representar estado anterior à migração. Comparar valores/campos, não só is_valid ou contagens.

Comandos a executar nas tasks correspondentes, a partir da raiz do repositório (não executados na elaboração desta spec):

```powershell
.\venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_activation_value.py -v
.\venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/test_seal_detail_and_listing.py -q
.\venv\Scripts\python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
.\venv\Scripts\python.exe -m pytest config/tests/test_whatsapp_seal_report.py config/tests/test_line_inventory_report.py -k "not RealVolume" -q
.\venv\Scripts\python.exe manage.py check --settings=config.settings_dev
git diff --check
```

Rodar suítes sequencialmente se compartilham SQLite. Confirmar isolamento antes de qualquer migrate/teste de migração; validar migração também em Postgres descartável antes da entrega. Registrar motivo se volume não for repetido; nenhuma alegação de desempenho de PRD baseada em testes locais.

## Compliance Report — registro inicial (histórico)

- Spec vs aprovações: quatro decisões registradas; escolhas complementares identificadas como propostas, não aprovação.
- Spec vs testes: matriz derivada, testes executáveis ainda não escritos/rodados.
- Spec vs código: levantamento de lacunas feito; nenhum código de aplicação alterado nesta tarefa.
- Fonte e tasks: documento único; SEV-01 concluída, SEV-02 a SEV-08 abertas.
- Sem migration criada/aplicada, commit, push, deploy ou acesso a PRD.

## Registro de execução

### 2026-10-01 — SEV-02: aprovação dos limites monetários

Usuário definiu zero somente para não ativos, rejeição de negativos e máximo R$ 299,00. No contrato, não ativo corresponde a Não ativado; Sem selo continua sem valor.

Spec Summary/Gap Analysis: mínimo condicional e máximo fechados; proposta anterior de máximo elevado substituída. Retorno Ativo → Não ativado e default/troca de seletores ainda aguardam resposta.

Implementation Plan/Test Checklist: domínio, forms e transição de ativação devem respeitar esses limites; T21 acrescentado com fronteiras concretas. Test Strategy: testes serão derivados/executados em SEV-03 e etapas seguintes, não nesta edição documental.

Compliance Report: somente spec alterada. SEV-02 permanece aberta; nenhuma implementação, migration, commit ou push.

### 2026-10-01 — SEV-02 iniciada: levantamento de compatibilidade

Spec Summary: fechamento complementar solicitado pelo usuário. Três perguntas enviadas para resolver mínimo/limite monetário, retorno Ativo → Não ativado e default/troca de seleção. Respostas ainda pendentes neste registro; nenhuma opção recomendada foi tratada como aprovação.

Gap Analysis e evidência de código:

- telecom/forms.py::PhoneLineForm.save: edição/commit=False usam o caminho ModelForm; criação repassa cinco campos atuais para PhoneLine.create_or_reuse. Os quatro campos novos deverão participar dos dois caminhos.
- telecom/models.py::PhoneLine.create_or_reuse: criação via objects.create e reutilização com select_for_update/update_fields; não há full_clean automático. A task de implementação deve garantir normalização/validação de selo nesse serviço sem passar a validar indiscriminadamente campos operacionais legados.
- telecom/admin.py::SIMcardAdmin.save_model, telecom/views.py::SIMcardCreateView.form_valid e core/services/telephony_use_case.py: chamadas verificadas não enviam selo; devem continuar Sem selo, sem novos argumentos obrigatórios para esses chamadores.
- telecom/views.py::PhoneLineUpdateView.post: action=release_line é processada antes de validar o formulário, atualizando status/alocação. Preservar esse desvio: liberar linha não exige preencher valor/categoria/plano legado.
- PhoneLineUpdateView.form_valid coordena vínculo após salvar o form em transação; testes devem comprovar ausência de alterações operacionais ao editar somente selo.

Implementation Plan: consolidar decisões após respostas, fixar tokens e parsing monetário, revisar matriz T01–T20 e então fechar SEV-02. Nenhuma implementação iniciada.

Test Checklist: manter testes de chamadores sem selo, criação/reutilização, save(commit=False), edição alocada e Liberar com legado incompleto. Inspeção não substitui execução desses testes em SEV-03/05.

Test Strategy: somente leitura de código nesta rodada, sem executar testes ou acessar banco.

Compliance Report: SEV-02 em andamento, não concluída. Somente documentação alterada; nenhum código, migration, commit, push ou deploy.

### 2026-10-01 — Adendo documental de categoria/plano

- Spec Summary: catálogo do usuário registrado com quatro combinações e preços de referência; valor efetivo por linha permanece editável.
- Gap Analysis: obrigatoriedade, legados e automação de preço não foram presumidos; acrescidos a SEV-02.
- Implementation Plan: mantidas oito tasks, ampliadas para catálogo/persistência/form/detalhe/aceite.
- Test Checklist: T17–T20 derivados do novo escopo; casos dependentes de decisões aguardam SEV-02.
- Test Strategy: revisão documental nesta rodada; nenhum teste executável criado ou rodado.
- Compliance Report: somente esta spec alterada; nenhum código, migration, commit, push ou deploy. Preços reproduzem informação do usuário, não pesquisa comercial.

### 2026-10-01 — Aprovação das três regras de categoria/plano/valor

Resposta literal do usuário: “aprovado”, à proposta de categoria/plano obrigatórios com selo, legados vazios com preenchimento na próxima edição e preço apenas como referência com valor efetivo manual.

Contrato e pontos 5–6 de SEV-02 atualizados. As pendências registradas no adendo anterior são históricas quanto a esses dois pontos. Permanecem abertos pontos 1–4 e 7; SEV-02 não concluída. Matriz T17–T20 passa a usar essas regras aprovadas. Revisão documental apenas; nenhum teste executável, código, migration, commit ou push nesta rodada.

Cada task deve acrescentar data, arquivos, decisões, node IDs, comandos/resultados, limitações e próximo passo. Só marcar task concluída com sua evidência; preservar histórico de correções sem apresentar evidência superada como atual.


### 2026-10-01 — SEV-02 concluída

- Spec Summary: usuário respondeu “sim para ambos” ao retorno Ativo → Não ativado e ao default/troca de seletores. Aprovações registradas junto das decisões anteriores de categoria/plano e valor.
- Gap Analysis: nenhuma ambiguidade impeditiva restante; diferenciação entre default de interface e ausência em POST/serviço fixada. Política de parsing/tokens é decisão técnica explícita.
- Implementation Plan: SEV-02 marcada concluída; próxima SEV-03, testes RED, ainda não iniciada.
- Test Checklist: T01–T23 cobrem regras e fronteiras; referências históricas a matriz menor permanecem como histórico.
- Test Strategy: revisão documental e de caminhos reais nesta task; nenhuma suíte executada, nenhum GREEN de implementação alegado.
- Compliance Report: somente fonte da verdade modificada; nenhum código, migration, commit, push, deploy ou acesso a PRD.

### 2026-10-01 — SEV-03 concluída: testes RED

**Spec Summary.** Objetivo desta task: criar os testes executáveis que provam, antes de qualquer código de aplicação, que os quatro campos novos (situação de ativação, categoria, plano, valor mensal) e as regras de catálogo/parsing fechadas em SEV-02 ainda não existem no domínio/model/form/HTTP/interface/relatórios. Arquivo criado: `telecom/test_whatsapp_seal_activation_value.py` (77 nodes coletados). `telecom/test_phoneline_form_ui.py` não foi ampliado: todos os cenários de interface do adendo (campos novos no HTML, default Não ativado) já cabiam no arquivo novo, sem overlap com o que esse arquivo já cobre (SEL-07, apresentação dos 4 campos antigos).

**Gap Analysis confirmado por leitura de código antes de escrever qualquer fixture:**

| Caminho | Estado em 01/10/2026 |
| --- | --- |
| telecom/whatsapp_seal.py | Sem `WhatsAppSealCategory`, `WhatsAppSealPlan`, sem validador de catálogo, sem parsing monetário. `compute_seal_status(seal, expires_on)` não recebe situação de ativação; quando `expires_on` é `None` retorna `{"tone": "neutral", "label": "Sem selo"}` — mesmo rótulo que Sem selo, sem distinguir Não ativado |
| telecom/models.py | PhoneLine só tem os 5 campos antigos de selo; `create_or_reuse` só aceita os 5 kwargs antigos (kwarg novo → `TypeError`); nenhuma validação de obrigatoriedade para os campos novos |
| telecom/forms.py | `PhoneLineForm.Meta.fields` não lista os 4 campos novos; dados extras no POST são ignorados pelo Django (não geram erro, nem populam `cleaned_data`) |
| templates/telecom/phoneline_form.html, phoneline_detail.html, operator_lines.html, overview.html | Nenhuma referência aos 4 campos novos; nenhum texto "Não informado" para valor ausente |
| core/services/whatsapp_seal_report_service.py | Filtro por `whatsapp_seal_activated_on` entre datas já exclui implicitamente qualquer linha sem essa data (inclusive futura Não ativado) — **já correto, confirmado por teste positivo, não presunção** |
| core/services/line_inventory_report_service.py | `_selo_label` conta posse por `whatsapp_seal != ""`, independente de ativação — **já correto, confirmado por teste positivo** |
| telecom/views.py (PhoneLineUpdateView.post, action=release_line) | Não chama `form_valid`/validação do form — Liberar com legado incompleto continua funcionando, confirmado por teste |
| telecom/migrations/ | Nenhuma sucessora da 0021 para este adendo — grafo de migração do backfill novo não existe |

**Implementation Plan.** SEV-03 concluída nesta rodada. Nenhum código de aplicação, migration, dependência nova ou PRD alterado — apenas o arquivo de teste e esta fonte da verdade.

**Test Checklist — rastreabilidade Node ID → Txx → camada → task futura → resultado → causa.**

Legenda de causa: **GAP** = funcionalidade realmente ausente (RED genuíno, vira GREEN quando a task futura implementar); **GAP-INTENCIONAL** = teste escrito para falhar de propósito, documentando pendência sem fabricar cobertura; **JÁ-CORRETO** = comportamento atual já atende o contrato novo, confirmado com controle elegível (GREEN genuíno, não ausência de motor).

| Node (classe::teste) | Txx | Camada | Task futura | Resultado | Causa |
| --- | --- | --- | --- | --- | --- |
| TestT01SemSeloLimpaDadosProprios::test_sem_selo_limpa_situacao_categoria_plano_valor | T01 | domínio/model | SEV-04 | RED | GAP — AttributeError (campo ausente na instância recém-buscada) |
| TestT01SemSeloLimpaDadosProprios::test_form_sem_selo_limpa_campos_novos_mesmo_com_residuo_no_post | T01 | form | SEV-05 | RED | GAP — AttributeError |
| TestT02NaoAtivado::test_nao_ativado_salva_datas_nulas_e_valor_zero[META_ONE/META_VERIFIED] (2 subtestes) | T02 | form | SEV-04/05 | RED | GAP — AttributeError |
| TestT02NaoAtivado::test_nao_ativado_nao_gera_alerta | T02/T11 | domínio | SEV-04/06 | RED | GAP — `compute_seal_status` retorna label "Sem selo" para Não ativado (mesma condição `not expires_on`), precisa distinguir |
| TestT03Ativo::test_ativo_exige_cada_data_e_valor | T03 | form | SEV-05 | RED | GAP — form válido sem erro no campo de valor (campo ausente) |
| TestT03Ativo::test_vencimento_anterior_a_ativacao_rejeitado | T03 | domínio | — (controle) | GREEN | JÁ-CORRETO — `validate_seal_fields` já rejeita datas invertidas |
| TestT04AtivacaoNaoAlteraOperacional::test_editar_apenas_selo_nao_altera_status_activated_at_ou_historico | T04/T16 | form/HTTP | SEV-04/05 | RED | GAP — `PhoneLineUpdateForm` não tem o campo `whatsapp_seal_activation_status`, form inválido |
| TestT05Legado::test_linha_legada_sem_campos_novos_eh_tratada_como_ativa | T05/T20 | model/migração | SEV-04 | RED | GAP — AttributeError |
| TestT05Legado::test_get_legado_funciona_sem_valor | T05 | HTTP | — (controle) | GREEN | JÁ-CORRETO — detalhe não referencia campos novos, não quebra |
| TestT05Legado::test_edicao_legado_sem_valor_eh_rejeitada | T05 | form | SEV-05 | RED | GAP — campo ausente, nenhuma exigência de valor |
| TestT06ValorMonetario::test_valor_valido_persiste_exato[3 casos: 59,00 / 0,01 / 299,00] | T06 | form | SEV-04/05 | RED | GAP — AttributeError |
| TestT06ValorMonetario::test_valor_invalido_ou_fora_de_faixa_para_ativo_rejeitado[7 casos] | T06/T21 | form | SEV-05 | RED | GAP — campo ausente, nada rejeita |
| TestT07SemMensagemContraditoria::test_valor_invalido_nao_duplica_obrigatorio_e_nao_grava_parcial | T07 | HTTP/form | SEV-05 | RED | GAP — `KeyError` (`whatsapp_seal_monthly_value` não existe em `form.errors`) |
| TestT08CreateOrReuseECommitFalse::test_create_or_reuse_aceita_kwargs_novos | T08/T23 | domínio | SEV-05 | RED | GAP — `TypeError: unexpected keyword argument` |
| TestT08CreateOrReuseECommitFalse::test_save_commit_false_nao_grava_e_preserva_valor_normalizado | T08 | form | SEV-05 | RED | GAP — AttributeError na instância de `save(commit=False)` |
| TestT08CreateOrReuseECommitFalse::test_reactivation_nao_recupera_categoria_plano_valor_antigos | T08 | domínio | SEV-05 | RED | GAP — `TypeError` (mesmo gap de kwargs novos) |
| TestT09AcoesIndependentesComLegadoIncompleto::test_liberar_linha_nao_exige_completar_selo_legado | T09 | HTTP | — (controle) | GREEN | JÁ-CORRETO — Liberar não valida form, confirmado com linha alocada real |
| TestT09AcoesIndependentesComLegadoIncompleto::test_editar_linha_alocada_sem_completar_legado_eh_rejeitado_mas_nao_pela_alocacao | T09 | HTTP/form | SEV-05 | RED | GAP — campo ausente nos erros do form |
| TestT10Migracao::test_cobertura_pendente_para_sev04 | T10 | migração | SEV-04 | RED | GAP-INTENCIONAL — `pytest.fail` documentando pendência; grafo de migração sucessora da 0021 não existe, sem migration fictícia/skip/xfail |
| TestT11AlertasEComputeSealStatus::test_ativo_mantem_alertas_atuais | T11 | domínio | — (controle) | GREEN | JÁ-CORRETO — limites 8/7/1/0/-1 dias inalterados |
| TestT11AlertasEComputeSealStatus::test_nao_ativado_jamais_alerta_mesmo_com_data_residual | T11 | domínio | SEV-04 | RED | GAP — `TypeError` (`compute_seal_status` não aceita kwarg `activation_status`) |
| TestT12InterfaceDistingueNaoAtivadoDeSemSelo::test_overview_ajax_distingue_nao_ativado_de_sem_selo | T12 | HTTP/interface | SEV-06 | RED | GAP — AttributeError ao gravar o campo novo na fixture |
| TestT12InterfaceDistingueNaoAtivadoDeSemSelo::test_detalhe_mostra_situacao_e_valor_nao_informado_para_legado | T12 | template | SEV-06 | RED | GAP — texto "Não informado" ausente no HTML atual |
| TestT13Relatorios::test_relatorio_selos_exclui_linha_sem_data_de_ativacao | T13 | relatório | — (controle) | GREEN | JÁ-CORRETO — filtro por `whatsapp_seal_activated_on` já exclui linha sem essa data; controle elegível (linha ativa no período) incluído |
| TestT13Relatorios::test_inventario_conta_selo_independente_de_ativacao | T13 | relatório | — (controle) | GREEN | JÁ-CORRETO — `_selo_label` conta por `whatsapp_seal != ""`; controle sem selo incluído |
| TestT14EstruturaDeFormularioParaNovosCampos::test_formulario_novo_nao_renderiza_campo_de_valor_ainda | T14 | template/estrutural | SEV-06 | RED | GAP — nenhum input com esses `name=` existe no HTML atual |
| TestT15PermissoesInalteradas::test_operator_continua_sem_poder_criar_selo_com_novos_campos | T15 | HTTP/permissão | — (controle) | GREEN | JÁ-CORRETO — `RoleRequiredMixin` inalterado |
| TestT16AtivoParaNaoAtivadoEDefault::test_ativo_para_nao_ativado_limpa_datas_preserva_demais_dados | T16 | form/domínio | SEV-04/05 | RED | GAP — `TypeError` nos kwargs novos de `create_or_reuse` |
| TestT16AtivoParaNaoAtivadoEDefault::test_novo_formulario_apresenta_nao_ativado_por_default | T16/T23 | template | SEV-05/06 | RED | GAP — campo/valor default ausente no HTML |
| TestT16AtivoParaNaoAtivadoEDefault::test_post_com_selo_sem_situacao_explicita_eh_invalido | T16/T23 | form | SEV-05 | RED | GAP — form válido indevidamente (campo ausente) |
| TestT17CatalogoCategoriaPlano::test_combinacao_do_catalogo_salva_e_reabre_corretamente[4 combinações] | T17 | form/domínio | SEV-04/05 | RED | GAP — AttributeError |
| TestT17CatalogoCategoriaPlano::test_token_de_categoria_desconhecido_rejeitado | T17 | form | SEV-05 | RED | GAP — campo ausente, nada rejeita |
| TestT17CatalogoCategoriaPlano::test_combinacao_cruzada_incompativel_rejeitada | T17 | form | SEV-05 | RED | GAP — campo ausente, nada rejeita |
| TestT17CatalogoCategoriaPlano::test_validador_de_catalogo_ainda_nao_existe_no_dominio | T17 | domínio | SEV-04 | RED | GAP-INTENCIONAL — `getattr` confirma ausência de `WhatsAppSealCategory`/`WhatsAppSealPlan`/validador, sem import no topo do arquivo (coleta permanece limpa) |
| TestT18ReferenciaNaoSobrescreveValor::test_referencia_de_preco_nao_preenche_nem_sobrescreve_valor_editado | T18 | form | SEV-05/06 | RED | GAP — AttributeError |
| TestT19RemocaoETrocaDeSeloCategoriaPlano::test_remover_selo_remove_categoria_plano_e_valor | T19 | form | SEV-05 | RED | GAP — AttributeError |
| TestT19RemocaoETrocaDeSeloCategoriaPlano::test_troca_de_categoria_sem_js_post_invalido_nao_grava_parcial | T19 | HTTP | SEV-05/06 | RED | GAP — linha é criada indevidamente (sem validação cruzada de catálogo) |
| TestT20LegadoSemInferencia::test_legado_nao_recebe_categoria_plano_inferidos_pelo_tipo | T20 | model/migração | SEV-04 | RED | GAP — AttributeError |
| TestT21FronteirasMonetarias (7 testes + 2 subtestes de `test_negativo_minimo_rejeitado_em_ambos_estados`) | T21 | form/domínio | SEV-04/05/07 | RED | GAP — AttributeError nos aceitos (0,00/0,01/299,00) ou campo ausente nos rejeitados (-0,01 em ambos estados, 299,01, ativar com zero sem gravação parcial) |
| TestT22ParsingMonetario::test_entradas_aceitas_pelo_parsing[5 casos: 59 / 59,0 / 59,00 / 59.00 / " 59,00 "] | T22 | form/domínio | SEV-04/05 | RED | GAP — AttributeError |
| TestT22ParsingMonetario::test_entradas_rejeitadas_pelo_parsing[11 casos: milhar, R$, notação científica, NaN, Infinity, -0,00, 3+ casas decimais, separador misto] | T22 | form/domínio | SEV-04/05 | RED | GAP — campo ausente, nada rejeita |
| TestT22ParsingMonetario::test_zero_explicito_diferente_de_ausencia | T22 | form/domínio | SEV-04/05 | RED | GAP — AttributeError |
| TestT23DefaultsEChamadoresCompatíveis::test_chamador_sem_selo_continua_compativel | T23 | domínio | — (controle) | GREEN | JÁ-CORRETO — `create_or_reuse` sem kwargs de selo funciona como hoje |
| TestT23DefaultsEChamadoresCompatíveis::test_create_or_reuse_com_selo_exige_novos_dados | T23 | domínio | SEV-04/05 | RED | GAP — `create_or_reuse` aceita selo sem nenhum dos 4 campos novos sem levantar `ValidationError` |

**Contagens reais (comando abaixo), coleta limpa (0 erros de coleta/import):**

```
telecom/test_whatsapp_seal_activation_value.py -v
77 collected, 69 failed, 8 passed, 2 warnings in 8.45s
```

8 PASSED são controles de regressão (comportamento já correto hoje, não ausência de motor — cada um tem fixture com dado elegível real: linha ativa dentro do período no relatório de Selos, linha sem selo no Inventário, linha alocada real na ação Liberar, etc.). 69 FAILED: 67 são GAP genuíno (funcionalidade ausente, comprovado por `AttributeError`/`TypeError`/`KeyError`/assert de HTML ausente — nunca por fixture quebrada) e 2 são GAP-INTENCIONAL (T10 migração pendente, T17 catálogo pendente — falhas registradas de propósito via `pytest.fail`/`assert ... is not None`, nomeando a task futura). Nenhum ERROR (de coleta, fixture ou configuração) ocorreu.

**Correção durante a execução (não é GAP de produto):** `TestT11AlertasEComputeSealStatus::test_ativo_mantem_alertas_atuais` falhou na primeira execução por erro aritmético do próprio teste (`date(2026,9,24)` dá delta=7 dias, faixa de "warning", não "neutral" como o teste presumia) — corrigido para `date(2026,9,25)` (delta=8, "neutral"), igual ao caso já coberto em `telecom/test_whatsapp_seal.py::test_expiry_boundaries`. Registrado para não confundir com GAP de produto.

**Cobertura pendente e motivo concreto:**

- T10 (migração): nenhuma migration executável pode ser escrita nesta task (instrução explícita de não criar migration/migration fictícia nem skip/xfail). O teste real de forward/reverse/backfill fica para SEV-04, quando `telecom/migrations/0022_*` existir — mesmo formato de `telecom/test_whatsapp_seal.py::test_migration_preserves_existing_lines_as_no_seal`/`test_migration_0021_is_reversible`.
- Aceite visual com/sem JavaScript real em navegador (T14/T19, parte visual) permanece fora do alcance de testes estruturais — fica para SEV-07, conforme a própria spec já determina.

**Test Strategy — comandos executados e resultados reais:**

```
venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_activation_value.py -v
  → 77 collected, 69 failed, 8 passed, 2 warnings in 8.45s

venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/test_seal_detail_and_listing.py -q
  → 65 passed, 2 warnings in 15.81s

venv\Scripts\python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
  → 236 passed, 1 skipped, 2 warnings, 5 subtests passed in 194.34s

venv\Scripts\python.exe -m pytest config/tests/test_whatsapp_seal_report.py config/tests/test_line_inventory_report.py -k "not RealVolume" -q
  → 215 passed, 8 deselected, 2 warnings, 10 subtests passed in 84.77s

venv\Scripts\python.exe manage.py check --settings=config.settings_dev
  → System check identified no issues (0 silenced).

git diff --check
  → sem saída (só aviso de LF/CRLF do arquivo de 09/10, não é erro de whitespace)
```

Suítes rodadas sequencialmente (SQLite único, `test_db.sqlite3`); nenhum volume pesado repetido sem motivo — `-k "not RealVolume"` excluiu os 8 testes de volume já cobertos em rodadas anteriores de REL-08/09, fora do escopo desta task.

**Compliance Report:**

- Spec vs aprovações: nenhuma decisão nova tomada nesta task; testes refletem exatamente o contrato fechado em SEV-02.
- Spec vs testes: as 23 linhas de T01–T23 têm pelo menos um node ID rastreável nesta rodada; nenhuma linha ficou sem teste executável.
- Spec vs código: nenhum código de aplicação, migration, template, JS ou dependência foi alterado — somente `telecom/test_whatsapp_seal_activation_value.py` (novo) e esta fonte da verdade.
- Regressão: nenhuma suíte existente quebrou (65 + 236 + 215 = 516 testes/subtestes preexistentes permanecem GREEN).
- `manage.py check` e `git diff --check` limpos.
- Sem commit, push, deploy ou acesso a PRD nesta task.

SEV-03 concluída. Próxima: SEV-04 (modelo, domínio e migration) — não iniciada.

### 2026-10-01 — SEV-03: correção de qualidade dos testes (retificação)

**Motivo.** Revisão apontou que a rodada anterior de SEV-03 classificara dois nodes como "RED" sem que fossem RED funcional válido: um `pytest.fail` incondicional (T10) e um teste que só provava a ausência de símbolos internos inventados pelo próprio teste, não exigidos pela spec por nome (T17). Esta rodada corrige os dois, sem tocar código de aplicação, migration, dependência, PRD ou commit. Revisão feita por inspeção direta do arquivo (`Read` completo de `telecom/test_whatsapp_seal_activation_value.py`), não por relato.

**Spec Summary.** Mesmo objetivo de SEV-03 (provar ausência das regras novas antes do código); esta rodada apenas corrige dois nodes de qualidade insuficiente e remove um auxiliar morto, preservando os demais 73 nodes já válidos.

**Gap Analysis dos dois problemas, confirmados por leitura direta do código:**

1. **T10 — `TestT10Migracao::test_cobertura_pendente_para_sev04`.** O corpo do teste era só `pytest.fail("Cobertura pendente para SEV-04: ...")`, incondicional — falha sempre, independente de qualquer estado do código, antes ou depois de SEV-04 implementar a migration. Não comprova nem refuta nenhum comportamento: não é RED funcional, é um lembrete travestido de teste. Contar esse node nos 69 FAILED da rodada anterior inflava a contagem de RED genuíno.
2. **T17 — `TestT17CatalogoCategoriaPlano::test_validador_de_catalogo_ainda_nao_existe_no_dominio`.** O teste fazia `getattr(whatsapp_seal, "WhatsAppSealCategory", None)`, `getattr(..., "WhatsAppSealPlan", None)` e `getattr(..., "validate_seal_catalog_combination", None)`, falhando porque esses três nomes não existem. A spec (contrato técnico, seção "Campos e tokens") não exige esses nomes específicos — exige comportamento (quatro combinações aceitas, token desconhecido e combinação cruzada rejeitados). O teste inventava um requisito de API interna sem respaldo na spec; qualquer implementação futura que resolvesse o catálogo com nomes diferentes (ex.: `SealCategory`, validação embutida em `validate_seal_fields` sem função dedicada) deixaria esse teste falhando para sempre, mesmo com o comportamento real correto — um falso RED permanente, não uma garantia de qualidade. Os três testes comportamentais já presentes na mesma classe (`test_combinacao_do_catalogo_salva_e_reabre_corretamente` com as 4 combinações parametrizadas, `test_token_de_categoria_desconhecido_rejeitado`, `test_combinacao_cruzada_incompativel_rejeitada`) já cobrem integralmente T17 pela fronteira real (`PhoneLineForm`), sem depender de nenhum nome interno.

Auditoria proporcional dos demais 73 nodes (mesmos quatro padrões: `pytest.fail` incondicional, símbolo sem prova de comportamento, GREEN por ausência de motor, assert fraco/HTML incidental) não encontrou outra ocorrência:

- Nenhum outro `pytest.fail` incondicional no arquivo.
- Nenhum outro `getattr` sobre símbolo inventado.
- Os 8 GREEN (T03 datas invertidas, T05 GET de legado, T09 Liberar com legado alocado real, T13 relatório Selos + Inventário com controle elegível real, T15 permissão OPERATOR, T11 limites de alerta 8/7/1/0/-1, T23 chamador sem selo) testam comportamento real já existente no código, com dado de controle real na fixture — não GREEN por ausência de motor.
- `test_detalhe_mostra_situacao_e_valor_nao_informado_para_legado` (T12): confirmado por grep que a string "Não informado" não existe hoje em `templates/telecom/phoneline_detail.html` — não é coincidência com outro campo, é RED genuíno.
- `_missing_model_field`, auxiliar definido mas nunca chamado em nenhum teste (código morto do mesmo tipo de padrão evitado em T17), removido.

**Implementation Plan.** Nenhuma mudança de task; apenas a qualidade dos testes de SEV-03 foi corrigida nesta rodada.

**Test Checklist — mudanças de nodes:**

| Node removido | Txx | Motivo da remoção |
| --- | --- | --- |
| `TestT10Migracao::test_cobertura_pendente_para_sev04` | T10 | `pytest.fail` incondicional; não é RED funcional. Cobertura registrada apenas em texto (comentário não executável no arquivo de teste + este registro), com os 6 cenários concretos que SEV-04 deve testar quando a migration existir: (1) legado com selo classificado ACTIVE; (2) datas preservadas; (3) categoria/plano vazios (""); (4) valor mensal null; (5) registros com linha e/ou SIMcard excluídos logicamente também classificados (via `all_objects`/modelos históricos); (6) reversão preserva os 5 campos antigos, perda dos 4 novos no rollback é esperada e deve ser documentada, não testada como sucesso. |
| `TestT17CatalogoCategoriaPlano::test_validador_de_catalogo_ainda_nao_existe_no_dominio` | T17 | Testava ausência de símbolo (`WhatsAppSealCategory`/`WhatsAppSealPlan`/`validate_seal_catalog_combination`) inventado pelo teste, não exigido pela spec por nome. Redundante: T17 já tem cobertura comportamental completa nos 3 testes remanescentes da mesma classe (4 combinações aprovadas + token desconhecido rejeitado + combinação cruzada rejeitada), todos pela fronteira real do formulário. |

Nenhum node foi adicionado nem substituído por outro RED artificial — os 73 nodes remanescentes (62 FAILED reais de T01–T09/T11/T12/T14/T16/T18–T23 + 1 FAILED de T02 domínio + 5 PASSED que eram controle + os 3 comportamentais de T17) continuam exatamente como estavam, revisados e confirmados corretos nesta auditoria.

**Test Strategy — comando e resultado real desta rodada:**

```
venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_activation_value.py -v
  → 75 collected, 67 failed, 8 passed, 2 warnings in 7.59s

venv\Scripts\python.exe manage.py check --settings=config.settings_dev
  → System check identified no issues (0 silenced).

git diff --check
  → sem saída (só aviso de LF/CRLF do arquivo de 09/10, não é erro de whitespace)
```

Nenhum helper compartilhado com outros arquivos de teste foi alterado (o helper removido, `_missing_model_field`, nunca foi usado nem por este arquivo nem por outro) — por isso a regressão ampla de `telecom/test_whatsapp_seal.py`, `test_phoneline_form_ui.py`, `test_seal_detail_and_listing.py`, `telecom/tests.py`, `tests_line_timeline.py` e dos relatórios (rodada anterior, todas GREEN) não foi reexecutada nesta correção, conforme instrução de não repetir regressão sem necessidade.

**Contagem reconciliada:** 75 collected = 67 FAILED + 8 PASSED + 0 ERROR (nenhum skip, nenhum subteste separado além dos já parametrizados). Dos 67 FAILED, todos são GAP genuíno (funcionalidade ausente, comprovado por `AttributeError`/`TypeError`/`KeyError`/assert de HTML ausente/`DID NOT RAISE` — nunca por fixture quebrada ou por placeholder). Nenhum FAILED remanescente é "gap-intencional" — essa classificação foi retirada: um placeholder que sempre falha não é RED funcional válido, e não deve ser contado como prova de ausência de comportamento. A única pendência de cobertura sem node executável é T10 (migração), registrada apenas em texto, nesta seção e como comentário no arquivo de teste, explicitamente atribuída a SEV-04.

**Compliance Report:**

- Spec vs testes: T01–T23 continuam com pelo menos um node executável rastreável, exceto T10, que fica explicitamente pendente para SEV-04 (sem node executável, por proibição explícita de migration/placeholder nesta task) — já não é mais apresentada como RED comprovado.
- Spec vs código: nenhum código de aplicação, migration, template, JS ou dependência alterado nesta correção — apenas `telecom/test_whatsapp_seal_activation_value.py` (2 nodes removidos, 1 auxiliar morto removido, docstring do módulo ajustada) e esta fonte da verdade.
- `manage.py check` e `git diff --check` limpos.
- Sem commit, push, deploy ou acesso a PRD nesta correção.

SEV-03 permanece concluída, agora com os testes corrigidos e os resultados reconciliados sem gap-intencional fabricado. Próxima: SEV-04 (modelo, domínio e migration) — não iniciada.

### 2026-10-01 — SEV-04 concluída: modelo, domínio e migration

**Spec Summary.** Objetivo desta task: implementar os 4 campos novos em `PhoneLine` (`whatsapp_seal_activation_status`, `whatsapp_seal_category`, `whatsapp_seal_plan`, `whatsapp_seal_monthly_value`), o catálogo e as regras de domínio em `telecom/whatsapp_seal.py`, e a migration 0022 com backfill, comprovando tudo por testes diretos de domínio/modelo/migração — independentemente de `PhoneLineForm`/`PhoneLineUpdateForm`/`create_or_reuse`, explicitamente fora de escopo desta task (reservados a SEV-05).

**Inspeção e classificação prévias (antes de qualquer código).** `git status`/`git diff` conferidos: nenhum trabalho em andamento de terceiros na área tocada. Migration 0021 e grafo de `telecom/migrations/` lidos por completo. Baseline de SEV-03 reconfirmado por execução real antes de qualquer alteração: `telecom/test_whatsapp_seal_activation_value.py` → **75 collected, 67 failed, 8 passed** (idêntico ao relatado). Node IDs classificados por task antes de implementar, usando a tabela já existente no registro de SEV-03: apenas nodes de domínio/model/migração puros (T01 model, T02 domínio, T05 model, T11 domínio, T20 model, T10 migração) pertencem a SEV-04; os demais (T03–T09, T12, T14, T16–T19, T21–T23 na sua forma de form/HTTP) permanecem SEV-05/06/07, não exigidos GREEN nesta task.

**Gap Analysis — decisão técnica central descoberta durante a implementação.** Ao integrar a validação nova em `PhoneLine.clean()`, a suíte de regressão (`telecom/test_whatsapp_seal.py` etc., 65 testes já GREEN antes desta task) quebrou com `ValueError: 'PhoneLineForm' has no field named 'whatsapp_seal_activation_status'` — não uma falha de validação comum, mas um crash. Causa raiz identificada lendo `django/db/models/base.py::Model.full_clean()` (Django 5.2.11, nesta venv): ao contrário do que a documentação antiga sugeria, `full_clean()` **não** filtra pelo conjunto `exclude` os erros levantados por `self.clean()` (só filtra `clean_fields()`/`validate_unique()`/`validate_constraints()`). Como `PhoneLineForm.Meta.fields` ainda não lista os 4 campos novos (integração é SEV-05), qualquer erro de `Model.clean()` referenciando esses campos chega a `ModelForm._post_clean()` → `_update_errors()` → `add_error(None, errors)`, que levanta `ValueError` porque o campo não existe no form — um erro não tratado (500 em produção), não um `form.is_valid() is False` normal.

Resolvido com um **portão de compatibilidade explícito** em `PhoneLine.clean()` (`_seal_extended_fields_in_use()`): a validação estendida (situação/categoria/plano/valor/catálogo) só roda quando **categoria OU plano OU valor mensal** já foram definidos na instância — os três campos que nenhum caminho de escrita atual preenche sozinho. `whatsapp_seal_activation_status` foi deliberadamente excluído desse portão porque `PhoneLine.save()` (compatibilidade com legado) o preenche automaticamente para `ACTIVE` sempre que há selo e a situação está vazia — se esse campo entrasse no portão, editar uma linha criada pelo formulário atual (que já teria `activation_status="ACTIVE"` herdado do `save()`) acionaria a validação estendida e quebraria do mesmo jeito. Com o portão restrito a categoria/plano/valor — nenhum dos quais o formulário atual ou o fallback de `save()` jamais tocam — toda submissão do formulário atual (criação **e** edição) permanece no caminho de validação antiga (preservada byte-a-byte em `validate_seal_fields`), e a validação nova só roda em escritas que já conhecem os campos novos (meus testes diretos de domínio, e, a partir de SEV-05, o formulário integrado).

**Arquivos alterados:**
- `telecom/whatsapp_seal.py`: adicionadas `WhatsAppSealActivationStatus`, `WhatsAppSealCategory`, `WhatsAppSealPlan` (TextChoices); `SEAL_CATALOG_COMBINATIONS` (as 4 combinações aprovadas) e `SEAL_PRICE_REFERENCE_LABELS` (referências textuais, não usadas em validação); `SEAL_MONTHLY_VALUE_MAX`/`_ACTIVE_MIN`/`_NOT_ACTIVATED_MIN`. `validate_seal_fields` (assinatura/comportamento original de 5 parâmetros) preservada intacta para o caminho de compatibilidade. Nova `validate_seal_extended_fields` com a validação completa. `clear_seal_fields` ampliada para os 9 campos. Nova `normalize_seal_fields` (normalização explícita, separada da validação). `compute_seal_status` ganhou parâmetro opcional `activation_status=""`.
- `telecom/models.py`: 4 campos novos em `PhoneLine` (`CharField` blank/default="" para situação/categoria/plano; `DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)` para valor). `seal_status` passa `activation_status`. `clean()` normaliza e then decide entre validação legada/estendida via `_seal_extended_fields_in_use()`. Novo `save()` com fallback de compatibilidade (`whatsapp_seal` presente + `activation_status` vazio → `ACTIVE`), mesmo padrão já usado por `SIMcard.save()` (normalização leve, sem `full_clean`). `create_or_reuse` **não foi tocado** (fora de escopo explícito).
- `telecom/migrations/0022_phoneline_whatsapp_seal_activation_status_and_more.py` (novo): 4 `AddField` + 1 `RunPython` (backfill via modelo histórico e `.update()` em massa, sem `full_clean`/serviços atuais). `reverse_code=migrations.RunPython.noop`. Gerado via `makemigrations`, que também propôs um `AlterField` de `origem` (drift pré-existente, idêntico ao citado na Gap Analysis de SEV-03) — removido manualmente do arquivo antes de salvar; confirmado via `makemigrations --check --dry-run` que esse drift (e o de `dashboard.DailyUserAction.action_type`) é alheio e continua pendente, não incorporado por mim.
- `telecom/test_whatsapp_seal_model_domain.py` (novo, 38 nodes): testes diretos de domínio/modelo via `PhoneLine(...).full_clean()`/`save()` e chamadas a `telecom/whatsapp_seal.py`, sem `PhoneLineForm`/HTTP — prova T01, T02, T03, T06, T16, T17, T18, T20, T21, T22 (fronteira Decimal), T11 independentemente dos formulários ainda não integrados.
- `telecom/test_whatsapp_seal_activation_migration.py` (novo, 2 nodes): T10 completo — os 6 cenários aprovados.
- `telecom/test_whatsapp_seal.py`: 1 ajuste pontual e documentado (ver Fixtures corrigidas abaixo) — alvo intermediário de migração de `"0021"` para `"0022"` em `test_migration_preserves_existing_lines_as_no_seal`.
- Esta fonte da verdade.

**Fixtures corrigidas — causa demonstrada, sem enfraquecer assertions.** `test_migration_preserves_existing_lines_as_no_seal` fixava o schema em `"0021"` antes de `refresh_from_db()`; como o modelo Python usado é o real (não histórico) e agora sempre declara os 4 campos de 0022, parar em "0021" faz o SELECT falhar com `OperationalError: no such column`. Causa: a introdução de **qualquer** migration nova após 0021 quebraria esse teste do mesmo jeito — não é uma falha da minha implementação, é uma fragilidade estrutural do teste (usa o model real contra um schema deliberadamente desatualizado). Corrigido apontando o alvo intermediário para `"0022"` (o HEAD real); nenhuma assertion foi alterada, removida ou enfraquecida — mesmas comparações, mesmo propósito (provar que registros sem selo não são afetados), documentado inline no próprio teste.

**Regras de domínio implementadas (telecom/whatsapp_seal.py::validate_seal_extended_fields):** situação/categoria/plano obrigatórios e validados contra o catálogo (token desconhecido ou combinação cruzada rejeitados); e-mail/pagamento obrigatórios (herdado); Ativo exige as duas datas (ordem invertida sempre rejeitada, incondicional à situação — ver nota abaixo); Não ativado rejeita datas preenchidas (a normalização as limpa antes, então esse ramo só dispara em uso direto de `validate_seal_extended_fields` fora do fluxo normal `clean()`); valor ausente sempre inválido; negativo sempre rejeitado em ambos os estados; Ativo exige valor > 0; limite máximo 299,00 em ambos; zero explícito em Não ativado é um valor válido e distinto de ausência. A checagem de datas invertidas foi deliberadamente mantida **incondicional** à situação (não só quando ACTIVE) — comportamento idêntico ao pré-SEV-04 — para não regressão do controle `test_vencimento_anterior_a_ativacao_rejeitado` (GREEN antes e depois).

**Test Checklist — nodes SEV-04 (novos, todos GREEN):**

| Arquivo | Nodes | Cobre |
| --- | --- | --- |
| telecom/test_whatsapp_seal_model_domain.py | 38 | T01, T02, T03, T06, T11, T16, T17, T18, T20, T21, T22 (domínio puro) |
| telecom/test_whatsapp_seal_activation_migration.py | 2 | T10 (6 cenários: legado→ACTIVE, datas preservadas, categoria/plano vazios, valor null, excluídos logicamente incluídos, reversão preserva os 5 campos antigos) |

**Nodes do arquivo RED de SEV-03 que viraram GREEN como efeito direto de SEV-04 (modelo/domínio, não forms):**

| Node | Motivo |
| --- | --- |
| TestT01SemSeloLimpaDadosProprios::test_sem_selo_limpa_situacao_categoria_plano_valor | Defaults de model agora existem |
| TestT01SemSeloLimpaDadosProprios::test_form_sem_selo_limpa_campos_novos_mesmo_com_residuo_no_post | Idem (Sem selo não aciona validação estendida) |
| TestT02NaoAtivado::test_nao_ativado_nao_gera_alerta | `compute_seal_status` distingue Não ativado |
| TestT04AtivacaoNaoAlteraOperacional::test_editar_apenas_selo_nao_altera_status_activated_at_ou_historico | `activation_status` já ACTIVE via `save()` desde a criação; edição no caminho legado não altera status/activated_at/histórico |
| TestT05Legado::test_linha_legada_sem_campos_novos_eh_tratada_como_ativa | `save()` fallback classifica legado como ACTIVE |
| TestT05Legado::test_get_legado_funciona_sem_valor | Controle, inalterado |
| TestT09.../test_liberar_linha_nao_exige_completar_selo_legado | Controle, inalterado |
| TestT11AlertasEComputeSealStatus (2 nodes) | `compute_seal_status` com `activation_status` |
| TestT12.../test_overview_ajax_distingue_nao_ativado_de_sem_selo | Idem via `seal_status` |
| TestT13Relatorios (2 nodes) | Controle, inalterado |
| TestT15.../test_operator_continua... | Controle, inalterado |
| TestT19.../test_remover_selo_remove_categoria_plano_e_valor | `normalize_seal_fields` limpa tudo ao remover selo, mesmo via form legado |
| TestT20LegadoSemInferencia::test_legado_nao_recebe_categoria_plano_inferidos_pelo_tipo | `save()` só define `activation_status`, nunca categoria/plano |
| TestT03Ativo::test_vencimento_anterior_a_ativacao_rejeitado | Controle (já era GREEN) |

**Contagem reconciliada de telecom/test_whatsapp_seal_activation_value.py após SEV-04:** 75 collected = **58 failed + 17 passed** (era 67 failed + 8 passed). Os 58 FAILED restantes são GAP genuíno de SEV-05/06/07 (forms/HTTP/UI/parsing textual), não regressão desta task — cada um ainda falha pela ausência dos 4 campos em `PhoneLineForm`/`PhoneLineUpdateForm` ou de parsing textual monetário (T22, explicitamente fora de escopo: "parsing textual monetário de formulário permanece para SEV-05").

**Test Strategy — comandos executados e resultados reais, nesta ordem, banco SQLite isolado (`test_db.sqlite3`, recriado a cada rodada, nunca duas suítes simultâneas):**

```
venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_model_domain.py -v
  → 38 passed

venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_activation_migration.py -v
  → 2 passed (T10 completo)

venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_activation_value.py -q
  → 75 collected, 58 failed, 17 passed  (baseline reconfirmada antes: 67 failed, 8 passed)

venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/test_seal_detail_and_listing.py -q
  → 65 passed  (zero regressão; 1 fixture de migração corrigida, ver acima)

venv\Scripts\python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
  → 236 passed, 1 skipped, 5 subtests passed  (idêntico à baseline de SEV-03)

venv\Scripts\python.exe -m pytest config/tests/test_whatsapp_seal_report.py config/tests/test_line_inventory_report.py -k "not RealVolume" -q
  → 215 passed, 8 deselected, 10 subtests passed  (idêntico à baseline de SEV-03)

venv\Scripts\python.exe manage.py check --settings=config.settings_dev
  → System check identified no issues (0 silenced).

venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.settings_dev
  → Detecta migration pendente (exit code ≠ 0) — mas SOMENTE drift alheio
    pré-existente, já citado na Gap Analysis de SEV-03 e explicitamente fora
    de escopo: dashboard.DailyUserAction.action_type e
    telecom.PhoneLine.origem. Nenhuma alteração minha (os 4 campos novos e a
    migration 0022) aparece nesta saída — confirma que 0022 está completa e
    consistente com o estado atual do model.

git diff --check
  → sem erro de whitespace (só avisos informativos de LF→CRLF, mesmos 3
    arquivos tocados nesta rodada: a spec, test_whatsapp_seal.py e
    whatsapp_seal.py)
```

**Backend e limitações de rollback (honestas, não omitidas):** todas as execuções acima rodaram em **SQLite** (forçado por `pytest-django` via `config/settings.py`, bloco `if "pytest" in sys.modules`) — **Postgres não foi exercitado nesta rodada** (indisponível neste ambiente sandbox; a engine real de produção é Postgres, ver `config/settings.py`). Isso não foi testado nem alegado como equivalente. Reversão (`migrate telecom 0021`) foi exercitada e comprovada por `test_migration_0022_is_reversible_sem_quebrar` e pelo teste de 6 cenários — em ambos os casos a perda dos 4 campos novos no rollback é esperada e documentada, não testada como sucesso silencioso; os 5 campos antigos de selo são preservados exatamente, comprovado por leitura SQL crua (não pelo model real, que já não corresponde ao schema revertido).

**Critério de conclusão — autoavaliação:**
- Domínio/modelo: todas as regras da seção "Regras de domínio" da spec implementadas e comprovadas por 38 nodes diretos, sem depender de forms.
- T10 (migração): os 6 cenários aprovados comprovados por 2 nodes reais (não placeholder), backfill restrito à feature, sem drift alheio.
- Falhas remanescentes de SEV-05/06/07 permanecem (58 nodes), identificadas por node ID e causa acima — nenhuma foi implementada para "zerar a suíte".
- Nenhuma regressão real: as 3 suítes de regressão (SEL/Telecom/Relatórios, total 516 testes/subtestes) permanecem 100% GREEN; 1 fixture de teste de migração pré-existente precisou de ajuste de alvo (causa demonstrada, documentada, sem enfraquecer assertion).
- `manage.py check` limpo; `makemigrations --check --dry-run` mostra apenas drift alheio pré-existente; `git diff --check` limpo.
- Sem commit, push, deploy, dependência nova ou acesso a PRD nesta task.

**Observação operacional importante para a ordem de entrega (não é escopo de código, é risco a registrar):** com `PhoneLine.clean()` agora expondo validação estendida, qualquer caminho de escrita que *venha a* tocar categoria/plano/valor sem integrar o formulário completo quebraria com o mesmo `ValueError` descrito na Gap Analysis. Isso significa que **SEV-04 não é segura para produção isoladamente caso algo além do `PhoneLineForm` atual comece a popular esses 3 campos antes de SEV-05 integrar os formulários** — risco teórico nesta base de código atual (nada mais os popula hoje), mas relevante para quem decidir a ordem de deploy futura.

SEV-04 concluída. Próxima: SEV-05 (formulários e salvamento) — não iniciada.

### 2026-10-01 — SEV-04: retificação de dois desvios de contrato

**Motivo.** Revisão apontou que o fechamento anterior de SEV-04 introduziu dois mecanismos não aprovados para evitar um crash de fronteira com `PhoneLineForm`: um portão em `PhoneLine.clean()` que pulava a validação obrigatória quando categoria/plano/valor estavam todos ausentes, e um fallback em `PhoneLine.save()` que classificava automaticamente `ACTIVE` qualquer save() comum com selo e situação vazia. Esta rodada corrige os dois por inspeção direta do código (não por relato), com RED reconstruído após a implementação, mediante reaplicação pontual dos mecanismos defeituosos. Não houve prova de execução desses novos testes antes da implementação da correção.

**Spec Summary.** Mesmo objetivo de SEV-04 (domínio/modelo/migration completos e independentes de forms); esta rodada remove dois mecanismos que comprometiam a obrigatoriedade do contrato, sem alterar escopo, sem tocar `create_or_reuse` nem implementar formulário algum.

**Gap Analysis — os dois achados, confirmados por leitura direta do código antes de qualquer alteração:**

**A. Portão em `PhoneLine.clean()` (`_seal_extended_fields_in_use`).** Condição: `self.whatsapp_seal and not self._seal_extended_fields_in_use()`, onde o método só checava categoria/plano/valor (situação deliberadamente excluída do portão). Fluxo: quando os três campos estavam todos ausentes, `clean()` desviava para a validação antiga de 5 campos (datas/e-mail/pagamento), pulando inteiramente a exigência de situação/categoria/plano/valor/catálogo. Consequência: `PhoneLine(whatsapp_seal="META_ONE", ...).full_clean()` com os 4 campos novos ausentes **não levantava erro algum** para eles — exatamente o caso que o contrato exige rejeitar ("categoria/plano/e-mail/pagamento obrigatórios com selo"). Confirmado por `git diff` da rodada anterior e teste de reprodução (ver abaixo).

**B. Fallback em `PhoneLine.save()`.** Condição: `if self.whatsapp_seal and not self.whatsapp_seal_activation_status`. Fluxo: **todo** `save()` (não só o backfill histórico) com selo e situação vazia gravava `ACTIVE` silenciosamente. Consequência: qualquer entrada nova com selo e sem situação explícita (via ORM direto, job, ou qualquer código que não passe por `full_clean()`) tinha a situação inferida e persistida, violando "Não inferir situação ausente em entrada com selo" e misturando responsabilidade de backfill histórico (que pertence exclusivamente à migration) com persistência comum.

**Teste de reprodução do crash de fronteira (achado 4, Django instalado).** Confirmado neste ambiente (Django 5.2.11): `PhoneLineForm(data={"whatsapp_seal": "META_ONE", ...}).is_valid()` levanta `ValueError: 'PhoneLineForm' has no field named 'whatsapp_seal_category'` (não um `form.errors` normal) — reproduzido isoladamente antes de qualquer decisão de correção. Causa raiz (Django 5.2.11, `django/db/models/base.py::Model.full_clean()`): o `exclude` passado por `ModelForm._post_clean()` filtra `clean_fields()`/`validate_unique()`/`validate_constraints()`, mas **não** filtra os erros levantados por `self.clean()`. Qualquer erro de `Model.clean()` referenciando um campo ausente de `self.fields` do form chega a `ModelForm._update_errors()` → `add_error(None, errors)` → `ValueError`, não a uma falha de validação normal.

**Implementation Plan — menor correção aplicada:**

1. `telecom/whatsapp_seal.py`: as duas funções (`validate_seal_fields` de 5 parâmetros e `validate_seal_extended_fields` de 9) foram consolidadas em uma única `validate_seal_fields` (9 parâmetros, contrato completo, incondicional). Elimina "duas regras concorrentes de validação".
2. `telecom/models.py::PhoneLine.clean()`: portão removido. `clean()` agora chama `validate_seal_fields` incondicionalmente, sempre que há selo — sem exceção baseada em quais campos estão preenchidos.
3. `telecom/models.py::PhoneLine.save()`: o método inteiro foi removido (nenhum override de `save()` em `PhoneLine`). Nenhuma inferência de situação em save() comum. O backfill histórico permanece exclusivamente na migration 0022 (`RunPython` sobre modelo histórico via `apps.get_model`, `.update()` em massa — nunca `PhoneLine.save()`/`full_clean()`), inalterada nesta retificação.
4. Fronteira do ModelForm: **não corrigida**. Decisão explícita de não aplicar nenhum ajuste em `telecom/forms.py` nesta task — nem supressão de erro, nem adição de campos ao form, nem captura de `ValueError`. O crash é real, confirmado, e fica registrado como dependência bloqueante de SEV-05 (ver Compliance Report). Entrega mantida como **não implantável isoladamente**.

**Fixtures corrigidas — duas, causa demonstrada, sem enfraquecer assertions:**

| Arquivo | Node | Causa | Correção |
| --- | --- | --- | --- |
| telecom/test_whatsapp_seal_model_domain.py | `test_legado_via_orm_direta_eh_classificado_ativo_sem_inferir_categoria_plano` | Asserção exigia `activation_status == "ACTIVE"` após `.objects.create()` direto — codificava exatamente o fallback do achado B | Renomeado para `test_save_comum_nao_infere_situacao_nem_categoria_plano`; asserção corrigida para `activation_status == ""`; docstring explica a retificação |
| telecom/test_whatsapp_seal_activation_value.py | `TestT05Legado::test_linha_legada_sem_campos_novos_eh_tratada_como_ativa` | Mesma causa — presumia que `.objects.create()` "simula pós-migração", o que só era verdade por causa do fallback removido | Renomeado para `test_criacao_direta_via_orm_nao_classifica_nem_infere_campos_novos`; asserção corrigida para `activation_status == ""`; docstring documenta a retificação, remete a `test_whatsapp_seal_activation_migration.py` para a cobertura real de T10 |

Nenhuma outra asserção foi alterada, enfraquecida ou removida. Nenhum node teve sua expectativa revertida para "mais fácil de passar" sem causa demonstrada e documentada.

**Test Checklist — novos nodes desta retificação (9 GREEN no código corrigido; 5 falham na reconstrução dos mecanismos defeituosos posterior à implementação):**

| Node | Cenário | RED capturado? |
| --- | --- | --- |
| test_selo_com_quatro_campos_novos_ausentes_eh_rejeitado_por_full_clean | full_clean rejeita com os 4 campos ausentes | Sim — portão pulava a validação |
| test_nao_ativado_sem_categoria_plano_valor_eh_rejeitado | NOT_ACTIVATED sem categoria/plano/valor | Sim |
| test_situacao_ausente_com_demais_dados_completos_eh_rejeitada | Situação ausente, resto completo | Não (gate já era true nesse caso; controle) |
| test_ativo_com_campos_completos_valida | ACTIVE completo valida | Não (controle) |
| test_nao_ativado_com_campos_completos_e_valor_zero_valida | NOT_ACTIVATED completo, valor zero valida | Não (controle) |
| test_ativo_com_valor_zero_eh_rejeitado | ACTIVE com valor zero rejeita | Não (controle) |
| test_backfill_historico_classifica_ative_sem_depender_de_save_ou_model | `.objects.create()` não classifica nada sozinho | Sim — fallback de save() classificava |
| test_operacao_independente_em_legado_nao_exige_nem_preenche_campos_novos | `save(update_fields=[...])` não preenche nem exige | Sim — fallback preenchia situação |
| test_save_comum_nao_inventa_active_quando_situacao_ausente | save() comum não infere ACTIVE | Sim — este é o teste direto do achado B |

**Metodologia do RED reconstruído (posterior à implementação):** os 2 mecanismos (portão + fallback) foram reaplicados temporariamente por cima do código já corrigido (edição pontual, não `git stash` — a primeira tentativa com `git stash` reverteu acidentalmente todo o SEV-04, não só os 2 desvios, e foi revertida imediatamente via `git stash pop` antes de qualquer teste rodar contra esse estado incorreto). Com os 2 mecanismos reaplicados: **5 de 9 nodes falharam** (os marcados "Sim" acima), confirmando RED genuíno. Removidos os mecanismos novamente (código corrigido restaurado): **9 de 9 passaram**.

**Reclassificação explícita — a contagem "58 falhas são todas gaps de SEV-05/06/07" do fechamento anterior está retirada.** A causa real de boa parte dessas falhas (e de 32 falhas adicionais na suíte de regressão, detalhado abaixo) é o crash de fronteira do ModelForm, não ausência de funcionalidade de SEV-05/06/07 como implicava o relato anterior. Reclassificação completa abaixo.

**Contagem reconciliada de `telecom/test_whatsapp_seal_activation_value.py` após a retificação:** 75 collected = **61 failed + 14 passed** (era 58 failed + 17 passed antes da retificação; 3 nodes que dependiam do portão/fallback voltaram a RED genuíno — `test_vencimento_anterior_a_ativacao_rejeitado`, `test_editar_apenas_selo_nao_altera_status_activated_at_ou_historico`, `test_remover_selo_remove_categoria_plano_e_valor` — e 1 node teve a fixture corrigida e passou a refletir o contrato real, ver tabela acima).

**Regressão da suíte SEL (telecom/test_whatsapp_seal.py + test_phoneline_form_ui.py + test_seal_detail_and_listing.py): 32 failed + 33 passed** (era 65 passed antes da retificação — os 32 agora RED eram GREEN só porque o portão mascarava o crash). Causa raiz confirmada por rastreamento completo de 2 nodes representativos (`test_updating_seal_preserves_activated_at_status_and_allocation` em test_whatsapp_seal.py, `test_release_action_still_works_http` em test_phoneline_form_ui.py — este último falha na própria etapa de setup do teste, que cria uma linha com selo via `PhoneLineForm`, antes de exercitar a ação de Liberar propriamente dita): todos os 32 compartilham a mesma causa raiz — `ValueError` ao submeter `PhoneLineForm`/`PhoneLineUpdateForm` com qualquer selo, descrita no achado 4 acima. Nenhum dos 32 é um defeito novo de lógica de domínio; todos são o mesmo crash de fronteira, confirmado, não corrigido nesta task por decisão explícita (dependência de SEV-05).

**telecom/test_whatsapp_seal.py + test_phoneline_form_ui.py — nodes FAILED (32), todos mesma causa (ModelForm ValueError):**

```
test_seal_requires_each_field[whatsapp_seal_activated_on-META_ONE/META_VERIFIED] (2)
test_create_persists_manual_dates[META_ONE-CREDIT_CARD/META_VERIFIED-GOOGLE_GIFT_CARD] (2)
test_seal_requires_each_field[whatsapp_seal_expires_on/email/payment-META_ONE/META_VERIFIED] (6)
test_invalid_seal_data[whatsapp_seal_email-invalid/whatsapp_seal_payment-CASH/whatsapp_seal_expires_on-2026-08-31] (3)
test_equal_dates_accepted
test_invalid_format_error_not_duplicated_with_required_message
test_invalid_email_format_on_edit_does_not_reuse_stale_value
test_removing_seal_clears_data
test_reactivation_does_not_restore_old_seal
test_switching_between_seal_types_persists_new_values_without_mixing_old
test_updating_seal_preserves_activated_at_status_and_allocation
test_model_validation_requires_seal_details
test_http_create_detail_list_and_edit
test_invalid_http_post_keeps_errors
test_missing_seal_field_error_message_not_duplicated
test_invalid_edit_does_not_reuse_stale_value_for_contradictory_message
test_invalid_http_edit_keeps_errors_and_does_not_persist_partial_data
test_phoneline_form_ui.py::test_invalid_post_shows_errors_and_keeps_values
test_phoneline_form_ui.py::test_invalid_edit_keeps_seal_block_open
test_phoneline_form_ui.py::test_release_action_bypasses_html_validation
test_phoneline_form_ui.py::test_release_action_still_works_http
test_phoneline_form_ui.py::test_error_summary_uses_friendly_ptbr_labels
test_phoneline_form_ui.py::test_switching_existing_seal_to_none_without_js_saves_and_clears
```

Causa: **integração ausente de SEV-05** (confirmado, não fabricado) — todos crasham em `ModelForm._post_clean` porque `PhoneLineForm`/`PhoneLineUpdateForm` ainda não listam os 4 campos novos em `Meta.fields`. Task responsável: SEV-05. `test_seal_detail_and_listing.py`: 0 falhas (não cria/edita selo via form nos caminhos exercitados).

**Suítes não afetadas (confirmado por execução, não presumido):**

```
telecom/tests.py + tests_line_timeline.py → 236 passed, 1 skipped, 5 subtests (idêntico à baseline)
config/tests/test_whatsapp_seal_report.py + test_line_inventory_report.py (-k "not RealVolume") → 215 passed, 8 deselected, 10 subtests (idêntico à baseline)
```

Nenhuma delas cria/edita selo via `PhoneLineForm`/`PhoneLineUpdateForm` nos caminhos exercitados — por isso o crash de fronteira não as afeta.

**Test Strategy — comandos e resultados reais desta retificação, banco SQLite isolado, recriado a cada rodada, nunca duas suítes simultâneas:**

```
venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_sev04_correction.py -v
  → RED (mecanismos reaplicados temporariamente): 5 failed, 4 passed
  → GREEN (código corrigido restaurado): 9 passed

venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_model_domain.py -q
  → 38 passed (1 node corrigido, ver tabela de fixtures)

venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_activation_migration.py -v
  → 2 passed (T10 intacto — migration não foi tocada nesta retificação)

venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_activation_value.py -q
  → 75 collected, 61 failed, 14 passed (1 node corrigido, ver tabela de fixtures)

venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/test_seal_detail_and_listing.py -q
  → 32 failed, 33 passed (regressão real exposta — ver reclassificação acima)

venv\Scripts\python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
  → 236 passed, 1 skipped, 5 subtests passed (sem regressão)

venv\Scripts\python.exe -m pytest config/tests/test_whatsapp_seal_report.py config/tests/test_line_inventory_report.py -k "not RealVolume" -q
  → 215 passed, 8 deselected, 10 subtests passed (sem regressão)

venv\Scripts\python.exe manage.py check --settings=config.settings_dev
  → System check identified no issues (0 silenced).

venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.settings_dev
  → Detecta apenas drift alheio pré-existente (dashboard.DailyUserAction.
    action_type, telecom.PhoneLine.origem) — nada desta retificação.

git diff --check
  → sem erro (só avisos informativos de LF→CRLF)
```

**Backend:** SQLite apenas (pytest-django força sqlite3 — ver `config/settings.py`). Postgres não exercitado nesta retificação (mesma limitação já registrada no fechamento anterior de SEV-04; a migration 0022 em si não foi alterada, então sua cobertura de T10 permanece a mesma, incluindo a mesma limitação de backend).

**Compliance Report:**

- **Domínio/modelo:** contrato restabelecido. `PhoneLine.clean()` aplica `validate_seal_fields` incondicionalmente quando há selo; nenhuma condição de campos ausentes dispensa obrigatoriedade. `PhoneLine.save()` não tem mais nenhum override — nenhuma inferência de situação em save() comum. Comprovado por 9 novos nodes (RED real capturado, depois GREEN) + 38 nodes de domínio já existentes (1 corrigido) + 2 nodes de migração intactos.
- **Migration (T10):** inalterada nesta retificação — os 6 cenários continuam comprovados por `telecom/test_whatsapp_seal_activation_migration.py`, que já usava modelo histórico via `apps.get_model` e nunca dependeu do `save()`/`clean()` do model real. Confirmado por reexecução, não presumido.
- **Fronteira ModelForm:** crash real e confirmado (`ValueError`), não corrigido, registrado como dependência bloqueante de SEV-05. Nenhuma supressão, nenhuma captura genérica de exceção, nenhuma integração parcial de formulário foi aplicada.
- **Regressão:** 32 nodes da suíte SEL (antes 100% GREEN) agora falham — causa única, confirmada, classificada (não fabricada): ausência de integração de SEV-05. Esta é uma regressão real de comportamento HTTP/form em relação ao estado anterior a qualquer trabalho de SEV-04, mas é consequência direta e esperada de restabelecer o contrato de domínio incondicionalmente — a alternativa (manter o portão/fallback) violava o contrato aprovado pelo usuário, que é o que esta retificação corrige.
- **Estado de implantação — separado do aceite de domínio/migração:** domínio/modelo/migration (SEV-04) **aceitos** pelo contrato; a aplicação como um todo **não está pronta para implantação** enquanto `PhoneLineForm`/`PhoneLineUpdateForm` não integrarem os 4 campos novos (SEV-05) — submeter qualquer selo pelo formulário atual resulta em erro não tratado (500), não em mensagem de validação compreensível.
- `manage.py check` e `git diff --check` limpos. `makemigrations --check --dry-run` mostra apenas drift alheio pré-existente, não incorporado.
- Sem commit, push, deploy ou acesso a PRD nesta retificação. Nenhuma implementação de SEV-05/interface iniciada.

Retificação de SEV-04 concluída. Dependência explícita e registrada para SEV-05: integrar `telecom/forms.py` (`PhoneLineForm`/`PhoneLineUpdateForm`) com os 4 campos novos é pré-requisito para a aplicação voltar a aceitar qualquer submissão de selo sem crash.


### 2026-10-01 — Ressalvas documentais da retificação SEV-04

**Spec Summary.** Precisar cronologia, estado de integração e limite da evidência de recuperação do incidente de stash. Esta rodada leu a spec e o estado Git atual; não reinspecionou a implementação nem reexecutou testes. Números abaixo são resultados registrados pelo executor anterior.

**Gap Analysis.**

1. **RED reconstruído, não TDD cronológico.** Os mecanismos defeituosos foram reaplicados sobre código já corrigido; nessa reconstrução, 5/9 testes falharam, e 9/9 passaram após removê-los novamente. Isso demonstra sensibilidade dos testes aos mecanismos reproduzidos. Não prova que os novos testes foram executados antes da implementação original. As duas frases que afirmavam essa cronologia foram retificadas acima; comandos, resultados e metodologia preservados.
2. **Regressão bloqueante de integração.** O resultado SEL registrado é 32 FAILED + 33 PASSED. A aplicação não está GREEN nem implantável. O aceite parcial de domínio/migration não elimina o crash ModelForm nem autoriza deploy. A causa comum é a classificação feita pelo executor; esta revisão documental não reconfirmou individualmente os 32 nodes. SEV-05 deve reexecutar e resolver/classificar cada falha, sem suprimir erros ou restaurar bypass no domínio.
3. **Stash: recuperação integral não comprovada por esta evidência.** O executor relata git stash pop e testes posteriores, mas não está registrada comparação completa anterior/posterior do conteúdo e do stage de todos os arquivos afetados, incluindo trabalho alheio e arquivos não rastreados. Testes GREEN verificam os caminhos exercitados, não identidade integral do workspace. Não afirmar “sem perda” apenas com base no pop, em git status ou em testes. Antes de nova mutação, conferir a recuperação contra artefatos anteriores disponíveis (diffs, snapshots, conteúdo capturado). Se não houver baseline suficiente, registrar expressamente “preservação integral não verificável retrospectivamente”; não inventar prova e não executar novo stash/reset/checkout para tentar produzi-la.

**Implementation Plan.** Somente retificação documental; preservar histórico. SEV-05 permanece próxima etapa técnica, com conferência inicial do workspace e bloqueio de integração explícito.

**Test Checklist.** Cronologia RED corrigida; 32 falhas mantidas visíveis; limitação do incidente registrada. Não há novo resultado de teste nesta rodada.

**Test Strategy.** Leitura documental e git status; sem suíte reexecutada, porque nenhum código/teste foi alterado por esta revisão. A conferência documental não substitui verificação funcional nem comparação de recuperação.

**Compliance Report.** Somente esta fonte da verdade alterada nesta rodada. Domínio/migration têm aceite parcial relatado; aplicação continua não implantável. Nenhum código, migration, teste, stage, commit, push, deploy ou PRD tocado. Não houve certificação de recuperação integral do stash.

### 2026-10-01 — SEV-05 concluída: formulários e salvamento

**0. Preservação do workspace (antes de qualquer edição).** `git status` e `git diff --stat` conferidos no início desta task: nenhum trabalho de terceiros em andamento nas áreas tocadas (telecom/forms.py, telecom/models.py, telecom/whatsapp_seal.py, telecom/test_whatsapp_seal*.py, telecom/test_phoneline_form_ui.py já constavam modificados/criados pelas tasks SEV-03/04 anteriores, confirmado pelo `git diff --stat` do início da sessão). Nenhum `stash`/`reset`/`checkout`/`revert` foi usado nesta task. Quanto à ressalva documental da retificação de SEV-04 (recuperação do stash daquele incidente): esta task não reexecutou nem reavaliou aquela evidência — permanece como registrado em "Ressalvas documentais da retificação SEV-04": **preservação integral do stash daquele incidente não verificável retrospectivamente**, não certificada aqui nem em nenhuma rodada anterior.

**Spec Summary.** Objetivo: integrar os 4 campos novos (`whatsapp_seal_activation_status`, `whatsapp_seal_category`, `whatsapp_seal_plan`, `whatsapp_seal_monthly_value`) em `PhoneLineForm`/`PhoneLineUpdateForm` e em `PhoneLine.create_or_reuse`, eliminando o crash `ValueError` de fronteira do ModelForm confirmado na retificação de SEV-04, sem reintroduzir portão de campos vazios, fallback de situação ou `full_clean` no save global — preservando a obrigatoriedade incondicional estabelecida pelo domínio em SEV-04.

**1. Inspeção prévia (antes de qualquer código), conforme mandado.** Lidos por completo: `telecom/forms.py` (`PhoneLineForm`/`PhoneLineUpdateForm`, `full_clean`/`_post_clean`/`save` existentes), `telecom/models.py` (`PhoneLine.clean`, `create_or_reuse`, ausência de `save()` override — confirmado consistente com a retificação de SEV-04), `telecom/whatsapp_seal.py` (`validate_seal_fields` já unificada e incondicional, `normalize_seal_fields`, `clear_seal_fields`), `telecom/views.py::PhoneLineUpdateView.post` (ação `release_line` processada **antes** de qualquer validação de form — confirmado preservado, não tocado nesta task) e os 3 chamadores de `create_or_reuse` sem selo (`telecom/admin.py`, `telecom/views.py::SIMcardCreateView`, `core/services/telephony_use_case.py` — nenhum envia `whatsapp_seal`, portanto nenhum é afetado pela validação nova).

Suítes focadas reexecutadas para reconfirmar o crash antes de codar:

```
venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_model_domain.py telecom/test_whatsapp_seal_activation_migration.py telecom/test_whatsapp_seal_sev04_correction.py -q
  → 49 passed (idêntico ao relatado: 38 + 2 + 9)

venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_activation_value.py -q
  → 75 collected, 61 failed, 14 passed (idêntico ao relatado)
```

Reprodução direta do crash confirmada antes de qualquer edição: `PhoneLineForm(data={"whatsapp_seal": "META_ONE", ...}).is_valid()` levanta `ValueError: 'PhoneLineForm' has no field named 'whatsapp_seal_activation_status'` — mesma causa raiz já documentada na retificação de SEV-04 (`Model.clean()` não filtrado por `exclude` em `ModelForm._post_clean`).

**Classificação de node IDs por task, antes do código (conforme mandado):** usando a tabela de SEV-03/04 como base, os 61 nodes então falhos de `test_whatsapp_seal_activation_value.py` foram classificados em: (a) form/HTTP/domínio alcançável sem template novo → SEV-05 (58 nodes); (b) depende de o template renderizar os 4 campos novos (inspeção direta de `templates/telecom/phoneline_form.html`/`phoneline_detail.html`, que listam cada campo manualmente, não iteram `{% for field in form %}`) → SEV-06, deve permanecer RED nesta task (3 nodes: `TestT12...test_detalhe_mostra_situacao_e_valor_nao_informado_para_legado`, `TestT14...test_formulario_novo_nao_renderiza_campo_de_valor_ainda`, `TestT16...test_novo_formulario_apresenta_nao_ativado_por_default`). Nenhum node de SEV-07 (aceite em navegador real) está neste arquivo. Confirmado que nem todas as 61 falhas tinham a mesma causa: 58 eram unicamente o crash/ausência de campo; os 3 de template são uma causa distinta (ausência de marcação HTML), não resolvida por mudança de form/model.

**2. Fronteira ModelForm — resolução.** Causa do crash (Django 5.2.11): `Model.clean()` não é filtrado por `exclude` em `ModelForm._post_clean()`; qualquer erro referenciando um campo ausente de `self.fields` do form vira `ValueError`, não uma falha de validação normal. Resolvido pela raiz: os 4 campos agora existem em `PhoneLineForm.Meta.fields`/`PhoneLineUpdateForm.Meta.fields`, então qualquer erro do domínio sobre eles chega a um campo real do form — nenhuma supressão, nenhum catch de `ValueError`, nenhum portão por campos ausentes.

**3. Integração dos formulários.**
- `whatsapp_seal_activation_status`, `whatsapp_seal_category`, `whatsapp_seal_plan` adicionados a `Meta.fields` de `PhoneLineForm` e `PhoneLineUpdateForm`, com widgets `Select` e labels em pt-BR. Django gera automaticamente a opção em branco "---------" para esses `ChoiceField` (campo `blank=True` no model), sem necessidade de override manual (diferente de `whatsapp_seal`, que já tinha override de label "Sem selo" preexistente).
- `whatsapp_seal_monthly_value` declarado explicitamente como `forms.CharField` (não o `DecimalField` que o ModelForm geraria automaticamente), porque o parser localizado padrão do Django é ambíguo entre separador decimal/milhar e não implementa o contrato textual de SEV-02. `clean_whatsapp_seal_monthly_value` converte via `telecom/whatsapp_seal.py::parse_seal_monthly_value` (nova), devolvendo `Decimal` ou `None`, nunca `float`.
- `validate_seal_fields` (domínio) continua a única autoridade de obrigatoriedade condicional — nenhuma duplicação no form. Erros do domínio aterrissam no campo correto porque o campo agora existe no form (`ModelForm.add_error` já mapeia por nome de campo).
- Nenhum `full_clean` global, nenhum fallback de situação, nenhum portão por campos vazios foram adicionados — confirmado por leitura do diff final de `telecom/models.py` (nenhum `save()` override) e `telecom/whatsapp_seal.py` (`validate_seal_fields` permanece a única função, incondicional, já existente desde a retificação de SEV-04).

**4. Contrato de entrada e normalização.**
- `PhoneLineForm.full_clean()` estendido: a lista `SEAL_DETAIL_FIELDS` (antes só os 4 campos antigos) agora inclui os 4 campos novos — quando o POST indica Sem selo, todos os 8 são zerados na cópia do `QueryDict` **antes** de `super().full_clean()` rodar qualquer parser de campo, evitando que um resíduo em formato inválido (ex.: valor monetário quebrado) bloqueie salvar Sem selo. Novo ramo `elif` cobre Não ativado: quando `whatsapp_seal_activation_status == "NOT_ACTIVATED"` no POST, as duas datas (`SEAL_DATE_FIELDS`) são zeradas antes do parsing de data, inclusive resíduo inválido — implementa literalmente a frase da spec "Não ativado normaliza apenas datas inaplicáveis... inclusive resíduos inválidos".
- `telecom/whatsapp_seal.py::parse_seal_monthly_value` (nova): aceita `59`, `59,0`, `59,00`, `59.00` e espaços externos; rejeita por regex (`^\d+([.,]\d{1,2})?$`, aplicado ao texto já despojado de espaços) símbolo de moeda, separador de milhar, separadores misturados, notação científica, `NaN`/`Infinity`, mais de duas casas decimais e **qualquer sinal** — inclusive `-0,00`, rejeitado textualmente antes de qualquer interpretação numérica (`Decimal("-0.00") < 0` é `False` em Python; a checagem de negativo em `validate_seal_fields`, que opera sobre `Decimal` já convertido, nunca pegaria esse caso). String vazia retorna `None` (ausência), distinto de `"0,00"` (zero explícito, `Decimal("0.00")`).
- Situação: `PhoneLineForm.__init__` define `self.fields["whatsapp_seal_activation_status"].initial = NOT_ACTIVATED` apenas quando a instância não tem `pk` (cadastro novo) — `initial` nunca influencia o binding de um POST (Django usa exclusivamente `self.data` ao validar um form vinculado), portanto POST com selo e situação ausente continua inválido (comprovado por `test_post_com_selo_sem_situacao_explicita_eh_invalido`), e edição sempre usa o valor real da instância (via `model_to_dict`), nunca o `initial` da classe.

**5. Salvamento e create_or_reuse.**
- `PhoneLine.create_or_reuse` ganhou 4 kwargs novos opcionais (default `""`/`None`), compatíveis com os 3 chamadores existentes que não enviam selo (confirmado por regressão).
- Normalização e validação **reutilizadas** do domínio, sem duplicar regra de negócio: uma instância `PhoneLine` descartável (nunca persistida) é construída só como veículo para `normalize_seal_fields`/`validate_seal_fields` (as mesmas funções usadas por `PhoneLine.clean()`), e os valores normalizados são extraídos de volta antes de decidir entre criar ou reaproveitar. Chamador sem selo nunca aciona validação (branch `if not seal: return` em `validate_seal_fields`); chamador com selo incompleto/inválido levanta `ValidationError` **antes** de qualquer `objects.create()`/`.save()` — sem gravação parcial, comprovado por `test_create_or_reuse_com_selo_exige_novos_dados` (dentro de `transaction.atomic()`, que já envolvia o método).
- Os 4 campos novos foram adicionados a ambos os branches de escrita (`objects.create()` e `existing_line.save(update_fields=[...])`), incluindo `update_fields`.
- `save(commit=False)`: inalterado (delega a `super().save(commit=False)` do ModelForm padrão), que já devolve a instância com os campos normalizados pelo `clean()` chamado durante `is_valid()`/`_post_clean()`, sem gravar — comprovado por `test_save_commit_false_nao_grava_e_preserva_valor_normalizado`.

**6. Correções de fixtures — todas com causa comprovada, assertions/intenção originais preservadas.** Nenhuma foi classificada como defeito de aplicação; todas decorrem de testes escritos antes de os 4 campos novos (e o catálogo) existirem, usando `create_or_reuse`/payloads como fábrica de dados sem prever a obrigatoriedade/validação cruzada agora vigente.

| Arquivo | Teste | Causa | Ajuste |
| --- | --- | --- | --- |
| test_whatsapp_seal_activation_value.py | `TestT02NaoAtivado::test_nao_ativado_salva_datas_nulas_e_valor_zero` | Parametrizava só `seal`, mantendo category/plan fixos em combinação válida apenas para META_ONE | Parametrização estendida para `seal,category,plan` com as duas combinações reais do catálogo |
| idem | `TestT04...::test_editar_apenas_selo_nao_altera_status_activated_at_ou_historico` | Setup via `create_or_reuse(whatsapp_seal="META_ONE")` sem os 4 campos novos — create_or_reuse agora exige dados completos | Setup completado com combinação NOT_ACTIVATED válida (coerente com o nome da classe, que pressupõe partida em Não ativado) |
| idem | `TestT08...::test_reactivation_nao_recupera_categoria_plano_valor_antigos` | Setup com category/plan/value mas sem activation_status/datas/e-mail/pagamento | Setup completado com combinação ACTIVE válida |
| idem | `TestT09...::test_liberar_linha_nao_exige_completar_selo_legado` e `test_editar_linha_alocada_sem_completar_legado_eh_rejeitado_mas_nao_pela_alocacao` | Simulavam "legado" via `create_or_reuse` (que agora valida) em vez de `.objects.create()` direto (como já faziam corretamente `TestT05Legado`/`TestT20`) | Trocado `create_or_reuse` por `.objects.create()` — legado real é produzido pela migration, nunca por `create_or_reuse` |
| test_whatsapp_seal.py | fixture `payload` (compartilhada por ~20 testes) | Anterior aos 4 campos novos; sem eles nenhum teste do arquivo sequer validava os campos antigos que cada um exercita | Acrescentados os 4 campos com combinação ACTIVE/META_ONE do catálogo, consistente com as datas já presentes |
| idem | `test_model_validation_requires_seal_details` | `validate_seal_fields` só exige datas quando `activation_status == ACTIVE`; sem esse campo a checagem de data nunca dispara | Acrescentado `whatsapp_seal_activation_status = "ACTIVE"` à instância construída manualmente |
| idem | `test_switching_between_seal_types_persists_new_values_without_mixing_old` | Troca de `whatsapp_seal` para META_VERIFIED sem trocar category/plan — combinação cruzada inválida pelo catálogo (SEV-04) | Acrescentado `whatsapp_seal_category="PERSONAL_CREATOR"`, `whatsapp_seal_plan="STANDARD"` ao payload de edição |
| idem | `test_create_persists_manual_dates` | Mesma causa, parametrização `seal,payment` sem category/plan correspondentes | Parametrização estendida para `seal,payment,category,plan` |
| test_phoneline_form_ui.py | fixture `payload` | Mesma causa da fixture homônima de test_whatsapp_seal.py | Mesmo ajuste (4 campos novos, combinação ACTIVE/META_ONE) |
| idem | `test_seal_detail_fields_accessible_without_js_by_default` e `test_get_edit_preserves_seal_data` | `create_or_reuse` com selo sem os 4 campos novos | Completados com combinações ACTIVE válidas (META_ONE e META_VERIFIED, respectivamente) |

Nenhuma assertion foi removida, enfraquecida ou teve sua expectativa revertida. Em nenhum caso a correção ocultou o cenário original sob teste.

**7. Limite com SEV-06.** Nenhum template, JS, detalhe ou listagem foi alterado. Os 3 nodes que dependem de o HTML renderizar os campos novos permanecem RED, com causa explícita (ausência de marcação, não de lógica de form/domínio): ver tabela de Test Checklist abaixo. Configuração de campo/labels/`initial` foi feita no form (permitido pela spec), mas isso não constitui aceite visual.

**Test Checklist — rastreabilidade desta rodada.**

| Node/grupo | Antes (SEV-04 retificado) | Depois (SEV-05) | Causa restante |
| --- | --- | --- | --- |
| telecom/test_whatsapp_seal_activation_value.py | 61 failed, 14 passed | **3 failed, 72 passed** | Os 3 failed são SEV-06 (template não renderiza os campos novos): `TestT12...test_detalhe_mostra_situacao_e_valor_nao_informado_para_legado`, `TestT14...test_formulario_novo_nao_renderiza_campo_de_valor_ainda`, `TestT16...test_novo_formulario_apresenta_nao_ativado_por_default` |
| telecom/test_whatsapp_seal.py + test_phoneline_form_ui.py + test_seal_detail_and_listing.py | 32 failed, 33 passed | **0 failed, 65 passed** | — (regressão do crash ModelForm totalmente eliminada) |
| telecom/test_whatsapp_seal_model_domain.py + migration + sev04_correction | 49 passed | 49 passed | Sem mudança (fora de escopo desta task, reconfirmado) |

Todas as linhas T01–T23 do Test Checklist da spec que dependem exclusivamente de form/domínio/HTTP (sem template) estão GREEN. T12 (parte de detalhe), T14 e T16 (parte de default visual) permanecem com a parcela dependente de HTML em aberto para SEV-06, exatamente como a spec previu ("Testes que dependem de controles novos no HTML podem permanecer RED para SEV-06").

**Test Strategy — comandos e resultados reais desta rodada, banco SQLite isolado, suítes sequenciais:**

```
venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_model_domain.py telecom/test_whatsapp_seal_activation_migration.py telecom/test_whatsapp_seal_sev04_correction.py -q
  → 49 passed (baseline reconfirmada, sem mudança)

venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_activation_value.py -q
  → 75 collected, 3 failed, 72 passed (era 61 failed, 14 passed)

venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/test_seal_detail_and_listing.py -q
  → 65 passed (era 32 failed, 33 passed — regressão de SEV-04 totalmente resolvida)

venv\Scripts\python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
  → 236 passed, 1 skipped, 5 subtests passed (idêntico à baseline, sem regressão)

venv\Scripts\python.exe -m pytest config/tests/test_whatsapp_seal_report.py config/tests/test_line_inventory_report.py -k "not RealVolume" -q
  → 215 passed, 8 deselected, 10 subtests passed (idêntico à baseline, sem regressão)

venv\Scripts\python.exe -m pytest config/tests/test_reports_hub.py -q
  → 38 passed, 15 subtests passed (verificação adicional: referências a "whatsapp_seal"/"selo" em filtros de relatório, nenhuma delas grava o campo via create_or_reuse/ORM; incluída por precaução, não mandada explicitamente)

venv\Scripts\python.exe manage.py check --settings=config.settings_dev
  → System check identified no issues (0 silenced).

venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.settings_dev
  → Detecta apenas o mesmo drift alheio pré-existente já documentado em SEV-03/04
    (dashboard.DailyUserAction.action_type, telecom.PhoneLine.origem) — nenhuma
    alteração desta task aparece nesta saída; nenhuma migration nova criada.

git diff --check
  → sem erro de whitespace (só avisos informativos de LF→CRLF nos arquivos tocados).
```

Suítes de `telecom/test_phoneline_form_ui.py`/`test_seal_detail_and_listing.py` fundidas na mesma invocação da suíte SEL por já constarem juntas no Test Strategy desta spec; nenhuma suíte de alto volume foi repetida sem necessidade (relatórios usaram `-k "not RealVolume"`, consistente com rodadas anteriores).

**Backend:** SQLite (pytest-django força esta engine — `config/settings.py`). Nenhuma mudança de schema nesta task (nenhuma migration criada), portanto a limitação de Postgres não exercitado documentada em SEV-04 não se aplica a este trabalho.

**Critério de conclusão — autoavaliação:**
- Fronteira ModelForm: crash `ValueError` eliminado pela raiz (campos agora existem no form); nenhuma supressão de exceção, nenhum portão, nenhum fallback de situação, nenhum `full_clean` global.
- Contrato de entrada: Sem selo/Não ativado/Ativo normalizados e validados exatamente conforme a seção 4 do contrato técnico, reutilizando (não duplicando) `validate_seal_fields`/`normalize_seal_fields`/`parse_seal_monthly_value`.
- `create_or_reuse`: aceita e persiste os 4 campos novos em ambos os branches; chamadores sem selo inalterados; chamador com selo incompleto/inválido rejeitado sem gravação parcial.
- Regressão: as 3 suítes de regressão (SEL/Telecom+Timeline/Relatórios, 516 testes/subtestes) voltaram a 100% GREEN — a regressão de 32 nodes introduzida pela retificação de SEV-04 foi completamente eliminada, não apenas mascarada (confirmado por reexecução completa, não presumido).
- Fixtures: 10 pontos de ajuste documentados acima, todos com causa comprovada (campo/validação agora exigidos que a fixture não previa), nenhuma assertion enfraquecida.
- Limite com SEV-06 respeitado: nenhum template/JS alterado; 3 nodes dependentes de HTML permanecem RED com causa explícita, não contados como implementados.
- `manage.py check` limpo; `makemigrations --check --dry-run` mostra só drift alheio pré-existente; `git diff --check` limpo; nenhuma migration nova criada.
- Sem commit, push, deploy, dependência nova ou acesso a PRD nesta task.

**Separação explícita entre aceite de backend e estado de implantação:** SEV-05 entrega o backend (model/domínio/form/serviço) completo e sem crash. A aplicação **ainda não está pronta para implantação de ponta a ponta**: os templates atuais (`phoneline_form.html`, `phoneline_detail.html`) não enviam nem exibem os 4 campos novos, então um usuário real usando a interface HTML hoje não consegue preencher categoria/plano/situação/valor — only POSTs construídos manualmente (como os desta suíte de testes) exercitam o caminho novo. Esta ausência de cobertura visual é escopo explícito de SEV-06, não uma alegação de aceite completo.

SEV-05 concluída. Próxima: SEV-06 (interface e consumidores) — não iniciada.

### 2026-10-01 — Ressalva documental: oito detalhes, nove campos de selo

**Spec Summary / Gap Analysis.** A expressão “limpa 8 campos do selo” descreve oito campos adicionais, não a quantidade total de campos do selo. Conferência direta de `telecom/forms.py::SEAL_DETAIL_FIELDS` e `PhoneLineForm.full_clean` confirma:

- Quatro detalhes antigos: `whatsapp_seal_activated_on`, `whatsapp_seal_expires_on`, `whatsapp_seal_email`, `whatsapp_seal_payment`.
- Quatro detalhes novos: `whatsapp_seal_activation_status`, `whatsapp_seal_category`, `whatsapp_seal_plan`, `whatsapp_seal_monthly_value`.
- O seletor `whatsapp_seal` é o nono campo e não integra essa lista. O ramo Sem selo é acionado quando esse seletor já está vazio/ausente no POST; antes do parsing, normaliza os oito detalhes para entrada vazia. A normalização posterior de persistência segue o domínio, não é comprovada apenas por esta leitura do form.

**Implementation Plan.** Esclarecimento documental somente; não há defeito de contagem na lista inspecionada nem mudança de contrato.

**Test Checklist / Test Strategy.** Inspeção direta da lista e condição de `full_clean`, sem reexecução de suíte. Esta conferência não constitui nova validação integral de SEV-05.

**Compliance Report.** Somente esta spec alterada nesta rodada. Sem código, testes, migration, commit, push ou deploy. A limitação de implantação registrada no fechamento de SEV-05 permanece até integração e aceite da interface.

### 2026-10-01 — SEV-06 concluída: interface e consumidores

**0. Inspeção prévia (antes de qualquer código).** `git status`/`git diff --stat` conferidos no início: nenhum trabalho de terceiros em andamento nas áreas a tocar; as modificações pendentes de SEV-03/04/05 (forms.py, models.py, whatsapp_seal.py, testes) foram preservadas intactas, nenhum `stash`/`reset`/`checkout` usado. Lidos por completo antes de qualquer edição: `telecom/forms.py`, `telecom/models.py`, `telecom/whatsapp_seal.py`, `telecom/views.py` (PhoneLineCreateView/UpdateView/DetailView, payload ajax de overview), `templates/telecom/phoneline_form.html`, `templates/telecom/phoneline_detail.html`, `templates/telecom/_seal_status_badge.html`, `templates/telecom/overview.html`, `templates/telecom/operator_lines.html`, `static/js/phone-line-form.js`.

Suíte focada reexecutada para reconfirmar o estado relatado antes de codar:

```
venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_activation_value.py -q
  → 75 collected, 3 failed, 72 passed (idêntico ao relatado no fechamento de SEV-05)
```

**3 falhas reconfirmadas por node ID, causa e camada (nenhuma suposição):**

| Node | Causa confirmada por leitura direta |
| --- | --- |
| `TestT12InterfaceDistingueNaoAtivadoDeSemSelo::test_detalhe_mostra_situacao_e_valor_nao_informado_para_legado` | `templates/telecom/phoneline_detail.html` não tinha nenhuma linha de categoria/plano/valor/situação; o texto "Não informado" não existia no HTML |
| `TestT14EstruturaDeFormularioParaNovosCampos::test_formulario_novo_nao_renderiza_campo_de_valor_ainda` | `templates/telecom/phoneline_form.html` só renderizava `whatsapp_seal`, as 2 datas, e-mail e pagamento — nenhum input/select com `name="whatsapp_seal_monthly_value"`/`"whatsapp_seal_category"`/`"whatsapp_seal_plan"` |
| `TestT16AtivoParaNaoAtivadoEDefault::test_novo_formulario_apresenta_nao_ativado_por_default` | Mesma causa — `whatsapp_seal_activation_status` (já com `initial=NOT_ACTIVATED` desde SEV-05, confirmado em `PhoneLineForm.__init__`) nunca era renderizado no HTML |

Os três testes já estavam escritos para o estado-alvo (`assert 'Não informado' in content` / `assert 'name="..."' in content` / `assert 'value="NOT_ACTIVATED" selected' in content`) — nenhuma reescrita de expectativa foi necessária nesta task, apenas implementar o HTML/contexto que os satisfaz.

Gap confirmado em `templates/telecom/overview.html`, `templates/telecom/operator_lines.html` e no payload ajax (`telecom/views.py`, função do `table=main`): **nenhuma ampliação necessária** — ambos já reutilizavam `line.seal_status`/`{% include "telecom/_seal_status_badge.html" %}` desde a correção de `compute_seal_status` em SEV-04 (confirmado também pelo node `TestT12...test_overview_ajax_distingue_nao_ativado_de_sem_selo`, já GREEN antes desta task). Nenhuma linha de template nem de payload foi alterada nessas duas superfícies.

**Implementation Plan — arquivos alterados e motivo:**

| Arquivo | Alteração | Motivo |
| --- | --- | --- |
| `telecom/whatsapp_seal.py` | `SEAL_CATALOG_ORDER` (tupla ordenada, mesma ordem da tabela da spec) extraída antes de `SEAL_CATALOG_COMBINATIONS` (agora derivada dela, não duplicada); nova `seal_catalog_entries()` | Fonte única e determinística do catálogo para serialização ao JS — sem segunda fonte de dados manual no front-end, conforme vedado pela spec |
| `telecom/models.py` | Nova property `whatsapp_seal_monthly_value_display` (formata `Decimal` como "R$ 59,00"; distingue por `is None`: ausência não é convertida em zero — retorna `None`; zero explícito permitido (selo Não ativado) é exibido como "R$ 0,00", não omitido) | Moeda brasileira no detalhe sem lógica de formatação duplicada em template; nenhum campo/migration/regra de domínio tocado |
| `telecom/views.py` | Novo `SealCatalogContextMixin` (cooperativo via `super()`) aplicado a `PhoneLineCreateView`/`PhoneLineUpdateView`; import de `seal_catalog_entries` | Contexto necessário para o `json_script` do catálogo no formulário — nenhuma alteração ao payload ajax de listagem (overview/Carregar mais), que continua emitindo exatamente os mesmos campos de antes |
| `templates/telecom/phoneline_form.html` | Inseridos campos de categoria, plano, situação e valor mensal na ordem aprovada (Selo → Categoria → Plano → Situação → Valor mensal), antes dos detalhes existentes; bloco de datas isolado em `#seal-dates-fields`; label dos campos de data trocado de "(obrigatório com selo)" para "(obrigatório quando ativo)" (texto mais preciso, já que datas não são mais obrigatórias com qualquer selo); `{{ seal_catalog_entries\|json_script:"seal-catalog-data" }}` adicionado | Implementa o contrato de interface da spec; nenhum controle recebe `required`/`hidden` HTML — permanece responsabilidade exclusiva do JS, preservando a melhoria progressiva já estabelecida em SEV-05 |
| `static/js/phone-line-form.js` | Reescrito: alterna bloco inteiro por `hasSeal` (como antes); agora também alterna `#seal-dates-fields` por situação (`ACTIVE`); filtra as opções de categoria (por selo) e plano (por selo+categoria) a partir do catálogo serializado, preservando seleção compatível e limpando a incompatível (nunca infere/auto-seleciona); exibe referência de preço somente informativa, nunca grava no campo de valor | Implementa "ocultar com JS", "não inferir categoria/plano", "preservar seleção compatível", "referência separada do valor efetivo" sem tocar validação de servidor |
| `templates/telecom/phoneline_detail.html` | Adicionadas linhas de Situação/Categoria/Plano/Valor mensal (fallback "Não informado" via filtro `default` — atua sobre `None`/string vazia, nunca sobre o Decimal zero, que a property já converteu em string truthy "R$ 0,00" antes do filtro ser avaliado); datas mostradas como "Não aplicável" quando `activation_status == "NOT_ACTIVATED"` (nunca como campo vazio/defeito) | Implementa "detalhe mostra situação, categoria, plano e valor mensal" e "não apresentar ausência de datas como defeito de um selo Não ativado" |
| `telecom/test_whatsapp_seal_interface_sev06.py` (novo, 7 nodes) | Cobre lacunas reais não exercitadas pelos arquivos de teste existentes (ver Test Checklist abaixo) | Evita duplicar os 3 nodes já existentes de T12/T14/T16; nenhum teste existente foi alterado nesta task |

Nenhum arquivo de `telecom/forms.py`, `telecom/models.py` (campos/migration/validação), `templates/telecom/overview.html`, `templates/telecom/operator_lines.html` ou `templates/telecom/_seal_status_badge.html` precisou de alteração — já atendiam ao contrato (overview/operator/badge reutilizam `seal_status` desde SEV-04; forms.py já expõe os 4 campos desde SEV-05 — template apenas não os renderizava ainda).

**Test Checklist — rastreabilidade desta rodada.**

| Node/grupo | Antes (SEV-05) | Depois (SEV-06) | Observação |
| --- | --- | --- | --- |
| `telecom/test_whatsapp_seal_activation_value.py` | 72 passed, 3 failed | **75 passed, 0 failed** | Os 3 RED de T12/T14/T16 (tabela acima) viraram GREEN só com HTML/contexto novo — nenhuma asserção foi tocada |
| `telecom/test_whatsapp_seal_interface_sev06.py` (novo) | — (não existia) | **13 passed** (7 do fechamento original + 6 da retificação do valor monetário, ver abaixo) | Situação Não ativado no detalhe ("Não aplicável", sem alerta); valor formatado em BRL no Ativo; legado ausente mostra "Não informado"; ausência vs zero explícito (None/0,00/59,00/53,90/299,00) recortados no `<dd>` exato do campo Valor mensal; overview inicial (não-ajax) e OPERATOR distinguem Não ativado de Sem selo; catálogo via `json_script` sem segunda fonte; 4 campos novos sem `required` incondicional |
| `telecom/test_whatsapp_seal.py` + `test_phoneline_form_ui.py` + `test_seal_detail_and_listing.py` | 65 passed | **65 passed** | Sem regressão; nenhum teste alterado |
| `telecom/test_whatsapp_seal_model_domain.py` + migration + sev04_correction | 49 passed | **49 passed** | Fora de escopo, sem mudança |

**Contagem reconciliada (comando real, bateria combinada):**

```
venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_activation_value.py telecom/test_whatsapp_seal_interface_sev06.py telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/test_seal_detail_and_listing.py telecom/test_whatsapp_seal_model_domain.py telecom/test_whatsapp_seal_activation_migration.py telecom/test_whatsapp_seal_sev04_correction.py -q
  → 196 passed (75 + 7 + 65 + 49) — 0 failed, 0 error
```

RED→GREEN real desta task: 3 nodes (T12 detalhe, T14 estrutural, T16 default visual), confirmados RED antes (reexecução acima) e GREEN depois, por implementação de template/contexto — nenhum deles por enfraquecimento de asserção. Nenhuma fixture precisou de correção nesta task (os 3 nodes já estavam escritos corretamente desde SEV-03/sua correção).

**Test Strategy — comandos e resultados reais desta rodada, banco SQLite isolado, suítes sequenciais:**

```
venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_activation_value.py -q
  → 75 collected, 3 failed, 72 passed (baseline reconfirmada)
  → depois da implementação: 75 passed

venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_interface_sev06.py -v
  → 7 passed

venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/test_seal_detail_and_listing.py -q
  → 65 passed (sem regressão)

venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_model_domain.py telecom/test_whatsapp_seal_activation_migration.py telecom/test_whatsapp_seal_sev04_correction.py -q
  → 49 passed (sem regressão, fora de escopo)

venv\Scripts\python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
  → 236 passed, 1 skipped, 5 subtests passed (idêntico à baseline, sem regressão)

venv\Scripts\python.exe -m pytest config/tests/test_whatsapp_seal_report.py config/tests/test_line_inventory_report.py -k "not RealVolume" -q
  → 215 passed, 8 deselected, 10 subtests passed (idêntico à baseline — contrato de
    relatórios não ampliado, confirmado por execução: Selos continua filtrando por
    ativação, Inventário continua contando posse de selo independente de ativação)

venv\Scripts\python.exe -m pytest config/tests/test_reports_hub.py -q
  → 38 passed, 15 subtests passed (verificação adicional, mesma suíte reexecutada em
    SEV-05 por precaução; nenhuma referência a whatsapp_seal/selo quebrou)

venv\Scripts\python.exe manage.py check --settings=config.settings_dev
  → System check identified no issues (0 silenced).

venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.settings_dev
  → Detecta apenas o mesmo drift alheio pré-existente já documentado em SEV-03/04/05
    (dashboard.DailyUserAction.action_type, telecom.PhoneLine.origem) — nenhuma
    alteração desta task (nenhum campo/model novo; whatsapp_seal_monthly_value_display
    é property Python, não gera migration) aparece nesta saída.

git diff --check
  → sem erro de whitespace (avisos informativos de LF→CRLF nos arquivos tocados:
    static/js/phone-line-form.js, templates/telecom/phoneline_form.html, e os já
    modificados por SEV-03/04/05).
```

**Backend:** SQLite (pytest-django força esta engine). Nenhuma migration criada nesta task — a limitação de Postgres não exercitado (registrada em SEV-04) não se aplica a este trabalho.

**Separação explícita entre evidência de servidor e de navegador (mandado pela spec).** Todas as evidências acima são de servidor: Django test client (`admin_client.get/post`), leitura de HTML retornado, inspeção de atributos (`required`, `hidden`) no HTML gerado pelo servidor, e leitura direta do bloco `json_script`. **Nenhuma ferramenta de navegador esteve disponível neste ambiente de execução** (sem MCP de browser/devtools, sem Playwright/Selenium configurado para esta sessão) — por isso, nenhuma destas afirmações foi feita nem é feita aqui: que o JavaScript de `static/js/phone-line-form.js` executa corretamente num navegador real; que a alternância de visibilidade/obrigatoriedade funciona ao digitar/clicar; que o filtro de catálogo (categoria→plano) ou a referência de preço aparecem corretamente na tela; que o layout/contraste/fundo azul escuro/responsividade (1280/390/360) estão corretos visualmente; que a ordem de teclado/foco funciona na prática. Essa cobertura é exatamente o que a spec já reserva para SEV-07 (aceite real em navegador) — **não comprovada nem presumida nesta task**. A limitação está registrada aqui, não omitida.

**Critério de conclusão — autoavaliação:**
- Formulário: os 4 campos novos renderizados na ordem aprovada (Selo → Categoria → Plano → Situação → Valor mensal), sem `required`/`hidden` HTML incondicional; catálogo serializado com segurança via `json_script`, sem segunda fonte de dados duplicada no JS; referência de preço nunca preenche/sobrescreve o valor efetivo (JS só exibe texto, nunca escreve no input).
- Detalhe: situação, categoria, plano e valor mensal mostrados; ausência não é convertida em zero — legados ausentes mostram "Não informado"; zero explícito permitido (selo Não ativado) é exibido como "R$ 0,00", nunca omitido; confirmado por teste na fronteira exata do campo (`<dd>` do Valor mensal), não por ocorrência genérica na página. Não ativado mostra datas como "Não aplicável", sem alerta de vencimento.
- Overview/Carregar mais/OPERATOR: confirmado (não alterado) que já distinguem Não ativado de Sem selo via `seal_status`/badge compartilhado; nenhum valor financeiro, categoria ou plano foi acrescentado a essas listagens; nenhuma query nova introduzida (templates/payload ajax inalterados).
- Relatórios: nenhum contrato alterado; regressão de Selos/Inventário 100% GREEN, confirmando filtro por ativação (Selos) e posse independente de ativação (Inventário) inalterados.
- Regressão: as 3 suítes de regressão (SEL/Telecom+Timeline/Relatórios) + reports_hub permanecem 100% GREEN (618 testes/subtestes: 65+236+1skip+215+38, mais os 75+7+49 desta e das tasks anteriores do próprio escopo SEV). Nenhuma fixture precisou de correção nesta task.
- `manage.py check` limpo; `makemigrations --check --dry-run` mostra só drift alheio pré-existente; `git diff --check` limpo; nenhuma migration nova criada; nenhuma dependência nova.
- Smoke de navegador: **não realizado** — ferramenta indisponível neste ambiente; limitação registrada explicitamente, nenhum comportamento dinâmico/visual declarado como comprovado.
- Sem commit, push, deploy ou acesso a PRD nesta task.

**Estado de implantação (separado do aceite de backend/servidor):** domínio, migração, formulário/salvamento e agora interface (template/JS/detalhe/listagens) estão aceitos por evidência de servidor — sem crash, sem portão, sem gravação parcial, sem regressão. A aplicação ainda não tem **aceite completo de ponta a ponta**: isso exige navegador real (desktop/mobile, com/sem JS), que é exatamente o escopo não iniciado de SEV-07, e revisão de diff completo/matriz requisito→teste→evidência de SEV-08. Nenhuma das duas foi antecipada nem presumida concluída por esta task.

SEV-06 concluída. Próxima: SEV-07 (aceite real em navegador) — não iniciada. Parado após SEV-06, conforme mandado: sem commit, push, deploy, acesso a PRD ou dependência nova.

### 2026-10-01 — Retificação: ressalva de apresentação monetária de SEV-06

**Spec Summary.** O registro original de SEV-06 afirmou, em 4 pontos, que o valor ausente "nunca" aparece como "R$ 0,00" — frase correta sobre o caso `None`, mas que, por imprecisão de redação (não por inspeção direta), podia ser lida como "zero nunca aparece". O contrato (seção "Fluxos e validação", linha 67) já determinava desde SEV-02 que zero é valor válido e distinto para Não ativado. Esta rodada inspeciona a implementação real antes de presumir defeito, corrige a redação e acrescenta a cobertura de teste que faltava na fronteira exata (não existia nenhum teste do `<dd>` do campo "Valor mensal (R$)" com `Decimal("0.00")`).

**Gap Analysis — inspeção direta, não por relato.**

1. `PhoneLine.whatsapp_seal_monthly_value_display` (telecom/models.py): usa `if self.whatsapp_seal_monthly_value is None: return None` — comparação por identidade, não por truthiness. `Decimal("0.00")` não é `None`; cai no `return f"R$ {...:.2f}".replace(".", ",")`, produzindo a string `"R$ 0,00"`. **Confirmado correto por leitura direta, sem RED.**
2. `templates/telecom/phoneline_detail.html`: `{{ phone_line.whatsapp_seal_monthly_value_display|default:"Não informado" }}`. O filtro `default` do Django substitui apenas quando o valor é falsy (`None`, `""`, etc.). Como a property já devolve a **string** `"R$ 0,00"` (não o `Decimal` zero) antes do filtro rodar, e essa string é truthy (não vazia), o filtro nunca a substitui. Só `None` (retorno real da property para ausência) é falsy e aciona o fallback. **Confirmado correto por leitura direta, sem RED.**
3. `telecom/forms.py::clean_whatsapp_seal_monthly_value` e `PhoneLine.create_or_reuse`/`validate_seal_fields` (telecom/whatsapp_seal.py): nenhum usa `if not monthly_value`; todos usam `is None` para ausência e `< 0`/`< SEAL_MONTHLY_VALUE_ACTIVE_MIN` para as regras de sinal/mínimo. Nenhum ponto confunde `Decimal("0.00")` com ausência. **Confirmado correto, sem RED.**
4. `static/js/phone-line-form.js`: não lê nem decide nada a partir do valor do campo de valor mensal (só alterna `required`/visibilidade por selo/situação); nenhuma lógica de zero/ausência existe no JS. **Confirmado correto, sem RED.**

**Conclusão da inspeção: nenhum defeito de código.** A ressalva motivadora desta task era um relato impreciso ("nunca R$ 0,00"), não um comportamento real do sistema. Nenhum `if not valor` ou equivalente foi encontrado em nenhum dos pontos listados pelo usuário.

**Lacuna real de cobertura encontrada (não um defeito):** nenhum teste existente (nem os 7 originais de `test_whatsapp_seal_interface_sev06.py`, nem os das suítes SEL/SEV anteriores) exercitava o detalhe HTML com `whatsapp_seal_monthly_value=Decimal("0.00")`. Os testes de domínio (`test_whatsapp_seal_model_domain.py`, `test_whatsapp_seal_sev04_correction.py` etc.) provam que `Decimal("0.00")` persiste corretamente, mas nenhum provava a fronteira de apresentação (template/property) para esse valor especificamente. Essa é a lacuna real derivada e preenchida nesta rodada — não um RED de defeito.

**Implementation Plan — correção mínima aplicada:**

1. **Nenhuma mudança de lógica** em `telecom/models.py`, `telecom/whatsapp_seal.py`, `telecom/forms.py`, `templates/telecom/phoneline_detail.html` ou `static/js/phone-line-form.js` — a implementação já estava correta; alterá-la sem necessidade violaria o mandado desta task.
2. `telecom/models.py::PhoneLine.whatsapp_seal_monthly_value_display`: docstring reescrita para declarar explicitamente a distinção por `is None` e o caso de zero explícito — correção documental no próprio código, não de comportamento.
3. `telecom/test_whatsapp_seal_interface_sev06.py`: adicionados 6 nodes novos (ver Test Checklist) cobrindo a lacuna real identificada — nenhum teste existente foi alterado, reduzido ou teve asserção enfraquecida.
4. Esta fonte da verdade: 4 ocorrências da frase imprecisa "nunca R$ 0,00"/"retorna None, nunca R$ 0,00" (linhas da entrega original de SEV-06) corrigidas para "ausência não é convertida em zero; zero explícito permitido é exibido como R$ 0,00", conforme mandado.

**Test Checklist — nodes novos desta retificação (todos GREEN na primeira execução — confirmando ausência de defeito, não corrigindo um):**

| Node | Cenário | Resultado |
| --- | --- | --- |
| `test_detalhe_campo_valor_distingue_ausencia_de_zero_explicito[0-None-Não informado]` | Legado sem valor (`None`) → `<dd>` exato = "Não informado" | GREEN direto |
| `test_detalhe_campo_valor_distingue_ausencia_de_zero_explicito[1-monthly_value1-R$ 0,00]` | `Decimal("0.00")`, Não ativado → `<dd>` exato = "R$ 0,00" | GREEN direto |
| `test_detalhe_campo_valor_distingue_ausencia_de_zero_explicito[2-monthly_value2-R$ 59,00]` | `Decimal("59.00")` → `<dd>` exato = "R$ 59,00" | GREEN direto |
| `test_detalhe_campo_valor_distingue_ausencia_de_zero_explicito[3-monthly_value3-R$ 53,90]` | `Decimal("53.90")` → `<dd>` exato = "R$ 53,90" | GREEN direto |
| `test_detalhe_campo_valor_distingue_ausencia_de_zero_explicito[4-monthly_value4-R$ 299,00]` | `Decimal("299.00")` → `<dd>` exato = "R$ 299,00" | GREEN direto |
| `test_property_whatsapp_seal_monthly_value_display_distingue_ausencia_de_zero` | Property isolada (sem HTTP/template): `None`→`None`, `Decimal("0.00")`→"R$ 0,00", `Decimal("299.00")`→"R$ 299,00" | GREEN direto |

Os 5 primeiros nodes usam um helper (`_monthly_value_dd`) que recorta por regex o `<dt>`/`<dd>` exato de "Valor mensal (R$)" no HTML — não uma busca genérica de substring na página — atendendo à exigência de não aceitar uma ocorrência incidental como prova. Nenhum desses nodes foi RED em nenhum momento: a implementação já estava correta antes desta rodada; o resultado é GREEN direto, registrado como tal, sem fabricar um ciclo RED→GREEN que não ocorreu.

**Test Strategy — comandos e resultados reais desta rodada:**

```
venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_interface_sev06.py -v
  → 13 passed (7 nodes originais de SEV-06 + 6 novos desta retificação, todos GREEN)

venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_interface_sev06.py telecom/test_whatsapp_seal_activation_value.py telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/test_seal_detail_and_listing.py -q
  → 153 passed (13 + 75 + 65) — sem regressão

venv\Scripts\python.exe manage.py check --settings=config.settings_dev
  → System check identified no issues (0 silenced).

git diff --check
  → sem erro de whitespace (avisos informativos de LF→CRLF nos arquivos já
    tocados por SEV-03/04/05/06).
```

Suítes de regressão ampla (telecom/tests.py, tests_line_timeline.py, relatórios) **não foram reexecutadas nesta rodada**: a única mudança de código de produção foi uma docstring (sem alteração de comportamento/assinatura); nenhum código compartilhado por essas suítes foi tocado. Proporcional ao impacto real, conforme mandado — não repetição de suíte ampla sem justificativa.

**Compliance Report.**

- **Defeito confirmado vs. erro de redação:** nenhum defeito de código foi encontrado. A ressalva motivadora era um erro de redação no registro de SEV-06 (frase "nunca R$ 0,00" lida fora do contexto do caso `None`), não um comportamento real do sistema. As 4 ocorrências imprecisas foram corrigidas nesta fonte da verdade.
- **Cobertura existente vs. teste novo:** a distinção ausência/zero já era garantida pela implementação (property + filtro `default` operando sobre a string já formatada, não sobre o Decimal); não havia, porém, nenhum teste de HTML/detalhe exercitando `Decimal("0.00")` nessa fronteira específica — lacuna real, não defeito, preenchida por 6 nodes novos.
- **Execução real vs. evidência reaproveitada:** todos os 6 nodes novos foram executados nesta rodada (não reaproveitados de relato anterior); os demais 147 (153 − 6) foram reexecutados para confirmar ausência de regressão, não apenas citados.
- **Escopo de SEV-06 em models/domínio (item 4 do mandado):** confirmado pelo diff isolado desta task (não o diff cumulativo de SEV-04/05/06) — SEV-06 introduziu apenas a property de apresentação (`whatsapp_seal_monthly_value_display`, leitura pura, sem escrita) e a projeção do catálogo (`SEAL_CATALOG_ORDER`/`seal_catalog_entries`, mesmas 4 combinações/preços já aprovados em SEV-02, sem alteração de `validate_seal_fields`, de `SEAL_CATALOG_COMBINATIONS` nem de obrigatoriedade). Nenhuma regra de domínio, migration ou validação foi alterada por SEV-06; confirmado, não apenas classificado por suposição.
- Sem migration, alteração de contrato, dependência nova, commit, push, deploy ou PRD nesta retificação.
- Parado antes de SEV-07; aceite visual/JS continua pendente, sem alegação de comprovação por test client ou leitura de código.

### 2026-10-01 — SEV-07 concluída: aceite real em navegador e validação Postgres

**Spec Summary.** Objetivo desta task: aceite visual e funcional real da evolução do selo em navegador real (não test client), nas larguras 1280/390/360, com e sem JavaScript, cobrindo salvamentos reais, validação monetária, transições, legado, operação independente, consumidores e relatórios — e, separadamente, a validação da migration 0022 em Postgres real descartável (pendência explícita deixada por SEV-04). Relatório completo, matriz requisito→cenário→evidência→resultado→limitação e logs em `docs/superpowers/evidence/SEV-07/` (`report.md`, `migration-postgres.log`, `screenshots/`, `results_*.json`).

**0. Preparação segura.** `git status`/`git diff --stat` conferidos no início: nenhum trabalho de terceiros em andamento; nenhum `stash`/`reset`/`checkout` usado. Ferramentas reais identificadas: Docker (daemon ativo, containers pré-existentes `lineops-db` porta 5433 e `postgres`/pgvector porta 5432 — não tocados), Google Chrome 151.0.7922.109 instalado localmente, Playwright 1.63.0 (pacote npm global) e Node.js v24.14.0. Nenhuma ferramenta de navegador MCP/DevTools estava registrada nesta sessão; Playwright com o Chrome real instalado foi usado como alternativa explicitamente autorizada pelo pedido. Ambiente de dados: container Docker descartável `sev07-disposable-pg` (postgres:15.8, porta 55432, banco/usuário `sev07`, credenciais descartáveis), criado nesta task e removido ao final. Servidor da aplicação: `runserver 127.0.0.1:8017 --noreload` contra esse Postgres, via variáveis de ambiente de processo (`.env` e `config/settings*.py` não foram alterados).

**1. Dataset e migration.** Dataset construído via scripts Python diretos (fora da aplicação) cobrindo todos os cenários pedidos: sem selo; não ativado valor zero/positivo; ativo com datas válidas e vencimentos +8/+7/+1/hoje/-1; as 4 combinações do catálogo; linha alocada (2 operadores com escopos distintos); 2 registros "legado migrado" (criados no estado anterior à migration 0021, com a migration real 0021→0022 executada via `call_command`, não substituídos por fixture ORM pós-migração); 1 registro logicamente excluído (incluído também na prova de migration). Validação Postgres real da migration 0022 (script dedicado, ver `migration-postgres.log`): forward, backfill (incluindo excluídos logicamente e legado inconsistente sem e-mail/pagamento) e reversão exercitados em banco descartável isolado — **100% das asserções passaram**, preservação dos 5 campos antigos comprovada por leitura SQL crua pós-reversão. Esta é a pendência de Postgres deixada aberta por SEV-04 (lá só SQLite havia sido exercitado); **está resolvida nesta task**.

**Anomalia de dataset encontrada e investigada (não é defeito de produto — ver `report.md` seção 4):** linhas criadas via ORM direto (fora da aplicação) no script de montagem do dataset tiveram categoria/plano/valor persistidos vazios apesar de passados explicitamente, e 3 linhas tiveram a situação forçada para ACTIVE apesar de criadas como NOT_ACTIVATED. Múltiplas tentativas de reprodução isolada (mesma sequência de migração + criação, em processos novos) não reproduziram o problema; busca no código por mecanismos capazes de causar esse efeito (`signals.py`, `save()`, `.update()` em massa) não encontrou nenhum no caminho de produção — os únicos usos de `.update()` em massa sobre `PhoneLine` existem em arquivos de teste. Classificada como artefato da ferramenta de setup de dados, não como defeito do produto, porque todos os caminhos reais da aplicação exercitados nesta mesma task (formulário via navegador, criação e edição) persistiram esses mesmos campos corretamente em 100% dos casos. Linhas corrigidas via `UPDATE` direto antes de continuar os testes; nenhuma correção de código de aplicação foi feita porque nenhum defeito de aplicação foi confirmado.

**2/3. Aceite do formulário no navegador real.** Larguras 1280/390/360, com e sem JavaScript, via Playwright controlando Chrome real (headless — limitação explícita registrada, ver `report.md` seção 6). Confirmados por medição real do motor de renderização (não por leitura de código): ordem Selo→Categoria→Plano→Situação→Valor mensal (posição vertical dos campos); ausência de overflow horizontal (`document.documentElement.scrollWidth == clientWidth`) nas 3 larguras × com/sem JS; fundo `rgb(2, 6, 23)` (azul escuro) em todos os casos; catálogo filtra categoria/plano dinamicamente por selo (JS); referência de preço exibida separada do valor efetivo, que permanece vazio ao escolher plano; troca de tipo invalida apenas a seleção incompatível e preserva o valor digitado; Não ativado oculta o bloco de datas (JS); detalhe do legado mostra "Não informado" e nunca "R$ 0,00" para valor ausente. Sem JS: todos os controles permanecem acessíveis (o bloco de detalhes nunca é ocultado sem JavaScript, por construção do template); combinação válida pode ser escolhida e salva; combinação incompatível (META_ONE + categoria de Pessoa Física) retorna erro do servidor sem gravação parcial, confirmado por consulta direta ao banco.

**4. Salvamentos reais.** Todos os 5 blocos do pedido (A–E) exercitados via navegador real, com confirmação por reabertura da página (GET pós-save) e, nos casos de transição afetados pela anomalia do dataset, reexecutados após a correção (`S6_redo`/`S7_redo`/`S11_redo`): Não ativado salva R$0,00 e valor positivo com datas nulas; Ativo aceita datas iguais e exige valor positivo (zero e datas invertidas rejeitados); Não ativado→Ativo exige datas e valor (rejeitado corretamente, pela causa certa após a correção); Ativo→Não ativado limpa datas ao salvar e preserva categoria/plano/valor/e-mail/pagamento; Com selo→Sem selo limpa os 8 detalhes; legado exige preencher categoria/plano/valor para salvar com selo e permite salvar sem eles ao remover o selo; Liberar linha legada não exige completar o selo; editar somente o valor do selo em linha alocada preserva status (ALLOCATED), vínculo (employee) e não altera histórico operacional.

**5. Valor monetário e erros.** 15 casos diretos + 9 sub-checagens de preservação de entrada, todos via navegador real (campo de texto, não `input[type=number]`): 0,00/0,01/299,00 (vírgula e ponto) aceitos nos estados aplicáveis; -0,01, -0,00, 299,01 rejeitados; separador de milhar, símbolo de moeda, notação científica, NaN/Infinity e 3+ casas decimais rejeitados; ausência com selo rejeitada; toda rejeição preserva a entrada digitada no campo para revisão, sem mensagem obrigatória contraditória. Campo exato do detalhe confirmado: `None`→"Não informado", zero explícito→"R$ 0,00", 59,00→"R$ 59,00" (já comprovado em SEV-06, reconfirmado aqui pela via do navegador real no cenário de legado).

**6. Consumidores.** Overview distingue "Não ativado" de "Sem selo"; nenhum valor financeiro novo detectado na listagem; "Carregar mais" real adicionou linhas de fato (10→20, clique real no botão); escopo OPERATOR comprovado com 2 operadores reais — cada um vê apenas sua própria linha alocada e não enxerga a do outro; hub de Relatórios confirmado ADMIN-only (200 para admin, 403 para operator) via navegador real. Smoke de relatórios via navegador real: Selos exclui linhas Não ativado (sem data de ativação) e inclui linhas Ativo no período; Inventário conta posse de selo independentemente de ativação; nenhuma coluna/total financeiro novo em nenhum dos dois.

**7. Evidências.** Guardadas em `docs/superpowers/evidence/SEV-07/`: `report.md` (relatório completo com a matriz requisito→cenário→evidência→resultado→limitação), `migration-postgres.log`, 11 screenshots reais (`screenshots/`), 7 arquivos `results_*.json` com o resultado estruturado de cada cenário (pass/fail + detalhe). Nenhum defeito de aplicação foi encontrado nesta task — a única anomalia observada (categoria/plano/valor/situação em criações diretas via ORM) tem causa não determinada; a investigação em `report.md` seção 4 não comprova origem na ferramenta nem exclusão de defeito de produto. Ver ressalvas documentais abaixo.

**8. Verificação proporcional.** Nenhum código de aplicação foi alterado nesta task (relatado pelo executor; `git status` semelhante não comprova identidade de conteúdo, e esta spec também foi atualizada); por isso as suítes pytest de regressão (516+ testes/subtestes de SEV-04/05/06) não foram reexecutadas — reaproveitadas com referência precisa, conforme instrução de proporcionalidade. `manage.py check` limpo; `git diff --check` limpo (mesmos avisos informativos de LF/CRLF pré-existentes). Container `sev07-disposable-pg` e o `runserver` desta task foram encerrados ao final; nenhum recurso pré-existente foi tocado.

**Compliance Report.**

- **Aceite visual/funcional em navegador real:** concluído. Todas as verificações pedidas nas seções 2–6 do pedido foram exercitadas via Chrome real controlado por Playwright (headless), com screenshots e medições reais de layout — não por HTML de test client nem por leitura de código.
- **Validação de migration em Postgres:** concluída nesta task, separadamente do aceite visual. Forward/backfill/reversão comprovados em banco descartável isolado, resolvendo a pendência deixada por SEV-04.
- **Prontidão para implantação:** ainda dependente da revisão SEV-08 (diff completo, matriz requisito→teste→evidência consolidada, plano de rollback). SEV-07 comprova o comportamento real da aplicação; não substitui a revisão de entrega.
- **Limitações explícitas e abertas:** navegador headless (não headed/interativo — engine real, sem observação visual humana em tempo real durante a execução); causa raiz da anomalia de dataset do §4 não isolada (não bloqueia o aceite, pois o caminho real da aplicação foi comprovado correto); exportação CSV/XLSX dos relatórios não exercitada (fora do escopo do pedido, que pede apenas smoke).
- Sem commit, push, deploy, acesso a PRD ou instalação de dependência não justificada nesta task.

SEV-07 concluída. Próxima: SEV-08 (revisão e preparação de entrega) — não iniciada. Parado antes de SEV-08, conforme mandado.


### 2026-10-01 — Ressalvas documentais ao aceite SEV-07

**Spec Summary / Gap Analysis.** Retirada a atribuição conclusiva da anomalia à ferramenta: causa não determinada. A ausência de reprodução e de mecanismo identificado não prova a origem do problema. Report.md retificado preservando os resultados capturados.

**Implementation Plan / Test Checklist.** Reconciliar inventário de linhas/campos corrigidos por UPDATE e alcance dos cenários repetidos. O relato identifica pk=8,9,19 para situação; não comprova inventário completo das demais correções. S6_redo/S7_redo/S11_redo constam no JSON, mas S11_redo_value_updated tem ok=false, divergente do PASS no relatório. Verificar assertion/esperado antes de aceitar; não converter o JSON para GREEN. Fechamento de SEV-07 ressalvado por essa pendência de evidência, sem invalidar automaticamente os ensaios independentes.

**Test Strategy.** Leitura direta de report.md e results_saves_redo.json; não houve reexecução funcional, visual ou de migration. Não atribuir causa ao false somente pelo detail mostrar 65.00.

**Compliance Report.** Spec e report.md alterados apenas para precisão documental. git status não comprova conteúdo intacto em arquivos previamente modificados/não rastreados; atualização da spec explicitada. Sem alteração de código, JSONs, screenshots, testes, stage, commit, push ou deploy. Próxima ação: reconciliar evidências pendentes antes de fechamento irrestrito de SEV-07/entrega.

### 2026-10-01 — SEV-07: reconciliação das evidências pendentes (rodada 2)

**Spec Summary.** Resolver, com evidência nova e identificada (não por edição dos artefatos antigos), as 5 ressalvas documentais registradas acima: divergência `S11_redo_value_updated`; alcance real do `UPDATE` de correção do dataset; proporção das reexecuções; limite da alegação "git status idêntico"; critério de fechamento. `git status`/`git diff --stat` conferidos no início; nenhum `stash`/`reset`/`checkout` usado; nenhum JSON/log/screenshot histórico foi editado.

**Gap Analysis.**

1. **S11 — causa localizada e demonstrada.** Assertion em `scratchpad/sev07_saves_redo.js:103` exigia igualdade estrita a `"65,00"`; o valor lido (`inputValue` do campo de edição, pós-GET) é `"65.00"`. Causa: `PhoneLineForm` declara `whatsapp_seal_monthly_value` como `CharField`, sem `prepare_value`/formatação customizada; na edição, Django popula o `initial` com o `Decimal` real do model e o widget o converte via `str()`, que usa ponto. O contrato (seção "Entrada monetária") trata `59,00`/`59.00` como formas de entrada equivalentes — não há exigência de que o campo de **edição** redisplay-e com vírgula (a exigência de formato `R$ XX,XX` é do **detalhe**, já comprovada). Prova de round-trip nesta rodada: resubmeter o valor exibido sem alterar salvou com sucesso e preservou o mesmo Decimal. **Classificação: ajuste de assertion do script, não defeito de aplicação.**
2. **Dataset — lacuna real encontrada.** `sev07_fix_dataset.py` corrigiu apenas categoria/plano/valor; nunca tocou `whatsapp_seal_activation_status`. pk=8, pk=9 e pk=19 (criados `NOT_ACTIVATED`, corrompidos para `ACTIVE`) permaneceram `ACTIVE` após o "fix" — não declarado antes. Tabela completa de 19 linhas (pretendido/observado/corrigido, com fonte de cada valor) em `docs/superpowers/evidence/SEV-07/dataset-anomaly-reconciliation.md`. Impacto delimitado: apenas S6 (original) e S6_redo dependiam de pk=8 estar genuinamente `NOT_ACTIVATED`; nenhum outro cenário do aceite depende do `activation_status` desses 3 PKs (tabela de impacto no mesmo arquivo).
3. **S6 original/redo — achado adicional.** Ambas as tentativas anteriores rodaram com JavaScript ligado; o próprio `phone-line-form.js` torna os campos de data `required` quando a situação é `ACTIVE`, e o navegador bloqueia o `submit` nativamente (HTML5) antes de qualquer requisição de rede — **nenhum POST real chegou ao servidor** nessas duas tentativas. Isso não havia sido distinguido do bloqueio de servidor.
4. **Causa raiz da anomalia de dataset:** permanece **não determinada**. Dado novo, não conclusivo, registrado nesta rodada: reconstrução do dataset mínimo sem `runserver` concorrente não reproduziu a anomalia — consistente com, mas não demonstrativo de, interação entre processos concorrentes.
5. **git status vs. conteúdo:** a lista de caminhos do `git status --short` capturada automaticamente pelo ambiente no início da sessão (antes de qualquer ação de SEV-07) é idêntica à lista atual, exceto pela pasta de evidências nova — comparação de caminhos verificável de forma independente. O conteúdo byte-a-byte dos arquivos já listados como `M`/`??` segue sem uma linha de base numérica (`git diff --stat`) anterior a SEV-07 para comparação — mantido como relato do executor nesse nível específico, não como prova independente.

**Implementation Plan.** Executado: (a) novo container Postgres descartável `sev07-recon-pg` (porta 55433, banco `sev07recon`, distinto do removido e dos pré-existentes `lineops-db`/`postgres`); (b) dataset mínimo novo, cada registro verificado imediatamente após a criação; (c) S6 reexecutado com premissa `NOT_ACTIVATED` genuína, em duas camadas (cliente e servidor, comprovadas separadamente); (d) S7 reexecutado em linha nova para reforçar a prova (resultado consistente com `S7_redo` anterior, que já não estava contaminado); (e) S11 reexecutado com `activated_at` de fixture preenchido (não vazio→vazio) e prova de round-trip do valor. Nenhum código de aplicação alterado.

**Test Checklist — nodes desta reconciliação:**

| Arquivo | Nodes | Resultado |
| --- | --- | --- |
| `results_s6_s7_s11_reconciliation.json` | 19 | 18 PASS, 1 FAIL por limitação de extração do próprio script (texto do erro capturado vazio por timing) — superado pelo node seguinte |
| `results_s6_nojs_server_rejection.json` | camada cliente + camada servidor de S6 | PASS — mensagem de erro real do servidor capturada: "Selo ativo exige valor mensal maior que zero. Ativação: Data de ativação do selo é obrigatória. Vencimento: Data de vencimento do selo é obrigatória." |
| `results_s6_error_message.json` | tentativa intermediária de captura de erro | registra a mesma limitação de extração (texto vazio); mantido como histórico do processo de depuração, superado pelo node acima |

**Matriz pendência → causa → ação → evidência → resultado → limitação:**

| Pendência | Causa comprovada ou não determinada | Ação | Nova evidência | Resultado | Limitação remanescente |
| --- | --- | --- | --- | --- | --- |
| `S11_redo_value_updated` ok=false | **Comprovada**: assertion exigia formato não respaldado pelo contrato; redisplay é representação Decimal equivalente | Assertion corrigida; round-trip comprovado | `results_s6_s7_s11_reconciliation.json` | PASS | Nenhuma — causa demonstrada e código não alterado porque não é defeito |
| Alcance do `UPDATE` de correção do dataset | **Comprovada parcialmente**: fix nunca tocou `activation_status`; pk=8,9,19 ficaram `ACTIVE` indevidamente | Tabela completa de 19 linhas; S6 reexecutado com premissa correta | `dataset-anomaly-reconciliation.md` | S6 PASS reexecutado; demais cenários confirmados não contaminados | Container antigo já removido — tabela depende de saídas já capturadas na sessão, não de nova consulta ao banco antigo |
| Causa raiz da anomalia de categoria/plano/valor vazios | **Não determinada** | Nova tentativa de reprodução (sem runserver concorrente) | `dataset-anomaly-reconciliation.md` seção 3 | Não reproduzida desta vez (dado não conclusivo) | Causa continua aberta; não reclassificada |
| "git status idêntico" como prova de conteúdo | **Parcialmente comprovada**: caminhos sim, conteúdo não | Comparação com baseline capturada pelo ambiente no início da sessão | Este registro + `report.md` | Lista de caminhos confirmada idêntica | Conteúdo byte-a-byte sem linha de base anterior para comparação |

**Test Strategy.** `manage.py check` limpo; `git diff --check` limpo (mesmos avisos de LF/CRLF); nenhuma suíte pytest reexecutada (nenhum código de aplicação alterado nesta reconciliação, apenas scripts de scratchpad e evidência). Reexecução funcional via navegador real para S6/S7/S11; demais cenários reaproveitados com justificativa de independência (tabela de impacto), não por rotina.

**Compliance Report.**

- Divergência S11: reconciliada, causa demonstrada, `false` histórico preservado, nova evidência com assertion corrigida.
- Dataset: reconciliado por completo com tabela de 19 linhas; lacuna real (activation_status de pk=8,9,19) encontrada e seu impacto delimitado a S6/S6_redo; S6 reexecutado com premissa válida.
- Anomalia: permanece causa não determinada, sem reclassificação indevida.
- git status: reconciliado — caminhos comprovados, conteúdo mantido como relato do executor.
- **Critério de fechamento do pedido de reconciliação atendido:** divergência S11 reconciliada e comportamento atual comprovado; cenários potencialmente afetados pelo UPDATE (S6) têm evidência válida nova; limitações históricas remanescentes (causa da anomalia não determinada, navegador headless, smoke de relatórios, exportações não exercitadas) permanecem explícitas, sem afirmação causal indevida.
- Container `sev07-recon-pg` e `runserver 127.0.0.1:8018` desta rodada encerrados ao final; `sev07-disposable-pg` da rodada anterior já estava removido; recursos pré-existentes (`lineops-db`, `postgres`/pgvector) confirmados intactos antes e depois.
- Sem commit, push, deploy, acesso a PRD ou alteração de contrato nesta reconciliação.

SEV-07 reconciliada e concluída, sem ressalva bloqueante. Limitações explícitas não bloqueantes permanecem abertas (listadas acima). Parado antes de SEV-08.

### 2026-10-01 — SEV-08 concluída: revisão final e preparação de entrega

**0. Workspace e escopo.** `git status`/`git branch --show-current`/`git rev-parse HEAD` conferidos no início: branch `feat/phone-line-whatsapp-seal`, HEAD `73b955b`. Nenhum `stash`/`reset`/`checkout`/`revert` usado nesta task; nenhum stage/commit/tag/versão/push realizado.

Lista explícita de arquivos pertencentes a SEV (rastreados modificados + novos não rastreados):

```
Rastreados (M):
  static/js/phone-line-form.js
  telecom/forms.py
  telecom/models.py
  telecom/test_phoneline_form_ui.py
  telecom/test_whatsapp_seal.py
  telecom/views.py
  telecom/whatsapp_seal.py
  templates/telecom/phoneline_detail.html
  templates/telecom/phoneline_form.html

Novos (??):
  docs/superpowers/evidence/SEV-07/ (report.md, dataset-anomaly-reconciliation.md,
    migration-postgres.log, 11 screenshots, 7 results_*.json)
  docs/superpowers/specs/2026-09-30-whatsapp-seal-activation-value-design.md (esta fonte da verdade)
  telecom/migrations/0022_phoneline_whatsapp_seal_activation_status_and_more.py
  telecom/test_whatsapp_seal_activation_migration.py
  telecom/test_whatsapp_seal_activation_value.py
  telecom/test_whatsapp_seal_interface_sev06.py
  telecom/test_whatsapp_seal_model_domain.py
  telecom/test_whatsapp_seal_sev04_correction.py
```

Migrations, testes, spec e evidências necessárias estão todos incluídos nessa lista — confirmado por inspeção direta, não presumido.

**Explicitamente excluídos da lista (alheios a SEV, preservados intactos, não tocados nesta task):**

- `docs/superpowers/specs/2026-09-10-line-daily-action-audit-design.md` (M) — spec de uma evolução anterior (auditoria de ações diárias), com uma seção de evidência de entrega em produção de 2026-09-14 acrescentada por outro trabalho; conferido por `git diff`, não tem nenhuma relação textual ou de código com o selo WhatsApp. Trabalho de terceiro, preservado sem alteração.
- `.clinerules/`, `.cursor/`, `.github/copilot-instructions.md`, `.opencode/`, `.superpowers/`, `.windsurf/`, `AGENTS.md` — arquivos/diretórios de configuração de ferramentas de IDE/agente, não pertencentes a esta feature.
- `docs/specs/whatsapp-orchestrator-v1.md` — spec de outra iniciativa (orquestrador de WhatsApp), não relacionada ao selo; nome semelhante causou conferência extra, confirmado por leitura que é assunto distinto.

Nenhum arquivo temporário, credencial, banco ou configuração pessoal identificado na árvore de trabalho. **Recuperação integral do incidente histórico de stash (retificação de SEV-04) não é certificada nesta task** — permanece exatamente como registrado em "Ressalvas documentais da retificação SEV-04": preservação integral não verificável retrospectivamente, sem baseline numérica suficiente. Esta rodada não tentou produzir essa prova retroativamente (nenhum novo stash/reset/checkout executado).

**1. Revisão de contrato e domínio.** Inspeção direta de `telecom/whatsapp_seal.py::validate_seal_fields` (109–222) e `telecom/models.py::PhoneLine.clean/create_or_reuse` (202–215, 260–411) confirma, sem exceção:

- Sem selo: `clear_seal_fields` limpa os 9 campos (seletor + 8 detalhes); `normalize_seal_fields` aciona isso incondicionalmente quando `whatsapp_seal` vazio.
- Não ativado: datas nulas obrigatórias (rejeita datas preenchidas), indicador neutro (`compute_seal_status`), valor 0,00–299,00 (`SEAL_MONTHLY_VALUE_NOT_ACTIVATED_MIN = 0.00`, `SEAL_MONTHLY_VALUE_MAX = 299.00`).
- Ativo: datas obrigatórias, vencimento ≥ ativação (checagem incondicional preservada), valor 0,01–299,00 (`SEAL_MONTHLY_VALUE_ACTIVE_MIN = 0.01`).
- Situação ausente com selo é rejeitada (`if not activation_status: errors[...]`); nenhum caminho de `PhoneLine.save()` existe (método removido na retificação de SEV-04) — `save()` comum nunca infere ACTIVE.
- Categoria/plano/e-mail/pagamento obrigatórios com selo, incondicionalmente — confirmado linha a linha, sem portão por campos vazios.
- As 4 combinações do catálogo (`SEAL_CATALOG_COMBINATIONS`, derivada de `SEAL_CATALOG_ORDER`) validadas por `(seal, category, plan) not in SEAL_CATALOG_COMBINATIONS` — token desconhecido e combinação cruzada rejeitados pela mesma checagem, no servidor (`PhoneLine.clean`/`create_or_reuse`, nunca só no JS).
- Referências de preço (`SEAL_PRICE_REFERENCE_LABELS`) usadas apenas por `seal_catalog_entries()`/JS para exibição; nenhuma função de validação ou persistência as lê.
- `None` (ausência) e `Decimal("0.00")` (zero explícito) distintos em todos os pontos: `validate_seal_fields` usa `monthly_value is None`; `whatsapp_seal_monthly_value_display` usa `is None`; `parse_seal_monthly_value` retorna `None` só para string vazia.
- Transições: Ativo→Não ativado limpa só as datas (`normalize_seal_fields`); qualquer estado→Sem selo limpa os 9 campos; nenhuma transição toca `status`/`activated_at`/vínculo/histórico (confirmado por grep: nenhuma referência a esses campos em `whatsapp_seal.py` ou nos métodos de selo de `models.py`).
- Nenhum bypass por campos vazios, `pk` existente ou "compatibilidade" encontrado em `PhoneLineForm`/`PhoneLineUpdateForm`/`create_or_reuse` — os dois mecanismos desse tipo (portão de campos vazios, fallback de `save()`) foram removidos na retificação de SEV-04 e não reaparecem no código atual (confirmado por leitura completa, não só grep).
- Nenhum `full_clean` global em `save()`: `PhoneLine` não tem `save()` próprio; `SIMcard.save()` (pré-existente, não relacionado a selo) só normaliza `carrier`.
- Nenhuma mudança indevida em `status`/`activated_at`/vínculo/histórico operacional: `PhoneLineUpdateView.form_valid` e `create_or_reuse` só tocam esses campos pelos caminhos já existentes (alocação/liberação), inalterados por esta feature — confirmado por leitura de `telecom/views.py` linhas 619–713.

Acoplamento observado, registrado como observação não bloqueante (não executado nesta task): `validate_seal_fields` concentra 9 parâmetros posicionais-nomeados e mistura validação de catálogo com validação de fronteiras monetárias e de datas; uma extração futura (ex.: validador de catálogo separado do validador de fronteiras) reduziria o tamanho da função, mas qualquer refatoração agora exigiria re-provar os 137 nodes que dependem dela — fora de escopo de SEV-08, proposta apenas como observação.

**2. Forms, serviço e segurança.**

- `PhoneLineForm.Meta.fields`/`PhoneLineUpdateForm.Meta.fields` (telecom/forms.py:114–128, 316–331): os 4 campos novos presentes nos dois, idênticos exceto `status`/`employee` exclusivos de Update — contrato compartilhado confirmado.
- Normalização antes do parsing: `full_clean()` (linhas 156–173) zera os 8 detalhes (Sem selo) ou as 2 datas (Não ativado) na cópia do `QueryDict`, **antes** de `super().full_clean()` rodar o parser de cada campo — confirmado pela ordem de execução no código, não apenas pelo comentário.
- Validação monetária textual e Decimal: `parse_seal_monthly_value` (regex `^\d+([.,]\d{1,2})?$`, aplicado ao texto já despojado de espaços) rejeita textualmente qualquer sinal — inclusive `-0,00` — antes de qualquer conversão para Decimal; `clean_whatsapp_seal_monthly_value` (forms.py:175–184) captura só `ValueError`, nunca mais amplo.
- Ausência de `ValueError` por erros em campos inexistentes: todos os 4 campos novos existem em `Meta.fields` dos dois forms — a causa raiz do crash da retificação de SEV-04 (`Model.clean()` não filtrado por `exclude`, erro em campo ausente do form vira `ValueError`) está estruturalmente eliminada, não suprimida. Confirmado por reexecução: `PhoneLineForm(data={"whatsapp_seal": "META_ONE", ...}).is_valid()` não levanta `ValueError` nesta rodada (reconfirmado pela suíte completa, 0 erros de coleta/execução).
- Mensagens sem duplicação/contradição: `_post_clean` (forms.py:186–210) remove a mensagem "obrigatório" quando já há erro de formato próprio no mesmo campo, preservando as demais mensagens — lógica inspecionada linha a linha, sem efeito colateral em campos sem erro de formato.
- `create_or_reuse`: validação (via instância descartável `seal_probe`, nunca persistida) ocorre **antes** de qualquer `objects.create()`/`.save()`, dentro do mesmo `transaction.atomic()` que já envolvia o método (models.py:327–411) — sem gravação parcial.
- Chamadores antigos sem selo (`telecom/admin.py::SIMcardAdmin.save_model` via `SIMcardCreateView.form_valid`, `core/services/telephony_use_case.py`) confirmados por leitura: nenhum envia `whatsapp_seal`; os 4 kwargs novos têm default `""`/`None`, portanto compatíveis sem alteração.
- `save(commit=False)`: `PhoneLineForm.save` (linhas 269–303) delega a `super().save(commit=False)` quando `not commit` e a instância não tem `pk` — nenhuma escrita; para edição, delega sempre a `super().save(commit=commit)` do ModelForm padrão, que já respeita `commit=False` nativamente.
- Liberar e demais operações independentes em legados incompletos: `PhoneLineUpdateView.post` (views.py:626–647) processa `action=release_line` **antes** de instanciar/validar o form — confirmado pela ordem do código, reforçado pela evidência SEV-07 S10a (navegador real, legado incompleto, Liberar sem erro).
- Permissões e escopo atuais: nenhuma linha de `RoleRequiredMixin`/`allowed_roles` foi tocada por esta feature (confirmado por diff vazio em `core/mixins.py`, não modificado); hub de Relatórios ADMIN-only confirmado por SEV-07 (`reports_hub_admin_allowed`/`reports_hub_operator_denied`) e não aplicado à navegação Telecom (`PhoneLineDetailView`/`TelecomOverviewView` usam `RECONNECT_ALLOWED_ROLES`, inalterado).
- Catálogo serializado com segurança: `{{ seal_catalog_entries|json_script:"seal-catalog-data" }}` (phoneline_form.html:167) — `json_script` do Django escapa HTML/XSS; `static/js/phone-line-form.js` lê exclusivamente esse bloco (`JSON.parse(catalogDataEl.textContent)`), sem nenhuma segunda fonte de catálogo hardcoded no JS (confirmado por leitura completa do arquivo, 168 linhas).
- Nenhum dado financeiro novo em listagens/payloads fora do contrato: `TelecomOverviewView._handle_ajax_request` (views.py:1009–1055) só adiciona `whatsapp_seal_display`/`seal_status` ao payload `main` — nenhuma referência a `whatsapp_seal_monthly_value`/categoria/plano; confirmado por grep negativo no arquivo e por SEV-07 (`overview_no_financial_value_leak` PASS).

**3. Migration e rollback.** Migration 0022 lida por completo no grafo real (`dependencies = [('telecom', '0021_...')]`, HEAD atual): 4 `AddField` + 1 `RunPython`. Backfill (`backfill_activation_status`) usa `apps.get_model` (modelo histórico) e `.update()` em massa, sem `full_clean`/domínio atual; `exclude(whatsapp_seal="")` classifica só quem tem selo como `ACTIVE`; categoria/plano ficam no default `""` do `AddField` (não tocados pelo backfill) e valor fica `null` (default do campo). Como `SoftDeleteManager` não declara `use_in_migrations`, o modelo histórico usa o manager padrão (`all_objects`-equivalente), incluindo linhas com `is_deleted=True` — confirmado pelo comentário do próprio arquivo e pelo teste dedicado. Reversão: `RunPython.noop` + reverse padrão de `AddField` (remove as 4 colunas); nenhuma alteração aos 5 campos antigos de selo em nenhum sentido. Nenhum drift alheio (`PhoneLine.origem`, `dashboard.DailyUserAction.action_type`) incorporado — confirmado nesta rodada por `makemigrations --check --dry-run` (ver Test Strategy): só esses dois drifts pré-existentes aparecem, nada da migration 0022.

Validação Postgres real (forward/backfill/reversão/idempotência de reaplicação) consta em `docs/superpowers/evidence/SEV-07/migration-postgres.log`, lido nesta task — não apenas citado. Confirma preservação exata dos 5 campos antigos por leitura SQL crua pós-reversão, inclusão de registro logicamente excluído no backfill, e legado inconsistente (sem e-mail/pagamento) classificado sem "corrigir" dados ausentes. **Não é alegado aqui como comprovação adicional de Postgres** além do que SEV-07 já registrou; esta task leu a evidência existente, não reexecutou o script Postgres.

Plano operacional (preparado, não executado nesta task):

1. **Backup.** Backup completo do banco de produção antes de aplicar 0022 (dump lógico, mesma prática já usada em entregas anteriores — ver seção 8 da spec de auditoria de ações diárias, não executado aqui).
2. **Conferência `migrate --plan`.** Construir/identificar a imagem nova, que contém a migration 0022, sem colocá-la atendendo tráfego. Executar `manage.py migrate --plan` com essa imagem e configuração do ambiente para conferir o plano completo, incluindo outros apps. Não usar apenas `migrate telecom --plan` como prova de ausência de pendências globais. Nenhuma operação inesperada deve ser aplicada sem análise.
3. **Ordem segura.** Após backup de banco/configuração/imagem anterior, suspender escritas durante a janela de migration e troca da aplicação; aplicar 0022 usando um container pontual da imagem nova e só então iniciar essa imagem atendendo tráfego. Isso evita registros com selo criados pelo código antigo depois do backfill e antes da troca. Confirmar conclusão da migration antes da publicação. Código novo com schema antigo pode falhar por coluna inexistente no banco; isso não é o ValueError de fronteira ModelForm anterior. Não confundir os dois mecanismos.
4. **Verificações pós-implantação.** Checar (consulta direta, não pela aplicação): contagem de linhas com `whatsapp_seal != ''` todas com `whatsapp_seal_activation_status = 'ACTIVE'`; contagem de linhas sem selo com os 4 campos novos vazios/nulos; nenhuma linha com `whatsapp_seal_monthly_value` preenchido antes da primeira edição pós-deploy (confirma ausência de backfill financeiro inventado); `manage.py check` e um smoke de criação/edição real de uma linha de teste (não um registro de produção real) com e sem selo.
5. **Rollback de aplicação preservando dados.** Manter as quatro colunas novas evita perda por reversão do schema, mas não garante compatibilidade funcional. Conferência direta de `git show 73b955b:telecom/whatsapp_seal.py`: o validador antigo exige ativação/vencimento para qualquer selo e o indicador antigo retorna “Sem selo” se não há vencimento. Logo registros NOT_ACTIVATED, válidos na versão nova, podem ficar impossíveis de editar com selo na antiga e ser apresentados incorretamente. A alegação anterior de que esse risco só existiria numa versão intermediária hipotética está retirada. Antes de voltar à imagem anterior, suspender escritas e avaliar dados criados/alterados desde o deploy; priorizar correção para frente ou manter fluxos incompatíveis indisponíveis até plano explícito. Não inventar datas/valores nem restaurar dump automaticamente. Reverter migration remove situação/categoria/plano/valor e não é procedimento rotineiro. Rollback exige verificação operacional e funcional própria; a preservação das colunas, sozinha, não autoriza afirmar segurança integral.


**4. Auditoria das evidências SEV-07.** Lidos diretamente nesta task: `report.md` (íntegro, por seções via grep + leitura de trechos-chave), `dataset-anomaly-reconciliation.md` (íntegro), `migration-postgres.log` (íntegro), `results_s6_s7_s11_reconciliation.json`, `results_s6_nojs_server_rejection.json`, `results_saves_redo.json`. Confirmado:

- O `false` histórico de `S11_redo_value_updated` permanece preservado em `results_saves_redo.json` (`"ok": false, "detail": "valor apos edicao=65.00"`) — não foi editado.
- Causa da divergência rastreável e demonstrada: `PhoneLineForm` declara `whatsapp_seal_monthly_value` como `CharField`; no redisplay de edição, o widget usa `str(Decimal)` (formato `65.00`), não a formatação `R$ 65,00`; o contrato trata `.`/`,` como formas de entrada equivalentes — a assertion antiga exigia vírgula no campo de **edição**, quando a exigência de formato `R$ XX,XX` do contrato é especificamente do **detalhe**, já comprovado por outro teste.
- Novo `S11` (`results_s6_s7_s11_reconciliation.json`, nodes `S11_detail_shows_65_00`, `S11_roundtrip_resubmit_unchanged_value_still_valid`) prova Decimal persistido (R$ 65,00 no detalhe), formato de redisplay explicado (não é defeito) e round-trip (resubmeter o valor exibido sem alteração salva com sucesso).
- `activated_at` foi preservado **com valor preenchido**: `S11_activated_at_preserved_non_empty` usa fixture com `activated_at` real (`15/08/2026 10:30`, não vazio→vazio como o `S11_redo` original) — confirmado como teste significativo, não trivial.
- `S6` começou genuinamente `NOT_ACTIVATED`: `S6_initial_state_is_not_activated` (pk novo, verificado por consulta imediata após criação em container Postgres isolado novo) confirma a pré-condição que faltava no `S6`/`S6_redo` originais (pk=8, corrompido para `ACTIVE` pela lacuna do fix de dataset).
- Bloqueio HTML5 e POST rejeitado pelo servidor são evidências **separadas**: `results_s6_nojs_server_rejection.json` tem as duas chaves distintas (`clientSideValidityCheck` — bloqueio nativo do navegador, nenhuma requisição de rede; `serverSideNoJsAttempt` — POST real, rejeitado pelo servidor com mensagem de negócio) — confirmado por leitura direta do JSON, não presumido.
- Alcance dos UPDATEs: tabela completa de 19 linhas em `dataset-anomaly-reconciliation.md` seção 1, cruzando pretendido/observado/corrigido por campo e por PK — confirmada íntegra nesta leitura.
- Cenários potencialmente contaminados reconciliados por matriz de dependência explícita (seção 2 do mesmo arquivo): S6/S6_redo marcados "Contaminado — invalidado"; S7_redo, S11_redo, overview, smoke de relatórios e escopo OPERATOR marcados "Não contaminado", cada um com a razão (qual PK usa, se depende do campo corrompido).
- A afirmação "apenas S6 foi contaminado" é sustentada pela matriz de dependências (seção 2), não presumida — cada linha da matriz declara explicitamente se o cenário depende do campo `activation_status` do PK afetado.
- Causa original da anomalia (categoria/plano/valor vazios e situação corrompida na criação direta via ORM) permanece **não determinada** — `dataset-anomaly-reconciliation.md` seção 4 mantém essa classificação explicitamente, inclusive após uma tentativa adicional de reprodução sem `runserver` concorrente (não conclusiva).
- Screenshots/JSONs correspondem aos cenários e estados descritos: 11 arquivos em `screenshots/` com nomes autoexplicativos (`create_w1280_jsoff.png`, `legacy_detail.png`, `catalog_interaction.png`, `nojs_valid_combo_result.png`, `overview_admin.png`, `saves_final_state.png`, etc.), consistentes com as referências da matriz da seção 5 de `report.md`.
- Resultados pass/fail não contradizem o veredito: o único `ok: false` restante na evidência nova (`S6_error_mentions_date_or_value` em `results_s6_s7_s11_reconciliation.json`) é uma limitação de extração/timing do script, não um defeito de produto — superado pelo node separado `results_s6_nojs_server_rejection.json` (`mentionsDateOrValue: true`, mensagem real capturada), consistente com o relato de SEV-07.

Nenhuma evidência bruta foi editada por esta task. Nenhuma divergência nova foi encontrada que exigisse repetição em ambiente isolado.

**5. Matriz final de cobertura — T01–T23.**

| Txx | Requisito (resumo) | Código responsável | Teste/node (amostra) | Evidência | Resultado | Limitação |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | Sem selo limpa dados próprios | `whatsapp_seal.py::clear_seal_fields/normalize_seal_fields` | `TestT01SemSeloLimpaDadosProprios` (2 nodes) | Reexecutado nesta task | PASS | — |
| T02 | Não ativado salva datas nulas, indicador neutro | `models.py::clean`, `compute_seal_status` | `TestT02NaoAtivado` (4 nodes) | Reexecutado | PASS | — |
| T03 | Ativo exige cada data/valor; datas iguais aceitas, invertidas rejeitadas | `validate_seal_fields` | `TestT03Ativo` | Reexecutado | PASS | — |
| T04 | Ativação não altera status/activated_at/vínculo/histórico | `views.py::PhoneLineUpdateView.form_valid` | `TestT04AtivacaoNaoAlteraOperacional` | Reexecutado | PASS | — |
| T05 | Legado ativo, datas preservadas, valor null; edição sem valor rejeitada | migration 0022 + forms.py | `TestT05Legado` | Reexecutado + `migration-postgres.log` (artefato conferido) | PASS | — |
| T06 | Valor válido persiste exato; fronteiras | `parse_seal_monthly_value`, `validate_seal_fields` | `TestT06ValorMonetario` | Reexecutado | PASS | — |
| T07 | Erro de valor/e-mail sem mensagem contraditória, sem gravação parcial | `forms.py::_post_clean` | `TestT07SemMensagemContraditoria` | Reexecutado | PASS | — |
| T08 | create_or_reuse/commit=False não perdem campos nem recuperam selo antigo | `models.py::create_or_reuse` | `TestT08CreateOrReuseECommitFalse` | Reexecutado | PASS | — |
| T09 | Linha alocada/Liberar preservam contratos com legado incompleto | `views.py::PhoneLineUpdateView.post` | `TestT09AcoesIndependentesComLegadoIncompleto` | Reexecutado + SEV-07 S10a/S11 (navegador real, artefato conferido) | PASS | — |
| T10 | Migração inclui excluídos; forward/reverse preservam campos antigos | migration 0022 | `test_whatsapp_seal_activation_migration.py` (2 nodes) | Reexecutado (SQLite) + `migration-postgres.log` (Postgres real, artefato conferido) | PASS | — |
| T11 | Ativo mantém alertas 8/7/1/0/-1; Não ativado jamais alerta | `compute_seal_status` | `TestT11AlertasEComputeSealStatus` | Reexecutado | PASS | — |
| T12 | Detalhe/overview/Carregar mais/OPERATOR distinguem Não ativado de Sem selo | templates + `views.py` | `TestT12InterfaceDistingueNaoAtivadoDeSemSelo` + `test_whatsapp_seal_interface_sev06.py` | Reexecutado + SEV-07 navegador real (artefato conferido) | PASS | — |
| T13 | Relatório Selos por ativação; Inventário por posse | `core/services/*_report_service.py` (não tocados) | `TestT13Relatorios` + suíte de relatórios (215+38) | Reexecutado | PASS | — |
| T14 | required/visibilidade/foco/vírgula monetária/datas manuais, com/sem JS | `phone-line-form.js`, `phoneline_form.html` | `TestT14EstruturaDeFormularioParaNovosCampos` + SEV-07 (5.1/5.3/5.4) | Reexecutado (estrutural) + artefato SEV-07 conferido (visual/JS real) | PASS | Navegador headless (SEV-07, não reexecutado aqui) |
| T15 | Escopo/permissão e POST inválido inalterados | `RoleRequiredMixin` (não tocado) | `TestT15PermissoesInalteradas` + SEV-07 (operator scope) | Reexecutado + artefato conferido | PASS | — |
| T16 | Ativo→Não ativado e default de novos selos | `models.py`, `forms.py.__init__` | `TestT16AtivoParaNaoAtivadoEDefault` | Reexecutado | PASS | — |
| T17 | 4 combinações do catálogo; cruzada/token rejeitados no servidor | `whatsapp_seal.py::SEAL_CATALOG_COMBINATIONS` | `TestT17CatalogoCategoriaPlano` (6 nodes) + SEV-07 (pk 15–17) | Reexecutado + artefato conferido | PASS | — |
| T18 | Referência separada do valor efetivo; valor editado preservado | JS + `forms.py` | `TestT18ReferenciaNaoSobrescreveValor` + SEV-07 (`catalog_price_reference_shown_and_separate`) | Reexecutado + artefato conferido | PASS | — |
| T19 | Remoção/troca de selo; obrigatoriedade com/sem JS, sem gravação parcial | `forms.py::full_clean`, JS | `TestT19RemocaoETrocaDeSeloCategoriaPlano` + SEV-07 (NOJS_*) | Reexecutado + artefato conferido | PASS | — |
| T20 | Legados não recebem categoria/plano/valor inferidos | migration 0022 | `TestT20LegadoSemInferencia` | Reexecutado + `migration-postgres.log` | PASS | — |
| T21 | Fronteiras monetárias por situação (0,00/0,01/299,00/-0,01/299,01) | `validate_seal_fields` | `TestT21FronteirasMonetarias` + SEV-07 (M01–M15) | Reexecutado + artefato conferido | PASS | — |
| T22 | Parsing textual (59/59,0/59,00/59.00, rejeições) | `parse_seal_monthly_value` | `TestT22ParsingMonetario` | Reexecutado | PASS | — |
| T23 | Default Não ativado; POST sem situação rejeitado; chamadores sem selo compatíveis | `forms.py.__init__`, `create_or_reuse` | `TestT23DefaultsEChamadoresCompatíveis` | Reexecutado | PASS | — |

Legenda aplicada: **Reexecutado nesta task** = suíte pytest correspondente rodada agora, nesta sessão (ver Test Strategy); **artefato conferido** = arquivo de evidência de SEV-07 (JSON/log/screenshot) lido diretamente nesta task, não apenas citado; nenhuma linha desta matriz se apoia só em "Histórico apenas relatado" sem conferência direta de pelo menos um dos dois tipos de evidência. Nenhum teste duplicado foi criado para aumentar contagem.

Revisão de testes em busca de falsos positivos/placeholders/assertion incidental/fixtures incompatíveis: já realizada e corrigida em SEV-03 (remoção de 2 nodes problemáticos), SEV-04 (2 fixtures corrigidas com causa demonstrada) e SEV-05 (10 fixtures corrigidas com causa demonstrada) — nenhuma nova ocorrência encontrada nesta rodada de revisão amostral (T17 catalog tests, T21 boundary tests, inspecionados diretamente nesta task).

**6. Validação proporcional — comandos executados nesta task, banco SQLite isolado, sequencial:**

```
venv\Scripts\python.exe -m pytest telecom/test_whatsapp_seal_activation_value.py telecom/test_whatsapp_seal_interface_sev06.py telecom/test_whatsapp_seal.py telecom/test_phoneline_form_ui.py telecom/test_seal_detail_and_listing.py telecom/test_whatsapp_seal_model_domain.py telecom/test_whatsapp_seal_activation_migration.py telecom/test_whatsapp_seal_sev04_correction.py -q
  → 202 passed, 2 warnings in 25.09s (idêntico ao relatado: 75+13+65+49)

venv\Scripts\python.exe -m pytest telecom/tests.py telecom/tests_line_timeline.py -q
  → 236 passed, 1 skipped, 2 warnings, 5 subtests passed in 163.87s (idêntico à baseline)

venv\Scripts\python.exe -m pytest config/tests/test_whatsapp_seal_report.py config/tests/test_line_inventory_report.py -k "not RealVolume" -q
  → 215 passed, 8 deselected, 2 warnings, 10 subtests passed in 68.64s (idêntico à baseline)

venv\Scripts\python.exe -m pytest config/tests/test_reports_hub.py -q
  → 38 passed, 2 warnings, 15 subtests passed in 17.97s (idêntico à baseline)

venv\Scripts\python.exe manage.py check --settings=config.settings_dev
  → System check identified no issues (0 silenced).

venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.settings_dev
  → Detecta apenas o mesmo drift alheio pré-existente (dashboard.DailyUserAction.
    action_type, telecom.PhoneLine.origem) — nenhuma alteração desta feature
    aparece nesta saída. (Aviso lateral, ambiental, não relacionado ao código:
    "could not translate host name 'db'" ao checar histórico de migração —
    o settings de dev aponta para um host de container Docker não resolvível
    neste shell local; não impede a checagem de makemigrations, que completou
    e retornou o diff esperado.)

git diff --check
  → sem erro de whitespace (mesmos avisos informativos de LF→CRLF pré-existentes
    nos arquivos já tocados por SEV-03/04/05/06).
```

Reconciliação das saídas registradas nesta task: **691 PASSED** = 202 + 236 + 215 + 38; **1 SKIPPED** (Telecom/Timeline); **30 subtests passed** = 5 + 10 + 15; **8 DESELECTED** (relatórios); **0 FAILED / 0 ERROR**. Portanto, 692 itens selecionados = 691 aprovados + 1 pulado; subtestes não são somados aos itens, e 8 não selecionados ficam separados. A expressão anterior “691 testes/subtestes” misturava categorias; a soma 202+237+215+38 inclui o skipped, não 692 aprovados. Suítes sobrepostas (`telecom/test_whatsapp_seal.py`, `test_phoneline_form_ui.py`, `test_seal_detail_and_listing.py` aparecem só na primeira bateria) não somadas duas vezes. Nenhum volume pesado repetido sem necessidade (`-k "not RealVolume"` mantido). SEV-07 (navegador real, Postgres real) **não foi reexecutado** nesta task — proporcional ao fato de nenhum código ter sido alterado por SEV-08; a evidência existente foi lida e auditada diretamente (seção 4 acima), não presumida.

Nenhum defeito funcional novo foi encontrado nesta revisão. Nenhuma correção de código foi necessária — portanto não há ciclo RED→GREEN para repetir nesta task.

**7. Veredito e achados.**

Nenhum achado bloqueante de severidade alta foi encontrado nesta revisão. Achados não bloqueantes, já documentados nas tasks correspondentes e reconfirmados nesta auditoria:

| Severidade | Achado | Arquivo/linha | Impacto | Status |
| --- | --- | --- | --- | --- |
| Baixa (observação, não corrigida) | `validate_seal_fields` concentra 9 parâmetros e 3 responsabilidades (catálogo, fronteiras monetárias, datas) | telecom/whatsapp_seal.py:108–222 | Legibilidade; nenhum risco funcional corrente | Observação para refatoração futura, fora de escopo de SEV-08 |
| Limitação não bloqueante | Navegador headless em todo o aceite de SEV-07 | docs/superpowers/evidence/SEV-07/report.md §6.1 | Nenhuma observação visual humana em tempo real; screenshots reais disponíveis para inspeção posterior | Aberta, não bloqueante |
| Limitação não bloqueante | Causa raiz da anomalia de dataset de SEV-07 não determinada | dataset-anomaly-reconciliation.md §4 | Não afeta o aceite (caminho real da aplicação comprovado correto); risco residual só para scripts de setup de dados fora da aplicação | Aberta, não bloqueante |
| Limitação não bloqueante | Exportação CSV/XLSX dos relatórios Selos/Inventário não exercitada em navegador real | report.md §6.4 | Fora do pedido original de SEV-07 (smoke, não exportação); cobertura pytest completa já existente para os serviços de relatório | Aberta, não bloqueante |
| Limitação não bloqueante (documental) | Recuperação integral do incidente de stash (retificação de SEV-04) não certificável retrospectivamente | registro "Ressalvas documentais da retificação SEV-04" | Nenhuma perda foi detectada por nenhum teste/inspeção subsequente; apenas a certeza retroativa é limitada | Aberta, documentada, não bloqueante — não revisitada por falta de baseline, conforme já decidido |

Nenhuma correção mínima foi necessária nesta task (nenhum defeito encontrado).

**Lista exata de arquivos propostos para futura integração** (idêntica à lista de escopo da seção 0, repetida aqui para o pedido de "lista exata"):

```
static/js/phone-line-form.js
telecom/forms.py
telecom/models.py
telecom/test_phoneline_form_ui.py
telecom/test_whatsapp_seal.py
telecom/views.py
telecom/whatsapp_seal.py
templates/telecom/phoneline_detail.html
templates/telecom/phoneline_form.html
telecom/migrations/0022_phoneline_whatsapp_seal_activation_status_and_more.py
telecom/test_whatsapp_seal_activation_migration.py
telecom/test_whatsapp_seal_activation_value.py
telecom/test_whatsapp_seal_interface_sev06.py
telecom/test_whatsapp_seal_model_domain.py
telecom/test_whatsapp_seal_sev04_correction.py
docs/superpowers/evidence/SEV-07/ (diretório completo)
docs/superpowers/specs/2026-09-30-whatsapp-seal-activation-value-design.md
```

**Resumo de release:** sem número de versão inventado nesta task. O repositório está em `73b955b` ("chore(release): bump version to 1.8.0"), que antecede esta feature — a decisão de qual versão receberá esta entrega cabe a quem fizer o release, não a esta revisão.

**Plano de migration/rollback:** ver seção 3 acima (backup → plano completo pela imagem nova → suspensão de escritas → 0022 pela imagem nova → publicação/verificações → rollback condicionado à compatibilidade dos dados; reversão de schema não rotineira).

**Compliance Report desta task:**

- Workspace: branch/HEAD/status registrados; lista de arquivos SEV explícita e auditada; arquivos alheios identificados e preservados sem toque; recuperação do stash histórico não certificada (mantido o limite já registrado).
- Contrato/domínio: todos os pontos do mandado de revisão (seção 2 do pedido) confirmados por leitura direta do código atual, sem exceção encontrada.
- Forms/serviço/segurança: confirmado sem bypass, sem full_clean global, sem dado financeiro fora do contrato, catálogo seguro.
- Migration/rollback: grafo real inspecionado; plano operacional preparado (não executado); limitação de rollback de schema documentada com análise concreta de compatibilidade do código antigo.
- Evidências SEV-07: auditadas diretamente (arquivos lidos, não apenas citados); nenhuma edição de evidência bruta; nenhuma divergência nova.
- Matriz T01–T23: consolidada com rastreabilidade requisito→código→teste→evidência→resultado→limitação; 691 testes aprovados, 1 skipped e 30 subtestes aprovados (8 deselected separados) nesta task, 0 failed, 0 error; `manage.py check` e `git diff --check` limpos; `makemigrations --check --dry-run` detectou drift preexistente, sem alteração nova da feature. Não descrever esse último como limpo; código de saída não foi preservado no trecho de execução acima.
- Nenhuma refatoração transversal executada; observação de acoplamento registrada como proposta, não aplicada.
- Sem stage, commit, tag, versão, push, deploy, acesso a PRD ou dependência nova nesta task.

**Veredito: pronto para integração**, com as limitações não bloqueantes explicitamente listadas acima (não corrigidas nesta task, por não serem bloqueantes e por risco de ampliar escopo). "Pronto para integração" não significa implantado e não autoriza commit/push/deploy — essas ações permanecem sujeitas a pedido explícito posterior do usuário.

SEV-08 concluída. Todas as oito tasks do Implementation Plan (SEV-01 a SEV-08) estão concluídas nesta fonte da verdade.


### 2026-10-01 — Correção documental de SEV-08

**Spec Summary / Gap Analysis.** Contagem reconciliada pelas saídas já registradas: 691 aprovados, 1 skipped, 30 subtestes aprovados e 8 deselected, categorias separadas. Não houve nova execução. Migration check detectou drift: não limpo; exit code histórico não consta no trecho disponível, portanto não foi inventado. Warning de resolução do host db limita conferência de histórico nesse ambiente.

**Implementation Plan.** Plano operacional retificado: migration com imagem nova antes de servir tráfego, plano de todos os apps e janela sem escritas. Retirada associação incorreta de schema ausente com ValueError de ModelForm. Retirada promessa de compatibilidade com 1.8.0: leitura direta do código no commit 73b955b comprova exigência de datas e indicador Sem selo quando vencimento ausente.

**Test Checklist / Test Strategy.** Conferência aritmética/documental e leitura do código histórico via git show; nenhuma suíte, migration ou operação remota executada nesta rodada. Verificação do rollback em ambiente real não foi feita.

**Compliance Report.** Somente esta spec alterada. Histórico de resultados preservado, conclusões incorretas substituídas e motivo registrado. Veredito de integração não equivale a autorização de deploy: plano de rollback deve respeitar as restrições funcionais explicitadas. Sem alteração de código, stage, commit, push ou PRD.
