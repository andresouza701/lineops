# Integracao MEOW no LineOps

## 1. Resumo Executivo

### Objetivo
Adicionar ao LineOps a capacidade de orquestrar conexoes WhatsApp via MEOW, cobrindo:

- criacao de conexao
- geracao de QR Code
- acompanhamento de status da sessao
- encerramento de sessao

### Direcao proposta
O LineOps continuara sendo o sistema principal de negocio e a fonte de verdade local.
O MEOW sera tratado como um executor externo, sujeito a falhas, lentidao e indisponibilidade.

### Resultado esperado
Ao final da implementacao, o LineOps passara a:

- manter o estado oficial da conexao WhatsApp no proprio banco
- expor endpoints padronizados via DRF
- processar polling e retry de forma assincrona e persistente
- operar com rastreabilidade por `correlation_id`
- reduzir dependencia direta do frontend em relacao ao MEOW

## 2. Contexto Atual do LineOps

Hoje o LineOps e um monolito Django com apps de dominio como `telecom`, `allocations`, `dashboard`, `employees` e `users`.

Pontos relevantes do estado atual:

- DRF ja esta habilitado, mas a API ainda e parcial
- o deploy produtivo e feito com Gunicorn + Docker Compose
- ha padroes ja consolidados de consistencia com `transaction.atomic` e `select_for_update`
- existe endpoint `/health/`
- ainda nao existe worker dedicado, fila persistente ou endpoint de readiness
- os testes automatizados ainda dependem bastante de SQLite, o que limita validacao real de concorrencia

Esse contexto favorece uma evolucao aderente ao stack atual, sem introduzir um segundo backend ou uma arquitetura paralela dentro do mesmo servico.

## 3. Problema que a Integracao Resolve

Sem uma integracao estruturada, o LineOps nao consegue tratar de forma confiavel o ciclo de vida das conexoes WhatsApp operadas externamente.

Os principais riscos do modelo atual ou de uma integracao simplificada seriam:

- dependencia excessiva da disponibilidade do MEOW
- perda de rastreabilidade operacional
- duplicidade de sessoes ou inconsistencias de estado
- retry sem controle
- falhas silenciosas em producao
- acoplamento forte entre frontend e provedor externo

## 4. Principios da Solucao

### 4.1 LineOps como orquestrador
Toda decisao de negocio e todo estado relevante ficam no LineOps.
O MEOW apenas executa a acao externa.

### 4.2 Persistencia antes de efeito externo
Antes de chamar o MEOW, o LineOps registra localmente a intencao e enfileira o trabalho.

### 4.3 Processamento assincrono confiavel
Chamadas externas, polling e retry nao rodam dentro do processo web nem dentro de request HTTP.

### 4.4 Estado explicito
A integracao usa state machine validada em servico, e nao regras dispersas em signal ou view.

### 4.5 Observabilidade
Toda operacao deve ser rastreavel por `correlation_id`, com logs estruturados e historico de integracao.

## 5. Arquitetura Proposta

### 5.1 Nova app Django dedicada
Criar uma app de dominio chamada `integrations_whatsapp`.

Estrutura interna prevista:

- `domain`
- `application`
- `infrastructure/db`
- `infrastructure/http`
- `api`
- `workers`

Essa organizacao melhora separacao de responsabilidade sem abandonar o modelo de app Django ja usado no LineOps.

### 5.2 Componentes principais

#### API DRF
Responsavel por receber comandos e consultas do LineOps:

- criar conexao
- listar conexoes
- consultar conexao
- gerar QR
- consultar status
- encerrar sessao

#### Camada de aplicacao
Responsavel pelos casos de uso, regras de orquestracao, validacao de transicao de estado e idempotencia.

#### Cliente HTTP do MEOW
Responsavel por encapsular a comunicacao externa, com timeout, tratamento de erro e redacao de dados sensiveis.

#### Worker dedicado
Responsavel por:

- consumir jobs persistidos
- executar chamadas ao MEOW
- aplicar polling
- realizar retry com backoff
- marcar falhas terminais

## 6. Fronteira de Responsabilidade

### O que fica no LineOps

- estado oficial da conexao
- `session_id`
- controle de versao (`version`)
- historico operacional
- regras de transicao
- retry e polling
- autorizacao e autenticacao dos endpoints

### O que fica no MEOW

- execucao da sessao WhatsApp
- geracao remota de QR
- informacao de status remoto
- encerramento tecnico da sessao

## 7. Modelo Conceitual de Dados

### `whatsapp_connections`
Tabela principal da integracao.

Responsabilidades:

- representar a conexao atual de WhatsApp no LineOps
- armazenar `session_id`, estado, QR atual, versao e ultimo erro

### `jobs`
Fila persistente para:

- criacao de sessao
- geracao de QR
- polling de status
- encerramento de sessao
- retries

### `integration_logs`
Historico tecnico e operacional da integracao, com foco em auditoria e suporte.

## 8. Estados da Conexao

Estados obrigatorios da fase 1:

