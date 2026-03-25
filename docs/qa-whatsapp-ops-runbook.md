# Runbook de Operacao WhatsApp em QA

Este runbook instala e valida os jobs operacionais de QA para:

- `check_meow_health`
- `check_meow_capacity`
- `sync_whatsapp_sessions`
- `reconcile_whatsapp_sessions`

O alvo e um host Debian 13.1 com o ambiente QA ja subido via
[`docker-compose.qa.yml`](/C:/Users/andre.souza/Desktop/reviewer/lineops/docker-compose.qa.yml).

## Objetivo

Manter o LineOps de QA com visibilidade basica sobre:

- saude das instancias `meow`
- capacidade por instancia
- sincronizacao do status das sessoes
- inconsistencias locais entre `PhoneLine`, `WhatsAppSession` e `MeowInstance`

## Artefatos preparados

- Wrapper de execucao: [`scripts/run_qa_manage_command.sh`](/C:/Users/andre.souza/Desktop/reviewer/lineops/scripts/run_qa_manage_command.sh)
- Exemplo de cron: [`scripts/cron/lineops-qa-whatsapp.cron.example`](/C:/Users/andre.souza/Desktop/reviewer/lineops/scripts/cron/lineops-qa-whatsapp.cron.example)

## Premissas

- repositorio clonado em `/opt/lineops/lineops`
- stack de QA rodando com `web`, `db` e `nginx`
- `.env.qa` presente
- `docker compose` funcional no host
- usuario operacional com permissao para executar Docker

## Configuracao relevante

No `.env.qa`, mantenha pelo menos:

```env
WHATSAPP_MEOW_TIMEOUT_SECONDS=5
WHATSAPP_SESSION_STALE_MINUTES=30
```

`WHATSAPP_SESSION_STALE_MINUTES` controla quando uma sessao passa a ser
considerada desatualizada na reconciliacao e na visao operacional.

## Bootstrap inicial das instancias Meow

Antes de habilitar os jobs operacionais, cadastre as instancias
`MeowInstance` no Django.

Use
[`docs/meow-instances.example.json`](/C:/Users/andre.souza/Desktop/reviewer/lineops/docs/meow-instances.example.json)
como base, ajustando `name` e `base_url` para o ambiente real.

### Validar sem persistir

```bash
cd /opt/lineops/lineops
./scripts/run_qa_manage_command.sh bootstrap_meow_instances --config docs/meow-instances.example.json --dry-run
```

### Aplicar bootstrap

```bash
cd /opt/lineops/lineops
./scripts/run_qa_manage_command.sh bootstrap_meow_instances --config docs/meow-instances.example.json
```

O comando e idempotente por `name`: ele cria novas instancias e atualiza as
existentes. Se o JSON tiver nomes duplicados, o bootstrap falha antes de
persistir.

## 1. Validar o ambiente antes do cron

```bash
cd /opt/lineops/lineops
docker compose --env-file .env.qa -f docker-compose.qa.yml ps
```

Esperado:

- container `lineops-app-qa` em estado `running`
- container `lineops-db-qa` em estado `running`

## 2. Criar diretorio de logs operacionais

```bash
cd /opt/lineops/lineops
mkdir -p logs/ops
```

## 3. Garantir permissao de execucao do wrapper

```bash
cd /opt/lineops/lineops
chmod +x scripts/run_qa_manage_command.sh
```

## 4. Testar os comandos manualmente

### Health check

```bash
cd /opt/lineops/lineops
./scripts/run_qa_manage_command.sh check_meow_health
```

### Capacidade

```bash
cd /opt/lineops/lineops
./scripts/run_qa_manage_command.sh check_meow_capacity
```

### Sync de sessoes

```bash
cd /opt/lineops/lineops
./scripts/run_qa_manage_command.sh sync_whatsapp_sessions
```

### Reconciliacao

```bash
cd /opt/lineops/lineops
./scripts/run_qa_manage_command.sh reconcile_whatsapp_sessions
```

Se algum comando falhar aqui, nao instale o cron ainda. Corrija o ambiente primeiro.

## 5. Instalar o cron

Copie o exemplo para um arquivo temporario:

```bash
cd /opt/lineops/lineops
cp scripts/cron/lineops-qa-whatsapp.cron.example /tmp/lineops-qa-whatsapp.cron
```

