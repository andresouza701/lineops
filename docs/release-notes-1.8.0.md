# Release Notes 1.8.0

Data: 2026-09-30

## Resumo

Hub de Relatórios exclusivo para ADMIN. Incremento MINOR de 1.7.0 para 1.8.0 por adicionar funcionalidades retrocompatíveis. Contratos e evidências: [fonte da verdade](superpowers/specs/2026-09-22-reports-hub-design.md).

## Funcionalidades

- Seis relatórios: Selos WhatsApp, Inventário de linhas, Alocações, Pendências, Histórico da linha e Indicadores diários.
- Seleção de relatório, período inicial/final, filtros específicos, totalizadores e paginação de 50 resultados.
- Período aplicado à data definida no contrato de cada relatório, com referência local America/Sao_Paulo.
- Exportação CSV e XLSX de todos os resultados filtrados, consultando os dados atuais no momento do download.
- Divisão automática em ZIP quando os resultados ultrapassam 100.000 linhas, preservando todas as partes.
- Indicadores diários incluem dias sem registros e reutilizam as fórmulas do dashboard sem gravar snapshots.

## Interface e validação

- Navegação visível apenas para ADMIN e autorização também aplicada no servidor.
- Layout com fundo azul escuro, tabelas com rolagem interna e funcionamento com ou sem JavaScript.
- Troca de relatório preserva datas e opção de exclusão; reinicia filtros específicos, filtro de linha e paginação.
- CSV com BOM e separador ponto e vírgula; XLSX com telefones como texto e contexto dos filtros.
- Proteção contra interpretação de texto como fórmula e limpeza de arquivos temporários em sucesso, falha e encerramento da resposta.
- Histórico da linha rejeita XLSX com célula acima de 32.767 caracteres, orientando usar CSV para preservar o conteúdo integral.
- Validação de datas extremas evita overflow nos relatórios que calculam o limite exclusivo do período.

## Compatibilidade e implantação

- Nenhuma migration nova nesta entrega. O plano de migrations executado pelo operador retornou sem operações pendentes.
- Nginx configura `proxy_read_timeout 180s` na rota de exportação; esse limite mede inatividade entre leituras, não duração total do download.
- Ambientes que definem `APP_VERSION` devem configurar `APP_VERSION=1.8.0` e recriar o container web. A variável de ambiente prevalece sobre o padrão do código.
- Deploy funcional confirmado pelo operador em 30/09. Esta alteração do rótulo para 1.8.0 ainda precisa ser integrada e implantada.
- Preservar backup e imagem de rollback da implantação; rollback de aplicação não exige restaurar o banco automaticamente.
- Drift preexistente de `PhoneLine.origem` e `DailyUserAction.action_type` permanece fora do escopo. Não gerar migrations em PRD para eliminar o aviso.

## Validação e limitações

- Revisão final documentada: 652 testes aprovados, 24 testes de volume não selecionados; ensaios de volume possuem evidências próprias nas etapas de cada relatório.
- Aceites visuais e operacionais em ambientes isolados registrados na fonte da verdade, incluindo larguras de 1280, 390 e 360 pixels e downloads reais.
- Resultados de desempenho em ambientes de teste não constituem SLA de produção; capacidade sob carga concorrente não foi demonstrada.
- Indicadores derivados de estado mutável podem mudar em consultas posteriores; exportações não preservam um snapshot da consulta anterior.
