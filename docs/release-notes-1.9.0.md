# Release Notes 1.9.0

Data: 2026-10-13

## Resumo

Incremento MINOR de 1.8.0 para 1.9.0 pelas funcionalidades de ativação/preço e identificação visual de selos WhatsApp e pela restrição de abertura de pendências por origem da linha. Consolida os commits ccfabc3, 8d03892, c76619e e 45fb42a. Contratos: [indicador visual](superpowers/specs/2026-10-05-phone-line-seal-indicator-design.md) e [restrição de pendências por origem](superpowers/specs/2026-10-13-pendency-origin-restriction-design.md).

## Funcionalidades

- Cadastro/edição de selo com situação de ativação, categoria, plano e valor mensal editável; referências de preço separadas do valor informado.
- Linhas com selo disponível, ainda não ativado, identificadas explicitamente. Valor zero permitido somente para não ativos; negativos rejeitados; máximo R$ 299,00.
- Círculo junto ao telefone nas superfícies aplicáveis, incluindo relatórios, conteúdo dinâmico, modais e Django Admin. Exportações CSV/XLSX preservadas sem decoração.
- Indicador à esquerda do número, com separador único e borda da mesma cor do preenchimento. Sem selo, sem círculo.
- Estados: ativo verde, próximo do vencimento amarelo, vence hoje laranja, vencido vermelho e não ativado/inconsistente cinza. Informação textual acessível e foco preservados.
- Tons com maior contraste somente no Admin claro; temas escuros preservados.
- Abertura/reabertura de pendências bloqueada para origens Aparelho OP e Aparelho Pessoal, inclusive requisição direta e Django Admin. Origem Aparelho permanece permitida; tratamento e resolução de pendências existentes preservam suas permissões.
- Modal informa o motivo e desabilita apenas a abertura bloqueada, permitindo salvar observação quando autorizado.

## Correções

- Isolamento do índice autorizado BLIP entre threads do Admin.
- Admin de Pendências tolera alocação ausente e carrega funcionário sem consulta adicional por registro.
- POST inválido BLIP preserva o número persistido no bloco “Dado salvo”.
- Indicadores em modais e detalhamento diário agrupados ao número; formulários mantêm campo utilizável quando o foco revela texto do selo.
- Respostas atrasadas de outro registro não sobrescrevem o modal atual. Salvar e Assumir/Liberar são serializados na exibição atual para impedir operações simultâneas pelos botões.
- Admin avalia a alocação proposta ao criar ou reabrir pendência; pedidos de abertura recusados não persistem alterações parciais de status/observação.

## Compatibilidade e implantação

- O conjunto desde 1.8.0 inclui a migration telecom.0022 de ativação/preço; o operador confirmou sua aplicação no deploy anterior. Este ajuste de versão não cria migration.
- No deploy de c76619e, o plano de migrations enviado pelo operador retornou sem operações pendentes; check e inicialização também foram confirmados. Não confundir esses resultados com aceite visual completo.
- No deploy de 45fb42a, build, check, plano sem migrations pendentes e inicialização foram confirmados pela saída do operador. Health final e smoke funcional desse deploy não foram apresentados nesta preparação de versão.
- Ambientes com APP_VERSION definido devem configurar APP_VERSION=1.9.0 e recriar o container web: a variável de ambiente prevalece sobre o padrão do código.
- A publicação da versão exige build e recriação do serviço web; atualizar o repositório sozinho não altera a versão em execução.
- Manter imagem de rollback e backups. Não reverter migration nem restaurar banco automaticamente para desfazer uma alteração visual.
- Drift conhecido de PhoneLine.origem e DailyUserAction.action_type permanece fora do escopo; não gerar migrations em produção para eliminar o aviso.

## Validação e limitações

- Revisão independente do ajuste visual: 45 testes focados aprovados. Revisão POR: 43 testes e 18 subtestes aprovados; correções posteriores de UI verificadas por execução das funções reais em harness Node e leitura dos logs de navegador (16/16 desktop e 9/9 mobile). Não são a suíte completa do projeto nem nova execução independente de navegador.
- Evidências anteriores de navegador e regressão constam da spec; não foram todas reexecutadas nesta preparação de versão.
- Pendente: comparação antes/depois do overflow de detalhamento mobile na página real completa. Harness local não encerra esse aceite; a versão não implica resolução dessa pendência.
- Contagem histórica RED 17 → GREEN 29 sem artefato anterior suficiente permanece como limitação documental, sem reconstituição presumida.
- POR não garante serialização contra alteração concorrente de PhoneLine.origem; aplica a origem persistida no momento da avaliação. Contenção estrita de foco do modal permanece como limitação documentada.
