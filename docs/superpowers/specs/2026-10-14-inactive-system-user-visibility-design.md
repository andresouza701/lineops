# Visibilidade de contas de acesso inativas

Data: 2026-10-14
Identificador: UVI
Status: UVI-01, UVI-02, UVI-03, UVI-03a (conferência corretiva), UVI-04 (política backend), UVI-04b (conferência corretiva de UVI-04), UVI-05 (interface e vínculos existentes), UVI-05b (conferência corretiva de UVI-05), UVI-06 (aceite integrado e revisão final) e UVI-06b (correção dos achados da revisão final) concluídas. Pronto para revisão/preparação de commit — sem stage/commit/push/deploy/PRD executados nesta feature.

## Spec Summary

Contas de acesso são `users.SystemUser`; inatividade significa `is_active=False` (campo herdado de AbstractUser). Não confundir com Employee.status, exclusão lógica de funcionário ou LineAllocation.is_active.

Decisões explícitas do usuário:
- ADMIN e DEV podem continuar vendo contas inativas, respeitadas permissões de rota/modelo e escopo existentes.
- SUPER, BACKOFFICE, GERENTE e OPERATOR não veem contas inativas em listas, buscas ou seletores de contas; acesso direto a essas contas também deve ser bloqueado.
- Históricos e relatórios preservam referências a contas inativas.
- Na edição de cadastro com supervisor/gerente inativo já vinculado: preservar vínculo sem exibir nome/e-mail no seletor; permitir manter ou trocar por ativo. A escolha foi confirmada pelo usuário nesta etapa.

Nenhuma conta será excluída, reativada ou terá role/permissões alteradas por esta feature. Login de contas inativas permanece sob a autenticação existente.

## Contract

### Autorização e apresentação

1. Visibilidade resulta da interseção entre permissões/escopo anteriores e a regra de inatividade. ADMIN/DEV não ganham acesso novo a áreas antes negadas.
2. Para os quatro papéis restritos, consultas de contas omitem inativas antes de paginação, contagem e busca. Filtros do cliente não removem essa restrição.
3. A proteção de objetos vale no servidor, não apenas nos links. Abrange entradas de leitura e escrita dirigidas à conta identificadas no inventário.
4. Preservar rejeição por autenticação/permissão antes de avaliar visibilidade. Para usuário autorizado à rota mas não ao objeto inativo, propor 404 sem identificar a conta; confirmar compatibilidade com convenções reais em UVI-02. Nenhuma nova rota de detalhe será criada.
5. `is_staff` e `is_superuser` não substituem a exceção por role ADMIN/DEV nesta política. Testar papéis restritos com permissões técnicas suficientes para alcançar a rota, evitando GREEN por negação anterior não relacionada.
6. Seletores operacionais para novos vínculos não oferecem contas inativas aos papéis restritos. POST forjado não pode atribuí-las por ID/e-mail.
7. Em edição, vínculo inativo existente pode ser conservado sem oferecer sua identidade no seletor nem no HTML/JSON de opções. Usar representação neutra, por exemplo "Manter vínculo atual", cujo significado é manter o valor persistido. O servidor deve verificar o objeto/valor anterior; marcador não permite atribuir outra conta escondida. Nome exato e transporte serão fixados em UVI-02 antes dos testes.
8. Não substituir silenciosamente vínculo inativo pela primeira opção ativa ou vazio. Salvar outro campo conserva vínculo. Troca explícita por ativo respeita validação anterior. Falha em outro campo não deve expor identidade nem perder seleção.
9. Coleção sem candidatos ativos não pode virar TextInput livre que permita selecionar conta inativa. Revisar fallback existente sem alterar aceitação histórica de valores não vinculados além do necessário; ambiguidades serão registradas em UVI-02.

### Referências e escopo

- Preservar identidades em histórico, auditoria e relatórios; ocultar conta operacional não é anonimizar autoria nem remover eventos/linhas de relatório.
- Referência histórica não concede acesso direto ao cadastro da conta. Links devem respeitar a proteção de objeto.
- Não filtrar globalmente SystemUser.objects nem relações históricas. A mesma conta pode estar oculta em seletor e presente como autor de evento.
- Não remover funcionários/linhas do escopo por desativação de supervisor/gerente. Visibilidade de conta e escopo de dados operacionais são preocupações distintas; qualquer alteração de escopo requer decisão separada.
- Não mudar concessões de ADMIN-only em relatórios para dar acesso a DEV.
- Nomes de supervisor escritos em constantes, strings históricas sem conta correspondente e agrupamentos de dashboard exigem classificação explícita no inventário (diretório operacional versus referência preservada), sem inferir inatividade a partir do texto.

## Gap Analysis / mapa inicial por inspeção direta

| Caminho | Comportamento observado | Consequência para UVI |
|---|---|---|
| users/models.py::SystemUser | AbstractUser, role com seis valores; manager sem filtro de is_active | Fonte correta do estado; não alterar manager global |
| config/urls.py | Gestão via admin.site.urls; accounts inclui auth; api/admin-only é demonstração, não diretório | Não foram localizadas views públicas de CRUD de contas nesta inspeção |
| users/admin.py::SystemUserAdmin | UserAdmin, busca herdada, list_filter is_active, sem filtro por role sobre objetos | Mapear lista/busca/change/delete/history/password, popup/autocomplete efetivamente disponíveis e ações em lote |
| employees/forms.py::EmployeeForm | Consulta SUPER/GERENTE sem is_active; listas de e-mails; sem candidatos troca widget por TextInput; clean valida pertinência só se lista não vazia | Superfície real de seleção de contas; tratamento de vínculo legado e conjunto vazio necessário |
| employees/views.py::EmployeeUpdateView | Papéis de EMPLOYEE_ACCESS_ROLES; get_form_kwargs passa can_edit_full_name, não viewer | Propagação explícita do solicitante necessária para decisão por role; não inventar thread-local |
| employees/views.py::EmployeeCreateView | ADMIN-only | Preservar comportamento autorizado; catalogar chamadores do form |
| allocations/forms.py::CombinedRegistrationForm | Consulta SUPER/GERENTE sem is_active; fallback semelhante | Reuso exige contexto de solicitante; não filtrar cegamente para ADMIN |
| allocations/views.py::RegistrationHubView | ADMIN-only; instancia CombinedRegistrationForm em GET/POST | Controle de preservação, não acesso novo de DEV |
| users/models.py::get_managed_supervisor_emails / scope_employee_queryset | Consulta supervisores por gerente sem is_active; usada para escopo de funcionários | Não adicionar is_active aqui sem separar efeitos sobre dados acessíveis |
| dashboard/views.py::ManagerDashboardView | Usa get_managed_supervisor_emails para grupos/rótulos e escopo relacionado | Classificar apresentação operacional e referências antes de decidir filtragem |
| users/models.py::get_effective_supervisor_user / clean | Resolução/validação de vínculo backoffice por e-mail | Não confundir validação de vínculo já existente com seleção de nova conta |
| pendencies/services.py | Destinatários já filtrados por is_active=True | Manter notificações; nenhuma alteração necessária presumida |
| telecom/line_timeline.py e line_operational_report.py | Buscam SystemUser por IDs para resolver atores | Referências históricas preservadas, fora de filtro operacional |
| FKs AUTH_USER_MODEL em allocations, pendencies, dashboard, employees, telecom | Autores, responsáveis e histórico | Inventariar widgets Admin e representações: opções operacionais versus autoria histórica |
| dashboard/forms.py | Choices de supervisor provenientes de constantes | Não equiparar automaticamente constante a conta SystemUser |

Mapa inicial, não declaração de inventário exaustivo. UVI-02 deve fechar todas as entradas, templates, APIs, filtros, contagens e chamadores; apontar o que é efetivamente alcançável por cada papel.

## Implementation Plan / Tasks

- [x] **UVI-01 — Contrato e fonte de verdade.** Decisões de produto, domínio correto, mapa inicial e tarefas (esta entrega).
- [x] **UVI-02 — Inventário completo e contratos técnicos.** Mapear seleção/gestão/referências e permissões. Fixar erro de acesso direto e marcador de vínculo preservado; classificar dashboard e widgets FK/Admin. Identificar riscos de POST forjado, resultados vazios, caches e N+1. Sem código.
- [x] **UVI-03 — Testes RED.** Matriz requisito→node ID→camada→tarefa; executar falhas reais e controles GREEN. Sem placeholders ou funções futuras inventadas.
- [x] **UVI-04 — Política backend e entradas.** Filtragem contextual compartilhada, proteção de objeto e validação de seleção/POST. Preservar escopos e referências. Fixtures só corrigidas com causa comprovada.
- [x] **UVI-05 — Interface e vínculos existentes.** Propagar contexto dos forms, opção neutra, resultados vazios e erros; nenhum dado escondido em options/hidden/JSON. Reuso da regra do servidor. Smoke real proporcional.
- [x] **UVI-06 — Aceite integrado e revisão final.** Navegador desktop/mobile, papéis, URL direta, POST forjado, preservação de auditoria/relatórios, regressão e revisão de diff. Plano de deploy/rollback; sem commit/deploy automático.

## Test Checklist

1. Conta ativa e inativa com identidade distinta; ADMIN/DEV versus quatro roles restritos, sem conceder permissões novas.
2. Lista/busca/filtros/paginação/contagens não revelam inativas ao público restrito.
3. URLs e POSTs diretos aos objetos inativos protegidos, inclusive variantes reais de Admin; nenhuma escrita indevida.
4. Papéis restritos com staff/superuser não ganham exceção de visibilidade; negativos de permissão separados dos negativos de objeto.
5. Seletores retornam apenas candidatos visíveis; ID/e-mail forjados rejeitados no servidor.
6. Zero ativos com inativos existentes não reabre entrada livre para essas contas.
7. Vínculo legado inativo: identidade ausente nas opções/HTML/JSON operacionais, manter salva mesmo valor; trocar salva ativo escolhido; tentativa de apontar outro inativo é recusada.
8. Erro em campo alheio preserva escolha e não expõe identidade inativa. Nenhum overwrite para vazio/primeira opção.
9. Desativação entre GET e POST reavaliada no servidor; garantia de concorrência adicional não presumida.
10. Históricos/relatórios preservam autor e conteúdo; acesso ao objeto referenciado continua restrito. Sem sumir funcionários/linhas por supervisor inativo.
11. ADMIN/DEV mantêm inativos onde já autorizados; OPERATOR/DEV continuam sem áreas antes negadas.
12. Dados não relacionados, autenticação e notificações sem regressão; nenhum filtro global ou exclusão.
13. Custo de consulta sem crescimento linear por item nos caminhos alterados; comparar conjuntos com identidades distintas e conteúdo efetivamente renderizado.
14. Navegador real: desktop/390/360px, teclado, mensagens/estado vazio, troca de escolha, ausência de dados nas opções e nenhuma regressão visual.

## Test Strategy

- pytest com interpretador venv do projeto; banco isolado; suítes sequenciais.
- Política pura se houver fronteira concreta, integração com Django Client/Admin reais e forms reais. Não mockar a própria regra.
- Ler testes de employees/allocations/Admin e dashboard/tests/test_manager_dashboard_removed_supervisor.py como controles; verificar coleta real antes de citar contagens.
- Provar ausência de escrita por estado persistido, não só resposta HTTP. Controles positivos elegíveis impedem falso GREEN por falta de acesso.
- Navegador real para UI; Client não prova interação, layout ou foco.
- PostgreSQL somente quando alegar semântica específica de DB/locking. SQLite não prova essas garantias.
- manage.py check e git diff --check nas etapas executáveis; nenhum teste executável criado nesta etapa documental.

## Compliance Report

Contrato aprovado pelo usuário e mapeamento inicial fundamentado em leitura do código. Uma decisão adicional (vínculo inativo existente no seletor) foi perguntada e aprovada antes de registrar o contrato. Detalhes técnicos classificados para UVI-02, sem implementação presumida.

Nesta entrega somente este documento foi criado. Nenhum código de aplicação, teste executável, migration, stage, commit, push, deploy ou banco operacional foi alterado. Documento alheio de auditoria diária e evidências/untracked preexistentes preservados. UVI-02 não executada.


## UVI-02 — Inventário e contratos técnicos (2026-10-14)

### Spec Summary

Inventário do código atual e do Django instalado. Sem mudanças executáveis. Decisão adicional explicitamente aprovada nesta etapa: nas telas atuais de funcionários e no painel por supervisor, ocultar nome/e-mail do supervisor/gerente inativo com rótulo neutro, preservando funcionários, vínculos e totais. Históricos e relatórios continuam com referências integrais. A aprovação não autoriza remover grupos, registros ou alterar escopos.

### Gap Analysis / inventário consolidado