- `NEW`
- `SESSION_REQUESTED`
- `QR_AVAILABLE`
- `WAITING_SCAN`
- `CONNECTED`
- `FAILED`
- `EXPIRED`
- `DISCONNECTED`

Esses estados tornam o comportamento visivel, auditavel e tratavel pelo suporte.

## 9. Fluxos de Alto Nivel

### 9.1 Criacao de conexao
1. Cliente chama `POST /integrations/whatsapp`
2. LineOps cria ou reutiliza a conexao local de forma idempotente
3. LineOps grava um job de criacao
4. Worker consome o job e chama o MEOW
5. O resultado atualiza o estado local

### 9.2 Geracao de QR
1. Cliente chama `POST /integrations/whatsapp/{id}/generate-qr`
2. Se houver QR valido, o mesmo QR e retornado
3. Se nao houver QR valido, o LineOps grava job
4. Worker chama o MEOW e atualiza o estado

### 9.3 Consulta de status
1. Cliente chama `GET /integrations/whatsapp/{id}/status`
2. O LineOps responde com o ultimo estado persistido localmente
3. O polling remoto continua sendo responsabilidade do worker

### 9.4 Encerramento de sessao
1. Cliente chama `DELETE /integrations/whatsapp/{id}/session`
2. O LineOps registra a intencao localmente
3. Um job e criado para cleanup remoto
4. O worker tenta encerrar a sessao no MEOW
5. O estado local converge para `DISCONNECTED` ou `FAILED`

## 10. Impacto Operacional

### Mudancas esperadas no deploy

- manter o servico `web` atual
- adicionar um servico `worker`
- manter banco PostgreSQL compartilhado
- adicionar endpoint `/readiness/`

### Beneficios operacionais

- retry resiliente a restart de container
- menos acoplamento do request HTTP com provedor externo
- possibilidade de observacao e suporte com trilha de execucao
- menor risco de perda de estado por falha transitiva

## 11. Riscos Principais

### Risco 1: concorrencia e inconsistencias
Sem controle de versao e claim seguro de jobs, dois workers ou duas requisicoes podem competir pela mesma conexao.

Mitigacao:

- `version` otimista na conexao
- claim de jobs com lock em PostgreSQL
- transacoes curtas

### Risco 2: indisponibilidade do MEOW
O provedor externo pode falhar, responder lentamente ou ficar fora.

Mitigacao:

- timeout explicito
- retry com backoff
- fallback controlado para `FAILED`
- leitura de status sempre local

### Risco 3: vazamento de credenciais ou dados sensiveis
Integracao externa aumenta risco de exposicao de segredo e payload tecnico.

Mitigacao:

- credenciais apenas em variaveis de ambiente
- redacao de logs
- nao expor segredo para frontend

### Risco 4: falso senso de cobertura de testes
SQLite nao cobre corretamente cenarios reais de lock e concorrencia.

Mitigacao:

- criar trilha de testes critica em PostgreSQL

## 12. Decisoes de Arquitetura Ja Recomendadas

- nao embutir FastAPI dentro do monolito
- nao executar background task dentro do processo web
- nao depender de memoria local para fila ou polling
- nao usar signal como camada principal de state machine
- usar DRF para expor o contrato da integracao
- tratar o LineOps como fonte local de verdade

## 13. Fases de Implementacao

### Fase 1 - Fundacao tecnica

- criar app `integrations_whatsapp`
- adicionar `correlation_id`
- ajustar logging
- criar readiness
- preparar trilha de testes PostgreSQL

### Fase 2 - Modelo local e API

- criar tabelas `whatsapp_connections`, `jobs`, `integration_logs`
- implementar state machine
- criar casos de uso locais
- expor endpoints DRF

### Fase 3 - Integracao externa e worker

- implementar `MeowClient`
- subir worker dedicado
- implementar polling e retry
- consolidar falhas terminais

### Fase 4 - Hardening operacional

- cleanup de jobs e logs
- cobertura adicional de concorrencia
- documentacao operacional
- ajustes de observabilidade

## 14. Beneficios Esperados para o Negocio

- maior confiabilidade no ciclo de vida das conexoes WhatsApp
- menor dependencia operacional de acao manual
- melhor rastreabilidade para suporte e auditoria
- base tecnica para futuras integracoes externas
- evolucao aderente ao stack atual, sem ruptura de arquitetura

## 15. Decisoes Pendentes para Fechamento

- confirmar se a conexao pertence oficialmente a `PhoneLine`
- fechar regra final de idempotencia do `POST`
- fechar regra de reuso ou expiracao do QR
- definir semantica final do `DELETE`
- confirmar escopo inicial de permissao
- confirmar formato final de credenciais do MEOW por ambiente

## 16. Recomendacao Final

A recomendacao e seguir com a integracao em uma nova app Django especializada, com DRF, fila persistente em banco e worker dedicado.

Essa abordagem:

- respeita a arquitetura atual do LineOps
- reduz risco operacional
- evita criar uma segunda stack dentro do mesmo servico
- suporta crescimento futuro com mais previsibilidade

Em termos executivos, e a opcao mais pragmatica para atingir qualidade de producao sem reescrever o sistema.