Revise o caminho `/opt/lineops/lineops` se o deploy estiver em outro diretorio.

Instale:

```bash
crontab /tmp/lineops-qa-whatsapp.cron
crontab -l
```

## 6. Frequencia recomendada

- `check_meow_health`: a cada 5 minutos
- `check_meow_capacity`: a cada 15 minutos
- `sync_whatsapp_sessions`: a cada 10 minutos
- `reconcile_whatsapp_sessions`: a cada 60 minutos

Esses intervalos sao suficientes para QA sem pressionar o host.

## 7. Logs esperados

Os jobs escrevem em:

- `/opt/lineops/lineops/logs/ops/check_meow_health.log`
- `/opt/lineops/lineops/logs/ops/check_meow_capacity.log`
- `/opt/lineops/lineops/logs/ops/sync_whatsapp_sessions.log`
- `/opt/lineops/lineops/logs/ops/reconcile_whatsapp_sessions.log`

Exemplo de verificacao:

```bash
tail -n 50 /opt/lineops/lineops/logs/ops/check_meow_health.log
tail -n 50 /opt/lineops/lineops/logs/ops/check_meow_capacity.log
tail -n 50 /opt/lineops/lineops/logs/ops/sync_whatsapp_sessions.log
tail -n 50 /opt/lineops/lineops/logs/ops/reconcile_whatsapp_sessions.log
```

## 8. Leitura rapida dos comandos

### `check_meow_health`

Atualiza `health_status` e `last_health_check_at` das instancias `MeowInstance`.

Uso direcionado:

```bash
./scripts/run_qa_manage_command.sh check_meow_health --instance-id 1
```

### `check_meow_capacity`

Mostra distribuicao de sessoes por instancia, incluindo:

- `active`
- `connected`
- `pending`
- `degraded`
- `capacity_level`

Uso direcionado:

```bash
./scripts/run_qa_manage_command.sh check_meow_capacity --instance-id 1
```

### `sync_whatsapp_sessions`

Consulta o `meow` e sincroniza o estado local das sessoes.

Uso direcionado:

```bash
./scripts/run_qa_manage_command.sh sync_whatsapp_sessions --instance-id 1
./scripts/run_qa_manage_command.sh sync_whatsapp_sessions --session-id session_+5511999999999
```

### `reconcile_whatsapp_sessions`

Verifica inconsistencias locais, como:

- `LINE_HIDDEN`
- `INSTANCE_INACTIVE`
- `INSTANCE_UNAVAILABLE`
- `INSTANCE_DEGRADED`
- `NEVER_SYNCED`
- `SYNC_STALE`

Uso direcionado:

```bash
./scripts/run_qa_manage_command.sh reconcile_whatsapp_sessions --instance-id 1
./scripts/run_qa_manage_command.sh reconcile_whatsapp_sessions --session-id session_+5511999999999
```

## 9. Troubleshooting

### `docker compose exec` falha com container parado

Valide o stack:

```bash
cd /opt/lineops/lineops
docker compose --env-file .env.qa -f docker-compose.qa.yml ps
docker compose --env-file .env.qa -f docker-compose.qa.yml logs web --tail=100
```

### `Arquivo .env.qa nao encontrado`

Confirme que o deploy de QA tem:

```bash
ls -la /opt/lineops/lineops/.env.qa
```

### Cron executa sem escrever log

Confirme:

```bash
ls -la /opt/lineops/lineops/logs/ops
crontab -l
```

### Muitos erros de `INSTANCE_UNAVAILABLE`

Validar:

- conectividade do host QA ate os 5 `meows`
- timeout `WHATSAPP_MEOW_TIMEOUT_SECONDS`
- firewall ou proxy entre QA e `meow`

## 10. Pos-deploy

Depois do primeiro deploy de QA com esse bloco, rode manualmente:

```bash
cd /opt/lineops/lineops
./scripts/run_qa_manage_command.sh check_meow_health
./scripts/run_qa_manage_command.sh check_meow_capacity
./scripts/run_qa_manage_command.sh sync_whatsapp_sessions
./scripts/run_qa_manage_command.sh reconcile_whatsapp_sessions
```

So depois disso habilite o cron.
