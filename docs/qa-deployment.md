# Deploy de QA

Esta configuração é voltada para um servidor Oracle Linux com:

- 4 vCPU
- 4 GB RAM
- 100 GB disco

## Topologia

O ambiente de QA sobe três containers:

- `db`: PostgreSQL 15
- `web`: Django + Gunicorn
- `nginx`: proxy reverso com TLS

## Ajustes de capacidade

O compose de produção usa `gunicorn` com `9 workers` e `4 threads`, o que é agressivo para 4 GB RAM.

Em QA, usar:

- `3 workers`
- `2 threads`

Isso mantém alguma concorrência sem pressionar demais memória e CPU.

O PostgreSQL em QA também usa parâmetros mais conservadores:

- `shared_buffers=256MB`
- `effective_cache_size=1GB`
- `max_connections=60`

## Arquivos

- Compose: `docker-compose.qa.yml`
- Settings: `config/settings_qa.py`
- Variáveis de ambiente: `.env.qa`

## Subida

1. Criar arquivo de ambiente:

```bash
cp .env.qa.example .env.qa
```

2. Ajustar no `.env.qa`:

- `SECRET_KEY`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `DB_PASSWORD`
- `TLS_CERT_PATH`
- `TLS_KEY_PATH`

3. Subir:

```bash
docker compose -f docker-compose.qa.yml down
docker compose -f docker-compose.qa.yml up -d --build
```

4. Validar:

```bash
docker compose -f docker-compose.qa.yml ps
curl -I http://localhost
curl -k https://localhost/health/
```

## Observações

- `RUN_MIGRATIONS=1` e `COLLECT_STATIC=1` seguem habilitados no startup do container web.
- O health check continua público por padrão em QA.
- `settings_qa.py` mantém o comportamento próximo de produção, mas desabilita HSTS persistente.
- Se o QA ficar atrás de outro proxy ou load balancer, ajuste `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` e os certificados conforme o host real.
