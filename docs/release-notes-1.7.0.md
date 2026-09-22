# Release Notes 1.7.0

Data: 2026-09-22

## Resumo

Cadastro e acompanhamento do SELO WHATS LINEOPS nas linhas telefônicas. Incremento MINOR de 1.6.0 para 1.7.0 por adicionar funcionalidade retrocompatível. Requisitos e evidências: [fonte da verdade](superpowers/specs/2026-09-17-phone-line-whatsapp-seal-design.md).

## Funcionalidades

- Cadastro e edição organizados em Dados da linha e Selo WhatsApp LineOps.
- Opções Sem selo, META ONE e META VERIFICADO.
- Com selo, ativação, vencimento informado manualmente, e-mail cadastrado e pagamento são obrigatórios.
- Pagamentos: cartão de crédito ou Gift Card Google.
- Remover o selo limpa seus dados ao salvar; reativar sem selo não recupera dados antigos.
- Detalhe e listagens overview/OPERATOR mostram selo e indicador de vencimento, incluindo Carregar mais.
- Aviso amarelo entre sete e um dias antes, laranja no dia e vermelho após vencer, com texto e singular/plural adequados.
- Indicadores calculados pela data local, sem alterar status, ativação ou alocação da linha.

## Interface e validação

- Campos condicionais com JavaScript e validação no servidor, mantendo formulário utilizável sem scripts.
- Labels em português, resumo de erros focável e correção de mensagens contraditórias para entradas inválidas.
- Contraste do indicador Vence hoje corrigido e contenção móvel da tabela OPERATOR ajustada.

## Compatibilidade e implantação

- Migration aditiva `telecom.0021_phoneline_whatsapp_seal_and_more`: cinco campos novos; linhas existentes permanecem Sem selo.
- Sem notificações externas ou tarefa agendada nesta entrega.
- Atualizar código/imagem e aplicar a migration antes de servir a nova versão.
- Ambientes que definem `APP_VERSION` devem configurar `APP_VERSION=1.7.0` e recriar o container web. A variável de ambiente prevalece sobre o padrão do código.
- Em rollback de aplicação, preservar os campos e dados já gravados; não reverter a migration operacional automaticamente.

## Validação e limitações

- Conferência anterior ao commit da feature: 301 testes aprovados, 1 pulado e 5 subtests aprovados; Django system check limpo.
- Validação visual e funcional registrada na fonte da verdade.
- Deploy da funcionalidade relatado pelo operador em 22/09: migration 0021 aplicada, web healthy, system check limpo e Nginx recarregado. Aceite funcional de PRD e atualização do rótulo 1.7.0 ainda não confirmados.
- Drift preexistente de `PhoneLine.origem` e `DailyUserAction.action_type` não integra esta release. Não gerar migrations em PRD para eliminar o aviso.
