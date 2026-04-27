# Spec: WhatsApp Reconnect Queue Position

## Objective

Mostrar ao usuario a posicao da sua solicitacao na fila de execucao da reconexao WhatsApp.

Quando um usuario iniciar uma reconexao pela tela de detalhe da linha, o LineOps deve retornar no payload a posicao atual da sessao na fila do RPA. A posicao deve ser exibida na tela enquanto a sessao estiver aguardando execucao (`QUEUED`). Quando a sessao sair da fila e entrar em execucao, a UI deve deixar de mostrar posicao numerica e indicar que a reconexao esta em execucao.

## Success Criteria

- Ao criar uma sessao `QUEUED`, o payload de `start` retorna `queue_position`.
- Ao consultar `status` de uma sessao `QUEUED`, o payload retorna `queue_position`.
- `queue_position=1` significa que a sessao e a proxima da fila para o servidor alvo.
- A posicao considera apenas sessoes `QUEUED` com `active_lock=True` do mesmo `target_server`.
- A ordenacao da fila e por `created_at` ascendente e `_id` ascendente como desempate deterministico.
- Sessoes em execucao ou terminais retornam `queue_position=None`.
- A UI mostra `Posicao na fila: N na fila de execucao` somente quando `queue_position` estiver preenchido.
- A UI mostra estado de execucao quando o status nao for `QUEUED` e ainda nao for terminal.
- O comportamento atual de iniciar, consultar status, enviar codigo, cancelar e historico de reconexao permanece compativel.

## Tech Stack

- Django 5.x
- Python 3.11
- MongoDB via PyMongo
- Template Django com JavaScript inline em `templates/telecom/phoneline_detail.html`
- Docker Compose existente para ambiente local/producao

## Commands

Run focused tests:

```powershell
python manage.py test telecom.tests --keepdb
```

Run broader telecom tests:

```powershell
python manage.py test telecom --keepdb
```

Run in Docker when validating container behavior:

```powershell
docker compose exec web python manage.py test telecom.tests --keepdb
```

## Project Structure

- `telecom/services/reconnect_service.py`: regra de negocio e serializacao do payload de reconexao.
- `telecom/repositories/reconnect_sessions.py`: consultas Mongo para sessoes de reconexao.
- `telecom/views.py`: endpoints AJAX de status/start/codigo/cancelamento.
- `templates/telecom/phoneline_detail.html`: componente visual de reconexao WhatsApp.
- `telecom/tests.py`: testes unitarios e integrados existentes do fluxo de telecom/reconexao.

## Current Flow

1. A tela `PhoneLineDetailView` renderiza a secao `Reconexao WhatsApp` quando `RECONNECT_ENABLED=True` e a linha e elegivel.
2. O botao `Iniciar reconexao` chama `PhoneLineReconnectStartView`.
3. `PhoneLineReconnectStartView` chama `ReconnectService.start_for_line(phone_line)`.
4. `ReconnectService` cria ou reutiliza uma sessao em `RPA.reconnect_sessions`.
5. A tela passa a fazer polling em `PhoneLineReconnectStatusView`.
6. O RPA consome sessoes `QUEUED` por servidor alvo e muda o status conforme o fluxo avanca.

## Proposed Contract

Adicionar os campos abaixo ao payload serializado por `ReconnectService._serialize_session`:

```json
{
  "queue_position": 3,
  "queue_position_label": "3 na fila de execucao"
}
```

Rules:

- `queue_position` e inteiro ou `null`.
- `queue_position_label` e string ou `null`.
- Para status `QUEUED`, calcular posicao por `target_server`.
- Para status diferente de `QUEUED`, retornar `null` nos dois campos.
- Se a repository nao conseguir calcular a posicao por erro de Mongo, o fluxo de status/start nao deve quebrar; deve retornar `null` e registrar log de warning.

## Repository Behavior

Adicionar metodo no repository Mongo:

```python
def count_queued_before_session(self, *, target_server: str, created_at, session_id: str) -> int:
    ...
```

Query esperada:

