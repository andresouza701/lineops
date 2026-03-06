# LineOps

Aplicação Django para gestão de linhas telefônicas, alocações e indicadores.

## Requisitos

- Docker e Docker Compose
- Python 3.11+ (se rodar sem Docker)

## Variáveis de ambiente

Crie o arquivo `.env` a partir do exemplo:

```bash
cp .env.example .env
```

Campos mínimos:

- `APP_ENV=dev|prod`
- `DEBUG=True|False`
- `SECRET_KEY=...`
- `ALLOWED_HOSTS=host1,host2`
- `DJANGO_SETTINGS_MODULE=config.settings_dev` (ou `config.settings_prod`)
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`

## Subir com Docker

```bash
docker compose down
docker compose up -d --build
```

## Migrações

```bash
docker compose exec web python manage.py migrate
```

## Criar superusuário

```bash
docker compose exec web python manage.py createsuperuser
```

Depois ajuste role para acessar telas com controle por função:

```bash
docker compose exec web python manage.py shell -c "from users.models import SystemUser; u=SystemUser.objects.get(email='seu-email@dominio.com'); u.role=SystemUser.Role.ADMIN; u.save(update_fields=['role']); print(u.email, u.role)"
```

## Health check

- Endpoint: `/health/`
- Retorno: `{"status": "ok"}`
- Cabeçalho: `Cache-Control: no-store`
- Para exigir autenticação no health check:

```env
HEALTHCHECK_REQUIRE_AUTH=True
```

## Troubleshooting (QA)

### Erro: `DB_PASSWORD not set`

Confirme que `DB_PASSWORD` existe no arquivo `.env` (não apenas no `.env.example`).

### Erro do Postgres: `directory "/var/lib/postgresql/data" exists but is not empty`

Se ambiente QA puder perder dados:

```bash
docker compose down -v
docker compose up -d --build
```

Se não puder perder dados, alinhe o volume do compose com o layout de dados já existente.