| ID | Entrada / consumidor | Situação atual e contrato de destino |
|---|---|---|
| U01 | users/models.py::SystemUser; is_active | Fonte do estado. Não alterar manager global, autenticação, roles ou persistência do usuário |
| U02 | users/admin.py::SystemUserAdmin, changelist e pesquisa herdada | Diretório real de contas. Filtrar antes de busca, paginação, contagens, filtros, popup e ações em lote; restringir também seleção de IDs forjados |
| U03 | UserAdmin change/delete/history/password e URLs legadas por ID | Proteger GET/POST dirigidos à conta inativa. História da própria conta oculta não vira bypass; autoria em histórico de outro objeto permanece |
| U04 | SystemUserAdmin manager_email/supervisor_email | Textos editáveis constituem associação operacional. Validar conta proposta; preservar vínculo inativo existente mediante opção neutra para viewer restrito. Não afrouxar SystemUser.clean para backoffice |
| U05 | EmployeeForm; EmployeeCreateView/EmployeeUpdateView | Dois seletores SUPER/GERENTE sem filtro atual. Passar viewer explicitamente. Create ADMIN-only preservado; update conserva permissões/escopo existentes |
| U06 | CombinedRegistrationForm; RegistrationHubView GET/POST | Dois chamadores diretos, ambos ADMIN-only. Propagar viewer, preservar acesso a inativos autorizado; sem novo acesso DEV |
| U07 | EmployeeAdminForm/EmployeeAdmin | E-mails livres hoje; caminho alternativo de associação e exposição em lista/busca/form. Aplicar mesma política por request, mantendo normalização e validações anteriores |
| U08 | employees/employee_list.html + JSON/AJAX EmployeeListView | corporate_email exposto inicialmente e no carregamento dinâmico. Projetar rótulo neutro em ambos, sem remover funcionário nem deixar e-mail escondido no payload |
| U09 | employees/employee_detail.html | corporate_email e manager_email são referências atuais: neutralizar identidade inativa para restritos, manter valores persistidos |
| U10 | dashboard/views.py::ManagerDashboardView + manager_dashboard.html | Resolver identidades em lote e neutralizar rótulos, sem colapsar grupos distintos nem mudar totais/escopo; chaves internas não devem vazar e-mail em DOM/JSON |
| U11 | get_managed_supervisor_emails / scope_employee_queryset | Dependências de acesso a empregados/linhas, não diretório. Manter sem filtro de atividade; apresentação é camada separada |
| U12 | get_effective_supervisor_user / get_effective_supervisor_email | Resolução de identidade/escopo existente. Não trocar globalmente por queryset filtrado; aplicar restrição somente ao consumidor operacional |
| U13 | LineAllocationAdmin: allocated_by/released_by | FKs de autoria no formulário padrão. Referência histórica exibida permanece; novas escolhas de usuários obedecem visibilidade. Manter autor existente não deve remover FK nem impedir edição alheia |
| U14 | AllocationPendencyAdmin: technical_responsible/updated_by | Responsável operacional versus autor. Opções novas filtradas; vínculo atual inativo pode ser mantido de forma neutra. Exibição histórica de autoria preservada. Não mudar POR/origem nem claim/release |
| U15 | Histórico EmployeeHistory.changed_by / PhoneLineHistory.changed_by | Referências históricas preservadas; modelos não registrados no Admin atual |
| U16 | LineDailyActionAuditEvent.performed_by / WhatsappReconnectHistory.started_by | Referências preservadas; nenhum filtro global. Não registrados no Admin |
| U17 | DailyIndicator.created_by/updated_by; DailyUserAction.supervisor/created_by/updated_by | Atribuições históricas e dados de indicadores preservados. Modelos não registrados no Admin |
| U18 | PendencyObservationNotification.recipient/sent_by; pendencies/services.py | Destinatários ativos já filtrados; preservar entrega/autoria, sem redefinir política de notificações |
| U19 | telecom/line_timeline.py / line_operational_report.py; relatórios do hub | Resolução de autores integral. Relatórios continuam ADMIN-only; DEV não recebe nova permissão |
| U20 | dashboard/forms.py choices B2B_SUPERVISORS/B2C_SUPERVISORS | Constantes não constituem prova de conta nem de inatividade. Não filtrar por coincidência de nome; preservar fórmula e referências de indicadores |
| U21 | accounts/*, JWT e api/admin-only/ | Autenticação/demo, não CRUD de contas. Nenhuma rota nova ou alteração de login prevista |
| U22 | Admin site: registro e endpoints de escolha | Introspecção sem query confirmou Group, SystemUser, Employee, SIMcard, BlipConfiguration, LineAllocation, AllocationPendency. Todos com autocomplete_fields/raw_id_fields vazios. Não inventar UI autocomplete existente; endpoint genérico não deve oferecer bypass se requisitado |

FKs de usuários foram conferidas por introspecção de apps.get_models e admin.site._registry, sem consultar o banco. LogEntry.user também existe, sem ModelAdmin registrado; manter auditoria. O processo imprimiu aviso de localização de C:/Python314/python.exe, mas completou introspecção com exit 0; isso não equivale a executar testes.

### Contratos técnicos fixados

**Acesso direto.** Para viewer autenticado com permissão prévia da operação, conta inativa oculta retorna 404 genérico, sem nome/e-mail ou mutação. Sem permissão, manter negação anterior. Fonte instalada mostra que get_object usa get_queryset, mas change/delete/history usam redirecionamento para objeto ausente; password já produz Http404. Portanto filtro de queryset sozinho NÃO comprova o contrato 404: testar cada entrada e adaptar pontualmente. IDs inexistentes e ocultos devem ter resposta indistinguível dentro da mesma operação. Ações em lote atuam apenas no queryset visível, inclusive seleção forjada; confirmação não lista identidades ocultas. Não permitir reativação por POST dirigido ao objeto oculto.

**Contexto e política.** Uma política contextual reutilizável, separada dos managers/escopos globais. Viewer vem da request, nunca de role informada no payload. ADMIN/DEV são exceções de atividade, não de permissão. Ausência de viewer não pode conceder exceção; produção deve passar contexto em todos os forms mapeados. Testes antigos que constroem forms sem viewer precisam de decisão explícita compatível com restrição, não fallback implícito ADMIN.

**Marcador de vínculo.** Token reservado `__keep_current__`, rótulo `Manter vínculo atual`. Não representa ID/e-mail. Somente válido em edição quando o campo possui referência persistida inativa e ocultada para aquele viewer. Resolver o valor a partir do objeto persistido no servidor, não de self.instance já mutado por ModelForm._post_clean, nem de hidden enviado pelo cliente. Token em criação, campo sem vínculo ou outro contexto: erro de campo genérico. Não aceitar e-mail/ID de outro inativo. Redisplay de POST inválido mantém o marcador, sem reinjetar identidade. Opção ativa explicitamente escolhida substitui vínculo; manter não grava token. Aplicar mecanismo equivalente aos FK operacionais; não tornar autor histórico recém-selecionável só porque sua identidade é preservada na leitura.

**Opções vazias e texto livre.** Nos caminhos que já exigem pertinência quando há candidatos, coleção vazia após filtro não libera inativos. Revalidar conta correspondente por e-mail normalizado no POST, mesmo quando widget é textual. Valores sem conta correspondente conservam tratamento anterior do respectivo formulário; não criar regra universal de obrigatoriedade/existência. TextInput não pode redisplayar vínculo inativo atual: usar representação neutra. Estado sem candidatos informa `Nenhum usuário ativo disponível`; vínculo preservável continua podendo ser mantido. Não atribuir primeira opção automaticamente.

**Apresentação atual.** Rótulo `Usuário inativo` substitui nome/e-mail resolvido como conta inativa em U08–U10 e outras referências operacionais mapeadas. Manter grupos separados por identidade interna; não agrupar todas as contas sob o mesmo rótulo como chave. Históricos/relatórios permanecem exceção. Texto legado sem conta correspondente não é declarado inativo. Campos usados para procurar contas e sugestões não revelam identidade oculta; filtros sobre funcionários não podem desaparecer com seus registros. Conferir HTML, options, atributos, scripts e JSON, não somente texto visível.

**Atualidade e custo.** Reavaliar atividade no POST; desativação entre GET/POST não autoriza novo vínculo oculto. Sem promessa de serialização concorrente adicional ou lock em SystemUser. Resolver referências por lote por requisição/página, sem cache global/estado mutável em ModelAdmin compartilhado entre requests. Não modificar helpers de escopo para economizar consulta. Preservar pré-validação de autorização.

**Persistência/API.** Sem migration esperada; FKs/e-mails permanecem armazenados. APIs/JSON de listagem mantêm estrutura compatível quando possível, com valores de apresentação neutralizados para restritos; não transportar e-mail oculto em novo campo auxiliar. Respostas de formulário conservam contrato de erro existente, exceto objeto oculto 404 definido acima. Não usar escape/HTML como substituto de filtragem.

### Implementation Plan

1. UVI-03: testes comportamentais sobre entradas reais acima, com fixtures staff/permissões suficientes, controles ativos e regras legadas. Classificar backend/UI/histórico e RED por causa real.
2. UVI-04: política contextual, proteção de Admin/POST, propagação de viewer e fronteiras de validação. Não deixar ModelForm sem campo receber ValidationError de campo inexistente.
3. UVI-05: marcador, rótulos e projeção em lote para lista/AJAX/detalhe/painel. Cuidar da redisplay e valores persistidos; integrar sem reescrever escopo.
4. UVI-06: navegador e regressão, conferência integral de diff e contratos. Nenhuma autorização implícita para commit/deploy.

### Test Checklist — derivação para UVI-03

- T01: seis roles, contas ativas/inativas, staff/permissões reais; lista, pesquisa, contagens, filtro is_active e paginação.
- T02: change/delete/history/password/URL legada e POST forjado, 404 genérico versus negação de permissão; estado e senha intactos.
- T03: popup, ações em lote e tentativa no endpoint genérico de autocomplete; nenhuma identidade oculta.
- T04: EmployeeForm e CombinedRegistrationForm, ADMIN/DEV autorizados versus restritos; não confundir ausência de permissão com filtro funcional.
- T05: EmployeeAdmin e SystemUserAdmin e-mails operacionais; caixa textual não permite associar inativo oculto.
- T06: manter vínculo, trocar por ativo, marcador forjado/criação, erro em outro campo, zero ativos e valor legado sem conta; sem overwrite/identidade oculta.
- T07: FK operacional e autoria em Admin; opções filtradas, vínculo histórico conservado, POR sem regressão.
- T08: lista inicial/AJAX, detalhe e painel: rótulo neutro, identidade ausente em payload/DOM, grupos distintos e totais idênticos.
- T09: desativar supervisor não reduz escopo de funcionários/linhas; acesso direto de empregado continua conforme escopo anterior.
- T10: histórico/timeline/relatórios retêm autores inativos; links de conta não contornam restrição; DEV não ganha relatório.
- T11: GET ativo/POST inativo, comparação de banco e zero escrita recusada. Não confundir com corrida PostgreSQL comprovada.
- T12: custo com poucos/muitos usuários distintos, conteúdo renderizado real; isolamento entre viewers e requests sucessivas.
- T13: constantes, notificações e autenticação preservadas; sem inferir conta a partir de nome.
- T14: navegador desktop/390/360, teclado, sem JS nos forms suportados, manter/trocar/erro/sem opções, paginação dinâmica.

### Test Strategy

UVI-02 usa leitura estática e introspecção sem queries; nenhum teste funcional foi executado. UVI-03 deverá produzir node IDs reais e logs RED/GREEN, sem placeholders. Usar pytest e fixtures isoladas; testes de app/Admin com HTTP real de Django Client, controles elegíveis e estado persistido. Separar permissão técnica de role. Regressão proporcional users/employees/allocations/pendencies/dashboard e histórico/relatórios quando caminhos compartilhados forem tocados. Execução sequencial e reconciliação de sobreposição, skips e subtestes. Navegador obrigatório em UVI-06; PostgreSQL só como evidência quando realmente utilizado.

### Compliance Report

UVI-02 concluída após resposta explícita sobre referências atuais. Inventário, contratos e testes derivados registrados antes de código. Nenhuma alteração executável, migration, banco, stage, commit, push ou deploy. Documento alheio já modificado preservado. Próxima tarefa UVI-03; não iniciada. Os nomes de token/rótulos e desenho de integração acima são decisões técnicas desta etapa, não alegação de implementação existente.


## UVI-03 — Testes RED (2026-10-14)

### Spec Summary

Tradução dos T01–T14 (UVI-02) em testes executáveis reais contra o código atual, sem nenhuma implementação de política (UVI-04/05/06 continuam pendentes). Toda consulta/formulário/Admin mapeado em UVI-02 ainda não filtra por `is_active` nem por papel: os testes abaixo codificam o contrato aprovado e falham onde o contrato é violado hoje, e passam onde o comportamento já é compatível (controle positivo) ou onde a rota/dados não estariam de fato acessíveis (prova de alcance). Nenhum teste usa `pytest.fail` incondicional, símbolo futuro inventado ou mock da própria política.

Cobertura entregue nesta etapa, por arquivo novo:

- `users/test_uvi03_admin_inactive_visibility.py` — Admin de `SystemUser` (T01/T02/T04).
- `employees/tests/test_uvi03_inactive_account_visibility.py` — `EmployeeForm`, `EmployeeListView` (HTML+AJAX), `EmployeeDetailView` (T05/T06/T08).
- `allocations/tests/test_uvi03_inactive_account_visibility.py` — `CombinedRegistrationForm`, `LineAllocationAdmin` (T04/T07).
- `pendencies/tests/test_uvi03_inactive_account_visibility.py` — `AllocationPendencyAdmin`, `pendencies/services.py` (T07/T13).
- `dashboard/tests/test_uvi03_inactive_account_visibility.py` — `ManagerDashboardView` (T08).
- `telecom/test_uvi03_inactive_author_preservation.py` — `line_timeline.py` (T10, controle positivo).

Não foi escrito código de aplicação, migration nem alterado nenhum arquivo existente de produção. Apenas os seis arquivos de teste acima foram criados.

### Gap Analysis — achados empíricos confirmados pela execução (não presumidos)

| Achado | Evidência real observada |
|---|---|
| `SystemUserAdmin` não filtra queryset por role: changelist, busca (`?q=`), contagem e páginas diretas (`change`/`delete`/`history`) retornam a conta inativa para qualquer staff com permissão do modelo, independente do role. | Resposta 200 com o e-mail da conta inativa no HTML/`cl.result_list` para viewer SUPER/BACKOFFICE/GERENTE/OPERATOR com permissões completas de `users`. |
| Busca por e-mail (`UserAdmin.search_fields` herdado, que inclui `"username"`) não quebra com `username=None` no model — não há `FieldError`; apenas não há filtro de atividade. | `test_restricted_role_search_must_not_find_inactive_account` falhou por conter o e-mail, não por erro 500/`FieldError`. Ambiguidade de UVI-02 resolvida: busca funciona tecnicamente, só falta a política. |
| POST forjado de `change` para a conta oculta é aceito e **muda o `role` persistido** (de `operator` para `admin`). Ação em lote `delete_selected` contra o ID oculto não excluiu a conta nesta rodada (o form de confirmação intermediário do Admin bloqueou a exclusão direta de 1 passo). | `test_forged_post_must_not_change_role_of_hidden_account` RED (role mudou); `test_forged_delete_action_must_not_remove_hidden_account` GREEN (conta sobreviveu — Admin exige confirmação em 2 passos, não é proteção de visibilidade). |
| `is_staff`/`is_superuser` não têm relação alguma com a regra pretendida: hoje **nada** filtra por atividade, então um OPERATOR com ambas as flags também vê a conta inativa — não porque as flags "concedem" a exceção, mas porque não existe exceção nem regra ainda. | `test_restricted_role_with_is_staff_and_is_superuser_still_blocked` RED. |
| `/admin/.../password/` usa nome de rota fixo do Django (`admin:auth_user_password_change`, não `admin:users_systemuser_password_change`) e hoje retorna 200 (form de senha) para a conta oculta — contrariando a nota de UVI-02 de que "password já produz Http404" (essa nota se referia a outro comportamento do Django, não confirmado aqui para o viewer restrito). | `test_restricted_role_password_change_page_must_be_404` RED (200, não 404). |
| `EmployeeForm`/`CombinedRegistrationForm` (mesmo padrão nos dois) incluem e-mails de supervisores/gerentes **inativos** nas choices do `<select>` e aceitam esse e-mail no POST (`clean_corporate_email` só valida pertencimento à lista, que já inclui inativos). Quando o único supervisor cadastrado está inativo, a lista fica vazia e o campo cai para `TextInput` **sem nenhuma validação** (`allowed_emails` vazio desativa o `clean_corporate_email`), aceitando literalmente qualquer e-mail, inclusive o do inativo. | `test_corporate_email_choices_must_not_include_inactive_supervisor`, `test_form_must_reject_forged_inactive_supervisor_email`, `test_form_must_not_accept_inactive_email_via_free_text_fallback` — todos RED nos dois formulários. |
| `employee_list.html`/AJAX e `employee_detail.html` imprimem `corporate_email`/`manager_email` em texto puro — a identidade do supervisor/gerente inativo aparece tanto no HTML inicial quanto no JSON do AJAX (`data[].corporate_email`). | `test_employee_list_page_...`, `test_employee_list_ajax_payload_...`, `test_employee_detail_page_...` RED; funcionário e `full_name` continuam presentes (controle incorporado na mesma asserção). |
| `LineAllocationAdmin`/`AllocationPendencyAdmin` não declaram `fieldsets` nem `raw_id_fields`/`autocomplete_fields` para os FKs de `SystemUser` (`allocated_by`/`released_by`, `technical_responsible`/`updated_by`): o `<select>` padrão do `ModelForm` lista **todas** as `SystemUser`, inclusive inativas sem vínculo nenhum com o registro aberto. O vínculo já persistido continua presente (autoria histórica preservada). | `test_change_page_must_not_offer_unrelated_inactive_user_as_new_choice` (allocations) e `...for_technical_responsible` (pendencies) RED; `test_change_page_still_preserves_persisted_author_identity`/`...technical_responsible` GREEN. |
| `ManagerDashboardView` agrupa funcionários pela chave `supervisor_email` (o próprio e-mail, não um nome) sem filtrar atividade (U11, correto — é escopo de dados, não apresentação); o template imprime esse e-mail como rótulo do grupo mesmo quando a conta está inativa. Funcionários, linhas de `DailyUserAction` e totais do grupo continuam intactos. | `test_manager_dashboard_must_not_reveal_inactive_supervisor_email` e `...actions_also_reveal...` RED; `test_manager_dashboard_preserves_employee_and_group_totals` GREEN (carteira "Alimentos" e `total_logged == 1` preservados). |
| `pendencies/services.py::notify_observation_change` já filtra `is_active=True` nos destinatários (U18) — nenhuma regressão necessária. | `test_inactive_role_matching_recipient_does_not_receive_notification` GREEN. |
| `telecom/line_timeline.py` resolve autores por `SystemUser.objects.filter(pk__in=actor_ids)` sem filtro de atividade (U19, correto — autoria histórica deve ser preservada) — a identidade do autor inativo é retornada e rotulada normalmente, tanto no label individual quanto nas opções de filtro. | `test_actor_label_still_resolves_inactive_author_email` e `...actor_choice` GREEN. |
| **Achado de infraestrutura de teste, pré-existente e fora de escopo desta tarefa:** `dashboard/tests.py` (módulo legado, 2446 linhas) e `dashboard/tests/` (pacote com `__init__.py`) colidem no mesmo nome de import `dashboard.tests`. O Python sempre resolve o pacote primeiro; `pytest dashboard/tests.py` isolado também falha com `import file mismatch`. Não foi alterado — é o mesmo problema já documentado no cabeçalho de `telecom/tests_line_timeline.py` ("como já documentado para o app dashboard"). `dashboard/tests/` (onde o novo teste UVI-03 vive) roda normalmente sob pytest. | `pytest dashboard/tests.py` isolado → `ERROR dashboard/tests.py: import file mismatch`. |

### Implementation Plan — execução desta etapa

1. Leitura integral de UVI-01/UVI-02 e confirmação dos caminhos reais (`users/models.py`, `users/admin.py`, `employees/forms.py`, `employees/views.py`, `employees/admin.py`, `allocations/forms.py`, `allocations/admin.py`, `pendencies/admin.py`, `pendencies/services.py`, `dashboard/views.py`, `dashboard/forms.py`, `telecom/line_timeline.py`, templates `employee_list.html`/`employee_detail.html`, `core/mixins.py::RoleRequiredMixin`) antes de escrever qualquer teste.
2. Confirmação de nomes de rota reais via `django/contrib/auth/admin.py` instalado (Django 5.2.11) — descartou a suposição inicial de `admin:users_systemuser_password_change` (não existe; o nome é fixo `admin:auth_user_password_change`).
3. Criação dos seis arquivos de teste (nenhum código de aplicação alterado).
4. Execução isolada por arquivo, depois suíte UVI-03 completa, depois regressão proporcional app por app (ver Test Strategy).
5. Uma correção de teste após observar causa real: `dashboard/tests/test_uvi03_inactive_account_visibility.py::test_manager_dashboard_preserves_employee_and_group_totals` assumia que `manager_dashboard.html` imprime `full_name` do funcionário; a execução mostrou que o template só agrega por carteira (sem nome individual). Trocada a asserção para a carteira "Alimentos" e os totais de contexto — causa comprovada pelo HTML real capturado no primeiro RED, documentada no próprio teste.
6. `manage.py check` e `git diff --check` executados ao final (ambos limpos; `git diff --check` não cobre os arquivos novos por serem untracked — verificação manual de trailing whitespace feita via grep, sem ocorrências).

### Test Checklist — resultado por node ID (T01–T14)

| Node ID | Requisito (resumo) | Superfície real | Camada/etapa | Resultado nesta rodada | Causa observada |
|---|---|---|---|---|---|
| T01 | Lista/busca/contagem/paginação não revelam inativas a papel restrito | `SystemUserAdmin` changelist | Backend — UVI-04 | 3 RED, 2 GREEN (controle ADMIN/DEV) | Queryset do Admin não filtra por role nem por `is_active` combinado a role |
| T02 | Acesso direto (change/delete/history/password) 404 genérico; POST forjado não muta estado | `SystemUserAdmin` URLs diretas | Backend — UVI-04 | 4 RED (change/delete/history/password), 3 GREEN (negação de permissão, acesso a conta ativa, ADMIN preservado) | Nenhuma proteção de objeto por role implementada; `get_object`/`get_queryset` do `ModelAdmin` não restringem por `is_active`+role |
| T03 | Popup/ações em lote/autocomplete não revelam identidade oculta | `SystemUserAdmin` sem `autocomplete_fields`/`raw_id_fields` registrados (confirmado em UVI-02, U22) | Backend — UVI-04 | Controle preexistente/N-A — não há widget de popup/autocomplete apontando para `SystemUser` hoje; ação em lote coberta em T02 (`delete_selected`) | Superfície de popup inexistente no inventário real; reavaliar se UVI-04 introduzir `autocomplete_fields` |
| T04 | ADMIN/DEV autorizados vs. papel restrito; `is_staff`/`is_superuser` não substituem exceção de role | `SystemUserAdmin`; `EmployeeForm`/`CombinedRegistrationForm` (sem contexto de viewer) | Backend — UVI-04 | 1 RED dedicado (is_staff+is_superuser não blinda) + GREEN de ADMIN/DEV embutidos em T01/T02; formulários sem viewer cobertos em T05/T06 | Política por role inexistente; forms não recebem viewer algum hoje |
| T05 | Seletores só oferecem candidatos visíveis | `EmployeeForm.corporate_email`/`CombinedRegistrationForm.corporate_email` | Backend — UVI-04 | 2 RED, 2 GREEN (supervisor ativo presente) | Consulta de choices sem filtro `is_active` (U05/U06) |
| T06 | ID/e-mail forjado rejeitado no servidor; zero ativos não libera entrada livre | `EmployeeForm.clean_corporate_email` | Backend — UVI-04 | 2 RED (forjado aceito; fallback livre aceita inativo), 1 GREEN (e-mail ativo aceito como controle) | `clean_corporate_email` só valida contra lista que já inclui inativos; lista vazia desativa a validação inteira |
| T07 | FK operacional filtra novas escolhas; autoria histórica preservada | `LineAllocationAdmin` (`allocated_by`/`released_by`), `AllocationPendencyAdmin` (`technical_responsible`/`updated_by`) | Backend/Interface — UVI-04 e UVI-05 | 2 RED (outro inativo oferecido), 2 GREEN (vínculo persistido preservado) | Nenhum `fieldsets`/`raw_id_fields`/`autocomplete_fields` restringe o `<select>` padrão do `ModelForm` |
| T08 | Lista/AJAX/detalhe/painel neutralizam identidade; funcionários/grupos/totais preservados | `employee_list.html`+AJAX, `employee_detail.html`, `manager_dashboard.html` | Interface — UVI-05 | 5 RED (identidade exposta em HTML/JSON/painel), 1 GREEN (totais e carteira preservados) | Templates/contexto imprimem `corporate_email`/`manager_email`/`supervisor` sem neutralização alguma (U08/U09/U10) |
| T09 | Desativar supervisor não reduz escopo de funcionários/linhas | `scope_employee_queryset`, `get_managed_supervisor_emails` | Backend — controle preexistente | GREEN por desenho (U11): não há `is_active` nessas consultas; não exercitado por teste dedicado nesta rodada — reuso recomendado de `dashboard/tests/test_manager_dashboard_removed_supervisor.py` como controle equivalente de escopo | Decisão explícita do contrato (UVI-02) de não tocar essas consultas; sem mudança, sem regressão a provar aqui |
| T10 | Histórico/timeline/relatórios retêm autores inativos; DEV não ganha acesso ADMIN-only | `telecom/line_timeline.py`; `TELECOM_HISTORY_ALLOWED_ROLES` já inclui todos os roles (confirmado em `telecom/views.py`, não é concessão nova) | Backend — controle preexistente | 2 GREEN (autor preservado); acesso de DEV a relatórios é controle preexistente não novo, não testado nesta rodada por já estar fora do escopo de mudança | `SystemUser.objects.filter(pk__in=...)` sem `is_active`; `TELECOM_HISTORY_ALLOWED_ROLES` já era `= all roles` antes desta feature |
| T11 | GET ativo/POST inativo (desativação entre requisições) reavaliada no servidor | Qualquer form com contexto de viewer (ainda inexistente) | Backend — UVI-04 | Não executável ainda: não há política de reavaliação para reavaliar. Diferido para UVI-04 (quando a policy existir, repetir o cenário GET/POST com desativação no meio) | Pré-requisito (política contextual) inexistente hoje; criar o teste antes da política seria mock da regra, proibido pelo guia |
| T12 | Custo de consulta sem crescimento linear; isolamento entre viewers | Caminhos alterados em UVI-04/05 (ainda não alterados) | Backend — UVI-04/05 | Diferido: sem filtro novo implementado, não há consulta adicional a medir ainda; medir como parte da revisão de UVI-04/05 | Não há política nova cujo custo possa ser comparado nesta rodada |
| T13 | Constantes/notificações/autenticação preservadas | `pendencies/services.py::notify_observation_change`; `dashboard/forms.py` (constantes B2B/B2C_SUPERVISORS) | Backend — controle preexistente | 1 GREEN (notificação já filtra `is_active`); constantes de `dashboard/forms.py` não são contas `SystemUser` (U20), não exercitadas por não serem o domínio desta feature | `_NOTIFIABLE_BY_*` já filtra `is_active=True`; constantes não têm relação com `SystemUser` |
| T14 | Navegador real: foco, teclado, estado vazio, troca de escolha, responsivo | UI real (nenhuma automatizável por `Client`) | Aceite navegador — UVI-06 | Não executado (fora de escopo desta etapa, por definição) | Reservado para UVI-06 conforme Test Strategy |

### Test Strategy

- pytest (`DJANGO_SETTINGS_MODULE=config.settings_dev`, via `venv/Scripts/python.exe -m pytest`), banco isolado por teste (`TestCase` padrão do Django), execução sequencial por app e depois em conjunto.
- `Client`/`force_login` reais contra URLs reais nomeadas (`reverse(...)`), nunca mocks de view ou de política. Formulários instanciados e validados de ponta a ponta (`form.is_valid()`), nunca stub de `clean_*`.
- Controles positivos sempre pareados com o RED correspondente (ex.: supervisor ativo nas choices, conta ativa acessível, autor persistido preservado) para provar que a consulta alcançou dados reais e que a rota foi de fato exercitada — nenhum GREEN vácuo foi aceito como requisito cumprido sem esse pareamento.
- Ausência de escrita provada por estado persistido (`refresh_from_db()`, `SystemUser.objects.filter(pk=...).exists()`), não apenas pelo status HTTP da resposta.
- Nenhum teste parseia página de erro como resposta válida; os 404 esperados (T02) são comparados por `status_code`, com o corpo da resposta de erro verificado apenas para ausência do e-mail, nunca como conteúdo funcional.
- Regressão executada app por app (não somada por sobreposição): `users` (19 testes, 10 pré-existentes + 9 novos RED), `employees` (76 testes, 70 pré-existentes GREEN + 6 novos RED), `allocations` (45 testes, 43 pré-existentes/controles GREEN + 2 novos RED), `pendencies` (115 testes + 14 subtests, pré-existentes GREEN + 1 novo RED e 2 novos GREEN), `dashboard/tests/` pacote (102 testes + 7 subtests, pré-existentes GREEN + 2 novos RED e 1 novo GREEN), `telecom` (545 testes + 1 skip + 5 subtests, todos GREEN incluindo os 2 novos). `dashboard/tests.py` (módulo legado) não pôde ser coletado isoladamente sob pytest por colisão de nome pré-existente com o pacote `dashboard/tests/` (ver Gap Analysis) — não presumido como "passou" nem "falhou": registrado como não executável nesta ferramenta.
- PostgreSQL não foi usado: nenhuma alegação de concorrência/locking foi feita nesta rodada (T11/T12 diferidos). SQLite (banco de teste padrão do projeto) não foi apresentado como prova de garantias específicas de Postgres.
- Navegador real não foi usado (T14 fora de escopo, reservado a UVI-06).

### Compliance Report

UVI-03 concluída. Seis arquivos de teste novos criados (`users/`, `employees/tests/`, `allocations/tests/`, `pendencies/tests/`, `dashboard/tests/`, `telecom/`), nenhum arquivo de produção alterado, nenhuma migration, nenhum `git add`/commit/push/deploy, nenhum acesso a PRD. `manage.py check` sem issues. `git diff --check` sem problemas nos arquivos rastreados (os seis novos são untracked; verificados manualmente contra trailing whitespace, sem ocorrências).

Resultado agregado da suíte nova (execução única, todos os seis arquivos juntos): **35 coletados — 20 FAILED (RED) e 15 PASSED (GREEN)**, sem ERROR e sem SKIPPED, sem subtestes nesta suíte específica. Todo RED corresponde a uma violação contratual real, inspecionada na resposta/estado persistido (nunca uma falha de coleta, import ou fixture); todo GREEN é controle positivo pareado (prova de alcance de rota/dados) ou controle preexistente documentado como tal — nenhum GREEN foi contado como requisito cumprido sem essa prova.

Uma correção de teste foi feita e documentada (ver Implementation Plan item 5) — causa comprovada pelo HTML real da primeira execução, não suposição. Nenhuma regra de negócio foi afrouxada para facilitar fixture; nenhuma fixture de produto foi alterada.

Ambiguidade registrada, não decidida (fora do escopo de UVI-03 decidir produto): T03 (popup/autocomplete) não tem superfície real hoje para `SystemUser` — se UVI-04/05 introduzir `autocomplete_fields` para reduzir o `<select>` gigante dos FKs de T07, essa mesma introdução pode reabrir uma superfície de popup que precisará de teste próprio naquele momento, não antes.

T09/T11/T12/T13(parcial)/T14 não têm teste RED dedicado nesta rodada pelos motivos registrados na Test Checklist (controle preexistente sem mudança a provar, pré-requisito de política ainda inexistente, ou fora de escopo por definição/navegador). Isso não é lacuna de cobertura esquecida: é a classificação correta pedida pelo guia (não forçar RED onde não há violação exercitável sem inventar política ainda não decidida).

Próxima tarefa: UVI-04 (política backend). Não iniciada — nenhum código de aplicação foi escrito nesta entrega.


## UVI-03a — Conferência corretiva de UVI-03 (2026-10-14)

### Spec Summary

Conferência solicitada antes de iniciar UVI-04, sobre quatro pontos da entrega UVI-03: (1) se os 35 testes originais realmente cobriam T01–T14 ou apenas estavam listados na matriz; (2) se a afirmação "fallback de e-mail livre aceita qualquer e-mail sem validação" estava correta e corretamente delimitada; (3) se os testes de formulário ADMIN-only (`CombinedRegistrationForm`) e de `EmployeeForm` apresentavam política de contexto inexistente como se fosse rota acessível a papéis restritos; (4) se "regressão por app sem quebra" era uma afirmação verificável ou um resumo vago.

Resultado da inspeção direta de cada teste, do código real e dos logs: **os quatro pontos tinham problemas reais**, detalhados abaixo. Todos foram corrigidos nos próprios arquivos de teste (nenhum código de aplicação foi alterado) e a suíte foi reexecutada. Nenhum dos quatro problemas era de "defeito inventado" — eram, em todos os casos, o teste afirmando mais (ou algo diferente) do que a evidência realmente sustentava.

### Gap Analysis — o que estava errado, por ponto

**Ponto 1 — Cobertura dos 35 testes.**

- Achado novo e mais grave desta conferência: a entrega anterior afirmou, na seção UVI-03 original, que "a busca funciona tecnicamente, só falta a política" para `SystemUserAdmin`, citando uma linha de log como evidência. Essa linha de log pertencia a OUTRO teste (a changelist, não a busca). A busca real (`?q=...` no Admin de `SystemUser`) **levanta `django.core.exceptions.FieldError: Cannot resolve keyword 'username' into field`** para QUALQUER usuário (inclusive ADMIN), porque `UserAdmin.search_fields` (herdado, nunca sobrescrito em `SystemUserAdmin`) inclui `"username"`, campo que não existe em `SystemUser` (`username = None`). Isto é um bug pré-existente, não relacionado a esta feature, que impede o sub-item "busca" de T01 de ser exercitado como prova de visibilidade: a funcionalidade quebra antes de qualquer filtro (de role ou de atividade) entrar em jogo. **Esta é a retificação mais importante desta conferência: a afirmação anterior estava errada e é retirada.** Os dois testes de busca foram reescritos para `assertRaises(FieldError)` (um com viewer restrito, um com ADMIN como controle), documentando o achado real em vez de mascará-lo.
- A ação em lote (`delete_selected`) tinha um teste que só fazia o PRIMEIRO passo (POST sem `"post":"yes"`), que apenas renderiza a confirmação — nunca executa a exclusão. O `GREEN` ("conta sobrevive") provava só ausência de execução, não comportamento (GREEN vácuo, exatamente o risco apontado no ponto 4). Reescrito em três testes: confirmação (primeira tela não deve listar a identidade oculta), segundo passo real (`"post":"yes"`) e um controle positivo (a mesma ação em lote remove de fato uma conta visível, provando que a ação funciona e que a sobrevivência da conta oculta não é por a ação estar inerte). **Resultado do segundo passo real: a conta oculta FOI excluída** — achado novo, mais grave que o GREEN anterior sugeria: hoje a ação em lote forjada apaga de verdade a conta oculta.
- Contagem/paginação (T01): reforçado com uma asserção direta sobre `cl.paginator.count` (hoje inclui a conta inativa; o valor correto excluiria só ela).
- Popup/autocomplete (T03): confirmado de novo, sem mudança — nenhum widget de popup aponta para `SystemUser` hoje (`autocomplete_fields`/`raw_id_fields` vazios em todos os ModelAdmins relevantes, por introspecção em UVI-02 e reconfirmado nesta conferência). Classificação "controle preexistente/N-A" mantida.
- Desativação entre GET/POST: ainda não executável sem a política contextual (não inventado; ver Ponto 3). Mantido como pendência de UVI-04.
- Marcador `__keep_current__` (manter vínculo / trocar por ativo / criação-forja / erro em outro campo / ausência de identidade no redisplay): o símbolo em si não existe no código e não foi inventado para gerar RED (proibido pela tarefa). Em vez disso, as partes do requisito que SÃO exercitáveis pela rota real hoje foram testadas: "trocar por ativo" (GREEN, `EmployeeUpdateView` aceita a troca), "erro em outro campo preserva escolha e não expõe identidade" (RED novo — `employee_id` inválido gera erro nesse campo, mas o `<select>` de `corporate_email` redisplay continua mostrando a conta inativa selecionada), e "ausência de identidade no redisplay" (mesmo teste). "Criação/forja" com o literal `__keep_current__` continua não testável sem o símbolo existir — documentado como pendência de UVI-04/05, não como RED.
- Escopo/grupos/totais preservados (T09): a entrega anterior citava `dashboard/tests/test_manager_dashboard_removed_supervisor.py` como controle equivalente. **Retificação:** aquele teste cobre supervisor REMOVIDO (e-mail sem `SystemUser` correspondente, nunca existiu conta), não supervisor DESATIVADO (conta existe, `is_active=False`) — precondições diferentes, não intercambiáveis. Foram escritos dois testes novos e reais (`employees/tests/test_uvi03_inactive_account_visibility.py::T09_...`) desativando um SUPER já vinculado e confirmando que `get_managed_supervisor_emails()` e `scope_employee_queryset()` (GERENTE e BACKOFFICE) continuam incluindo os funcionários — GREEN, por desenho (U11), agora com prova direta em vez de referência incorreta.
- Referências históricas (T10): sem mudança — `telecom/test_uvi03_inactive_author_preservation.py` já prova isso, confirmado estável nesta conferência.
- Custo de consultas / isolamento entre viewers (T12): a parte de "isolamento entre viewers" TEM cobertura preexistente exata e foi referenciada (não duplicada): `employees/tests.py::test_backoffice_cannot_access_unrelated_employee_update` (linha 369), `::test_manager_cannot_access_unrelated_employee_update` (linha 393) e `::test_backoffice_can_access_employee_list_with_linked_supervisor_scope` (linha 354) — provam que o escopo por viewer já é isolado e não depende de `is_active`, logo não regride com esta feature. A parte de "custo de consulta sem crescimento linear" continua não mensurável: nenhuma política nova foi implementada ainda, não há "antes/depois" real para comparar sem simular a política futura (proibido). Mantido como pendência de UVI-04/05.

**Ponto 2 — Fallback de e-mail livre.**

A entrega anterior tinha um teste (`T06b`) que criava UM supervisor inativo e chamava isso de "fallback de texto livre". Está errado: com uma linha de `SystemUser` (ativa ou inativa) para o role, `_allowed_supervisor_emails` não fica vazio, então `supervisor_choices` também não fica vazio, e o campo permanece `<select>` — NUNCA cai para `TextInput`. O `TextInput` só aparece quando existem **zero linhas de `SystemUser` com aquele role no banco**, não "zero ativas com inativas existindo" (essa distinção simplesmente não existe no código hoje, porque nada filtra por `is_active` ainda). Reclassificado em dois testes:
- `T06b_SingleInactiveSupervisorIsStillTheOnlySelectChoiceTest` — renomeado e re-documentado: é a MESMA causa de T05/T06 (vazamento via `<select>`), só no caso extremo de cardinalidade 1, não uma rota distinta.
- `T06c_ZeroSupervisorRowsFreeTextFallbackPreservesLegacyBehaviorTest` (novo) — cenário REAL de zero linhas: confirma que o `TextInput` aceita um e-mail **sem conta correspondente** (categoria "b" do ponto 2) — comportamento legado explicitamente preservado pelo contrato ("valores sem conta correspondente conservam tratamento anterior"), classificado como **GREEN**, não como defeito novo. Não existe hoje, e não foi criado um teste para, um cenário de "conta inativa exposta via TextInput real" porque esse cenário não é alcançável no código atual (qualquer linha de SUPER, ativa ou inativa, impede o TextInput) — a distinção pedida no ponto 2 ("zero candidatos atual" vs. "zero candidatos visíveis após filtragem futura") é real e só a segunda forma exporia esse caso, o que exigiria simular a política ainda não implementada (proibido). Registrado como esclarecimento, não como pendência de teste.

**Ponto 3 — Forms ADMIN-only e contexto.**

Confirmado por leitura direta: `CombinedRegistrationForm` é instanciado SOMENTE por `RegistrationHubView` (`allowed_roles=[SystemUser.Role.ADMIN]`, `allocations/views.py:27`). A entrega anterior testava o form isolado (sem HTTP, sem viewer) e afirmava RED ("não deve incluir inativo"), o que apresentava a ausência de uma fronteira de contexto como se fosse uma violação alcançável por papel restrito — mas o ÚNICO chamador real é ADMIN, que o próprio contrato exime da restrição de seletores operacionais ("aos papéis restritos", item 6) e da visibilidade de contas inativas em geral (Spec Summary/UVI-01). **Reclassificado para GREEN** (`T04_CombinedRegistrationFormAdminOnlyExceptionTest`): um teste de controle confirma que a rota é de fato ADMIN-only, e dois testes confirmam que a tela que ADMIN realmente usa (`allocations:allocation_list`) oferece o supervisor inativo como opção — consistente com a exceção, não uma falha. O gap estrutural (form sem parâmetro de contexto, reutilizável sem proteção se algum dia uma rota de papel restrito o chamar) foi documentado em prosa, sem assertiva de teste, porque não há rota real a testar hoje.

O mesmo problema existia no Admin de `LineAllocation`/`AllocationPendency` (T07): o Django Admin não é protegido pelo `RoleRequiredMixin` (só por `is_staff` + permissão de modelo Django), então testar com viewer ADMIN não prova nada sobre os quatro papéis restritos. Cada arquivo (`allocations`, `pendencies`) foi dividido em: um controle ADMIN (GREEN — exceção preservada, viewer ADMIN continua vendo a conta inativa como opção) e um teste novo com viewer genuinamente restrito (SUPER/GERENTE, com `is_staff` e permissões concedidas manualmente — cenário administrativamente possível) que produz o RED inequívoco (`T07b_*`).

Confirmado também: `EmployeeForm` É diferente — `EmployeeUpdateView.allowed_roles = SystemUser.EMPLOYEE_ACCESS_ROLES` inclui SUPER/BACKOFFICE/GERENTE (não só ADMIN), e `get_form_kwargs` não propaga nenhum viewer ao form (confirmado em `employees/views.py`). Os testes de `EmployeeForm` (T05/T06) continuam válidos como estavam, e foram REFORÇADOS com `T05b_EmployeeUpdateViewRealRouteLeaksInactiveSupervisorTest`, que exercita a mesma causa pela rota HTTP real, logado como BACKOFFICE, com um controle de alcance prévio (`test_backoffice_can_reach_the_employee_update_route_as_control`, 200) para provar que a rota foi de fato alcançada antes de qualquer assertiva de violação — respondendo directly ao pedido do ponto 3 de não apresentar política de form isolado como rota acessível sem essa prova.

Ambiguidade registrada, não decidida: o contrato não resolve explicitamente se a máscara de identidade em `employee_list`/`employee_detail` (T08) também vale para ADMIN (que preserva visibilidade de CONTAS inativas em outras superfícies) ou só para os quatro papéis restritos. O teste original (`T08`, viewer ADMIN) foi mantido como está — ainda é um RED válido sob a leitura "hoje não existe máscara para ninguém", independente de como essa ambiguidade for resolvida — e um teste paralelo inequívoco (`T08b`, viewer BACKOFFICE) foi adicionado para não depender dela.

**Ponto 4 — Regressão e contagens.**

"Regressão por app sem quebra" era um resumo, não uma evidência auditável, e não distinguia a suíte nova da regressão nem mostrava os comandos. Corrigido na seção Test Strategy abaixo: comandos completos, coletados/PASSED/FAILED/ERROR/SKIPPED por app, subtestes separados, sobreposição explicitada (a suíte nova é um SUBCONJUNTO de cada regressão por app, não uma soma adicional), e toda falha nova confirmada por causa real (reexecutada e inspecionada nesta conferência, não presumida do relato anterior).

### Implementation Plan — correções aplicadas nesta conferência

1. `users/test_uvi03_admin_inactive_visibility.py`: busca reescrita para `assertRaises(FieldError)` (achado novo, retificação do relato anterior); ação em lote dividida em confirmação/segundo passo real/controle positivo; asserção de `paginator.count` adicionada a T01; nova classe `U04_BackofficeSupervisorLinkValidationIgnoresActivityTests` (model `full_clean()` + rota real do Admin) para o gap U04 (vínculo backoffice→supervisor não valida atividade).
2. `employees/tests/test_uvi03_inactive_account_visibility.py`: `T06b` renomeado/re-documentado (mesma causa de T05/T06, não fallback de texto livre); `T06c` novo (GREEN real do fallback de texto livre genuíno); `T05b` novo (rota HTTP real via `EmployeeUpdateView`, viewer BACKOFFICE, com controle de alcance, GET de edição e redisplay inválido); `T08b` novo (viewer restrito inequívoco, paralelo ao T08 com viewer ADMIN ambíguo); `T09` novo (desativação real de supervisor vinculado, GERENTE e BACKOFFICE, substituindo a referência incorreta ao teste de supervisor removido).
3. `allocations/tests/test_uvi03_inactive_account_visibility.py`: `T04` (CombinedRegistrationForm) reclassificado de RED para GREEN com controle de alcance ADMIN-only; `T07` dividido em controle ADMIN (GREEN) e `T07b` com viewer SUPER staff restrito (RED).
4. `pendencies/tests/test_uvi03_inactive_account_visibility.py`: mesma divisão do item 3, com `T07b` usando viewer GERENTE staff restrito.
5. `dashboard/tests/test_uvi03_inactive_account_visibility.py` e `telecom/test_uvi03_inactive_author_preservation.py`: inspecionados, sem alteração — `ManagerDashboardView.allowed_roles = [GERENTE]` já é um papel genuinamente restrito (sem a ambiguidade do ponto 3), e os testes de preservação de autoria continuam corretos.
6. Nenhum código de aplicação, migration, fixture de produto ou regra de negócio foi alterado. Nenhum teste foi enfraquecido para facilitar a correção — todas as correções tornaram as afirmações MAIS precisas (algumas mais severas: o achado do `delete_selected` real e do `FieldError` na busca são PIORES, não melhores, que o relato anterior).

### Test Checklist — matriz reconciliada (T01–T14)

| Node ID | Classificação (UVI-03 original) | Classificação reconciliada (UVI-03a) | O que mudou |
|---|---|---|---|
| T01 | 3 RED, 2 GREEN | 2 RED (changelist/contagem+paginação) + 2 GREEN (ADMIN/DEV) + 2 testes novos de ERRO real (`FieldError`) para busca, substituindo os 2 RED anteriores do sub-item busca | Retificação: busca não é "falta política", é bug pré-existente que quebra a funcionalidade para qualquer usuário |
| T02 | 4 RED, 3 GREEN | Inalterado (4 RED: change/delete/history/password; 3 GREEN: negação de permissão, conta ativa acessível, ADMIN preservado) | Confirmado estável, sem mudança de causa |
| T03 | Controle preexistente/N-A | Inalterado | Reconfirmado: nenhum widget de popup aponta para SystemUser hoje |
| T04 | 1 RED dedicado (is_staff/superuser) + GREEN embutidos | Inalterado para `SystemUserAdmin`; **retificado** para `CombinedRegistrationForm` (RED→GREEN, ponto 3) | Form ADMIN-only reclassificado; `is_staff`/`is_superuser` RED continua válido |
| T05 | 2 RED, 2 GREEN (form isolado) | Mantido + reforçado com `T05b` (rota HTTP real, BACKOFFICE, com controle de alcance): 1 RED novo (GET de edição) | Mesma causa, agora provada pela rota real alcançável, não só pelo form isolado |
| T06 | 2 RED, 1 GREEN | Mantido + `T06b` reclassificado (mesma causa de T05/T06, não "fallback") + `T06c` novo GREEN (fallback real, categoria "sem conta correspondente") + `T05b` 1 RED novo (redisplay de erro em outro campo não neutraliza identidade) | Retificação do ponto 2; cobertura do "erro em outro campo" e "ausência de identidade no redisplay" adicionada |
| T07 | 2 RED, 2 GREEN (viewer ADMIN) | Reclassificado: 2 GREEN (viewer ADMIN, exceção preservada) + 2 RED novos (`T07b`, viewer restrito staff) + controles de alcance | Retificação do ponto 3: viewer ADMIN não prova violação para papel restrito |
| T08 | 5 RED, 1 GREEN | Mantido (ambiguidade ADMIN registrada, não resolvida) + `T08b` novo (1 RED com viewer inequivocamente restrito) | Reforço, sem mudança de classificação; ambiguidade agora explícita no texto do teste |
| T09 | "GREEN por desenho... não exercitado por teste dedicado" + referência incorreta a teste de supervisor removido | 2 GREEN novos e reais (desativação de supervisor vinculado, GERENTE e BACKOFFICE) | Lacuna fechada com teste comportamental real; referência incorreta retirada |
| T10 | 2 GREEN | Inalterado, reconfirmado estável | — |
| T11 | Não executável (pré-requisito inexistente) | Inalterado | Ainda depende da política contextual de UVI-04 |
| T12 | Diferido (custo); isolamento não testado dedicadamente | Custo: inalterado (diferido). Isolamento entre viewers: referenciado por 3 testes preexistentes exatos (`employees/tests.py` linhas 354/369/393), sem duplicação | Lacuna do "isolamento" fechada por referência, não por teste novo redundante |
| T13 | 1 GREEN (notificação) + constantes fora do domínio | Inalterado | — |
| T14 | Fora de escopo (UVI-06) | Inalterado | — |

### Test Strategy

Comandos executados nesta conferência (todos via `venv/Scripts/python.exe -m pytest`, `DJANGO_SETTINGS_MODULE=config.settings_dev`, banco de teste isolado por `TestCase`):

**Suíte nova revisada, isolada por arquivo (para inspecionar causa de cada FAILED/PASSED individualmente):**
- `pytest users/test_uvi03_admin_inactive_visibility.py -v` → 21 coletados, **10 FAILED, 11 PASSED**, 0 ERROR, 0 SKIPPED.
- `pytest employees/tests/test_uvi03_inactive_account_visibility.py -v` → 17 coletados, **8 FAILED, 9 PASSED**, 0 ERROR, 0 SKIPPED.
- `pytest allocations/tests/test_uvi03_inactive_account_visibility.py -v` → 8 coletados, **1 FAILED, 7 PASSED**, 0 ERROR, 0 SKIPPED.
- `pytest pendencies/tests/test_uvi03_inactive_account_visibility.py -v` → 6 coletados, **1 FAILED, 5 PASSED**, 0 ERROR, 0 SKIPPED.
- `pytest dashboard/tests/test_uvi03_inactive_account_visibility.py -v` → 3 coletados, **2 FAILED, 1 PASSED** (inalterado desta conferência).
- `pytest telecom/test_uvi03_inactive_author_preservation.py -v` → 2 coletados, **0 FAILED, 2 PASSED** (inalterado desta conferência).

**Suíte nova revisada, os seis arquivos juntos em uma única execução** (`pytest users/test_uvi03_admin_inactive_visibility.py employees/tests/test_uvi03_inactive_account_visibility.py allocations/tests/test_uvi03_inactive_account_visibility.py pendencies/tests/test_uvi03_inactive_account_visibility.py dashboard/tests/test_uvi03_inactive_account_visibility.py telecom/test_uvi03_inactive_author_preservation.py -v`): **57 coletados, 22 FAILED, 35 PASSED, 0 ERROR, 0 SKIPPED**, sem subtestes nesta suíte específica. (21+17+8+6+3+2 = 57, soma simples pois são arquivos distintos sem sobreposição entre si.)

**Regressão proporcional, por app, suíte nova incluída (não somada de novo — é a MESMA execução dos testes acima, agora dentro do app inteiro):**
- `pytest users -q` → **25 coletados, 10 FAILED, 15 PASSED**, 0 ERROR, 0 SKIPPED. Os 10 FAILED são exatamente os 10 da suíte nova isolada; os 15 PASSED = 11 novos GREEN + 4 pré-existentes (`users/tests.py::SystemUserRoleTests`, inalterados). **Nenhuma regressão.**
- `pytest employees -q` → **85 coletados, 8 FAILED, 77 PASSED**, 0 ERROR, 0 SKIPPED. Os 8 FAILED são os 8 da suíte nova; os 77 PASSED = 9 novos GREEN + 68 pré-existentes (inalterado desde a entrega original). **Nenhuma regressão.**
- `pytest allocations -q` → **49 coletados, 1 FAILED, 48 PASSED**, 0 ERROR, 0 SKIPPED. O 1 FAILED é o `T07b` novo; os 48 PASSED = 7 novos GREEN + 41 pré-existentes. **Nenhuma regressão.**
- `pytest pendencies -q` → **104 coletados (+ 14 subtestes separados), 1 FAILED, 103 PASSED**, 0 ERROR, 0 SKIPPED. O 1 FAILED é o `T07b` novo. **Nenhuma regressão.**
- `pytest dashboard/tests/ -q` → **102 coletados (+ 7 subtestes separados), 2 FAILED, 100 PASSED**, 0 ERROR, 0 SKIPPED. Os 2 FAILED são os 2 já conhecidos de T08. **Nenhuma regressão.**
- `pytest dashboard/tests.py -q` (módulo legado) → continua **não coletável isoladamente** sob pytest (`ERROR: import file mismatch`, colisão de nome pré-existente `dashboard.tests` entre o módulo e o pacote `dashboard/tests/` com `__init__.py` — Python resolve o pacote primeiro). Não corrigido nesta tarefa (fora de escopo, conforme instrução explícita). Não contado como PASSED nem FAILED — registrado como não executável por esta ferramenta.
- `telecom`: não reexecutado nesta conferência (nenhum arquivo de telecom foi alterado); evidência reaproveitada da entrega original (**545 coletados, 544 PASSED, 1 SKIPPED, 5 subtestes passed**, incluindo os 2 testes T10 novos). Sobreposição explícita: esses 2 testes já estavam contados nesses 545; não somados de novo aqui.

Nenhuma suíte foi somada com outra que a contivesse (users/employees/allocations/pendencies/dashboard têm seus totais próprios acima; a "suíte nova" de 57 é citada separadamente da regressão por app exatamente para não duplicar). Toda falha nova foi reaberta e inspecionada por causa real nesta conferência (resposta HTTP, estado persistido ou traceback completo), não presumida do relato anterior — dois achados pioraram em relação ao relato anterior (busca quebrada por `FieldError`; exclusão em lote forjada realmente remove a conta oculta), e três testes foram corrigidos por causa própria comprovada no HTML/traceback real (T06c `AttributeError` por acessar `.choices` em `TextInput`; `test_invalid_post_redisplay` por campo `full_name` desabilitado não gerar erro; mensagem de erro de `employee_id` em locale pt-br).

### Compliance Report

Os quatro pontos levantados eram procedentes:

1. **Cobertura:** parcialmente incompleta e com uma afirmação factualmente errada (busca). Fechada nesta conferência com achados mais precisos (inclusive mais graves em dois casos) e dois gaps comportamentais novos (T09 real, U04).
2. **Fallback de e-mail livre:** a afirmação original estava mal delimitada, confundindo "um supervisor inativo" com "zero candidatos". Corrigida com reclassificação e um teste GREEN novo que preserva corretamente o comportamento legado da categoria "e-mail sem conta correspondente".
3. **Forms ADMIN-only:** a entrega original apresentou política de formulário isolado, sem viewer e sem rota, como se fosse violação alcançável por papel restrito — procedente para `CombinedRegistrationForm` (agora GREEN) e para os Admins de `LineAllocation`/`AllocationPendency` (agora divididos em controle ADMIN + RED com viewer restrito real). Para `EmployeeForm`, a rota restrita é real (`EmployeeUpdateView`) e o RED foi reforçado com prova de alcance, não retirado.
4. **Regressão e contagens:** "sem quebra" era verdadeiro, mas não verificável a partir do relato anterior. Nesta conferência, cada execução foi refeita com comando, contagem completa (coletados/PASSED/FAILED/ERROR/SKIPPED/subtestes) e confirmação de que toda falha é a esperada (nenhuma regressão real em nenhum app).

Retificações explícitas registradas (afirmações da entrega anterior que estavam erradas e são retiradas):
- "Busca funciona tecnicamente, só falta a política" — **errado**; busca levanta `FieldError` para qualquer usuário, bug pré-existente não relacionado a esta feature.
- "Ação em lote (`delete_selected`) com ID forjado não remove a conta oculta" (GREEN) — **incompleto/vácuo**; o teste nunca executava o passo real. O passo real EXCLUI a conta oculta.
- "`CombinedRegistrationForm` não deve incluir supervisor inativo nas opções" (RED) — **mal enquadrado**; o único chamador real é ADMIN, exceto da restrição. Reclassificado para GREEN.
- "Admin de `LineAllocation`/`AllocationPendency` com viewer ADMIN não deve oferecer conta inativa" (RED) — **mal enquadrado** pela mesma razão; reclassificado para GREEN de controle, com RED real movido para viewer restrito.
- "Cenário de um único supervisor inativo = fallback de texto livre" — **impreciso**; é o ramo `<select>`, mesma causa de T05/T06.
- Referência a `dashboard/tests/test_manager_dashboard_removed_supervisor.py` como controle equivalente para T09 (supervisor desativado) — **referência incorreta** (precondição "removido" ≠ "desativado"); substituída por dois testes novos e reais.

Nenhuma regra de negócio foi enfraquecida para fechar estes pontos; nenhum `pytest.fail` incondicional foi usado; nenhum símbolo futuro (`__keep_current__` literal) foi inventado — onde a cobertura dependia dele, foi registrada como pendência explícita de UVI-04/05, não simulada. `manage.py check`: sem issues. `git diff --check`: sem problemas nos arquivos rastreados; os arquivos de teste novos/alterados são untracked, verificados manualmente contra espaço em branco no fim de linha (`grep -rnP "[ \t]+$"`), sem ocorrências. Nenhum código de aplicação, migration, stage, commit, push, deploy ou acesso a PRD nesta conferência.

### Veredito final

**UVI-03 concluída**, com as correções desta conferência incorporadas aos mesmos seis arquivos de teste (nenhum arquivo novo de teste fora do conjunto já entregue). Pendências identificadas e registradas para etapas posteriores, não bloqueantes para iniciar UVI-04:

- T11 (reavaliação GET/POST) e a parte "custo de consulta" de T12 continuam não executáveis até existir uma política real para medir — não é lacuna de UVI-03, é dependência de UVI-04.
- "Criação/forja" do marcador `__keep_current__` e a UI de redisplay com rótulo neutro continuam pendentes de UVI-04 (política) e UVI-05 (interface) — o símbolo não existe ainda, por desenho.
- O bug de busca quebrada (`FieldError` em `SystemUserAdmin`) é um achado NOVO desta conferência, pré-existente e não relacionado à feature de visibilidade: fica registrado aqui como ambiguidade/achado para decisão externa (corrigi-lo pode ser decisão de produto/manutenção separada; UVI-04 não precisa resolvê-lo para cumprir o contrato de visibilidade, mas o Admin de contas tem uma funcionalidade de busca quebrada para todos os usuários independentemente desta feature).
- A colisão `dashboard/tests.py` vs. `dashboard/tests/` permanece não corrigida, por instrução explícita desta tarefa.

Nenhuma decisão de produto foi tomada por conta própria nesta conferência; as reclassificações (ponto 3) seguem decisões já registradas em UVI-01/UVI-02 (exceção de role ADMIN/DEV) aplicadas com mais rigor às rotas reais, não uma mudança de contrato.


## UVI-04 — Política backend e proteção das entradas (2026-10-14)

### Spec Summary

Implementação da política contextual de visibilidade (SystemUser.is_active + exceção de role ADMIN/DEV) centralizada em `users/visibility.py`, aplicada a todas as entradas reais mapeadas em UVI-02/UVI-03: `SystemUserAdmin` (queryset, busca, 404 genérico, POST forjado, ações em lote), `EmployeeForm`/`EmployeeUpdateView`/`EmployeeCreateView`, `EmployeeAdmin`/`EmployeeAdminForm` (U07, texto livre), `CombinedRegistrationForm`/`RegistrationHubView` (controle ADMIN-only preservado), `LineAllocationAdmin`/`AllocationPendencyAdmin` (FKs de autoria). Marcador `__keep_current__` implementado na fronteira de backend (resolução a partir do objeto persistido, nunca de `self.instance` mutado ou de hidden do cliente). Defeito pré-existente da busca do Admin de `SystemUser` (`FieldError` por `search_fields` herdado incluir `"username"`) corrigido com teste próprio, documentado separadamente da política nova. Nenhuma migration, alteração de manager global, de autenticação, de `get_managed_supervisor_emails`/`scope_employee_queryset` ou de notificações.

Apresentação (rótulo neutro "Usuário inativo" em `employee_list`/`employee_detail`/AJAX/`manager_dashboard`, neutralização visual completa do marcador no HTML) continua reservada para UVI-05, conforme contrato — os seis testes correspondentes (T08/T08b de `employees` e T08 de `dashboard`) permanecem RED intencionalmente nesta etapa, por serem presentation-layer, não backend.

### Gap Analysis — lacunas complementadas antes do código correspondente

Baseline reconfirmado por execução real antes de qualquer alteração: `pytest users/test_uvi03_admin_inactive_visibility.py employees/tests/test_uvi03_inactive_account_visibility.py allocations/tests/test_uvi03_inactive_account_visibility.py pendencies/tests/test_uvi03_inactive_account_visibility.py dashboard/tests/test_uvi03_inactive_account_visibility.py telecom/test_uvi03_inactive_author_preservation.py -v` → **57 coletados, 22 FAILED, 35 PASSED**, idêntico ao relatado em UVI-03a. Nenhum número foi ajustado por expectativa; a reconfirmação precedeu qualquer edição de código ou teste.

Lacunas identificadas e fechadas com teste novo **antes** da implementação correspondente (RED real observado e documentado nos próprios arquivos):

| Lacuna | Arquivo novo | Cobertura |
|---|---|---|
| `__keep_current__`: manter vínculo persistido, trocar por ativo, rejeitar criação/forja, rejeitar outro inativo, preservar escolha após erro alheio | `employees/tests/test_uvi04_keep_current_and_cost.py` (classes `KeepCurrentTokenFormUnitTests`, `T05b_KeepCurrentRealRouteTests`) | 9 testes — nível de unidade (form isolado, viewer explícito) e rota HTTP real (`EmployeeUpdateView`, viewer BACKOFFICE) |
| T11 — conta ativa no GET, inativada antes do POST; nova associação bloqueada, banco preservado | mesmo arquivo, classe `T11_DeactivationBetweenGetAndPostTest` | 2 testes: GET prova alcance (conta ainda ativa aparece), POST após desativação é rejeitado e `Employee.corporate_email` permanece o valor anterior (`refresh_from_db`) |
| T12 — custo de consulta sem crescimento linear; isolamento entre viewers | mesmo arquivo, classe `T12_QueryCostAndViewerIsolationTest` | 2 testes: `CaptureQueriesContext` comparando 2 vs. 22 contas (mesma contagem de queries); duas instâncias de `EmployeeForm` com viewers diferentes em sequência não contaminam uma à outra, e o mesmo viewer produz o mesmo resultado em chamadas sucessivas |
| Exclusão em lote: confirmação final executada e conta oculta preservada no banco | já existia em `users/test_uvi03_admin_inactive_visibility.py::T02b_ForgedPostMustNotMutateHiddenAccountTests` (conferência corretiva já havia dividido em confirmação/segundo passo real/controle positivo) | Reexecutado nesta etapa como parte da suíte — GREEN confirmado após a implementação (ver Test Checklist) |
| U07 — `EmployeeAdmin`/`EmployeeAdminForm`: caminho de texto livre sem cobertura alguma em UVI-03 | `employees/tests/test_uvi04_admin_free_text_association.py` | 4 testes: viewer restrito não associa a oculta nova, pode trocar por ativa, preserva vínculo oculto já persistido sem alterar, controle ADMIN preserva exceção |
| Busca quebrada (`FieldError`) — defeito preexistente, não a política | `users/test_admin_search_field_defect.py` | 2 testes dedicados, RED→GREEN comprovado empiricamente (ver Test Strategy) |

Classificação por node ID (backend/UVI-04 vs. interface/UVI-05 vs. controle) — ver matriz consolidada na seção Test Checklist abaixo. Nenhum GREEN de apresentação (T08/T08b) foi exigido nesta etapa.

**Retificação do fechamento de UVI-03**: a entrega de UVI-03a já havia registrado T11/T12/`__keep_current__`(criação-forja)/U07 como pendências explícitas, não lacunas esquecidas. Esta etapa fecha essas pendências com testes reais antes do código correspondente, preservando o histórico das três entregas anteriores (nenhum arquivo de teste UVI-03 foi removido; apenas dois testes foram reclassificados por mudança de comportamento real — ver "Retificações" abaixo).

### Defeito pré-existente da busca — separado da política nova

`django.contrib.auth.admin.UserAdmin.search_fields` (herdado, nunca sobrescrito em `SystemUserAdmin`) incluía `"username"`, campo inexistente em `SystemUser` (`username = None`, `USERNAME_FIELD = "email"`). Qualquer busca (`?q=`) no Admin de contas levantava `django.core.exceptions.FieldError` para **qualquer** viewer, inclusive ADMIN, independente de `is_active`.

Processo seguido (RED→GREEN comprovado empiricamente, não presumido):
1. Teste dedicado criado em `users/test_admin_search_field_defect.py`.
2. `search_fields = ("email",)` temporariamente removido de `users/admin.py` → suíte executada → **RED real confirmado**: `FieldError: Cannot resolve keyword 'username' into field` propagando sem captura, e `assertNotIn("username", ...)` falhando.
3. Correção mínima restaurada (`search_fields = ("email",)`, o único campo real de login do cadastro) → suíte reexecutada → **GREEN**.

Os dois testes antigos de `users/test_uvi03_admin_inactive_visibility.py` que documentavam o defeito via `assertRaises(FieldError)` foram reescritos (o defeito que eles provavam está corrigido) para passar a provar a **política** sobre a busca já funcional: `test_search_feature_is_fixed_and_respects_restricted_role_visibility` (papel restrito buscando pelo e-mail da conta oculta não a encontra — comparado por `cl.result_list`/`cl.paginator.count`, nunca pelo HTML inteiro, pois a caixa de busca ecoa de volta o termo digitado pelo próprio viewer, o que não é vazamento de identidade), `test_search_finds_active_account_for_restricted_role` (controle positivo — busca não está simplesmente quebrada/vazia) e `test_search_finds_inactive_account_for_admin_and_dev` (controle positivo — exceção de role preservada na busca).

### Achado real durante a regressão (não previsto no plano inicial)

Ao rodar a suíte completa do app `employees` (não apenas o arquivo isolado), `T05b_EmployeeUpdateViewRealRouteLeaksInactiveSupervisorTest::test_invalid_post_redisplay_must_not_leak_inactive_supervisor_email` falhou mesmo após a política de `<select>` estar correta: a mensagem de erro padrão do Django `ChoiceField` (`"Select a valid choice. %(value)s is not one of the available choices."`) **interpola o valor forjado de volta na mensagem renderizada**, vazando a identidade da conta oculta no modal de erro (`error-modal-item`) mesmo sem ela aparecer como `<option>`. Corrigido com `error_messages={"invalid_choice": "Selecione uma opcao valida."}` em `employees/forms.py::EmployeeForm._configure_account_field` (sem interpolação do valor submetido). Isto reforça por que a Test Strategy desta etapa exige regressão por app inteiro, não apenas o arquivo-alvo: o achado só apareceu na execução completa de `employees` porque a ordem/composição de testes expôs o caminho de erro com o payload exato que disparava a interpolação.

### Implementation Plan — o que foi implementado

1. **`users/visibility.py` (novo)** — política centralizada e reutilizável: `VISIBILITY_EXEMPT_ROLES` (ADMIN, DEV), `viewer_is_exempt`, `visible_accounts_queryset`, `is_account_visible`, `account_is_hidden_for_viewer`, `KEEP_CURRENT_TOKEN`/`KEEP_CURRENT_LABEL`/`NO_ACTIVE_ACCOUNTS_LABEL`. Viewer vem sempre do parâmetro explícito (nunca lido de payload); ausência de viewer é tratada como o caso mais restrito, nunca como exceção ADMIN implícita.
2. **`users/admin.py::SystemUserAdmin`** — `search_fields` corrigido; `get_queryset` filtra por `visible_accounts_queryset`, cobrindo changelist/busca/contagem/paginação/popup/ações em lote de uma só vez (todos consomem o mesmo queryset); `_get_obj_does_not_exist_redirect` sobrescrito para levantar `Http404` em vez do redirecionamento (302) padrão do Django — único ponto de sobrescrita necessário, pois `change_view`/`delete_view`/`history_view` convergem para esse hook no Django 5.2.11 instalado (confirmado por leitura direta, não presumido); `password_change_view` já levanta `Http404` nativamente quando `get_object` (que usa `get_queryset`) retorna `None`, sem necessidade de override adicional.
3. **`employees/forms.py::EmployeeForm`** — `_configure_account_field` (novo método) centraliza a regra para `corporate_email`/`manager_email`: resolve três estados (zero contas do role = fallback texto livre legado preservado; há visíveis = `ChoiceField` com essas opções + marcador quando aplicável; há contas mas nenhuma visível = `ChoiceField` apenas com marcador ou rótulo "Nenhum usuário ativo disponível", nunca texto livre). Campo trocado de tipo (não só widget) para `ChoiceField`/`CharField` conforme o estado, evitando que o `EmailField` padrão do `ModelForm` rejeite o marcador. Aceita `viewer=` no `__init__`.
4. **`employees/views.py`** — `EmployeeUpdateView.get_form_kwargs` e `EmployeeCreateView.get_form_kwargs` passam `viewer=self.request.user`.
5. **`allocations/forms.py::CombinedRegistrationForm`** — aceita `viewer=`, filtra `supervisor_emails`/`manager_emails` por `visible_accounts_queryset`. **`allocations/views.py::RegistrationHubView`** passa `viewer=self.request.user` no GET (`get_context_data`) e no POST (`_handle_employee`), preservando a exceção ADMIN já comprovada em UVI-03 (`T04_CombinedRegistrationFormAdminOnlyExceptionTest`, ainda GREEN).
6. **`employees/admin.py`** (U07) — `EmployeeAdminForm` aceita `viewer=`; `clean_corporate_email`/`clean_manager_email` chamam `_reject_new_hidden_account_assignment`, que preserva um vínculo **já persistido** (mesmo inativo) e rejeita apontar para uma conta oculta **diferente** da atual. `EmployeeAdmin.get_form` injeta `request.user` via subclasse dinâmica do form (padrão usual do Django Admin para propagar contexto de request a um `ModelForm`).
7. **`allocations/admin.py::LineAllocationAdmin`** e **`pendencies/admin.py::AllocationPendencyAdmin`** — `formfield_for_foreignkey` filtra `allocated_by`/`released_by` e `technical_responsible`/`updated_by` por `visible_accounts_queryset`, unindo com o valor **já persistido** no objeto aberto (lido do banco via `object_id` de `request.resolver_match.kwargs`, nunca de `self.instance` do form) para preservar autoria histórica sem exigir atividade do autor atual.
8. **`__keep_current__`** — implementado apenas onde há uma fronteira real de seleção textual mascarável (`EmployeeForm`). Não implementado em `SystemUserAdmin.supervisor_email`/`manager_email` (U04, ver Ambiguidades) nem como marcador textual em `EmployeeAdminForm`/FKs de Admin: nestes dois últimos casos a identidade já é integralmente visível na própria tela do Admin (texto livre editável e `<select>` padrão do `ModelForm` mostrando o `__str__` completo do objeto persistido), então a resolução adotada foi "preservar sem exigir validação de atividade no valor inalterado" em vez de um marcador textual — mascaramento visual desses dois caminhos é explicitamente UVI-05/fora de escopo do Admin.

### Test Checklist — matriz antes/depois por node ID

| Node ID | Camada | Antes (UVI-03/03a) | Depois (UVI-04) |
|---|---|---|---|
| T01 (changelist/contagem/paginação) | Backend | 2 RED | GREEN |
| T01 (busca) | Backend — defeito preexistente | 2 testes provando `FieldError` (bug) | Bug corrigido (teste dedicado RED→GREEN); 3 testes novos provam busca funcional + política |
| T02 (change/delete/history/password 404) | Backend | 4 RED | GREEN |
| T02b (POST forjado, batch delete confirmação/execução) | Backend | 3 RED | GREEN |
| T04 (is_staff/is_superuser não isentam) | Backend | 1 RED | GREEN |
| T04 (`CombinedRegistrationForm` ADMIN-only) | Controle | GREEN | GREEN (reconfirmado com viewer propagado) |
| U04 (`SystemUser.clean()` ignora atividade do supervisor) | Backend — ambiguidade registrada | GREEN (sem validação) | **Inalterado** — ver Ambiguidades |
| T05/T06 (`EmployeeForm` choices/forjado) | Backend | 2+2 RED | GREEN |
| T05b (rota real, redisplay de erro alheio) | Backend | 2 RED | GREEN (inclusive o achado do `ChoiceField.invalid_choice`) |
| T06b (único supervisor inativo) | Backend — reclassificado | GREEN (select oferecia o inativo) | **Reclassificado para GREEN sob nova semântica**: select não oferece mais o único inativo; forjar é rejeitado |
| T06c (fallback texto livre, zero contas) | Controle | GREEN | GREEN (inalterado — comportamento legado preservado) |
| `__keep_current__` (manter/trocar/forja-criação/outro-inativo/erro-alheio) | Backend — novo | Não executável (símbolo inexistente) | 9 testes novos, todos GREEN |
| T07/T07b (FK `LineAllocationAdmin`) | Backend | 1 GREEN controle + 1 RED | GREEN |
| T07/T07b (FK `AllocationPendencyAdmin`) | Backend | 1 GREEN controle + 1 RED | GREEN |
| U07 (`EmployeeAdmin` texto livre) | Backend — novo | Sem cobertura em UVI-03 | 4 testes novos, todos GREEN |
| T08/T08b (`employee_list`/`employee_detail`/AJAX) | **Interface — UVI-05** | 4 RED | **Inalterado, RED intencional** (fora de escopo UVI-04) |
| T08 (`manager_dashboard`) | **Interface — UVI-05** | 2 RED | **Inalterado, RED intencional** |
| T09 (escopo preservado com supervisor desativado) | Controle preexistente | 2 GREEN | GREEN (inalterado) |
| T10 (histórico/timeline preserva autor) | Controle preexistente | 2 GREEN | GREEN (inalterado) |
| T11 (GET ativo/POST inativo) | Backend — novo | Não executável (política inexistente) | 2 testes novos, GREEN |
| T12 (custo de consulta/isolamento) | Backend — novo | Diferido | 2 testes novos, GREEN |
| T13 (notificações/constantes) | Controle preexistente | 1 GREEN | GREEN (inalterado) |
| T14 (navegador) | Aceite — UVI-06 | Fora de escopo | Fora de escopo (inalterado) |

### Test Strategy

Comandos executados nesta etapa (`venv/Scripts/python.exe -m pytest`, `DJANGO_SETTINGS_MODULE=config.settings_dev`, banco de teste isolado, execução sequencial por app):

- Baseline reconfirmado (seis arquivos originais, antes de qualquer edição): **57 coletados, 22 FAILED, 35 PASSED** — idêntico ao relatado em UVI-03a.
- Suíte combinada final (seis arquivos originais + três novos: `users/test_admin_search_field_defect.py`, `employees/tests/test_uvi04_admin_free_text_association.py`, `employees/tests/test_uvi04_keep_current_and_cost.py`): **80 coletados, 6 FAILED, 74 PASSED, 2 subtests passed**. Os 6 FAILED são exatamente os de apresentação reservados para UVI-05 (4 em `employees` T08/T08b + 2 em `dashboard` T08); nenhum FAILED de backend restante.
- Regressão por app inteiro (não a suíte nova isolada — o app completo, incluindo testes pré-existentes):
  - `pytest users -q` → **28 coletados, 0 FAILED, 28 PASSED**, 2 subtests passed. Nenhuma regressão.
  - `pytest employees -q` → **105 coletados, 4 FAILED (T08/T08b, UVI-05), 101 PASSED**. Nenhuma regressão nos 70 pré-existentes.
  - `pytest allocations -q` → **49 coletados, 0 FAILED, 49 PASSED**. Nenhuma regressão.
  - `pytest pendencies -q` → **104 coletados (+14 subtests), 0 FAILED, 104 PASSED**. Nenhuma regressão.
  - `pytest dashboard/tests/ -q` → **102 coletados (+7 subtests), 2 FAILED (T08, UVI-05), 100 PASSED**. Nenhuma regressão.
  - `pytest telecom -q` → **545 coletados (+5 subtests), 0 FAILED, 544 PASSED, 1 SKIPPED**. Idêntico ao baseline de UVI-03a (app não tocado nesta etapa) — reexecutado integralmente nesta rodada, não presumido.
  - `dashboard/tests.py` (módulo legado): continua não coletável isoladamente por colisão de nome pré-existente com o pacote `dashboard/tests/` — **não corrigido**, por instrução explícita desta tarefa.
- Reconciliação de contagens: nenhuma suíte foi somada com outra que já a contivesse. A "suíte combinada" (80) é citada separadamente da regressão por app (cada app com seu total próprio) exatamente para não duplicar — mesmo padrão adotado em UVI-03a.
- `manage.py check` → sem issues. `git diff --check` → sem problemas nos arquivos rastreados (os arquivos novos são untracked; verificados manualmente contra espaço em branco no fim de linha via `grep -rnP "[ \t]+$"`, sem ocorrências).
- PostgreSQL não foi usado nesta etapa; nenhuma alegação de locking/concorrência específica de Postgres foi feita (T11 prova reavaliação por requisição com SQLite, não uma garantia de serialização transacional).
- Navegador real não foi usado (T14 fora de escopo, reservado a UVI-06).

### Compliance Report

Fluxo seguido: contrato (UVI-01/02) → testes novos escritos e confirmados RED antes do código correspondente (`__keep_current__`, T11, T12, U07, defeito de busca) → implementação mínima → validação (suíte combinada + regressão por app inteiro, não apenas arquivos isolados — o que revelou o achado real do `ChoiceField.invalid_choice`). Nenhuma fixture de produto foi enfraquecida; as duas únicas alterações de teste existentes (`T06b` em `employees/tests/test_uvi03_inactive_account_visibility.py` e os dois testes de busca em `users/test_uvi03_admin_inactive_visibility.py`) foram retificações por MUDANÇA REAL de comportamento (política implementada / defeito corrigido), documentadas com justificativa no próprio arquivo, nunca para facilitar GREEN artificial.

**Ambiguidades registradas, não resolvidas nesta etapa** (fora do escopo decidir produto sem aprovação):
- **U04** — `SystemUser.clean()` continua validando apenas existência + role do supervisor vinculado a um BACKOFFICE, não sua atividade (`U04_BackofficeSupervisorLinkValidationIgnoresActivityTests`, inalterado, ainda GREEN sob o comportamento atual). O contrato (UVI-02) menciona "não afrouxar `SystemUser.clean` para backoffice", o que está satisfeito (nada foi afrouxado), mas não exige explicitamente apertar essa validação, e nenhum teste RED cobra esse aperto. Decisão de produto pendente, não tomada unilateralmente aqui.
- **`SystemUserAdmin.supervisor_email`/`manager_email`** (campos de texto livre do próprio cadastro de conta) não recebem a mesma validação de `account_is_hidden_for_viewer` aplicada em `EmployeeAdminForm` (U07) — mesma razão do ponto acima (sem teste RED prévio cobrando esse caminho especificamente; o acesso a essa tela já é controlado por permissão de Django Admin sobre o próprio modelo `SystemUser`, superfície de risco menor que U07).

**Pendências exatas de UVI-05** (interface e vínculos existentes — não iniciadas nesta etapa, dependência mínima de backend já pronta):
- Rótulo neutro "Usuário inativo" em `employee_list.html` (HTML inicial + AJAX) e `employee_detail.html` (`corporate_email`/`manager_email`) — testes `T08_EmployeeListAndDetailRevealInactiveSupervisorIdentityTest` e `T08b_EmployeeListUnambiguouslyRestrictedViewerTest`, RED.
- Rótulo neutro em `manager_dashboard.html` (grupo por `supervisor_email`) — testes `T08_ManagerDashboardRevealsInactiveSupervisorEmailTest::test_manager_dashboard_must_not_reveal_inactive_supervisor_email` e `...actions_also_reveal...`, RED.
- Rotulagem visual do marcador `__keep_current__` no `<option>` (atualmente renderiza o rótulo "Manter vínculo atual" vindo de `users.visibility.KEEP_CURRENT_LABEL" — já neutro, mas a revisão completa de redisplay/CSS/acessibilidade do seletor é UVI-05/UVI-06).
- Navegador real (T14) — UVI-06.

Nenhuma dessas pendências foi declarada concluída nesta etapa. A aplicação como um todo **não** está concluída: identidade de conta inativa ainda aparece nas três superfícies de apresentação acima, reservadas para UVI-05.

### Veredito final

**UVI-04 concluída.** Política backend centralizada e reutilizável implementada e testada; todas as entradas reais mapeadas em UVI-02 (Admin de `SystemUser`, `EmployeeForm`/views, `EmployeeAdmin`, `CombinedRegistrationForm`/`RegistrationHubView`, FKs de `LineAllocationAdmin`/`AllocationPendencyAdmin`) protegidas contra leitura e escrita de/para contas ocultas, com vínculos persistidos e referências históricas preservados. Defeito pré-existente da busca corrigido e documentado separadamente da política. Regressão executada e confirmada sem quebras em cada app completo (`users` 28, `employees` 105, `allocations` 49, `pendencies` 104+14 subtests, `dashboard/tests/` 102+7 subtests, `telecom` 545+5 subtests — números acima, não somados entre si por conterem a suíte nova como subconjunto, mesmo critério de UVI-03a). Próxima tarefa: UVI-05 (interface, rótulos neutros, redisplay). Sem migration, refatoração ampla, correção da colisão `dashboard/tests.py`, stage, commit, push, deploy ou acesso a PRD nesta etapa.

**Retificação desta mesma entrega, incorporada na conferência UVI-04b abaixo:** o veredito acima tratou `SystemUserAdmin.supervisor_email`/`manager_email` como "ambiguidade registrada, não resolvida", citando falta de teste RED prévio como justificativa para não implementar. Essa leitura estava equivocada: o contrato UVI-02 (U04) já exigia explicitamente "validar conta proposta" para os dois campos — não era uma decisão de produto em aberto, era uma lacuna de implementação não fechada. Corrigido em UVI-04b, com teste RED real escrito antes da correção (não presumido do relato anterior).


## UVI-04b — Conferência corretiva de UVI-04 (2026-10-14)

### Spec Summary

Conferência solicitada antes de iniciar UVI-05, sobre três pontos: (1) se `SystemUserAdmin.supervisor_email`/`manager_email` (texto livre) realmente permanecem sem proteção contra nova associação a conta oculta, ou se a classificação anterior como "ambiguidade" estava correta; (2) classificação exata das seis falhas restantes (requisito → entrada real → primeira asserção falha → causa observada → etapa responsável), para confirmar que são exclusivamente de apresentação; (3) reconciliação de contagens após a investigação.

Resultado: **o ponto 1 era procedente** — a entrega anterior deixou uma lacuna real de backend sem implementar, rotulando-a como ambiguidade de produto quando o contrato já a resolvia. Corrigida nesta conferência com teste RED real (escrito e confirmado falho antes da correção) e implementação mínima reutilizando `users/visibility.py`. **O ponto 2 não encontrou problema**: as seis falhas são genuinamente de apresentação (confirmado por inspeção do primeiro `assertNotContains` falho em cada uma — todas alcançam HTTP 200 com dado correto no contexto/JSON, a única falha é o HTML/JSON conter o e-mail cru). Nenhum código de produto foi alterado por causa do ponto 2 (nada a corrigir ali). O ponto 3 foi reconciliado com números reais abaixo.

### Gap Analysis — SystemUserAdmin, campos textuais

Inspeção direta de `users/admin.py` (antes desta conferência) e `users/models.py::SystemUser.clean()` confirmou: o único caminho real de edição de `SystemUser` é `SystemUserAdmin` (sem rota de auto-edição de perfil em `accounts/*`, reconfirmado). `SystemUser.clean()` valida `supervisor_email` **apenas** para `role=BACKOFFICE` (existência de `SystemUser(role=SUPER, email=...)`, sem `is_active`) — **inalterado nesta conferência, por decisão explícita** (alterar o model afetaria qualquer consumidor futuro de `full_clean()`, fora do escopo do Admin; a correção foi aplicada no FORM do Admin, não no model). `manager_email` não tinha (e continua sem) validação de existência alguma, para nenhum role — comportamento legado preservado, não é o alvo desta correção.

**Achado real confirmado por teste antes do fechamento:** nenhuma validação de ATIVIDADE existia para nenhum dos dois campos, em nenhum role. Um viewer restrito (SUPER/BACKOFFICE/GERENTE/OPERATOR) com `is_staff` + permissão de modelo suficiente para alcançar a rota de `SystemUserAdmin` podia editar uma conta ATIVA (portanto alcançável pelo `get_queryset` já filtrado) e apontar seu `supervisor_email`/`manager_email` para uma conta de um TERCEIRO, inativa e sem qualquer vínculo anterior com o registro — uma nova associação a conta oculta, exatamente o que o contrato veda. Isto é distinto do objeto do próprio `U04_BackofficeSupervisorLinkValidationIgnoresActivityTests` (que cobre a VALIDAÇÃO de existência+role, já documentada, inalterada) — aqui o objeto é a ausência de barreira de ATIVIDADE sobre o CONTEÚDO proposto do campo, por qualquer viewer, para ambos os campos.

Os cinco cenários pedidos, verificados separadamente (ver Test Checklist):

| Cenário | Antes (sem proteção) | Depois |
|---|---|---|
| 1. Manter vínculo inativo já persistido (reenvio do mesmo valor) | Aceito (sem validação alguma) | Aceito — preservado explicitamente, não é nova associação |
| 2. Nova associação/troca para OUTRO inativo | Aceito (bypass real) | **Recusado** — `ValidationError` genérica, sem citar o valor |
| 3. Associação a ativo elegível | Aceito | Aceito (inalterado) |
| 4. Valor sem conta correspondente | Aceito (tratamento legado) | Aceito (inalterado — nenhuma restrição de existência nova) |
| 5. ADMIN/DEV com permissão técnica suficiente | Aceito (exceção já existente) | Aceito (exceção preservada, não uma concessão nova) |

Nenhuma regra global de existência/atividade foi acrescentada a `SystemUser.clean()` nem a qualquer consumidor fora do Admin — a correção vive inteiramente em `users/admin.py` (`get_form` + função auxiliar de validação), reutilizando `users.visibility.account_is_hidden_for_viewer` já existente desde UVI-04.

**Nenhuma contradição real foi encontrada entre os pontos da spec** (U04, item 6 do Contract, e os contratos técnicos de UVI-02) — a leitura "validar conta proposta" para `SystemUserAdmin manager_email/supervisor_email` já estava escrita em UVI-02 linha U04 desde a origem; a entrega anterior simplesmente não a implementou e rotulou a lacuna como decisão de produto em aberto, o que esta conferência retifica.

### Implementation Plan — correção aplicada

1. **Teste RED real escrito primeiro**: `users/test_uvi04b_admin_text_field_association.py` (14 testes). Executado antes de qualquer alteração de `users/admin.py` — RED confirmado em 5 testes (3 recusas esperadas ainda aceitas, 1 asserção de mensagem, 1 erro de desenho do próprio teste de controle legado, corrigido no próprio arquivo antes da implementação — ver Test Strategy).
2. **Correção mínima em `users/admin.py`**: função `_validate_account_text_field(form, field_name, viewer)` (reutiliza `account_is_hidden_for_viewer` de `users/visibility.py`) + `SystemUserAdmin.get_form` injeta o viewer (`request.user`) numa subclasse dinâmica do form real do Admin (mesmo padrão já usado em `EmployeeAdmin.get_form`), adicionando `clean_supervisor_email`/`clean_manager_email`. `SystemUser.clean()` **não foi tocado**.
3. Suíte reexecutada: RED→GREEN confirmado nos 5 testes pendentes (um deles exigiu correção do próprio teste — ver abaixo, não do código de produção).
4. Regressão: `pytest users -q` → **37 coletados, 0 FAILED** (28 anteriores + 9 novos, nenhuma quebra). `manage.py check` e `git diff --check` sem problemas.

Uma correção de teste foi necessária e documentada: `RestrictedViewerLegacyValueWithoutMatchingAccountTest::test_email_without_any_matching_account_is_still_accepted` usava um registro com `role=BACKOFFICE`, que já dispara a validação de EXISTÊNCIA pré-existente (`SystemUser.clean()`, inalterada) para qualquer `supervisor_email` sem conta `SUPER` correspondente — causa real observada no primeiro RED (erro de outro campo, não do campo sob teste), não presumida. Corrigido trocando o `role` do registro para `OPERATOR` nesse teste específico (que não tem essa validação de existência), isolando exatamente o cenário pretendido (e-mail sem conta, tratamento legado do CAMPO em si). Nenhuma asserção foi enfraquecida — o teste continua exigindo e-mail aceito e persistido.

Uma segunda correção de teste, por causa real observada (não presumida): `ErrorMessageDoesNotLeakIdentityTest` originalmente exigia `assertNotContains(response, email_rejeitado)` — mas o campo é um `<input>` de texto livre que o PRÓPRIO viewer preencheu; o redisplay padrão do Django ecoa o valor submetido de volta no `value=` do input (mesmo raciocínio já registrado em UVI-04 original para a caixa de busca do Admin: não é vazamento, o viewer já sabia o que digitou). Reclassificado para verificar a mensagem de erro genérica (`"Selecione uma conta ativa."`, sem interpolação do valor) e o estado persistido inalterado — a garantia real exigida pelo contrato (não citar o valor na MENSAGEM, não mudar o banco), não a ausência literal do texto digitado pelo próprio autor da requisição.

### Test Checklist — matriz das seis falhas restantes (apresentação, UVI-05)

| # | Node ID | Requisito | Entrada real | Primeira asserção falha | Causa observada | Etapa responsável |
|---|---|---|---|---|---|---|
| 1 | T08 | Lista inicial não revela supervisor inativo | `GET /employees/` (`employee_list.html`, viewer ADMIN) | `assertNotContains(response, inactive_super.email)` após `assertEqual(status_code, 200)` já GREEN | Template imprime `{{ employee.corporate_email }}` cru na célula "Supervisor" da tabela — confirmado no HTML capturado (`<td>super.inativo.lista.uvi03@test.com</td>`) | UVI-05 |
| 2 | T08 (AJAX) | Payload JSON de load-more não revela supervisor inativo | `GET /employees/?...` com `X-Requested-With: XMLHttpRequest` | `assertNotIn(email, emails_in_payload)` | `EmployeeListView._handle_ajax_request` (`employees/views.py`) serializa `emp.corporate_email` cru no dict retornado como JSON | UVI-05 |
| 3 | T08 (detalhe) | Detalhe de funcionário não revela supervisor/gerente inativo | `GET /employees/<pk>/` (`employee_detail.html`) | `assertNotContains(response, inactive_super.email)` | Template imprime `corporate_email`/`manager_email` crus | UVI-05 |
| 4 | T08b | Mesma lacuna com viewer inequivocamente restrito (BACKOFFICE) | `GET /employees/` (mesmo template de #1) | `assertNotContains(response, inactive_super.email)` | Mesma causa de #1 — confirma que a lacuna independe de role (template não teria lógica de mascaramento para ninguém hoje) | UVI-05 |
| 5 | T08 (painel) | Painel do gerente não revela e-mail do supervisor inativo | `GET /dash-gerencial/` (`manager_dashboard.html`, viewer GERENTE) | `assertNotContains(response, inactive_supervisor.email)` | Template imprime `<h2>Supervisor {{ item.supervisor }}</h2>` cru (a chave de agrupamento é o próprio e-mail, por desenho de U11 — escopo de dados preservado, não a apresentação) | UVI-05 |
| 6 | T08 (painel + ações) | Mesma lacuna com uma `DailyUserAction` presente no grupo | Mesma rota de #5, após criar ação do dia | `assertNotContains(response, inactive_supervisor.email)` | Mesma causa de #5 — presença de ação não altera o rótulo do grupo | UVI-05 |

Em todas as seis, a rota foi alcançada (200), autorização/permissão foram concedidas corretamente, e o contexto/JSON continha o dado correto (funcionário, totais e `full_name` preservados, conforme controles positivos pareados nos mesmos testes) — nenhuma falha de autorização, validação ou persistência foi mascarada como "apresentação". Classificação confirmada correta, não há recategorização pendente.

### Test Strategy

Comandos executados nesta conferência (`venv/Scripts/python.exe -m pytest`, banco isolado, execução sequencial):

- `pytest users/test_uvi04b_admin_text_field_association.py -q` (RED, antes da correção em `users/admin.py`) → **9 coletados, 5 FAILED, 4 PASSED**. Reexecutado após a correção → **9 coletados, 0 FAILED** (uma correção de teste aplicada no meio, documentada acima, por causa real).
- `pytest users -q` (regressão completa do app, incluindo os testes novos) → **37 coletados, 0 FAILED, 37 PASSED**, 2 subtests passed. (28 anteriores + 9 novos — nenhuma regressão.)
- Suíte combinada UVI-03/UVI-04/UVI-04b (dez arquivos: os seis originais + `users/test_admin_search_field_defect.py` + `users/test_uvi04b_admin_text_field_association.py` + `employees/tests/test_uvi04_admin_free_text_association.py` + `employees/tests/test_uvi04_keep_current_and_cost.py`) → **89 coletados, 6 FAILED, 83 PASSED**, 2 subtests passed. Delta em relação ao baseline de UVI-04 (80 coletados, 74 PASSED, 6 FAILED): **+9 coletados, +9 PASSED, FAILED inalterado (6)** — exatamente os 9 testes novos de `test_uvi04b_admin_text_field_association.py`, todos GREEN; nenhum dos 6 FAILED pré-existentes foi tocado (são os mesmos seis node IDs da matriz acima, confirmados por nome de teste idênticos na saída).
- Demais apps (`employees`, `allocations`, `pendencies`, `dashboard/tests/`, `telecom`) **não foram alterados nesta conferência** (nenhum arquivo de produção desses apps foi tocado) — não reexecutados integralmente por app nesta rodada; a suíte combinada acima já reexecuta os arquivos de teste UVI-03/04 desses apps e confirma ausência de regressão nos node IDs cobertos. Reaproveitado o resultado completo por app de UVI-04 original (`employees` 105/4 FAILED, `allocations` 49/0, `pendencies` 104+14 subtests/0, `dashboard/tests/` 102+7 subtests/2 FAILED, `telecom` 545+5 subtests/0) como válido, por corresponder exatamente ao mesmo código avaliado (nenhuma edição desde então nesses apps).
- `manage.py check` → sem issues. `git diff --check` → sem problemas nos arquivos rastreados; `users/test_uvi04b_admin_text_field_association.py` é novo/untracked, verificado manualmente contra espaço em branco no fim de linha (`grep -rnP "[ \t]+$"`), sem ocorrências.
- Nenhuma suíte foi somada com outra que já a contivesse (mesmo critério de UVI-03a/UVI-04).

### Compliance Report

Ponto 1 (SystemUserAdmin) era procedente: lacuna real de backend, não ambiguidade de produto — corrigida com teste RED real antes do código, reutilizando `users/visibility.py`, sem alterar `SystemUser.clean()` nem managers/escopos globais. Ponto 2 (seis falhas) não encontrou problema: todas confirmadas como apresentação pura, com evidência linha a linha (primeira asserção falha + causa) na matriz acima — nenhuma reclassificação necessária. Ponto 3 (contagens) reconciliado: delta de +9/+9/0 explicado por node ID, sem soma de suítes sobrepostas.

Retificação explícita (afirmação da entrega anterior que estava errada e é retirada): "`SystemUserAdmin.supervisor_email`/`manager_email`... ambiguidade registrada, não resolvida" — **errado**; era uma lacuna de implementação do contrato já fixado em U04/UVI-02, fechada nesta conferência.

Nenhuma regra de negócio foi enfraquecida; nenhum `skip`/`xfail` foi usado; nenhuma permissão nova foi concedida; nenhum manager/escopo global foi alterado. `manage.py check` sem issues, `git diff --check` sem problemas.

### Veredito final

**UVI-04 concluída (backend comprovado), com a correção desta conferência incorporada.** As seis falhas restantes são exclusivamente de apresentação (UVI-05), confirmadas por evidência direta, não por suposição. Nenhuma pendência de backend permanece aberta para os caminhos mapeados em UVI-02. Próxima tarefa: UVI-05. Sem migration, refatoração ampla, correção da colisão `dashboard/tests.py`, stage, commit, push, deploy ou acesso a PRD nesta conferência.


## UVI-05 — Interface e neutralização das referências atuais a contas inativas (2026-10-14)

### Spec Summary

Fecha a última pendência de apresentação identificada em UVI-04/04b: `employee_list.html` (render inicial + AJAX), `employee_detail.html` e `manager_dashboard.html` imprimiam `corporate_email`/`manager_email`/`supervisor` em texto puro, mesmo quando a conta referenciada estava `is_active=False`. Implementado rótulo neutro `Usuario inativo` (`users.visibility.INACTIVE_ACCOUNT_LABEL`, já reservado desde UVI-04) nessas três superfícies, resolvido em lote por requisição (sem N+1, sem cache entre requisições).

**Decisão de produto desta etapa, resolvendo a ambiguidade registrada em UVI-03a/04/04b:** nas três superfícies acima (U08-U10), a neutralização é **independente de role** — inclusive para ADMIN/DEV. Isto não contradiz a exceção ADMIN/DEV já implementada em UVI-04 (`SystemUserAdmin`, `EmployeeForm`/`CombinedRegistrationForm`, FKs de `LineAllocationAdmin`/`AllocationPendencyAdmin`): aquela exceção vale para **diretórios e seletores de conta** (onde ADMIN/DEV já tinham autorização de ver/gerenciar o objeto `SystemUser` inativo, Spec Summary original). `employee_list`/`employee_detail`/`manager_dashboard` não são diretórios nem seletores de conta — são superfícies operacionais de funcionário que referenciam um supervisor/gerente por e-mail como campo descritivo, exatamente a categoria "Apresentação atual" do contrato técnico de UVI-02 (U08-U10), que não registra ressalva de role, apenas a exceção de históricos/relatórios. Evidência objetiva que resolve a ambiguidade a favor desta leitura: `EmployeeDetailView.allowed_roles = [ADMIN]` (rota ADMIN-only, nunca alcançável por SUPER/BACKOFFICE/GERENTE/OPERATOR) — se a máscara dependesse de role restrito, o requisito U09/T08 do próprio contrato de UVI-02 seria inexequível por desenho, o que não é uma leitura sustentável do contrato. Os três RED de `T08` com viewer ADMIN (lista, AJAX, detalhe) e os dois RED de `T08`/painel com viewer GERENTE, mais o `T08b` com viewer BACKOFFICE, foram escritos exatamente para ficarem GREEN sob esta leitura — nenhum teste foi alterado ou enfraquecido para chegar a este resultado.

### Gap Analysis — baseline reconfirmado antes do código

Baseline reexecutado antes de qualquer edição (dez arquivos de teste das etapas UVI-03/03a/04/04b, mesmos da entrega anterior): comando `pytest users/test_uvi03_admin_inactive_visibility.py employees/tests/test_uvi03_inactive_account_visibility.py allocations/tests/test_uvi03_inactive_account_visibility.py pendencies/tests/test_uvi03_inactive_account_visibility.py dashboard/tests/test_uvi03_inactive_account_visibility.py telecom/test_uvi03_inactive_author_preservation.py users/test_admin_search_field_defect.py users/test_uvi04b_admin_text_field_association.py employees/tests/test_uvi04_admin_free_text_association.py employees/tests/test_uvi04_keep_current_and_cost.py -q` → **89 coletados, 6 FAILED, 83 PASSED, 2 subtests passed**, idêntico ao relatado no veredito de UVI-04b. Os seis FAILED, confirmados por node ID, são exatamente os da matriz "seis falhas restantes" de UVI-04b:

1. `employees/tests/test_uvi03_inactive_account_visibility.py::T08_EmployeeListAndDetailRevealInactiveSupervisorIdentityTest::test_employee_list_page_must_not_reveal_inactive_supervisor_email`
2. `...::test_employee_list_ajax_payload_must_not_reveal_inactive_supervisor_email`
3. `...::test_employee_detail_page_must_not_reveal_inactive_supervisor_email`
4. `...::T08b_EmployeeListUnambiguouslyRestrictedViewerTest::test_restricted_viewer_employee_list_must_not_reveal_inactive_supervisor_email`
5. `dashboard/tests/test_uvi03_inactive_account_visibility.py::T08_ManagerDashboardRevealsInactiveSupervisorEmailTest::test_manager_dashboard_must_not_reveal_inactive_supervisor_email`
6. `...::test_manager_dashboard_actions_also_reveal_inactive_supervisor_email`

Conferência do diff de UVI-04b: `users/visibility.py` permaneceu **intacto** nesta etapa até a adição das duas novas funções descritas abaixo (nenhuma função/constante existente foi alterada ou removida). Testes que exercitam integração entre a política e `SystemUserAdmin` (inalterados, reconfirmados GREEN na regressão): `users/test_uvi03_admin_inactive_visibility.py` (changelist/busca/404/POST forjado/ações em lote) e `users/test_uvi04b_admin_text_field_association.py` (`supervisor_email`/`manager_email` do próprio cadastro de conta) — nenhuma regressão por rotina sem causa; nada foi reexecutado "só para confirmar" além do baseline e da regressão por app já exigidos.

Auditoria dos formulários administrativos de UVI-04/04b (`EmployeeAdminForm`/`EmployeeAdmin.get_form`, `SystemUserAdmin.get_form`, FK pickers de `LineAllocationAdmin`/`AllocationPendencyAdmin`): confirmado por leitura direta que nenhum deles precisa de alteração nesta etapa — são seletores/diretórios de conta (exceção ADMIN/DEV já correta desde UVI-04), não as três superfícies de apresentação U08-U10. `EmployeeAdmin.list_display` (Django Admin de `Employee`, distinto de `employee_list.html`) continua exibindo `corporate_email` cru; não está no inventário U08-U10 (não é `employee_list.html`/`employee_detail.html`/`manager_dashboard.html`) e nenhum RED o cobre — registrado como fora do escopo desta entrega, não uma omissão.

### Implementation Plan — o que foi implementado

1. **`users/visibility.py`** — duas funções novas, reutilizando o módulo já existente (nenhuma função/constante anterior alterada): `resolve_inactive_email_labels(emails)` resolve em **uma única consulta** (`Q(email__iexact=...)` encadeado por OR, nunca um `.filter()` por item do loop) quais dos e-mails informados correspondem a conta `SystemUser` com `is_active=False`, retornando um `set` normalizado (strip+casefold); `mask_inactive_email(email, inactive_set, label=INACTIVE_ACCOUNT_LABEL)` aplica o rótulo quando o e-mail está no set, preservando valores vazios e strings legadas sem conta correspondente (nunca entram no set, porque a consulta só busca contas que realmente existem).
2. **`employees/views.py::EmployeeListView`** — `get_context_data` (render inicial) e `_handle_ajax_request` (JSON) resolvem o lote de `corporate_email` dos funcionários da página atual (nunca da tabela inteira) e aplicam `mask_inactive_email`; o atributo `corporate_email_display` (render inicial) e a própria chave `"corporate_email"` do payload JSON (AJAX) passam a carregar o valor já neutralizado — o AJAX não precisou de nenhuma mudança no JavaScript, porque o template já renderiza o campo recebido do backend sem lógica própria de mascaramento no cliente (nenhuma política reimplementada no frontend).
3. **`employees/views.py::EmployeeDetailView`** — `get_context_data` resolve `corporate_email`+`manager_email` do funcionário em uma única chamada (os dois campos, não duas consultas) e expõe `corporate_email_display`/`manager_email_display` na mesma instância usada pelo template (removida uma segunda consulta redundante a `get_object()` que existia antes e não alimentava o contexto real).
4. **`dashboard/views.py::ManagerDashboardView`** — após montar `supervisor_dashboards` (chave de agrupamento inalterada: o e-mail real do supervisor, U11 preservado), resolve o lote de todas as chaves distintas e adiciona `group["supervisor_label"]`, nunca substituindo `group["supervisor"]` (usado internamente para agrupar/comparar) — dois supervisores inativos distintos continuam como dois grupos/totais distintos, ambos exibindo o mesmo rótulo neutro sem serem mesclados.
5. **Templates** — `templates/employees/employee_list.html` (coluna "Supervisor": `employee.corporate_email` → `employee.corporate_email_display`), `templates/employees/employee_detail.html` (`corporate_email`/`manager_email` → `..._display`), `templates/dashboard/manager_dashboard.html` (`supervisor_data.supervisor` → `supervisor_data.supervisor_label` no título da seção). Nenhum HTML/atributo/script/hidden adicional foi tocado; nenhuma identidade é transportada em campo auxiliar paralelo.
6. **Formulários e vínculos existentes (item 3 do pedido)** — conferência completa de `EmployeeForm`/`EmployeeUpdateView`/`EmployeeCreateView` (`employees/forms.py`, `employees/views.py`) e seu template (`templates/employees/employee_form.html`): marcador `__keep_current__`/rótulo "Manter vínculo atual", seleção inicial correta, troca explícita por ativo, redisplay após erro em campo alheio, estado sem candidatos ativos ("Nenhum usuário ativo disponível"), ausência de identidade oculta em `<option>`/mensagens de erro, e funcionamento sem JavaScript (campo é um `<select>`/`<input>` HTML padrão, POST funciona sem JS; o modal de erro usa Bootstrap JS só para exibição automática, comportamento pré-existente não alterado por esta feature) — **tudo já implementado em UVI-04 e confirmado GREEN nesta etapa sem necessidade de código novo**; nenhuma reimplementação de política no frontend, nenhum token gravado/vínculo apagado/seleção automática de primeiro ativo foi introduzida.

### Test Checklist — matriz antes/depois por node ID

| Node ID | Superfície | Antes (UVI-04/04b) | Depois (UVI-05) |
|---|---|---|---|
| T08 (lista, viewer ADMIN) | `employee_list.html` render inicial | RED | GREEN |
| T08 (AJAX, viewer ADMIN) | `EmployeeListView._handle_ajax_request` JSON | RED | GREEN |
| T08 (detalhe, viewer ADMIN) | `employee_detail.html` | RED | GREEN |
| T08b (lista, viewer BACKOFFICE) | `employee_list.html` | RED | GREEN |
| T08 (painel, viewer GERENTE) | `manager_dashboard.html` | RED | GREEN |
| T08 (painel + ação, viewer GERENTE) | `manager_dashboard.html` | RED | GREEN |
| Legado sem conta (lista/detalhe) | `employee_list.html`/`employee_detail.html` | Não coberto por teste dedicado | 2 testes novos, GREEN (não mascarado por suposição) |
| Dois supervisores inativos distintos (lista+AJAX) | `employee_list.html`/JSON | Não coberto | 2 testes novos, GREEN (rótulo repetido, funcionários/linhas distintos preservados) |
| Dois supervisores inativos distintos (painel) | `manager_dashboard.html` | Não coberto (UVI-03a só cobria um supervisor inativo) | 1 teste novo, GREEN (grupos/totais distintos preservados) |
| Custo de consulta (lista) | `EmployeeListView` | Não mensurável (sem política de apresentação ainda) | 1 teste novo, GREEN (contagem de queries constante, 2 vs. 22 funcionários) |
| Custo de consulta (painel) | `ManagerDashboardView` | Não mensurável | 1 teste novo, GREEN (contagem de queries constante, 2 vs. 15 supervisores) |
| Isolamento entre requisições sucessivas (lista) | `EmployeeListView` | Não coberto | 1 teste novo, GREEN (ADMIN→BACKOFFICE→ADMIN, sem contaminação) |
| Isolamento entre requisições sucessivas (painel) | `ManagerDashboardView` | Não coberto | 1 teste novo, GREEN |
| Formulários/vínculos existentes (manter/trocar/redisplay/vazio) | `EmployeeForm`/`EmployeeUpdateView` | GREEN (UVI-04) | GREEN (reconfirmado, sem código novo) |
| Admin/FK pickers/diretório de contas (exceção ADMIN/DEV) | `SystemUserAdmin`, `EmployeeAdminForm`, `LineAllocationAdmin`, `AllocationPendencyAdmin` | GREEN (UVI-04/04b) | GREEN (reconfirmado por regressão completa, nenhum arquivo tocado) |
| Históricos/relatórios/timeline | `telecom/line_timeline.py` e afins | GREEN (controle preexistente) | GREEN (reconfirmado, nenhum arquivo tocado) |

### Test Strategy

Arquivos novos desta etapa: `employees/tests/test_uvi05_presentation_neutralization.py` (6 testes: string legada sem conta na lista e no detalhe; dois supervisores inativos distintos na lista HTML e no payload AJAX; custo de consulta constante; isolamento entre viewers sucessivos) e `dashboard/tests/test_uvi05_manager_dashboard_label_neutralization.py` (3 testes: dois supervisores inativos distintos sem colapsar grupos/totais; custo de consulta constante; isolamento entre requisições sucessivas). Nenhum teste usa mock da própria política (`users.visibility`), placeholder, ou assertiva que passe por ausência de dados — todos usam `Client`/`force_login` reais, `reverse(...)`, e verificam estado renderizado (HTML/JSON/`response.context`) e contagem real de queries (`CaptureQueriesContext`).

Comandos executados (`venv/Scripts/python.exe -m pytest`, `DJANGO_SETTINGS_MODULE=config.settings_dev`, banco de teste isolado, execução sequencial):

- Baseline reconfirmado antes do código (dez arquivos originais): **89 coletados, 6 FAILED, 83 PASSED, 2 subtests passed** — idêntico ao relatado em UVI-04b.
- Mesmos dez arquivos, após o código desta etapa: `employees/tests/test_uvi03_inactive_account_visibility.py` + `dashboard/tests/test_uvi03_inactive_account_visibility.py` isolados → **21 coletados, 0 FAILED** (os seis RED, GREEN confirmado).
- Suíte combinada final (dez arquivos originais + dois novos desta etapa): **98 coletados, 0 FAILED, 98 PASSED, 2 subtests passed**. Delta em relação ao baseline de UVI-04b (89/83/6): **+9 coletados, +15 PASSED, -6 FAILED** (os 6 RED resolvidos + os 9 testes novos, nenhuma soma de suíte sobreposta).
- Regressão por app inteiro (não a suíte nova isolada):
  - `pytest employees -q` → **111 coletados, 0 FAILED, 111 PASSED** (105 anteriores + 6 novos desta etapa). Nenhuma regressão.
  - `pytest dashboard/tests/ -q` → **105 coletados (+7 subtests), 0 FAILED, 105 PASSED** (102 anteriores + 3 novos). Nenhuma regressão.
  - `pytest allocations -q` → **49 coletados, 0 FAILED, 49 PASSED**. Inalterado (nenhum arquivo deste app tocado nesta etapa) — reexecutado integralmente, não presumido.
  - `pytest pendencies -q` → **104 coletados (+14 subtests), 0 FAILED, 104 PASSED**. Inalterado, reexecutado integralmente.
  - `pytest users -q` → **37 coletados (+2 subtests), 0 FAILED, 37 PASSED**. Inalterado, reexecutado integralmente.
  - `pytest telecom -q` → **545 coletados (+5 subtests), 0 FAILED, 544 PASSED, 1 SKIPPED**. Idêntico ao baseline de UVI-04 (app não tocado), reexecutado integralmente nesta rodada, não presumido.
  - `dashboard/tests.py` (módulo legado): continua não coletável isoladamente por colisão de nome pré-existente — inalterado, fora de escopo desta tarefa (mesma decisão de UVI-03/03a/04/04b).
- Reconciliação: nenhuma suíte foi somada com outra que já a contivesse (mesmo critério das etapas anteriores). A "suíte combinada" (98) é citada separadamente da regressão por app (cada app com seu total próprio).
- `venv/Scripts/python.exe manage.py check` → sem issues. `git diff --check` → sem problemas nos arquivos rastreados (apenas avisos de CRLF/LF em `dashboard/views.py` e em um documento alheio, não relacionados a espaço em branco); os dois arquivos de teste novos são untracked, verificados manualmente contra espaço em branco no fim de linha (`grep -rnP "[ \t]+$"`) em todos os arquivos tocados nesta etapa (`users/visibility.py`, `employees/views.py`, `dashboard/views.py`, os dois templates de `employees`, `manager_dashboard.html`, e os dois arquivos de teste novos) — sem ocorrências introduzidas por esta etapa (as únicas linhas com espaço em branco final encontradas são pré-existentes em `templates/employees/employee_list.html`, em linhas não tocadas por este diff).
- PostgreSQL não foi usado nesta etapa (SQLite do projeto); nenhuma alegação de concorrência/locking específica de Postgres foi feita.

### Smoke em navegador real — bloqueio registrado

**Navegador real indisponível neste ambiente de execução**: nenhuma ferramenta de automação de navegador (Chrome DevTools MCP, Playwright ou equivalente) está configurada/acessível nesta sessão; a única ferramenta de busca web disponível (`WebFetch`) explicitamente não atende `localhost`/servidor de desenvolvimento. Confirmado por tentativa real de localizar a ferramenta antes de declarar o bloqueio (não presumido).

Conforme a instrução desta tarefa ("se navegador estiver indisponível, registrar bloqueio; não substituir aceite visual por Django Client nem declarar interação comprovada"), **nenhuma das verificações de navegador real foi executada nem declarada como comprovada**: viewer restrito e ADMIN autorizado em interação real, desktop/390px/360px, navegação por teclado, inspeção de console/rede, e confirmação visual de ausência de identidade oculta no DOM renderizado. As evidências desta etapa (HTML/JSON capturados via `Client` nos testes automatizados acima) comprovam o **conteúdo correto da resposta do servidor** — não substituem layout, foco, responsividade ou interação real, que ficam explicitamente como bloqueio registrado, não como aceite.

### Compliance Report

Fluxo seguido: contrato (UVI-01/02, com a ambiguidade de role em U08-U10 resolvida nesta etapa e justificada acima) → reconfirmação do baseline real (89/83/6, idêntico ao relato anterior, sem ajuste por expectativa) → testes novos escritos e confirmados antes do código correspondente (string legada, dois supervisores distintos, custo, isolamento — 9 testes, GREEN só após o código) → implementação mínima reutilizando `users/visibility.py` já existente → validação (suíte combinada + regressão por app inteiro, todos os seis apps reexecutados integralmente, não presumidos de etapas anteriores).

Os seis RED de apresentação ficaram **genuinamente GREEN**: confirmados por reexecução real dos mesmos node IDs (não por reescrita de asserção), com controles positivos preservados (funcionário/`full_name` continuam presentes; totais e carteiras do painel continuam íntegros) em todos os testes afetados — ver matriz acima.

Nenhuma regra de negócio foi enfraquecida; nenhum teste foi relaxado para facilitar GREEN artificial; nenhum `skip`/`xfail`/mock da própria política foi usado; nenhuma migration, manager/escopo global, autenticação, notificação ou regra POR foi alterada; nenhum acesso a PRD; nenhum stage/commit/push/deploy realizado nesta etapa. `manage.py check` sem issues; `git diff --check` sem problemas de espaço em branco introduzidos por este diff.

**Pendência exata de UVI-06** (não iniciada nesta etapa):

- **Aceite em navegador real completo** — bloqueado nesta etapa por indisponibilidade de ferramenta (registrado acima, não substituído por `Client`). UVI-06 precisa executar (ou obter acesso a uma ferramenta de automação de navegador, ou aceite manual do usuário) pelo menos: viewer restrito (SUPER/BACKOFFICE/GERENTE) e ADMIN autorizado navegando lista/AJAX ("Carregar mais"), detalhe, painel e formulário de edição; fluxo completo de manter vínculo / trocar por ativo / erro de validação com foco e mensagens visíveis; desktop e mobile real (390px/360px); navegação por teclado (tab order, foco visível no `<select>`); inspeção de console (zero erros/warnings) e aba de rede (payload AJAX real sem identidade oculta); confirmação visual de que nenhum atributo/`data-*`/script no DOM renderizado carrega o e-mail oculto (verificação textual já feita nos testes automatizados desta etapa, mas não a inspeção visual/DOM ao vivo exigida pelo contrato de UVI-06).
- Revisão final de diff completo da feature (todas as etapas UVI-01 a UVI-05) e plano de deploy/rollback — não iniciados, reservados a UVI-06 por definição.
- A colisão `dashboard/tests.py` vs. `dashboard/tests/` permanece não corrigida, por instrução explícita mantida desde UVI-03.
- `EmployeeAdmin.list_display` (Django Admin de `Employee`) continua exibindo `corporate_email` cru — fora do inventário U08-U10, sem RED que o exija; registrado aqui para decisão explícita futura caso o escopo da feature seja estendido, não uma pendência desta entrega.

### Veredito final

**UVI-05 concluída.** As três superfícies de apresentação mapeadas em U08-U10 (`employee_list.html` com AJAX, `employee_detail.html`, `manager_dashboard.html`) neutralizam a identidade de supervisor/gerente de conta inativa com o rótulo `Usuario inativo`, resolvido em lote por requisição, sem crescimento de custo por item e sem contaminação entre viewers/requisições sucessivas — para qualquer viewer, inclusive ADMIN/DEV, decisão de produto explicitada e justificada nesta etapa. Funcionários, linhas, vínculos, escopo, grupos distintos e totais permanecem intactos; valores legados sem conta correspondente não são mascarados por suposição; históricos/relatórios/timeline permanecem com identidade integral (nenhum arquivo desses caminhos foi tocado). Formulários e vínculos existentes (`EmployeeForm`/`EmployeeUpdateView`), já implementados em UVI-04, foram auditados e reconfirmados sem necessidade de código novo. Os seis RED de apresentação ficaram genuinamente GREEN; nove testes novos cobrem as lacunas reais pedidas (legado sem conta, dois supervisores distintos, custo, isolamento). Regressão completa executada em todos os seis apps, sem quebras. Smoke em navegador real bloqueado por indisponibilidade de ferramenta nesta sessão, registrado como pendência exata de UVI-06, não substituído por `Client` nem declarado como comprovado. Sem migration, refatoração ampla, correção da colisão `dashboard/tests.py`, stage, commit, push, deploy ou acesso a PRD nesta etapa. Próxima tarefa: UVI-06 — não iniciada.

**Retificação desta mesma entrega, incorporada na conferência UVI-05b abaixo:** a decisão "para qualquer viewer, inclusive ADMIN/DEV" acima foi tomada unilateralmente nesta entrega, com uma justificativa escrita na spec que não substitui aprovação do usuário — e contradiz o contrato aprovado (Spec Summary/UVI-01: "ADMIN e DEV podem continuar vendo contas inativas"). Corrigida em UVI-05b: a neutralização passa a depender do viewer, preservando identidade para ADMIN/DEV onde já tinham autorização.


## UVI-05b — Conferência corretiva de UVI-05 (2026-10-14)

### Spec Summary

Conferência solicitada antes de iniciar UVI-06, sobre um desvio relatado pelo usuário: a entrega de UVI-05 neutralizou `employee_list` (render inicial + AJAX), `employee_detail` e `manager_dashboard` para **qualquer** viewer, inclusive ADMIN/DEV. Isso contradiz o contrato aprovado desde UVI-01 (Spec Summary: "ADMIN e DEV podem continuar vendo contas inativas em listas, buscas ou seletores de contas") e a decisão de UVI-04 de tratar ADMIN/DEV como excecão de ROLE (`users.visibility.viewer_is_exempt`), não de superfície. A justificativa escrita na spec de UVI-05 ("estas três superfícies não são diretórios/seletores de conta") foi uma leitura própria desta entrega, não uma aprovação do usuário — e o usuário agora confirma que está errada.

**Resultado da inspeção:** o desvio era real e exatamente como relatado. Corrigido: `users/visibility.py::resolve_inactive_email_labels` passa a receber o `viewer` explicitamente e reutiliza `viewer_is_exempt` (a mesma exceção central usada por `visible_accounts_queryset`/`account_is_hidden_for_viewer` desde UVI-04) — para ADMIN/DEV retorna sempre um set vazio (nenhuma consulta de mascaramento é feita, a identidade real é exibida); para os quatro papéis restritos (ou ausência de viewer) resolve normalmente. Nenhuma permissão de rota foi alterada: ADMIN continua podendo acessar `employee_list`/`employee_detail` exatamente como antes (`EMPLOYEE_ACCESS_ROLES`/`allowed_roles` inalterados), e DEV continua sem acesso a nenhuma das três rotas (nunca esteve em `EMPLOYEE_ACCESS_ROLES` nem em `ManagerDashboardView.allowed_roles` — a exceção é de política de apresentação, não de rota).

### Gap Analysis — confirmado por inspeção, não por suposição

| Caminho | Antes da correção (desvio) | Depois (retificado) |
|---|---|---|
| `users/visibility.py::resolve_inactive_email_labels` | Assinatura `(emails)`, sem parâmetro de viewer; resolvia e mascarava para qualquer chamador, sem distinção de role | Assinatura `(viewer, emails)`; retorna set vazio imediatamente quando `viewer_is_exempt(viewer)` é verdadeiro (ADMIN/DEV), sem fazer a consulta de mascaramento nesse caso |
| `employees/views.py::EmployeeListView._handle_ajax_request` | Chamava `resolve_inactive_email_labels(emails)` sem viewer | Chama `resolve_inactive_email_labels(request.user, emails)` |
| `employees/views.py::EmployeeListView.get_context_data` | Idem (render inicial) | Chama `resolve_inactive_email_labels(self.request.user, emails)` |
| `employees/views.py::EmployeeDetailView.get_context_data` | Idem (rota ADMIN-only, mas a função ainda mascarava) | Chama `resolve_inactive_email_labels(self.request.user, emails)` — nesta rota o set resolvido é sempre vazio, porque só ADMIN alcança |
| `dashboard/views.py::ManagerDashboardView.get_context_data` | Idem | Chama `resolve_inactive_email_labels(self.request.user, emails)` — `ManagerDashboardView.allowed_roles = [GERENTE]`, role sempre restrita; a chamada passa o viewer mesmo assim para reutilizar a mesma política central, não para mudar o resultado desta rota especificamente |
| Demais chamadores de `resolve_inactive_email_labels`/`mask_inactive_email` | — | Confirmado por `grep`: apenas os quatro pontos acima chamam estas funções; nenhum outro caminho precisou de correção |
| `EmployeeForm`/`EmployeeAdminForm`/`SystemUserAdmin`/FKs de Admin (`viewer_is_exempt`, `visible_accounts_queryset`, `account_is_hidden_for_viewer`) | Já corretos desde UVI-04 (exceção ADMIN/DEV nunca removida destes caminhos) | Inalterados — confirmado por leitura direta e pela regressão completa, nenhum destes arquivos foi tocado nesta conferência |

Diferenciação confirmada versus hipótese: o desvio foi localizado por leitura direta de `users/visibility.py` (ausência de parâmetro de viewer na função nova de UVI-05, ao lado de três funções mais antigas que já recebem viewer) e confirmado empiricamente por um RED real produzido deliberadamente (ver Test Strategy) — não presumido do relato do usuário sem verificação.

Nenhuma permissão foi alterada para tornar uma tela acessível a ADMIN/DEV: `EmployeeListView.allowed_roles`, `EmployeeDetailView.allowed_roles`, `EmployeeCreateView.allowed_roles`, `EmployeeUpdateView.allowed_roles` e `ManagerDashboardView.allowed_roles` permanecem exatamente como estavam desde antes de UVI-04.

### Retificação da spec — regra vigente

A afirmação de UVI-05 "a neutralização é independente de role — inclusive para ADMIN/DEV" é **retirada como regra vigente** (mantida apenas como histórico, marcada acima). Regra vigente a partir desta conferência, para `employee_list` (inicial e AJAX), `employee_detail` e `manager_dashboard`:

- **ADMIN/DEV**: identidade preservada, dentro do acesso que já possuíam antes desta feature. Não é uma concessão nova de rota — é a mesma exceção de role (`VISIBILITY_EXEMPT_ROLES`) já aplicada a `SystemUserAdmin`/seletores desde UVI-04, agora também respeitada por esta camada de apresentação.
- **SUPER/BACKOFFICE/GERENTE/OPERATOR**: toda referência atual (não histórica) a conta comprovadamente inativa é neutralizada com o rótulo exato **"Usuário inativo"** (com acento — `users.visibility.INACTIVE_ACCOUNT_LABEL`, corrigido de "Usuario inativo" para "Usuário inativo" nesta conferência).
- **Históricos/relatórios/timeline**: referências preservadas, inalterado (exceção que nunca dependeu de role, já correta desde UVI-02/UVI-03).
- Funcionários, linhas, vínculos, escopo, grupos distintos e totais continuam intactos (U11, inalterado).

### Implementation Plan — testes antes da correção, depois correção mínima

1. **Testes escritos antes da correção**, nas entradas reais (nenhum acesso artificial concedido para fabricar controle positivo):
   - `employees/tests/test_uvi03_inactive_account_visibility.py::T08_EmployeeListAndDetailAdminPreservesIdentityTest` (renomeada de `...RevealInactiveSupervisorIdentityTest`) — ADMIN autorizado (rota já alcançável antes desta feature) deve ver nome/e-mail da conta inativa na lista, no AJAX e no detalhe. Docstring documenta a retificação explicitamente, preservando o histórico da ambiguidade registrada em UVI-03a/04/04b.
   - `T08b_EmployeeListUnambiguouslyRestrictedViewerTest` (BACKOFFICE) — inalterada: role restrita autorizada continua vendo somente o rótulo neutro. Docstring atualizada para registrar que não foi afetada pela retificação.
   - `employees/tests/test_uvi05_presentation_neutralization.py` — reescrita: os cenários que exercitam o rótulo neutro (dois supervisores inativos distintos, custo de consulta) passaram a usar um viewer genuinamente restrito (GERENTE, com escopo real via `manager_email`) em vez de ADMIN; string legada sem conta testada tanto para o viewer restrito (lista) quanto para ADMIN (detalhe, única rota alcançável); teste de alternância de viewers reescrito para `ADMIN (vê real) → BACKOFFICE (vê rótulo) → ADMIN (vê real de novo)`, provando que nenhum resultado é reutilizado indevidamente entre requisições sucessivas de viewers diferentes.
   - `employees/tests/test_uvi05b_role_scoped_neutralization.py` (novo, 5 testes) — DEV é exceção na política (`viewer_is_exempt(dev) == True`, controle direto da função) mas continua **sem acesso** a `employee_list`/`employee_detail`/`manager_dashboard` (403 nas três rotas, mesma negação de sempre); GERENTE (restrito) continua sem acesso a `employee_detail` (ADMIN-only), com ou sem a exceção de política. Quando a role não tem acesso à tela, o teste verifica a negação de rota existente (`RoleRequiredMixin` → `PermissionDenied` → 403), não uma política de apresentação inalcançável.
   - `dashboard/tests/test_uvi03_inactive_account_visibility.py` e `dashboard/tests/test_uvi05_manager_dashboard_label_neutralization.py` — inspecionados, **sem alteração**: ambos já usavam GERENTE (role sempre restrita nesta rota, `allowed_roles = [GERENTE]`), nunca dependeram do desvio.
2. **RED real confirmado contra o código com o desvio** (não presumido): revertida temporariamente apenas a linha `if viewer_is_exempt(viewer): return set()` de `resolve_inactive_email_labels` (para `if False: ...`, simulando exatamente o comportamento da entrega anterior, sem tocar mais nada), suíte reexecutada → **4 FAILED reais**: os três testes de `T08_EmployeeListAndDetailAdminPreservesIdentityTest` (ADMIN não via a identidade, era mascarada) e `test_alternating_viewers_do_not_leak_or_reuse_each_others_result` (ADMIN via o rótulo neutro em vez da identidade real). Os outros 31 testes do mesmo lote permaneceram GREEN (papéis restritos e a negação de rota de DEV não dependem dessa linha). Revertida a reversão (restaurado o arquivo corrigido) → suíte reexecutada → **35 PASSED, 0 FAILED**.
3. **Correção mínima aplicada**: `users/visibility.py::resolve_inactive_email_labels` ganha o parâmetro `viewer` e o early-return de exceção (reutilizando `viewer_is_exempt`, já existente, nenhuma regra de role duplicada); os quatro chamadores (`EmployeeListView` x2, `EmployeeDetailView`, `ManagerDashboardView`) passam a enviar `request.user`/`self.request.user`. `INACTIVE_ACCOUNT_LABEL` corrigido para `"Usuário inativo"` (com acento). Nenhum template foi alterado nesta conferência (já usavam os campos `*_display`/`supervisor_label` resolvidos pela view, sem lógica de role duplicada). Nenhuma consulta por linha foi introduzida: o early-return de ADMIN/DEV evita até a única consulta em lote que existia; para os papéis restritos a consulta em lote única (um `Q(email__iexact=...)` por OR) é inalterada. Nenhum manager global, autenticação, notificação ou regra POR foi tocado.

### Test Checklist — evidência RED→GREEN

| Cenário | Antes da correção (código com o desvio, revertido temporariamente) | Depois (correção aplicada) |
|---|---|---|
| ADMIN vê identidade na lista (render inicial) | RED (`test_employee_list_page_preserves_inactive_supervisor_email_for_admin`) | GREEN |
| ADMIN vê identidade no AJAX | RED (`test_employee_list_ajax_payload_preserves_inactive_supervisor_email_for_admin`) | GREEN |
| ADMIN vê identidade no detalhe | RED (`test_employee_detail_page_preserves_inactive_supervisor_email_for_admin`) | GREEN |
| Alternância ADMIN→BACKOFFICE→ADMIN sem reuso indevido | RED (`test_alternating_viewers_do_not_leak_or_reuse_each_others_result`) | GREEN |
| BACKOFFICE/GERENTE veem somente o rótulo neutro (lista/AJAX/painel) | GREEN (nunca dependeu do desvio) | GREEN (reconfirmado) |
| DEV exceção na política, sem rota nova (lista/detalhe/painel, 3 testes 403) | N/A (teste novo) | GREEN |
| GERENTE sem acesso a `employee_detail` (controle negativo, ADMIN-only) | N/A (teste novo) | GREEN |
| Dois supervisores inativos distintos não colapsam (viewer restrito) | GREEN (reescrito para GERENTE) | GREEN |
| String legada sem conta correspondente intacta (lista restrita + detalhe ADMIN) | GREEN (reescrito) | GREEN |
| Custo de consulta constante (viewer restrito) | GREEN (reescrito para GERENTE) | GREEN |

### Test Strategy

Comandos executados (`venv/Scripts/python.exe -m pytest`, banco de teste isolado, execução sequencial):

- RED real produzido deliberadamente (reversão temporária de uma linha em `users/visibility.py`, restaurada imediatamente após a captura): `pytest employees/tests/test_uvi03_inactive_account_visibility.py employees/tests/test_uvi05_presentation_neutralization.py employees/tests/test_uvi05b_role_scoped_neutralization.py dashboard/tests/test_uvi03_inactive_account_visibility.py dashboard/tests/test_uvi05_manager_dashboard_label_neutralization.py -v` → **35 coletados, 4 FAILED, 31 PASSED**.
- Mesmo comando após restaurar a correção → **35 coletados, 0 FAILED, 35 PASSED**.
- Suíte combinada (dez arquivos de UVI-03/03a/04/04b + os dois arquivos de UVI-05 + o arquivo novo de UVI-05b): **103 coletados, 0 FAILED, 103 PASSED, 2 subtests passed**. Delta em relação ao veredito de UVI-05 (98/98/0): **+5 coletados, +5 PASSED, 0 FAILED** — exatamente os 5 testes novos de `test_uvi05b_role_scoped_neutralization.py` (nenhum teste antigo foi removido; três tiveram a asserção invertida com a mesma contagem, um teve o viewer trocado, mantendo o total de node IDs coletados estável nos arquivos reescritos).
- Regressão por app inteiro, confirmando que `users/visibility.py` sendo compartilhado não regrediu Admin/forms/seletores (não limitada aos templates):
  - `pytest employees -q` → **116 coletados, 0 FAILED, 116 PASSED** (111 anteriores + 5 novos de `test_uvi05b_role_scoped_neutralization.py`). Nenhuma regressão.
  - `pytest dashboard/tests/ -q` → **105 coletados (+7 subtests), 0 FAILED, 105 PASSED**. Inalterado (nenhum arquivo deste app tocado nesta conferência).
  - `pytest allocations -q` → **49 coletados, 0 FAILED, 49 PASSED**. Inalterado — confirma que `CombinedRegistrationForm`/`LineAllocationAdmin` (consumidores de `viewer_is_exempt`/`visible_accounts_queryset`, não de `resolve_inactive_email_labels`) não foram afetados pela correção.
  - `pytest pendencies -q` → **104 coletados (+14 subtests), 0 FAILED, 104 PASSED**. Inalterado — mesma confirmação para `AllocationPendencyAdmin`.
  - `pytest users -q` → **37 coletados (+2 subtests), 0 FAILED, 37 PASSED**. Inalterado — confirma `SystemUserAdmin`/busca/ações em lote/campos textuais (consumidores diretos de `viewer_is_exempt`/`account_is_hidden_for_viewer`) intactos.
  - `pytest telecom -q` → **545 coletados (+5 subtests), 0 FAILED, 544 PASSED, 1 SKIPPED**. Inalterado.
- Reconciliação: nenhuma suíte foi somada com outra que já a contivesse. `grep` confirmou que apenas os quatro pontos listados no Gap Analysis chamam `resolve_inactive_email_labels`/`mask_inactive_email` — a validação não ficou limitada aos templates, cobriu os quatro apps que compartilham `users/visibility.py` através de outras funções (Admin/forms/seletores).
- `venv/Scripts/python.exe manage.py check` → sem issues. `git diff --check` → sem problemas (apenas aviso de CRLF/LF em um documento alheio). Arquivos tocados verificados manualmente contra espaço em branco no fim de linha (`grep -rnP "[ \t]+$"`) — sem ocorrências introduzidas por esta conferência.
- PostgreSQL não foi usado; nenhuma alegação de concorrência/locking específica foi feita.

### Testes corrigidos e motivo

| Teste | Motivo da correção | Classificação |
|---|---|---|
| `T08_EmployeeListAndDetailRevealInactiveSupervisorIdentityTest` → `T08_EmployeeListAndDetailAdminPreservesIdentityTest` (3 asserções invertidas de `assertNotContains` para `assertContains`) | Codificava a neutralização universal (desvio); corrigido para refletir o contrato real — ADMIN autorizado vê a identidade. Retificação contratual, não enfraquecimento de proteção: a proteção das roles restritas (T08b) não foi tocada. | Corrigido por causa real (desvio confirmado), docstring documenta a retificação preservando o histórico da ambiguidade anterior |
| `TwoDistinctInactiveSupervisorsDoNotCollapseTest` (viewer trocado de ADMIN para GERENTE) | O cenário (rótulo neutro para dois supervisores distintos) só é exercitável por um viewer genuinamente restrito, agora que ADMIN não é mais mascarado | Corrigido — mesmo requisito, viewer correto |
| `QueryCostAndViewerIsolationTest::test_list_rendering_query_count_is_constant...` (viewer trocado de ADMIN para GERENTE) | Custo de consulta da projeção de mascaramento só é mensurável sob um viewer que efetivamente a executa (ADMIN agora tem early-return sem consulta) | Corrigido — mesmo requisito, viewer correto |
| `test_successive_requests_by_different_viewers_do_not_leak_state` → `test_alternating_viewers_do_not_leak_or_reuse_each_others_result` | Reescrito para provar exatamente o cenário que o usuário pediu (ADMIN vê real, restrito vê neutro, ADMIN volta a ver real) — o teste anterior media "sempre mascarado", que já não é a regra correta | Corrigido — requisito mais preciso que o original |
| `LegacySupervisorStringWithoutMatchingAccountTest` (viewer da lista trocado de ADMIN para GERENTE) | Com ADMIN a asserção seria trivial (nunca mascarado); com GERENTE prova que a política de "sem conta correspondente" é respeitada mesmo no caminho que realmente mascara | Corrigido — mesmo requisito, cenário mais forte |

Nenhuma correção reduziu a cobertura das roles restritas: todas continuam com os mesmos testes de masking (agora sob viewer GERENTE/BACKOFFICE em vez de ADMIN), e três testes novos (DEV×3 rotas, GERENTE×detalhe) foram adicionados, não removidos.

### Aceite visual

Inalterado desde UVI-05: navegador real indisponível nesta sessão (mesma verificação repetida — nenhuma ferramenta de automação de navegador configurada; `WebFetch` não serve `localhost`). Não substituído por `Client`, não declarado como comprovado. Pendência exata de UVI-06, idêntica à já registrada.

### Compliance Report

O desvio relatado era procedente e foi confirmado por inspeção direta do código (ausência de parâmetro de viewer em `resolve_inactive_email_labels`, ao lado de três funções mais antigas no mesmo módulo que já recebiam viewer desde UVI-04) e por um RED real produzido deliberadamente, não presumido. A justificativa escrita na entrega de UVI-05 não foi tratada como aprovação — foi retirada como regra vigente e mantida apenas como histórico marcado. Correção mínima: um parâmetro novo em uma função já existente, reutilizando `viewer_is_exempt` central (nenhuma regra de role duplicada em views/templates), e os quatro chamadores atualizados. Nenhuma migration, alteração de permissão de rota, manager/escopo global, autenticação, notificação ou regra POR. Nenhum stage/commit/push/deploy/acesso a PRD. `manage.py check` sem issues; `git diff --check` sem problemas.

**Conformidade de código/testes:** confirmada — RED→GREEN real documentado, regressão completa nos seis apps sem quebra, inclusive nos consumidores de `users/visibility.py` que não passam por `resolve_inactive_email_labels` (Admin/forms/seletores). **Aceite visual:** permanece não executado nesta sessão (ferramenta indisponível) — separado explicitamente da conformidade de código acima, não combinado em um único veredito.

**Pendência exata de UVI-06** (inalterada, reconfirmada):
- Aceite em navegador real completo (viewer restrito e ADMIN, lista/AJAX, detalhe, painel, formulário; desktop/390px/360px; teclado; console/rede; ausência de identidade oculta no DOM) — bloqueado por indisponibilidade de ferramenta nesta sessão.
- Revisão final de diff completo da feature e plano de deploy/rollback.
- Colisão `dashboard/tests.py` vs. `dashboard/tests/` — não corrigida, por instrução explícita.
- `EmployeeAdmin.list_display` exibindo `corporate_email` cru — fora do inventário U08-U10, registrado para decisão futura, não pendência desta entrega.

### Veredito final

**Conferência corretiva de UVI-05 concluída.** O desvio relatado (neutralização universal, inclusive ADMIN/DEV) era real, confirmado por inspeção e por RED real, e foi corrigido com a menor alteração possível: `users/visibility.py::resolve_inactive_email_labels` agora recebe o viewer e reutiliza a exceção central `viewer_is_exempt` (a mesma de UVI-04), com early-return para ADMIN/DEV sem nenhuma consulta de mascaramento. ADMIN/DEV preservam identidade dentro do acesso que já possuíam; SUPER/BACKOFFICE/GERENTE/OPERATOR continuam vendo apenas o rótulo "Usuário inativo" (agora com acento); históricos/relatórios permanecem preservados; nenhuma rota foi aberta ou fechada. Testes corrigidos com motivo documentado, sem enfraquecer a proteção das roles restritas; três testes novos provam que a exceção de política não concede rota nova a DEV. Regressão completa nos seis apps sem quebra, incluindo os consumidores de `users/visibility.py` fora dos templates (Admin, forms, seletores). Aceite visual continua pendente de UVI-06, não substituído por `Client`. Sem migration, alteração de permissão, stage, commit, push, deploy ou PRD nesta conferência. Parada após a correção, conforme instruído — UVI-06 não iniciada.


## UVI-06 — Aceite integrado, navegador real e revisão final (2026-10-14)

### Spec Summary

Fecha a feature: reconciliação da suíte UVI completa, revisão do código final contra o contrato (UVI-01/02), aceite real em navegador (retificando o bloqueio registrado em UVI-05/05b — a ferramenta estava indisponível NAQUELA sessão, não permanentemente), proteção HTTP/persistência revalidada, e esta atualização final da spec. Nenhum defeito novo dentro do contrato foi encontrado nesta etapa; um achado cosmético (grafia sem acento de um rótulo) foi registrado, não corrigido, por não ser exigido por nenhum teste do contrato. Sem migration, alteração de permissão, stage, commit, push, deploy ou acesso a PRD.

### Reconciliação inicial

Baseline reconfirmado por execução real, antes de qualquer trabalho desta etapa, dos treze arquivos de teste UVI acumulados desde UVI-03:

```
users/test_uvi03_admin_inactive_visibility.py
employees/tests/test_uvi03_inactive_account_visibility.py
allocations/tests/test_uvi03_inactive_account_visibility.py
pendencies/tests/test_uvi03_inactive_account_visibility.py
dashboard/tests/test_uvi03_inactive_account_visibility.py
telecom/test_uvi03_inactive_author_preservation.py
users/test_admin_search_field_defect.py
users/test_uvi04b_admin_text_field_association.py
employees/tests/test_uvi04_admin_free_text_association.py
employees/tests/test_uvi04_keep_current_and_cost.py
employees/tests/test_uvi05_presentation_neutralization.py
dashboard/tests/test_uvi05_manager_dashboard_label_neutralization.py
employees/tests/test_uvi05b_role_scoped_neutralization.py
```

Resultado: **103 coletados, 0 FAILED, 103 PASSED, 2 subtests passed** (141.71s) — idêntico ao veredito de UVI-05b. Os 103 **não** são soma adicional a nada: é a contagem direta e única da suíte UVI completa nesta execução (os treze arquivos listados, sem sobreposição entre si — cada um é um módulo de teste distinto).

RED de UVI-05b, registrado corretamente: o único RED real produzido na história desta feature por reversão temporária de código foi em UVI-05b (`resolve_inactive_email_labels`, uma linha revertida e restaurada na mesma etapa, 4 FAILED capturados e documentados ali) — **não** um teste escrito antes do código correspondente (padrão TDD normal das demais etapas). UVI-06 não repetiu essa reversão; esta etapa é só de verificação, não de implementação.

Git status/diff inicial capturado antes de qualquer ação desta etapa (idêntico ao snapshot do início da conversa): treze arquivos de aplicação modificados (`allocations/admin.py`, `allocations/forms.py`, `allocations/views.py`, `dashboard/views.py`, `employees/admin.py`, `employees/forms.py`, `employees/views.py`, `pendencies/admin.py`, três templates, `users/admin.py`, mais um documento alheio de outra feature) e os treze arquivos de teste + `users/visibility.py` untracked. Nenhum arquivo alheio (evidências/specs de outras features, `.clinerules/`, `.cursor/`, `AGENTS.md` etc.) foi tocado nesta etapa; `git status` ao final desta etapa mostra o mesmo conjunto de treze arquivos de aplicação modificados mais a nova pasta `docs/superpowers/evidence/2026-10-14-uvi06/` — nenhuma edição de código de produção ocorreu nesta etapa (só leitura/revisão).

### Revisão integrada do contrato (leitura direta do código atual, não resumos anteriores)

Releitura completa e verificação linha a linha contra os itens do Contract (UVI-01) e dos contratos técnicos (UVI-02), nos arquivos reais:

| Item do contrato | Arquivo/mecanismo | Confirmado por |
|---|---|---|
| ADMIN/DEV preservam identidade onde já autorizados | `users/visibility.py::viewer_is_exempt`/`VISIBILITY_EXEMPT_ROLES`, usado por `visible_accounts_queryset`, `is_account_visible`, `account_is_hidden_for_viewer`, `resolve_inactive_email_labels` | Leitura direta + aceite em navegador (ADMIN vê e-mail real em lista/AJAX/detalhe) |
| SUPER/BACKOFFICE/GERENTE/OPERATOR não acessam inativos em diretórios/buscas/seletores/URLs diretas | `SystemUserAdmin.get_queryset`/`_get_obj_does_not_exist_redirect` (404), `EmployeeForm._configure_account_field`, `CombinedRegistrationForm.__init__`, `LineAllocationAdmin`/`AllocationPendencyAdmin._visible_*_queryset` | Leitura direta + 103 testes GREEN + aceite em navegador (GERENTE não vê e-mails, 404 real em `/admin/users/systemuser/<oculto>/change/`) |
| `is_staff`/`is_superuser` não substituem exceção por role | `viewer_is_exempt` consulta exclusivamente `viewer.role` | Leitura direta; `T04` GREEN |
| Referências operacionais mostram "Usuário inativo" para roles restritas | `resolve_inactive_email_labels` + `mask_inactive_email`, chamados em `EmployeeListView` (x2), `EmployeeDetailView`, `ManagerDashboardView`; templates usam `*_display`/`supervisor_label` | Leitura direta + aceite em navegador (rótulo exato "Usuário inativo", com acento, visível nas capturas) |
| Históricos/relatórios preservam autoria | `telecom/line_timeline.py` inalterado nesta feature (confirmado por `git diff` não tocar o arquivo) | `T10` GREEN, reconfirmado nesta etapa |
| Funcionários/linhas/grupos/vínculos/totais preservados | `ManagerDashboardView`: `group["supervisor"]` (chave) nunca substituída, só `group["supervisor_label"]` adicionado | Leitura direta + aceite em navegador (dois grupos distintos, totais corretos nas capturas) |
| Nenhuma nova permissão para DEV | `EMPLOYEE_ACCESS_ROLES`, `ManagerDashboardView.allowed_roles`, `allowed_roles` de cada view — nenhum inclui DEV; `resolve_inactive_email_labels` é exceção de apresentação, não de rota | `test_uvi05b_role_scoped_neutralization.py` (DEV recebe 403 nas três rotas) |
| Sem filtro global de SystemUser/cache compartilhado/consulta por item | `users/visibility.py` nunca filtra `SystemUser.objects` globalmente; resolução sempre por lote (`Q(...)` encadeado) por requisição, sem cache entre requests | Leitura direta + `T12` GREEN (contagem de query constante) |
| Novas associações a inativos ocultos recusadas; vínculo persistido mantido via `__keep_current__` | `EmployeeForm._clean_account_field`/`_configure_account_field`, `users/admin.py::_validate_account_text_field`, `employees/admin.py::_reject_new_hidden_account_assignment` | Leitura direta + 9 testes de `__keep_current__` GREEN + aceite em navegador (manter/trocar/forjar, 4 verificações PASS) |

Mensagens de validação, redisplay e campos textuais/FKs dos Admins conferidos: `EmployeeForm` usa `error_messages={"invalid_choice": "Selecione uma opcao valida."}` (sem interpolar o valor forjado — achado de UVI-04 permanece corrigido); `users/admin.py::_validate_account_text_field` e `employees/admin.py::_reject_new_hidden_account_assignment` levantam `ValidationError` genérica ("Selecione uma conta ativa."), nunca citando o valor recusado. Confirmado que POST forjado por ID/e-mail não basta ocultar a opção no HTML — a validação ocorre no `clean_*` do servidor em todos os quatro pontos (SystemUserAdmin, EmployeeForm, EmployeeAdminForm, FKs de Admin), não apenas na ausência da `<option>`.

### Preparo e execução do navegador real

Ferramentas de automação de navegador desta sessão (Chrome DevTools MCP/Playwright/Selenium) verificadas: nenhuma presente via `ToolSearch` nem instalada no venv do projeto (`playwright`/`selenium` ausentes). **Isto não encerrou a investigação**: o bloqueio registrado em UVI-05/UVI-05b foi tratado como não permanente, conforme instruído. Localizado Microsoft Edge (Chromium) instalado em `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`, suficiente para o mesmo mecanismo CDP stdlib-only (sem pacote novo no venv) já usado e validado em `docs/superpowers/evidence/2026-10-13-por05/`, `.../por06*/` e `SVI-06/`.

Ambiente descartável montado (detalhado em `docs/superpowers/evidence/2026-10-14-uvi06/report.md`): Postgres descartável via Docker (`uvi06-pg-disposable`, porta `55435`, removido ao final — preexistentes `lineops-db`/`postgres` intactos), `runserver` dev contra esse banco (porta `8799`, encerrado ao final), Edge headless em perfil isolado (`--user-data-dir` dedicado, `--remote-debugging-port=9444`, processo raiz identificado e encerrado especificamente por PID ao final — a sessão real do usuário no Edge, já em execução nesta máquina, não foi tocada em nenhum momento). Dados sintéticos criados por `uvi06_setup_fixtures.py`, sem credenciais reais.

Navegador real **foi executado de fato** nesta etapa — não substituído por `Client`, não declarado como comprovado sem execução.

### Dataset e matriz de aceite

Dataset sintético (`uvi06_setup_fixtures.py`): ADMIN e DEV; quatro roles restritas (SUPER, BACKOFFICE, GERENTE, OPERATOR) com `is_staff` e permissões de modelo suficientes para alcançar as rotas sob teste; dois supervisores inativos distintos (`uvi06.supervisor.a.inativo@test.com`, `uvi06.supervisor.b.inativo@test.com`) vinculados a dois funcionários distintos e geridos pelo mesmo GERENTE ativo usado como viewer; um gerente inativo (`uvi06.gerente.inativo@test.com`) vinculado a um terceiro funcionário; um supervisor ativo; um funcionário com texto legado sem conta correspondente (`supervisor.legado.sem.conta@test.com`); quatorze funcionários adicionais (prefixo `Zzz`, para ordenarem depois dos funcionários-alvo) para exercitar paginação/"Carregar mais" por AJAX.

**22/22 verificações reais em navegador passaram** (`docs/superpowers/evidence/2026-10-14-uvi06/results.json`, screenshots em `.../screenshots/`), cobrindo: lista inicial e AJAX (ADMIN vê identidade real; GERENTE vê rótulo neutro, dois funcionários distintos); detalhe de funcionário (ADMIN-only, identidades distintas para dois supervisores diferentes e para um gerente inativo); painel do gerente (dois grupos distintos não colapsados, totais corretos, nenhum e-mail real no DOM); alternância ADMIN→GERENTE→ADMIN→GERENTE sem reuso indevido de resultado entre viewers; formulário de edição (marcador "Manter vinculo atual" presente, identidade ausente das options/HTML, troca explícita por ativo persistida, POST forjado com outro inativo injetado via `<option>` recusado sem vazar identidade e sem alterar o banco); navegação por teclado (Tab move o foco a partir do primeiro campo focável — `full_name` fica `disabled` para viewer não-ADMIN, por desenho, não testável via foco); console sem erros/exceções JS nas navegações do fluxo. Viewports desktop (1280), 390px e 360px capturados para lista, painel, detalhe e formulário — inspeção visual confirma sem overflow horizontal da página, campos legíveis, nenhuma identidade visível em nenhuma largura. Checagem adicional fora do contador: payload AJAX do GERENTE confirmado mascarado via `fetch()` real; acesso direto de BACKOFFICE a conta oculta no Admin real retorna 404 genérico no navegador (não só no `Client` de teste).

Nenhuma permissão de aplicação foi alterada para criar acesso artificial — as quatro roles restritas usaram permissões técnicas Django concedidas administrativamente (padrão já usado desde UVI-03/03a para alcançar as rotas sem alterar `RoleRequiredMixin`/`allowed_roles`). DEV em rota negada (empregados/painel): confirmado 403 nos três (evidência automatizada reconfirmada nesta etapa, `test_uvi05b_role_scoped_neutralization.py`, 0 FAILED na suíte), consistente com a exceção de política (não de rota) verificada também no código em "Revisão integrada".

**Limitações registradas, não executadas nesta rodada** (detalhadas no `report.md`): cenário "zero candidatos ativos" e "erro em campo alheio preserva seleção" não foram reproduzidos visualmente (exigiriam desativar roles usadas pelos próprios viewers de teste, ou um campo editável adicional não disponível para o viewer de teste usado); ambos permanecem cobertos por evidência automatizada já GREEN (`T06c`, `T05b_KeepCurrentRealRouteTests`), reaproveitada e não re-executada em navegador nesta rodada — registrado como reaproveitamento explícito, não presumido.

### Proteção HTTP e persistência

Reconfirmado por leitura de código (não apenas pela suíte): `SystemUserAdmin` protege change/delete/history (404 via `_get_obj_does_not_exist_redirect`) e password (`Http404` nativo do Django quando `get_object` via `get_queryset` filtrado retorna `None`); ações em lote operam só sobre o queryset visível (`get_queryset` já filtrado, único ponto de verdade reutilizado por changelist/busca/contagem/paginação/popup/ações); POST forjado por ID/e-mail é revalidado no servidor em todos os quatro pontos de entrada (`SystemUserAdmin`, `EmployeeForm`, `EmployeeAdminForm`, FKs de `LineAllocationAdmin`/`AllocationPendencyAdmin`) — nenhum depende só da ausência da opção no HTML, confirmado tanto pelos 103 testes quanto pelo POST forjado real em navegador (verificação #20 da matriz). Marcador em contexto inválido (criação, campo sem vínculo): coberto por `KeepCurrentTokenFormUnitTests` (unidade, GREEN). Conta ativa no GET e inativa no POST: coberto por `T11_DeactivationBetweenGetAndPostTest` (GREEN, reconfirmado na suíte de 103) — não re-executado em navegador real nesta rodada (mudança de estado do banco entre as duas requisições do mesmo fluxo não foi orquestrada via CDP; o `Client` já prova reavaliação por requisição, e nenhuma alegação de concorrência/locking foi feita a partir disso, consistente com a Test Strategy de todas as etapas anteriores). Autorização anterior versus 404 de objeto oculto: distinguido em `T02` (negação de permissão continua diferente de 404 de objeto). Estado persistido comparado após recusas (não só status HTTP) em todos os testes relevantes e na verificação #21 do navegador (banco inspecionado via `/employees/<pk>/` real após o POST forjado).

### Defeitos encontrados

Nenhum defeito novo dentro do contrato foi encontrado nesta etapa. Um achado cosmético, fora do contrato testado, foi registrado e não corrigido: `KEEP_CURRENT_LABEL = "Manter vinculo atual"` (`users/visibility.py`) não recebeu acento em "vínculo" quando `INACTIVE_ACCOUNT_LABEL` foi corrigido para "Usuário inativo" (com acento) em UVI-05b. Nenhum teste do contrato exige essa grafia exata; o significado funcional não é afetado (visível nas capturas de tela do formulário). Não corrigido por não ser um defeito comportamental dentro do contrato aprovado — registrado para decisão explícita futura do usuário, consistente com a instrução de não corrigir achados alheios ao contrato sem necessidade.

### Validação e documentação

Suíte UVI completa (103 testes, 13 arquivos) executada nesta etapa: **103 PASSED, 0 FAILED, 2 subtests passed**, idêntico ao baseline — sem regressão. Regressão proporcional por app inteiro, reexecutada integralmente nesta etapa (não reaproveitada de etapas anteriores, por não haver correspondência de código ainda comprovada antes desta própria execução):

| App | Resultado | Observação |
|---|---|---|
| `users` | 37 passed, 2 subtests passed | Inalterado |
| `employees` | 116 passed | Inalterado |
| `allocations` | 49 passed | Inalterado |
| `pendencies` | 104 passed, 14 subtests passed | Inalterado |
| `dashboard/tests/` | 105 passed, 7 subtests passed | Inalterado |
| `telecom` | 544 passed, 1 skipped, 5 subtests passed | Inalterado |

Nenhuma suíte somada com outra que já a contivesse (mesmo critério de todas as etapas anteriores). `manage.py check`: sem issues. `git diff --check`: sem problemas nos arquivos rastreados (único aviso é CRLF/LF em um documento alheio de outra feature, pré-existente).

Evidência salva em `docs/superpowers/evidence/2026-10-14-uvi06/`: `uvi06_setup_fixtures.py`, `uvi06_browser_accept.py`, `cdp_client.py` (reutilizado de POR-06), `results.json`, `screenshots/` (12 capturas), `report.md`. Nenhuma credencial real; senha sintética única ao banco descartável.

**Separação evidência executada / reaproveitada / não executada:**
- **Executada nesta etapa**: suíte UVI completa (103), regressão por app inteiro (6 apps), revisão de código linha a linha do contrato, aceite em navegador real (22 verificações + 2 checagens adicionais), `manage.py check`, `git diff --check`.
- **Reaproveitada** (com correspondência de código demonstrada por reexecução dos mesmos arquivos nesta etapa, não presumida de relato anterior): nenhuma — todas as execuções desta etapa foram refeitas do zero, não há número citado sem reexecução própria.
- **Não executada**: "zero candidatos ativos" e "erro em campo alheio" em navegador real (cobertos por evidência automatizada já GREEN, citada acima, não re-executada em navegador); concorrência/locking específica de Postgres (nenhuma alegação feita, consistente com todas as etapas anteriores).

### Contagens sem dupla soma

103 (suíte UVI, treze arquivos distintos sem sobreposição) + regressão por app (cada app conta a suíte UVI como subconjunto do seu próprio total, não somada de novo: `users` 37 inclui os testes UVI daquele app, idem para os demais) — mesmo critério de reconciliação usado em UVI-03a/04/04b/05/05b. Nenhum número desta seção foi somado a outro que já o contivesse.

### Arquivos candidatos à entrega

Treze arquivos de aplicação modificados: `allocations/admin.py`, `allocations/forms.py`, `allocations/views.py`, `dashboard/views.py`, `employees/admin.py`, `employees/forms.py`, `employees/views.py`, `pendencies/admin.py`, `templates/dashboard/manager_dashboard.html`, `templates/employees/employee_detail.html`, `templates/employees/employee_list.html`, `users/admin.py`, mais o arquivo novo `users/visibility.py`. Treze arquivos de teste novos: `users/test_uvi03_admin_inactive_visibility.py`, `users/test_admin_search_field_defect.py`, `users/test_uvi04b_admin_text_field_association.py`, `employees/tests/test_uvi03_inactive_account_visibility.py`, `employees/tests/test_uvi04_admin_free_text_association.py`, `employees/tests/test_uvi04_keep_current_and_cost.py`, `employees/tests/test_uvi05_presentation_neutralization.py`, `employees/tests/test_uvi05b_role_scoped_neutralization.py`, `allocations/tests/test_uvi03_inactive_account_visibility.py`, `pendencies/tests/test_uvi03_inactive_account_visibility.py`, `dashboard/tests/test_uvi03_inactive_account_visibility.py`, `dashboard/tests/test_uvi05_manager_dashboard_label_neutralization.py`, `telecom/test_uvi03_inactive_author_preservation.py`. Sem migration (nenhuma alteração de schema nesta feature). Documentação: este arquivo de spec e a pasta de evidência `docs/superpowers/evidence/2026-10-14-uvi06/`.

Fora do escopo de entrega desta feature (não alterados, não candidatos): `docs/superpowers/specs/2026-09-10-line-daily-action-audit-design.md` (modificado por outra feature, preservado intacto), todo o conteúdo untracked de outras features (`.clinerules/`, `.cursor/`, `.opencode/`, `.superpowers/brainstorm/`, `AGENTS.md`, `docs/specs/whatsapp-orchestrator-v1.md`, `docs/superpowers/evidence/2026-10-13-*`, `docs/superpowers/evidence/SVI-*`).

### Plano de deploy e rollback

**Deploy**: sem migration — `git add` dos quatorze arquivos de aplicação (treze modificados + `users/visibility.py` novo) e dos treze arquivos de teste; deploy padrão do projeto (sem etapa extra de banco). Nenhuma variável de ambiente nova. Nenhuma alteração de permissão/grupo/role em produção.

**Rollback**: reverter o commit da feature restaura o comportamento anterior (contas inativas voltam a aparecer para todos os papéis, sem a política de `users/visibility.py`) sem exigir migration reversa, pois nenhuma coluna/tabela foi alterada — a feature é inteiramente código de apresentação/validação sobre dados já existentes. Nenhum dado é perdido ou precisa ser corrigido em caso de rollback (nenhuma escrita irreversível é introduzida por esta feature: `is_active` de `SystemUser` nunca é alterado por ela).

### Recursos descartáveis encerrados / preexistentes preservados

Encerrados nesta etapa: container Docker `uvi06-pg-disposable` (removido), `runserver` dev descartável na porta 8799 (processo em background parado via `TaskStop`), instância isolada do Edge headless (processo raiz e toda sua árvore de subprocessos encerrados por PID específico, identificado pela `CommandLine` conter `uvi06-edge-profile`).

Preservados e confirmados intactos: containers Docker preexistentes `lineops-db` (porta 5433) e `postgres`/pgvector (porta 5432) — ambos seguem `Up` após esta etapa; sessão real do usuário no Microsoft Edge (processo preexistente, nunca tocado); todo o trabalho untracked de outras features/documentos já presente no repositório antes desta etapa (listado em "Arquivos candidatos à entrega", seção "fora do escopo").

### Compliance Report

Fluxo seguido: reconciliação do baseline (103/103, sem ajuste por expectativa) → revisão de código linha a linha contra o contrato completo (UVI-01/02), não presumida dos resumos das etapas anteriores → preparo de ambiente genuinamente descartável e isolado (Postgres, servidor, navegador) → dataset sintético cobrindo a matriz pedida → 22 verificações reais em navegador, todas executadas de fato (não substituídas por `Client`) → proteção HTTP/persistência revalidada por leitura de código e pelos testes/navegador → nenhum defeito dentro do contrato encontrado (um achado cosmético fora do contrato registrado, não corrigido) → regressão completa por app inteiro reexecutada (sem reaproveitamento não demonstrado) → `manage.py check`/`git diff --check` limpos → esta atualização final da spec → encerramento dos recursos descartáveis com preservação comprovada dos preexistentes.

Nenhuma regra de negócio foi enfraquecida; nenhum teste foi relaxado; nenhuma permissão nova foi concedida; nenhum manager/escopo global foi alterado; nenhuma migration; nenhum acesso a PRD (ambiente 100% descartável e isolado, nunca o `lineops-db` nem o host `db` do `docker-compose`); nenhum `stash`/`reset`/`checkout` usado para obter RED (nenhum RED foi produzido nesta etapa — é etapa de verificação, não de implementação); nenhuma reversão ampla; trabalho alheio preservado (confirmado por `git status` idêntico ao snapshot inicial da conversa, mais a nova pasta de evidência).

### Veredito final

**UVI-06 concluída. Feature pronta para revisão/preparação de commit.** Suíte UVI completa (103 testes, 13 arquivos, 0 FAILED) e regressão por app inteiro (6 apps, 0 FAILED novo) reexecutadas e confirmadas nesta etapa. Revisão de código linha a linha confirma conformidade com todos os itens do contrato (UVI-01/02) nos quatro pontos de entrada (`SystemUserAdmin`, `EmployeeForm`/`EmployeeAdminForm`, `CombinedRegistrationForm`, FKs de `LineAllocationAdmin`/`AllocationPendencyAdmin`) e nas três superfícies de apresentação (`employee_list`/AJAX, `employee_detail`, `manager_dashboard`). Aceite em navegador real **executado de fato** nesta sessão (retificando o bloqueio registrado em UVI-05/05b, que não era permanente): 22/22 verificações PASS, desktop e mobile (390/360px), teclado, console, POST forjado, alternância de viewers, todas com captura de tela. Um achado cosmético fora do contrato (acentuação de um rótulo) registrado, não corrigido. `manage.py check` e `git diff --check` limpos. Nenhum dado/alteração de permissão fora do escopo da feature. Ambiente descartável desta rodada inteiramente encerrado; recursos preexistentes (bancos Docker, sessão real do navegador, trabalho untracked de outras features) confirmados intactos.

**Sem stage, commit, push, versão, deploy ou acesso a PRD nesta etapa ou em qualquer etapa anterior desta feature.** Parada após UVI-06, conforme instruído.

**Retificação desta mesma entrega, incorporada na conferência corretiva UVI-06b abaixo:** o veredito acima declarou "nenhum defeito novo dentro do contrato foi encontrado" e tratou a grafia sem acento de `KEEP_CURRENT_LABEL` como único achado, cosmético. Essa leitura estava incompleta — a revisão não havia inspecionado a renderização real de GET em `SystemUserAdmin`/`EmployeeAdminForm` nem `AllocationPendencyAdmin._visible_responsible_queryset`, onde vínculos inativos JÁ PERSISTIDOS continuavam expondo a identidade real (changelist e formulário de edição), e `technical_responsible` recebia o mesmo tratamento de `updated_by` apesar de serem categorias distintas (operacional vs. autoria histórica). Corrigido em UVI-06b, com RED real obtido por reversão temporária do código ao estado desta entrega.


## UVI-06b — Correção dos achados da revisão final (2026-10-14)

### Spec Summary

Correção de três achados reais da revisão UVI-06, confirmados por inspeção direta do código antes de qualquer alteração (não aceito o veredito anterior de conformidade como prova, conforme instruído): (1) `SystemUserAdmin.supervisor_email`/`manager_email` e `EmployeeAdminForm.corporate_email`/`manager_email` validam **novas** associações desde UVI-04/04b, mas o GET de edição e a changelist continuavam renderizando a identidade real de um vínculo **já persistido** quando esse vínculo está oculto para o viewer; (2) `AllocationPendencyAdmin._visible_responsible_queryset` aplicava o mesmo mecanismo (reinclusão do pk persistido com `__str__` real, portanto e-mail exposto na `<option>`) tanto a `technical_responsible` (referência operacional) quanto a `updated_by` (autoria histórica), sem distinguir as duas categorias; (3) `KEEP_CURRENT_LABEL`/`NO_ACTIVE_ACCOUNTS_LABEL` estavam sem acento, e a entrega anterior havia tratado isso como "fora do contrato por ausência de teste" — leitura retirada: os três literais aprovados sempre fizeram parte do contrato (UVI-01/02), a ausência de teste cobrando a grafia exata nunca tornou a grafia sem acento aceitável.

Correção mínima, reutilizando `users/visibility.py`: nenhum filtro global novo, nenhuma permissão nova, nenhuma migration, nenhuma refatoração ampla. `LineAllocationAdmin.allocated_by`/`released_by` foram conferidos (não presumido que autoria histórica e responsável operacional têm o mesmo contrato) e confirmados **já corretos** desde UVI-04 — nenhuma alteração necessária ali.

### Gap Analysis — achados confirmados por inspeção direta (não presumidos)

| # | Achado | Caminho | Confirmado por |
|---|---|---|---|
| 1 | GET de edição renderiza o e-mail real do vínculo persistido oculto no `<input value="...">` (EmailField padrão, sem mascaramento) | `users/admin.py::SystemUserAdmin.get_form` (sem `__init__` próprio); `employees/admin.py::EmployeeAdminForm.__init__` (sem ajuste de `initial`) | Leitura direta do código revertido ao estado de UVI-06 + RED real (ver Implementation Plan) |
| 2 | `list_display` de `SystemUserAdmin` (`manager_email`, `supervisor_email`) e `EmployeeAdmin` (`corporate_email`) usa o nome do campo bruto, sem projeção | `users/admin.py::SystemUserAdmin.list_display`; `employees/admin.py::EmployeeAdmin.list_display` (tuplas estáticas) | Leitura direta + RED real |
| 3 | `_visible_responsible_queryset` (pendencies) aplica a MESMA lógica (filtra novas escolhas + reinclui pk persistido com `__str__` real) a `technical_responsible` E `updated_by` — `RESPONSIBLE_FK_FIELDS = ("technical_responsible", "updated_by")` | `pendencies/admin.py` | Leitura direta + RED real (changelist e GET expõem `technical_responsible` oculto) |
| 4 | `LineAllocationAdmin.allocated_by`/`released_by` usa mecanismo equivalente (`_visible_author_queryset`), mas aqui é o tratamento CORRETO: U13 (UVI-02) já decidiu explicitamente "referência histórica exibida permanece" para estes dois campos — são autoria, não responsabilidade operacional | `allocations/admin.py` | Leitura direta: nenhuma mudança de comportamento necessária; conferido, não presumido |
| 5 | `KEEP_CURRENT_LABEL = "Manter vinculo atual"`, `NO_ACTIVE_ACCOUNTS_LABEL = "Nenhum usuario ativo disponivel"` sem acento | `users/visibility.py` | Leitura direta; nenhum teste do contrato exigia a grafia exata, mas os literais aprovados (UVI-01, seção "Rótulos" desta correção) sempre tiveram acento |

Nenhum teste pré-existente (103 da suíte UVI) cobria o GET de edição em Admin nem a changelist para vínculo persistido oculto — toda a cobertura anterior (UVI-04/04b) testava apenas a validação de **novas** associações via POST, nunca a renderização do valor já salvo. Esta é a lacuna real: a entrega original de UVI-04 implementou a metade "não aceitar nova associação oculta" do contrato (item 7 do Contract: "vínculo inativo existente pode ser conservado sem oferecer sua identidade no seletor") mas não a metade "sem oferecer sua identidade" para os campos de texto livre e FK de `technical_responsible`.

### Contratos técnicos fixados nesta correção

**Campos de texto livre (SystemUserAdmin, EmployeeAdminForm).** Quando o valor persistido de `supervisor_email`/`manager_email`/`corporate_email` está oculto para o viewer, o GET passa a renderizar o token `__keep_current__` como valor do campo (nunca o e-mail real), com `help_text` = `KEEP_CURRENT_LABEL` ("Manter vínculo atual") visível ao lado do campo. O campo é trocado de `EmailField` para `CharField` nesse caso específico (mesmo padrão já usado em `EmployeeForm._configure_account_field`), porque o `EmailField` padrão rejeitaria o token antes mesmo de `clean_<campo>` rodar ("Enter a valid email address", achado real desta correção, confirmado por teste isolado). O campo continua editável: o viewer pode digitar por cima um e-mail ativo para trocar explicitamente. No POST, o token só é válido quando há vínculo persistido oculto para aquele viewer especificamente (resolvido do banco, nunca de `self.instance` já mutado); fora desse contexto (criação, campo sem vínculo, vínculo já visível) é um erro de campo genérico ("Selecione uma conta ativa."), nova exceção `KeepCurrentInvalidContext` em `users/visibility.py`.

**`list_display` dos três Admins.** `SystemUserAdmin.get_list_display`/`EmployeeAdmin.get_list_display`/`AllocationPendencyAdmin.get_list_display` substituem os nomes de campo estáticos por funções de exibição que aplicam `mask_inactive_email` (texto) ou verificam `is_active` do objeto FK (`technical_responsible`). A resolução do conjunto de e-mails inativos é feita **uma única vez por requisição** (`resolve_all_inactive_emails_casefold`, nova função em `users/visibility.py` — uma consulta a `SystemUser.objects.filter(is_active=False)`, independente do número de linhas da página), capturada por *closure* dentro de `get_list_display` — nunca atribuída a `self` (ModelAdmin é compartilhado entre requests). ADMIN/DEV recebem sempre o set vazio (identidade real preservada, mesma exceção central).

**`technical_responsible` vs. `updated_by` (AllocationPendencyAdmin).** `technical_responsible` ("Responsável Técnico") é referência operacional — quem está tratando a pendência agora — e recebe o mesmo tratamento de "opção neutra" das demais entradas operacionais: novas escolhas continuam filtradas por `visible_accounts_queryset`; quando o vínculo persistido está oculto, ele é reincluído no queryset (para o POST sem alteração continuar válido) mas o **rótulo** da opção é substituído por `KEEP_CURRENT_LABEL` via `ModelChoiceField.label_from_instance` sobrescrito por instância (nunca o pk, que não é identidade) — a identidade real nunca chega ao HTML. `updated_by` ("Atualizado por") é autoria histórica — mesma categoria de `LineAllocationAdmin.allocated_by`/`released_by`, já corretamente tratada desde UVI-04 (U13: "referência histórica exibida permanece") — **sem mudança**: novas escolhas continuam filtradas, mas o vínculo persistido continua **exibido com a identidade real**, nunca mascarado. POST forjado continua recusado pelo `ModelChoiceField` padrão em ambos os campos (queryset restrito).

**`LineAllocationAdmin.allocated_by`/`released_by`.** Conferido explicitamente, sem presumir equivalência com `technical_responsible`: estes dois campos são preenchidos automaticamente pela aplicação (`AllocationService.allocate_line`/`release_line`, nunca escolhidos manualmente no fluxo real) — autoria histórica, não responsabilidade operacional assinalável. O contrato já aprovado em UVI-02 (U13) pede exatamente o comportamento já implementado (filtrar novas escolhas, exibir a referência histórica com identidade real). **Nenhuma alteração de código nesta correção.**

**Rótulos.** `KEEP_CURRENT_LABEL = "Manter vínculo atual"`, `NO_ACTIVE_ACCOUNTS_LABEL = "Nenhum usuário ativo disponível"`, `INACTIVE_ACCOUNT_LABEL = "Usuário inativo"` (inalterado desde UVI-05b) — os três com acento, conforme os literais aprovados desde a origem do contrato (UVI-01, Contract item 7). Retificação explícita: a afirmação de UVI-06 ("ausência de teste tornava a grafia fora do contrato") está **retirada** — a ausência de teste nunca tornou a grafia sem acento aceitável, apenas não havia prova automatizada do desvio.

### Implementation Plan — testes antes do código, confirmação de RED real

1. **Reversão temporária ao estado exato de UVI-06**, não presumida: os quatro arquivos de produção envolvidos (`users/visibility.py`, `users/admin.py`, `employees/admin.py`, `pendencies/admin.py`) foram reescritos byte a byte com o conteúdo lido no início desta tarefa, confirmado por `git diff --stat` idêntico ao snapshot do início da conversa (47/28/73 linhas — mesmos números do `git status` inicial). Nenhum `stash`/`reset`/`checkout` usado; a reversão foi feita escrevendo o conteúdo conhecido diretamente (preservando os outros dez arquivos da feature intactos).
2. **Três arquivos de teste novos escritos contra o código revertido**, cobrindo Admin real com viewer restrito com permissões suficientes: `users/test_uvi06_admin_keep_current.py` (8 testes), `employees/tests/test_uvi06_admin_keep_current.py` (8 testes), `pendencies/tests/test_uvi06_responsible_vs_author.py` (6 testes).
3. **RED real confirmado**: `pytest` nos três arquivos → **22 coletados, 11 FAILED, 11 PASSED**. Os 11 FAILED correspondem exatamente aos achados 1–3 (GET/changelist expõem identidade; marcador ainda não existe). Os 11 PASSED são os comportamentos já corretos desde UVI-04 (validação de novas associações), confirmando que o RED não decorria de rota negada nem de fixture malformada — dois ajustes de fixture foram necessários e documentados por causa real antes do RED ficar limpo: (a) `EmployeeAdminKeepCurrentFixture._make_restricted_viewer` não definia `supervisor_email` do próprio viewer BACKOFFICE, causando `scope_employee_queryset` vazio e rota inalcançável por um motivo de escopo (U11), não desta política — corrigido vinculando o viewer ao mesmo supervisor do funcionário de teste, mesmo cuidado já documentado em `test_uvi04_admin_free_text_association.py`; (b) o helper de POST de `EmployeeAdminKeepCurrentFixture` não enviava `line_status`/`is_deleted` (campos reais do `ModelForm`, `fields = "__all__"`), causando êxito de save não comparável ao esperado em dois testes — corrigido alinhando ao helper já usado em `test_uvi04_admin_free_text_association.py`.
4. **Correção mínima aplicada**, restaurando os quatro arquivos ao conteúdo com a correção: `users/visibility.py` ganha `resolve_all_inactive_emails_casefold`, `KeepCurrentInvalidContext`, `account_text_field_initial`, `resolve_account_text_field_post`, e os três literais corrigidos com acento; `users/admin.py` e `employees/admin.py` ganham `_apply_keep_current_text_field`/equivalente (troca de tipo de campo + `initial`) e `get_list_display`; `pendencies/admin.py` separa `OPERATIONAL_RESPONSIBLE_FK_FIELDS = ("technical_responsible",)` de `HISTORICAL_AUTHOR_FK_FIELDS = ("updated_by",)`, com `_technical_responsible_field` (mascaramento via `label_from_instance`) e `get_list_display` para a coluna `technical_responsible`.
5. **GREEN confirmado**: os mesmos três arquivos → **22 coletados, 0 FAILED, 22 PASSED**.

### Test Checklist — RED→GREEN por achado

| Achado | Cenário | RED (código revertido) | GREEN (correção aplicada) |
|---|---|---|---|
| 1 — GET SystemUserAdmin | Identidade ausente do HTML | FAIL | PASS |
| 1 — GET SystemUserAdmin | Marcador neutro presente | FAIL | PASS |
| 1 — POST SystemUserAdmin | Token preserva vínculo oculto | FAIL | PASS |
| 1 — POST SystemUserAdmin | Token em contexto inválido (campo sem vínculo) recusado | PASS (já correto) | PASS |
| 1 — POST SystemUserAdmin | Token na criação recusado | PASS (já correto) | PASS |
| 1 — POST SystemUserAdmin | Redisplay após erro em campo alheio preserva estado | PASS (já correto) | PASS |
| 2 — changelist SystemUserAdmin | Projeção oculta para restrito | FAIL | PASS |
| 2 — changelist SystemUserAdmin | Identidade real para ADMIN | PASS (já correto) | PASS |
| 1 — GET EmployeeAdminForm | Identidade ausente / marcador presente | FAIL / FAIL | PASS / PASS |
| 1 — POST EmployeeAdminForm | Token preserva vínculo oculto | FAIL | PASS |
| 1 — POST EmployeeAdminForm | Troca explícita por ativo | PASS (já correto) | PASS |
| 1 — POST EmployeeAdminForm | Forjado (outro inativo) recusado | PASS (já correto) | PASS |
| 2 — changelist EmployeeAdmin | Projeção oculta / identidade real ADMIN | FAIL / PASS | PASS / PASS |
| 3 — GET/changelist `technical_responsible` | Identidade ausente / marcador presente | FAIL / FAIL | PASS / PASS |
| 3 — GET `updated_by` | Identidade real permanece visível (controle) | PASS (já correto) | PASS |
| 3 — POST `technical_responsible` | Manter vínculo / forjado recusado | PASS (já correto, mecanismo antigo) | PASS (mecanismo novo) |

### Test Strategy

`pytest` (`venv/Scripts/python.exe -m pytest`, `DJANGO_SETTINGS_MODULE=config.settings_dev`, banco de teste isolado, execução sequencial): RED com os quatro arquivos de produção revertidos → **22/22 FAILED+PASSED conforme tabela acima (11 FAILED, 11 PASSED)**; GREEN com a correção restaurada → **22/22 PASSED**. Suíte UVI completa (16 arquivos: os 13 acumulados desde UVI-03 + os 3 novos) → **125 coletados, 0 FAILED, 125 PASSED, 2 subtests passed** (103 + 22, sem sobreposição — cada arquivo é módulo distinto). Regressão por app inteiro, reexecutada integralmente: `users` 45 passed + 2 subtests (37+8), `employees` 124 passed (116+8), `allocations` 49 passed (inalterado, app não tocado), `pendencies` 110 passed + 14 subtests (104+6), `dashboard/tests/` 105 passed + 7 subtests (inalterado), `telecom` 544 passed + 1 skipped + 5 subtests (inalterado). Nenhuma suíte somada com outra que já a contivesse. `manage.py check`: sem issues. `git diff --check`: sem problemas nos arquivos rastreados (único aviso é CRLF/LF em documento alheio pré-existente, não relacionado).

**Aceite em navegador real**, ambiente genuinamente descartável e isolado (detalhes em `docs/superpowers/evidence/2026-10-14-uvi06-correcao/report.md`): Postgres descartável via Docker (`uvi06b-pg-disposable`, porta `55436`, removido ao final — `lineops-db`/`postgres` preexistentes confirmados intactos antes e depois), `runserver` dev contra esse banco (porta `8798`, encerrado ao final), Edge headless em perfil isolado (`--user-data-dir` dedicado, `--remote-debugging-port=9445`, processo raiz identificado por `CommandLine` e encerrado especificamente por PID ao final — sessão real do usuário no Edge nunca tocada). Dados sintéticos (`uvi06b_setup_fixtures.py`), sem credenciais reais.

**23/23 verificações reais em navegador passaram** (`results.json`, 14 screenshots desktop 1280 + mobile 390/360 em `screenshots/`), cobrindo os três Admins (Usuários, Funcionários, Pendências), viewer restrito (BACKOFFICE/GERENTE com permissões técnicas suficientes) e ADMIN autorizado: changelist e GET de edição sem identidade oculta no DOM; marcador "Manter vínculo atual" visível; manter vínculo (submit sem alterar) persiste; troca explícita por ativo persiste e é confirmada pelo ADMIN; POST forjado recusado com mensagem genérica sem citar o valor, banco inalterado; `updated_by` confirmado **visível** no mesmo GET de Pendências (distinção operacional-vs-histórico comprovada lado a lado na mesma tela, ver screenshot `08_gerente_pendency_edit_1280.png`); navegação por teclado (Tab); console sem erros/exceções JS; responsivo em 1280/390/360 sem overflow, campos legíveis e marcadores neutros visíveis em todas as larguras.

Um ajuste de verificação foi necessário durante a execução, documentado e não é defeito de aplicação: a checagem inicial exigia a ausência total do e-mail forjado na página após a rejeição de `corporate_email` (campo de texto livre); a inspeção real mostrou que o `<input value="...">` ecoa de volta o valor que o próprio viewer digitou — mesmo raciocínio já aprovado em UVI-04b (`ErrorMessageDoesNotLeakIdentityTest`). A verificação foi corrigida para checar a garantia real do contrato (mensagem de erro genérica sem citar o valor + estado persistido inalterado), ambas já comprovadas.

Navegador real **foi executado de fato** — não substituído por `Client`, não declarado como comprovado sem execução.

### Compliance Report

Fluxo seguido, por achado: reconciliação do veredito anterior de UVI-06 não aceito como prova → inspeção direta do código → reversão temporária e controlada (byte a byte, confirmada por `git diff --stat` idêntico ao baseline) → três arquivos de teste escritos contra o código revertido → RED real confirmado (22 coletados, 11 FAILED, 11 PASSED, nenhum RED por rota negada) → dois ajustes de fixture por causa real documentada → correção mínima restaurada, reutilizando `users/visibility.py` → GREEN confirmado (22/22) → suíte UVI completa (125/125) e regressão por app inteiro (6 apps, reexecutados integralmente) sem quebra → aceite em navegador real genuinamente executado (23/23) → `manage.py check`/`git diff --check` limpos → esta atualização da spec, preservando o histórico das entregas anteriores (nenhum resultado apagado, apenas a estrutura do documento corrigida: o veredito de UVI-05b, deslocado acidentalmente para o fim do arquivo na edição anterior, foi restaurado à sua posição correta antes de UVI-06).

`LineAllocationAdmin.allocated_by`/`released_by` foi inspecionado e confirmado **já correto** — nenhuma mudança de código, decisão registrada com a razão (autoria histórica automática da aplicação, não responsabilidade operacional assinalável, U13 já aprovado). Nenhuma regra de negócio foi enfraquecida; nenhum teste foi relaxado; nenhuma permissão nova foi concedida; nenhum manager/escopo global foi alterado; nenhuma migration; nenhum acesso a PRD (ambiente 100% descartável, nunca `lineops-db` nem o host `db` do `docker-compose`); nenhuma reversão ampla além da reversão controlada e documentada dos quatro arquivos para obter RED real (restaurada integralmente antes do GREEN); trabalho alheio preservado (confirmado por `git status` ao final idêntico ao snapshot inicial mais as duas novas pastas de evidência e os arquivos novos desta correção).

Não se ampliou o escopo além dos achados pedidos: `EmployeeAdmin.list_display` exibindo `is_deleted`/outros campos sem relação com conta operacional não foi tocado; `dashboard/tests.py` vs. `dashboard/tests/` permanece não corrigido, por instrução explícita mantida desde UVI-03; `EmployeeAdmin.list_display` exibindo `corporate_email` agora É projetado (fazia parte do achado 2, não uma extensão de escopo).

### Veredito final

**UVI-06b concluída.** Os três achados da revisão final (identidade exposta em GET/changelist de vínculo já persistido em `SystemUserAdmin`/`EmployeeAdminForm`; `technical_responsible` tratado como autoria histórica quando é referência operacional; literais de rótulo sem acento) eram procedentes e foram corrigidos com RED→GREEN real (22 testes, reversão controlada e restaurada, não presumido). `LineAllocationAdmin.allocated_by`/`released_by` conferido e confirmado correto, sem necessidade de mudança — decisão registrada, não presumida. Suíte UVI completa 125/125 (0 FAILED), regressão por app inteiro sem quebra em nenhum dos 6 apps. Aceite em navegador real genuinamente executado: 23/23 verificações PASS, três Admins, viewer restrito e ADMIN, desktop/390/360px, teclado, console, POST forjado, com capturas de tela demonstrando lado a lado a distinção `technical_responsible` (mascarado) vs. `updated_by` (visível). `manage.py check` e `git diff --check` limpos. Estrutura do documento corrigida (veredito de UVI-05b restaurado à posição correta). Ambiente descartável desta rodada inteiramente encerrado; recursos preexistentes (bancos Docker, sessão real do navegador, trabalho de outras features) confirmados intactos.

**Diff corretivo pronto para nova revisão.** Sem stage, commit, push, versão, deploy ou acesso a PRD nesta correção ou em qualquer etapa anterior desta feature.

**Retificação desta mesma entrega, incorporada na conferência corretiva UVI-06c abaixo:** a revisão do diff resultante desta correção confirmou dois achados adicionais que o veredito acima não cobria. (1) A afirmação "o ROTULO da opcao... e substituido pela representacao neutra... a identidade real nunca chega ao HTML" (docstring de `_technical_responsible_field`) estava **incompleta**: `label_from_instance` neutraliza apenas o TEXTO visível da opção; o `<option value="...">` continuava carregando o PK real da conta oculta, reincluída no queryset. O contrato exige o token `__keep_current__` como valor da opção, não apenas rótulo neutro com PK real por baixo. (2) A afirmação de que uma `ValidationError` genérica ("Selecione uma conta ativa.") bastava para impedir exposição de identidade estava igualmente **incompleta**: a mensagem de erro não citava o valor, mas o `<input value="...">` do redisplay continuava ecoando o e-mail recusado — um vetor de exposição distinto da mensagem de erro, não coberto pela correção anterior. Ambos corrigidos em UVI-06c, com RED real.


## UVI-06c — Correção dos dois achados confirmados na revisão do diff UVI (2026-10-14)

### Spec Summary

Correção de dois achados confirmados por reprodução direta na revisão do diff resultante de UVI-06b: (1) `AllocationPendencyAdmin.technical_responsible` neutralizava apenas o rótulo da opção preservável (`label_from_instance`), mas o `<option value="...">` continuava carregando o PK real da conta oculta (reprodução confirmada: `<option value="1" selected>Manter vínculo atual</option>`) — o contrato exige o token `__keep_current__` como VALOR da opção, não apenas um rótulo neutro sobre um PK real; (2) em `SystemUserAdmin`, um POST de `manager_email`/`supervisor_email` apontando para conta inativa era corretamente recusado com mensagem genérica, mas o `<input value="...">` do redisplay continuava contendo o e-mail recusado — reprodução confirmada também em `EmployeeAdmin` (mesmo padrão, mesmos dois campos).

Correção mínima, reutilizando `users/visibility.py`: nenhum filtro global novo, nenhuma permissão nova, nenhuma migration. `updated_by` e `allocated_by`/`released_by` (autoria histórica, já corretos desde UVI-06b) não receberam a mesma regra — conferido explicitamente, não presumido. POR, permissões e tratamento geral da pendência inalterados.

**Retificações explícitas de afirmações anteriores (retiradas):**
- "o ROTULO da opcao... e substituido pela representacao neutra... a identidade real nunca chega ao HTML" (UVI-06b, docstring de `_technical_responsible_field`) — **incompleta**: o rótulo era neutro, mas o `<option value>` carregava o PK real da conta oculta no queryset reincluído. O "nunca chega ao HTML" só valia para o texto visível, não para o atributo `value`.
- Implícito em UVI-06b: que uma mensagem de erro genérica (sem citar o valor) bastava para impedir exposição de identidade no fluxo de rejeição. **Incompleto**: a mensagem genérica impede a exposição na PRÓPRIA mensagem, mas não no `<input value="...">` do campo — um vetor de exposição distinto, não coberto por aquela correção.

### Gap Analysis — achados confirmados por inspeção direta (não presumidos)

| # | Achado | Caminho | Confirmado por |
|---|---|---|---|
| 1 | `<option value="<pk-oculto>" selected>Manter vínculo atual</option>` — PK real da conta oculta como valor da opção preservável | `pendencies/admin.py::AllocationPendencyAdmin._technical_responsible_field` (reincluía `base.filter(pk=persisted_id)` no queryset, só trocava `label_from_instance`) | Leitura direta do código de UVI-06b + RED real (ver Implementation Plan) |
| 2 | `<input type="text" name="supervisor_email" value="<e-mail-recusado>">` após POST rejeitado | `users/admin.py` (campo sem override de `bound_data`/redisplay) | Leitura direta + RED real |
| 2 (mesmo padrão) | `<input type="text" name="corporate_email" value="<e-mail-recusado>">` após POST rejeitado | `employees/admin.py::EmployeeAdminForm` (mesmo padrão, mesma ausência de guarda) | Leitura direta + RED real |
| — | `updated_by`/`allocated_by`/`released_by` não devem receber a mesma regra | `pendencies/admin.py` (`HISTORICAL_AUTHOR_FK_FIELDS`), `allocations/admin.py` | Conferido: nenhuma mudança nesses caminhos; `test_uvi06_responsible_vs_author.py::UpdatedByHistoricalExceptionUnaffectedTest` continua GREEN sem alteração |

### Contratos técnicos fixados nesta correção

**`technical_responsible` — token como valor, nunca o PK oculto.** O PK da conta oculta **nunca** entra mais no queryset nem nas `choices` do campo. Quando o vínculo persistido está oculto para o viewer, uma opção **sintética** é adicionada — `(KEEP_CURRENT_TOKEN, KEEP_CURRENT_LABEL)`, valor literal `__keep_current__`, nunca um PK real — via `formfield.choices = [(KEEP_CURRENT_TOKEN, KEEP_CURRENT_LABEL)] + list(formfield.choices)`. `formfield.to_python` é sobrescrito por instância (mesmo padrão já usado para `label_from_instance` em UVI-06b, agora substituído por este mecanismo): quando o valor submetido é o token, resolve para `SystemUser.objects.filter(pk=persisted_id).first()` — o responsável **realmente persistido naquele registro específico**, relido do banco via `object_id` da URL a cada requisição (nunca de um PK enviado pelo cliente). `get_form` foi adicionado a `AllocationPendencyAdmin` (não existia antes) para sobrescrever `form.initial["technical_responsible"] = KEEP_CURRENT_TOKEN` quando mascarado — sem isso, `model_to_dict(instance)` preencheria o `initial` com o PK real, e o `<select>` não marcaria nenhuma opção como selecionada (a opção real foi removida do queryset). POST com PK de outro inativo (fora do queryset e diferente do token) continua recusado pelo `ModelChoiceField` padrão — nenhuma identidade reincluída para tornar isso possível. Token em contexto inválido (criação; pendência sem vínculo oculto) é recusado pelo mesmo mecanismo padrão (token não está no queryset nem é tratado como especial quando não mascarado). Troca explícita por um responsável ativo elegível continua funcionando (PK ativo está no queryset normalmente).

**Redisplay de campos de texto livre — `bound_data`, nunca a validação.** `users/visibility.py::should_mask_submitted_value_for_redisplay(viewer, submitted_value)` (nova função): retorna `True` quando o valor BRUTO submetido (não o persistido) resolve para uma conta oculta para aquele viewer — o token neutro nunca conta como oculto. `_guard_redisplay_of_hidden_value(field, viewer)` (nova função local em `users/admin.py` e `employees/admin.py`, mesmo padrão nos dois) sobrescreve `field.bound_data` por instância: quando `should_mask_submitted_value_for_redisplay` é verdadeiro, retorna o token em vez do valor bruto; caso contrário delega ao `bound_data` original. **Crítico**: `bound_data` é chamado exclusivamente por `BoundField.value()` (a REPRESENTAÇÃO), nunca por `BaseForm._clean_fields()` (a VALIDAÇÃO, que lê `bf.data` diretamente) — a entrada original continua chegando intacta ao `clean_<campo>`, que a recusa normalmente. Isto significa, por construção, que uma tentativa inválida não pode virar manutenção silenciosa nem sucesso: a neutralização acontece estritamente depois da decisão de validação, nunca antes. Quando o valor submetido é válido (ativo, ou legado sem conta correspondente), a guarda não interfere — o valor digitado continua visível no redisplay, inclusive quando o erro está em outro campo (preserva a escolha do viewer). ADMIN/DEV nunca acionam a guarda (`account_is_hidden_for_viewer` já retorna `False` para eles).

### Implementation Plan — testes antes do código, RED real confirmado

1. **Três arquivos de teste novos**, escritos contra o código de UVI-06b (os dois defeitos já estavam em produção nesta sessão — não foi necessária reversão, os defeitos já eram o estado real do código): `pendencies/tests/test_uvi06c_responsible_token_value.py` (11 testes), `users/test_uvi06c_redisplay_guard.py` (6 testes), `employees/tests/test_uvi06c_redisplay_guard.py` (3 testes).
2. **RED real confirmado**: 20 coletados, **8 FAILED, 11 PASSED** → após dois ajustes de ESCOPO DE ASSERÇÃO (não de comportamento) nos próprios testes, por causa real: duas checagens buscavam `value="1"` na página inteira, colidindo com o PK coincidente do `<select>` de "Usuário" (funcionário, não o responsável) — corrigido restringindo a busca ao `<select name="technical_responsible">` via regex escopado — **20 coletados, 8 FAILED, 12 PASSED** confirmado como o RED real e limpo. Os 8 FAILED correspondem exatamente aos dois achados; os 12 PASSED são comportamentos já corretos (troca por ativo, forjado-outro-pk já recusado, ADMIN preservado, valor ativo preservado em erro alheio — nenhum por rota negada).
3. **Correção mínima aplicada**: `users/visibility.py` ganha `should_mask_submitted_value_for_redisplay`; `users/admin.py` e `employees/admin.py` ganham `_guard_redisplay_of_hidden_value`, chamada ao final de `_apply_keep_current_text_field`/`_resolve_account_text_field`-equivalente para TODOS os campos (não só os já mascarados em GET — o achado 2 é geral); `pendencies/admin.py::_technical_responsible_field` reescrito (token real em vez de `label_from_instance`), mais `get_form`/`_masked_technical_responsible_pk` novos.
4. **GREEN confirmado**: os mesmos três arquivos → **20 coletados, 0 FAILED, 20 PASSED**.
5. **Regressão revelou um teste desatualizado pelo PRÓPRIO mecanismo antigo** (não um defeito novo): `pendencies/tests/test_uvi06_responsible_vs_author.py::test_unchanged_submission_preserves_hidden_responsible` reenviava o PK oculto BRUTO (aceito pelo mecanismo antigo, que o reincluía no queryset) e esperava sucesso — após a correção, isso é corretamente recusado (o PK oculto não está mais no queryset). Teste retificado para refletir a interação real pós-correção (reenvio via o TOKEN, que é o que um viewer real veria e reenviaria); um teste de controle novo (`test_raw_hidden_pk_resubmission_is_now_rejected`) prova explicitamente que o PK bruto agora é recusado — nenhuma cobertura perdida, o requisito original ("manter vínculo") continua coberto, só pelo caminho correto.

### Test Checklist — RED→GREEN por achado

| Achado | Cenário | RED | GREEN |
|---|---|---|---|
| 1 | `<option value>` da opção preservável é o token, não o PK oculto | FAIL | PASS |
| 1 | PK oculto ausente de qualquer `<option>` do select | FAIL | PASS |
| 1 | POST do token preserva o responsável persistido NESTE registro | FAIL | PASS |
| 1 | Token nunca é o valor escrito na FK (sempre o objeto real resolvido) | PASS (trivial, sem suporte a token) | PASS (significativo, com suporte real) |
| 1 | Token em contexto inválido (sem vínculo oculto) recusado | PASS (já correto, token sempre rejeitado) | PASS |
| 1 | Token na criação recusado | PASS (já correto) | PASS |
| 1 | Outro inativo forjado (PK diferente) recusado | PASS (já correto) | PASS |
| 1 | Troca explícita por ativo funciona | PASS (já correto) | PASS |
| 1 | Redisplay após erro em campo alheio preserva token sem vazar PK | FAIL | PASS |
| 1 | ADMIN vê identidade real e pode reassociar | PASS (já correto) | PASS |
| 2 (SystemUserAdmin) | Redisplay de forjado não ecoa e-mail no `value=` | FAIL | PASS |
| 2 (SystemUserAdmin) | Mensagem de erro genérica | PASS (já correto) | PASS |
| 2 (SystemUserAdmin) | Valor ativo válido preservado em erro alheio | PASS (já correto) | PASS |
| 2 (SystemUserAdmin) | Campo já mascarado: forjado-outro-inativo não vaza / token resubmetido preserva | FAIL / PASS | PASS / PASS |
| 2 (SystemUserAdmin) | ADMIN sem restrição (exceção) | PASS (já correto) | PASS |
| 2 (EmployeeAdmin) | Redisplay de forjado não ecoa e-mail no `value=` | FAIL | PASS |
| 2 (EmployeeAdmin) | Valor ativo válido preservado em erro alheio | PASS (já correto) | PASS |
| 2 (EmployeeAdmin) | ADMIN sem restrição | PASS (já correto) | PASS |

### Test Strategy

`pytest` (`venv/Scripts/python.exe -m pytest`, `DJANGO_SETTINGS_MODULE=config.settings_dev`, banco de teste isolado, execução sequencial): RED com o código de UVI-06b (sem reversão — os defeitos eram o estado real) → **20 coletados, 8 FAILED, 12 PASSED** (após ajuste de escopo das 2 asserções); GREEN com a correção aplicada → **20/20 PASSED**. Suíte UVI completa (19 arquivos: os 16 acumulados desde UVI-03/06b + os 3 novos) → **146 coletados, 0 FAILED, 146 PASSED, 2 subtests passed** (125 anteriores + 20 novos + 1 teste de controle novo em `test_uvi06_responsible_vs_author.py`, sem sobreposição). Regressão por app inteiro, reexecutada integralmente: `users` 51 passed + 2 subtests (45+6), `employees` 127 passed (124+3), `pendencies` 122 passed + 14 subtests (110+11+1), `allocations` 49 passed (inalterado, app não tocado), `dashboard/tests/` 105 passed + 7 subtests (inalterado), `telecom` 544 passed + 1 skipped + 5 subtests (inalterado). Nenhuma suíte somada com outra que já a contivesse. `manage.py check`: sem issues. `git diff --check`: sem problemas nos arquivos rastreados.

**Smoke em navegador real**, ambiente genuinamente descartável e isolado (detalhes em `docs/superpowers/evidence/2026-10-14-uvi06c-correcao/report.md`): Postgres descartável via Docker (`uvi06c-pg-disposable`, porta `55437`, removido ao final — `lineops-db`/`postgres` preexistentes confirmados intactos), `runserver` dev contra esse banco (porta `8797`, encerrado ao final), Edge headless em perfil isolado (`--remote-debugging-port=9446`, processo raiz encerrado por PID ao final — sessão real do usuário no Edge nunca tocada). Dataset sintético reaproveitado do fixture de UVI-06b (recriado no novo banco, mesmo formato), sem credenciais reais.

**16/16 verificações reais em navegador passaram** (`results.json`, 11 screenshots desktop 1280 + mobile 390/360 em `screenshots/`): `<option value="__keep_current__">` confirmado como o valor literal do marcador (não o PK) em `technical_responsible`; PK oculto (7) ausente do `<select>`; manter vínculo via token persiste e é confirmado pelo ADMIN; forjado (outro responsável inativo, PK injetado via `<option>` por JS) recusado sem vazar identidade; troca explícita por um responsável ativo persiste; teclado (Tab); `SystemUserAdmin`: `<input value="__keep_current__">` confirmado no redisplay após recusa (capturado via `outerHTML` do campo, não apenas busca textual na página) — nunca o e-mail forjado; mesma confirmação em `EmployeeAdmin`; ADMIN confirma estado persistido inalterado em ambos; responsivo 390/360 sem overflow; console sem erros/exceções JS.

Navegador real **foi executado de fato** — não substituído por `Client`, não declarado como comprovado sem execução.

### Compliance Report

Fluxo seguido, por achado: reconciliação dos achados confirmados na revisão do diff → leitura direta do código (não presumido do veredito anterior) → dois arquivos/três classes de teste escritos contra o código real com os defeitos → RED real confirmado (20 coletados, 8 FAILED, 12 PASSED, com dois ajustes de escopo de asserção documentados por causa real, não enfraquecimento) → correção mínima restaurada, reutilizando `users/visibility.py` → GREEN confirmado (20/20) → um teste pré-existente retificado por depender do mecanismo antigo exatamente corrigido, com teste de controle novo provando a mudança de comportamento → suíte UVI completa (146/146) e regressão por app inteiro (6 apps) sem quebra → smoke em navegador real genuinamente executado (16/16) → `manage.py check`/`git diff --check` limpos → esta atualização da spec, retificando as duas afirmações incompletas de UVI-06b e preservando o histórico integral (nenhum resultado anterior apagado).

`updated_by`/`allocated_by`/`released_by` conferidos e confirmados **sem alteração necessária** — autoria histórica continua recebendo tratamento distinto do responsável operacional, por decisão já registrada em UVI-06b e reconfirmada aqui sem mudança de código. Nenhuma regra de negócio foi enfraquecida; nenhuma permissão nova; nenhum manager/escopo global alterado; nenhuma migration; nenhum acesso a PRD; nenhum `stash`/`reset`/`checkout`/reversão ampla usado (os dois defeitos corrigidos eram o estado real do código nesta sessão, não exigiram reversão para produzir RED); trabalho alheio preservado (confirmado por `git status` com o mesmo conjunto de arquivos de aplicação desde o início da feature, mais os arquivos novos desta correção e a nova pasta de evidência).

### Veredito final

**UVI-06c concluída.** Os dois achados confirmados na revisão do diff UVI eram procedentes e foram corrigidos com RED→GREEN real (20 testes novos + 1 teste de controle, nenhuma reversão ampla necessária). `technical_responsible` agora usa o token `__keep_current__` como valor literal da opção preservável — o PK da conta oculta nunca mais entra no queryset/choices, resolvido server-side a partir do objeto realmente persistido naquele registro. Redisplay de POST recusado em `SystemUserAdmin`/`EmployeeAdmin` não ecoa mais a identidade oculta no `<input value="...">`, via `bound_data` sobrescrito (afeta só a representação, nunca a validação — nenhuma tentativa inválida vira manutenção silenciosa ou sucesso). `updated_by`/`allocated_by`/`released_by` conferidos, sem alteração. Suíte UVI completa 146/146 (0 FAILED), regressão por app inteiro sem quebra nos 6 apps. Smoke em navegador real genuinamente executado: 16/16 PASS, capturas de tela confirmando `value="__keep_current__"` tanto no `<select>` de responsável quanto nos `<input>` de texto livre recusados. `manage.py check` e `git diff --check` limpos. Duas afirmações incompletas de UVI-06b retificadas explicitamente. Ambiente descartável desta rodada inteiramente encerrado; recursos preexistentes confirmados intactos.

**Diff corretivo pronto para nova revisão.** Sem migration, stage, commit, push, versão, deploy ou acesso a PRD nesta correção ou em qualquer etapa anterior desta feature.

**Retificação desta mesma entrega, incorporada na conferência corretiva UVI-06d abaixo:** a afirmação "Redisplay de POST recusado... não ecoa mais a identidade oculta no `<input value="...">`, via `bound_data` sobrescrito" estava **incompleta**. A revisão focada subsequente confirmou que `should_mask_submitted_value_for_redisplay` devolvia o token `__keep_current__` para QUALQUER valor submetido que resolvesse para conta oculta, mesmo sem vínculo persistido oculto preservável naquele campo (`manager_email=None`, ou vínculo persistido ATIVO) — nesses casos o campo nunca é trocado para `CharField` (continua `type="email"`), e o token vira um "e-mail" sintaticamente inválido no próprio input. A afirmação implícita de que "devolver `__keep_current__` em qualquer redisplay recusado" era a representação correta está **retirada**: o token só pode representar um vínculo persistido, oculto e preservável naquele campo específico; nos demais casos a representação correta é vazia. Corrigido em UVI-06d, com RED real.


## UVI-06d — Correção do defeito de redisplay sem vínculo persistido (2026-10-14)

### Spec Summary

Correção do defeito confirmado na revisão focada do diff UVI: `SystemUserAdmin` com `manager_email=None` recebendo POST para conta inativa oculta tinha a associação corretamente recusada, mas o redisplay renderizava `<input type="email" value="__keep_current__">` — sem vínculo algum a manter, o token aparecia como um "e-mail" inválido no próprio campo (reenviar sem alteração produziria erro de formato, não a preservação de nada real). Mesmo padrão confirmado em `EmployeeAdmin.manager_email`. Um segundo caso relacionado foi corrigido junto: vínculo persistido **ativo** também não pode ser substituído pelo marcador, reservado exclusivamente a vínculos inativos.

Correção mínima, reutilizando `users/visibility.py` e o contexto do vínculo persistido já calculado em `_apply_keep_current_text_field`/`_resolve_account_text_field` — nenhuma regra de negócio duplicada entre os dois Admins (mesma função central, mesma assinatura nos dois chamadores). Nenhuma alteração de permissão, manager global ou regra legada. O seletor de `technical_responsible` (corrigido em UVI-06c) não foi tocado.

**Retificação explícita (retirada):** a afirmação de UVI-06c de que `bound_data` sobrescrito resolvia genericamente a exposição de identidade no redisplay estava incompleta — resolvia o VAZAMENTO DE IDENTIDADE, mas introduzia um defeito distinto (token sem vínculo correspondente) ao assumir que QUALQUER valor oculto submetido deveria virar o token. O token exige um vínculo persistido, oculto e preservável especificamente naquele campo.

### Gap Analysis — achado confirmado por reprodução direta

| Cenário | Comportamento antes da correção | Causa |
|---|---|---|
| (a) `manager_email=None`, POST para conta inativa | `<input type="email" value="__keep_current__">` -- token sem vínculo a representar | `should_mask_submitted_value_for_redisplay` ignorava se havia vínculo persistido; só considerava o valor SUBMETIDO |
| (b) `manager_email=<ativo>`, POST para conta inativa diferente | Mesmo problema -- token substituía a representação de um vínculo ATIVO | Mesma causa |
| (c) `manager_email=<inativo>` (oculto, preservável), POST para OUTRO inativo | Já correto desde UVI-06c (token representa o vínculo oculto real) | Não afetado -- reconfirmado sem regressão |

Reproduzido em `SystemUserAdmin.manager_email` (achado original) e confirmado por conferência explícita também em `EmployeeAdmin.manager_email` (mesma lógica, `_guard_redisplay_of_hidden_value`/`_apply_keep_current_text_field` local, mesmo padrão duplicado nos dois Admins).

### Contratos técnicos fixados nesta correção

`users/visibility.py::redisplay_value_for_rejected_submission(viewer, submitted_value, persisted_email)` substitui `should_mask_submitted_value_for_redisplay` (removida, sem outros consumidores — confirmado por `grep` antes da remoção). Retorna `None` quando a representação padrão deve ser usada (token literal, valor que não resolve para conta oculta — ativo ou legado sem conta). Quando o valor submetido resolve para conta oculta: retorna o token `__keep_current__` **somente** se `persisted_email` (o vínculo JÁ persistido, resolvido do banco pelo chamador, nunca de `self.instance` já mutado pelo `ModelForm`) também estiver oculto para o viewer — vínculo preservável de fato. Caso contrário (sem vínculo persistido, ou vínculo persistido visível/ativo) retorna string vazia (`""`) — representação vazia, nunca gravada (a função só afeta `Field.bound_data`, chamada exclusivamente por `BoundField.value()`; a validação em `_clean_fields` continua lendo `bf.data` diretamente, recusando a entrada original normalmente — nenhuma tentativa inválida vira manutenção silenciosa, limpeza ou sucesso). `_guard_redisplay_of_hidden_value(field, viewer, persisted_email)` (ambos os Admins) passa o `persisted_email` já calculado pelo chamador (`_apply_keep_current_text_field`/`_resolve_account_text_field`), sem nova consulta ao banco.

### Implementation Plan — testes antes do código, RED real confirmado

1. **Dois arquivos de teste novos**, escritos contra o código com o defeito (sem reversão — o defeito já era o estado real do código desta sessão): `users/test_uvi06d_redisplay_without_link.py` (10 testes, cenários a–f para `SystemUserAdmin`), `employees/tests/test_uvi06d_redisplay_without_link.py` (9 testes, mesmos cenários para `EmployeeAdmin`).
2. **RED real confirmado**: 19 coletados, **4 FAILED, 15 PASSED**. Os 4 FAILED reproduzem exatamente o achado (cenários a/b, nos dois Admins). Os 15 PASSED cobrem: recusa com banco intacto (já correto — a validação nunca foi o problema), cenário (c) reconfirmado sem regressão, recuperação após erro, erro em campo alheio preserva escolha ativa válida, controle ADMIN/DEV — nenhum por rota negada. Dois testes exigiram ajuste de asserção (não de comportamento): a checagem original exigia `value=""` literal no HTML, mas o widget do Django omite o atributo `value` por completo quando o valor é string vazia (comportamento padrão do `TextInput`) — corrigido para `assertNotIn("value=", ...)`, mesma garantia (nenhum valor renderizado), forma de verificação ajustada à causa real observada.
3. **Correção mínima aplicada**: `users/visibility.py` ganha `redisplay_value_for_rejected_submission` (substitui a função anterior); `users/admin.py` e `employees/admin.py` passam `persisted` (já calculado) para `_guard_redisplay_of_hidden_value`, que agora usa a nova função.
4. **GREEN confirmado**: os mesmos dois arquivos → **19 coletados, 0 FAILED, 19 PASSED**.

### Test Checklist — RED→GREEN por cenário

| Cenário | SystemUserAdmin | EmployeeAdmin |
|---|---|---|
| (a) sem vínculo: POST recusado, banco intacto | PASS (já correto) | PASS (já correto) |
| (a) redisplay vazio, sem e-mail oculto, sem token | FAIL → PASS | FAIL → PASS |
| (a) erro explícito de campo presente | PASS (já correto) | — (equivalente coberto) |
| (b) vínculo ativo: POST recusado, vínculo ativo preservado no banco | PASS (já correto) | PASS (já correto) |
| (b) redisplay não usa o token reservado a inativos | FAIL → PASS | FAIL → PASS |
| (c) vínculo oculto: representação neutra válida (GET) | PASS (já correto, UVI-06c) | PASS (já correto, UVI-06c) |
| (c) reenvio do token conserva o vínculo real | PASS (já correto, UVI-06c) | PASS (já correto, UVI-06c) |
| (d) correção pelo usuário (valor válido) e reenvio salva | PASS (já correto) | PASS (já correto) |
| (e) erro em campo alheio preserva valor ativo válido submetido | PASS (já correto) | PASS (já correto) |
| (f) ADMIN/DEV sem restrição | PASS (já correto) | PASS (já correto) |

### Test Strategy

`pytest` (`venv/Scripts/python.exe -m pytest`, `DJANGO_SETTINGS_MODULE=config.settings_dev`, banco de teste isolado, execução sequencial): RED com o código com o defeito → **19 coletados, 4 FAILED, 15 PASSED**; GREEN com a correção aplicada → **19/19 PASSED**.

Baseline UVI-06c reconfirmado sem alteração (não presumido do relato anterior): `pendencies/tests/test_uvi06c_responsible_token_value.py` + `users/test_uvi06c_redisplay_guard.py` + `employees/tests/test_uvi06c_redisplay_guard.py` → **20 coletados, 0 FAILED, 20 PASSED**, idêntico ao veredito de UVI-06c.

Suíte UVI completa (21 arquivos: os 19 acumulados desde UVI-03/06c + os 2 novos) → **165 coletados, 0 FAILED, 165 PASSED, 2 subtests passed**. Reconciliação do delta: baseline UVI informado nesta tarefa = 146 (125 + 20 + 1 controle, UVI-06c); 165 − 146 = 19, exatamente os testes novos desta correção, por node ID, sem sobreposição (dois arquivos distintos, nenhum teste duplicado entre si).

Regressão por app inteiro: `users` 61 passed + 2 subtests (51 + 10 novos), `employees` 136 passed (127 + 9 novos), `pendencies` 122 passed + 14 subtests (inalterado — confirmado por `grep` que a função removida não tinha consumidores em `pendencies/admin.py`). `allocations`, `dashboard/tests/`, `telecom` não tocados nesta correção (apenas três arquivos modificados: `users/visibility.py`, `users/admin.py`, `employees/admin.py`) — não reexecutados nesta etapa por ausência de qualquer alteração de código que os afete, consistente com o critério de regressão proporcional já usado desde UVI-03a. `manage.py check`: sem issues. `git diff --check`: sem problemas nos arquivos rastreados.

**Smoke em navegador real**, ambiente genuinamente descartável e isolado (detalhes em `docs/superpowers/evidence/2026-10-14-uvi06d-correcao/report.md`): Postgres descartável via Docker (`uvi06d-pg-disposable`, porta `55438`, removido ao final — `lineops-db`/`postgres` preexistentes confirmados intactos), `runserver` dev contra esse banco (porta `8796`, encerrado ao final), Edge headless em perfil isolado (`--remote-debugging-port=9447`, processo raiz encerrado por PID ao final — sessão real do usuário no Edge nunca tocada). Dataset sintético dedicado (`uvi06d_setup_fixtures.py`): três contas `SystemUser` e três `Employee` cobrindo os três estados do campo `manager_email` (sem vínculo, vínculo ativo, vínculo oculto preservável).

**29/29 verificações reais em navegador passaram** (`results.json`, 10 screenshots desktop 1280 + mobile 390/360 em `screenshots/`): recusa sem vínculo anterior confirmada com redisplay vazio (sem token, sem e-mail oculto) e erro explícito visível na tela; banco intacto confirmado pelo ADMIN; recuperação com valor vazio salva corretamente; vínculo ativo preservado sem o token substituí-lo; cenário (c) reconfirmado sem regressão; teclado (Tab); **validação HTML5 nativa confirmada por execução real**: o campo permanece `type="email"` nos cenários (a)/(b), e `element.checkValidity()` do próprio navegador retorna `False` para um valor de formato inválido digitado no campo — prova de que a correção não contornou nem desabilitou a validação nativa do navegador (o `Client` de teste não teria como provar isso, por não executar o motor de validação HTML5 de um navegador real). Responsivo 390/360 sem overflow. Console sem erros/exceções JS.

Navegador real **foi executado de fato** — não substituído por `Client`, não declarado como comprovado sem execução.

### Compliance Report

Fluxo seguido: reconciliação do achado confirmado na revisão focada → leitura direta do código → dois arquivos de teste escritos contra o código com o defeito (sem reversão, o defeito já era o estado real) → RED real confirmado (19 coletados, 4 FAILED, 15 PASSED, com dois ajustes de asserção documentados por causa real do widget Django, não enfraquecimento) → correção mínima restaurada, reutilizando `users/visibility.py` e o `persisted_email` já calculado pelos chamadores (sem consulta adicional ao banco, sem estado compartilhado em `ModelAdmin`) → GREEN confirmado (19/19) → baseline UVI-06c reconfirmado sem alteração (20/20) → suíte UVI completa (165/165) e regressão proporcional de `users`/`employees`/`pendencies` sem quebra → smoke em navegador real genuinamente executado, incluindo validação HTML5 nativa (29/29) → `manage.py check`/`git diff --check` limpos → esta atualização da spec, retificando a afirmação incompleta de UVI-06c e preservando o histórico integral.

Nenhuma regra de negócio foi enfraquecida; nenhuma permissão nova; nenhum manager/escopo global alterado; nenhuma migration; nenhum acesso a PRD; nenhum `stash`/`reset`/`checkout`/reversão ampla usado (o defeito corrigido era o estado real do código nesta sessão, não exigiu reversão para produzir RED); nenhuma consulta adicional ao banco introduzida (o `persisted_email` já era calculado pelo chamador antes desta correção, apenas passado adiante); trabalho alheio preservado (confirmado por `git status` com o mesmo conjunto de arquivos de aplicação desde o início da feature, mais os arquivos novos desta correção e a nova pasta de evidência).

### Veredito final

**UVI-06d concluída.** O defeito de redisplay sem vínculo persistido preservável, confirmado na revisão focada do diff UVI, era procedente e foi corrigido com RED→GREEN real (19 testes novos, nenhuma reversão ampla necessária). O token `__keep_current__` agora só é usado como representação quando existe, naquele campo específico, um vínculo persistido que também está oculto para o viewer — nos demais casos (sem vínculo, ou vínculo ativo) a representação é vazia, com o erro de campo explícito preservado. Mesma correção aplicada nos dois Admins (`SystemUserAdmin`/`EmployeeAdmin`) via a mesma função central, sem duplicação de regra de negócio. Baseline UVI-06c (20 testes) reconfirmado sem regressão. Suíte UVI completa 165/165 (0 FAILED) — 146 (baseline informado) + 19 novos, sem sobreposição. Regressão em `users`/`employees`/`pendencies` sem quebra; `allocations`/`dashboard`/`telecom` não tocados, não reexecutados por ausência de qualquer alteração que os afete. Smoke em navegador real genuinamente executado: 29/29 PASS, incluindo confirmação real de que a validação HTML5 nativa do navegador permanece ativa nos campos não mascarados. `manage.py check` e `git diff --check` limpos. Afirmação incompleta de UVI-06c retificada explicitamente. Ambiente descartável desta rodada inteiramente encerrado; recursos preexistentes confirmados intactos.

**Diff corretivo pronto para nova revisão.** Sem migration, stage, commit, push, versão, deploy ou acesso a PRD nesta correção ou em qualquer etapa anterior desta feature.


## Ressalva da revisão focada e preparação do commit — 2026-10-14

Retifica a expressão "zero consulta adicional" de UVI-06d: capturar e passar o e-mail persistido não exige nova consulta para recuperá-lo, mas redisplay_value_for_rejected_submission consulta a atividade da conta submetida e, quando aplicável, do vínculo anterior. Não foi comprovada ausência de consultas adicionais na renderização.

Revisão focada reexecutou os cinco arquivos UVI-06c/06d: 39 PASSED, dois warnings preexistentes de CheckConstraint, 67,14s. manage.py check e git diff --check sem erros. Nenhum novo bloqueio funcional encontrado nesse escopo. Navegador e suíte completa de 165 não foram reexecutados nessa revisão; os resultados anteriores permanecem históricos.

Preparação autorizada pelo usuário: commit de código, testes UVI e esta spec. Evidências locais de navegador permanecem fora do commit; os links locais anteriores não constituem artefatos disponíveis no clone remoto. Documento de auditoria diária e demais arquivos alheios preservados. Sem mudança de versão, migration ou deploy.