```python
{
    "target_server": target_server,
    "status": "QUEUED",
    "active_lock": True,
    "$or": [
        {"created_at": {"$lt": created_at}},
        {"created_at": created_at, "_id": {"$lt": session_id}},
    ],
}
```

Return:

- Quantidade de sessoes na frente da sessao atual.
- `queue_position = count_before + 1`.

## Service Behavior

`ReconnectService._serialize_session` deve:

1. Normalizar `raw_status`.
2. Se `raw_status != "QUEUED"`, retornar `queue_position=None`.
3. Se `raw_status == "QUEUED"`, usar `target_server`, `created_at` e `_id` do documento para calcular posicao.
4. Se faltar qualquer campo necessario, retornar `queue_position=None`.
5. Se repository nao expuser `count_queued_before_session`, retornar `queue_position=None` para manter compatibilidade com fakes/testes antigos.
6. Se a consulta falhar, capturar a excecao, logar warning e retornar `queue_position=None`.

## UI Behavior

Adicionar uma linha no bloco `data-reconnect-user-flow`:

```html
<dt class="col-sm-4" data-reconnect-queue-position-row>Posicao na fila</dt>
<dd class="col-sm-8" data-reconnect-queue-position-row data-reconnect-queue-position>-</dd>
```

JavaScript:

- Ler `payload.queue_position_label || payload.queue_position`.
- Mostrar a linha somente quando `payload.queue_position` existir.
- Para `QUEUED`, o hint deve informar que a solicitacao esta aguardando sua vez.
- Para status ativo diferente de `QUEUED`, o hint deve seguir como execucao/preparo.
- Para terminal, ocultar a linha de posicao.

Texto recomendado:

```text
Posicao na fila: 3 na fila de execucao
```

## Docker Operational Boundary

Nao ha mudanca esperada em `Dockerfile` ou `docker-compose.yml`.

O container `web` ja consome as variaveis de ambiente do projeto. A feature depende das configuracoes existentes:

- `RECONNECT_ENABLED=True`
- `RECONNECT_MONGO_URI`
- `RECONNECT_MONGO_DATABASE`
- `RECONNECT_MONGO_COLLECTION`

Validacao em Docker e recomendada somente para confirmar que o container consegue consultar Mongo com as variaveis reais.

## Testing Strategy

Unit/service tests:

- Criar uma sessao `QUEUED` com dois itens anteriores no fake repository e validar `queue_position=3`.
- Validar que sessao `QUEUED` sem `created_at` retorna `queue_position=None`.
- Validar que status `WAITING_FOR_CODE` retorna `queue_position=None`.
- Validar que erro do repository nao quebra `_serialize_session`.
- Validar que `start_for_line` retorna `queue_position` no payload da sessao criada.
- Validar que reutilizar sessao ativa `QUEUED` tambem retorna a posicao atual.

Repository tests with fake collection:

- Validar query de `count_queued_before_session` para `target_server`, `QUEUED`, `active_lock=True`, `created_at < current` e desempate por `_id`.

Template/response tests:

- Validar que a resposta JSON de start/status contem `queue_position`.
- Validar que o template contem os data attributes da posicao na fila.

## Boundaries

Always:

- Calcular posicao no backend.
- Usar apenas sessoes `QUEUED` com `active_lock=True`.
- Filtrar por mesmo `target_server`.
- Manter compatibilidade com payloads existentes.
- Nao expor lista completa da fila para o usuario.

Ask first:

- Alterar regra de prioridade do RPA.
- Exibir telefones ou dados de outras sessoes na UI.
- Criar endpoint novo publico para listagem de fila.
- Alterar Dockerfile ou docker-compose.

Never:

- Calcular posicao no frontend com lista completa de sessoes.
- Contar sessoes em execucao como posicao de fila.
- Quebrar start/status se a posicao nao puder ser calculada.
- Expor credenciais Mongo em logs, testes ou templates.

## Open Questions

Nenhuma pendencia funcional. A decisao aprovada e exibir a posicao do usuario na fila de execucao.
