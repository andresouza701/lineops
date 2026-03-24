# Runbook de Provisionamento do Servidor QA

Este runbook prepara o ambiente de QA do LineOps em um servidor Oracle Linux com:

- 4 vCPU
- 4 GB RAM
- 100 GB disco

O alvo é subir o stack Docker do projeto com:

- PostgreSQL
- Django + Gunicorn
- Nginx com TLS

## Premissas

- Oracle Linux 8 ou 9
- acesso `sudo`
- DNS ou IP já definido para o host de QA
- certificados TLS já emitidos ou copiados para o servidor
- 5 instâncias MEOW já acessíveis em rede quando a integração começar a ser usada

## Referências usadas

- Docker Compose plugin em Linux: Docker Docs  
  https://docs.docker.com/compose/install/linux/
- Docker em Oracle Linux: Oracle docs  
  https://docs.oracle.com/en/operating-systems/oracle-linux/docker/docker-InstallingOracleContainerRuntimeforDocker.html

## 1. Atualizar o servidor

```bash
sudo dnf update -y
sudo dnf install -y git curl yum-utils ca-certificates
sudo systemctl reboot
```

Depois do reboot:

```bash
sudo dnf update -y
```

## 2. Instalar Docker Engine e Compose

Para Oracle Linux 8/9, a forma mais previsível é usar o repositório oficial do Docker para RPM-based Linux.

```bash
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Validar:

```bash
docker --version
docker compose version
```

## 3. Habilitar e iniciar Docker

```bash
sudo systemctl enable --now docker
sudo systemctl status docker --no-pager
```

Adicionar seu usuário operacional ao grupo Docker:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

Validar:

```bash
docker info
```

## 4. Ajustar firewall

Se `firewalld` estiver ativo:

```bash
sudo systemctl enable --now firewalld
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
sudo firewall-cmd --list-services
```

Se o acesso ao SSH estiver restrito por regra própria, valide antes de aplicar mudanças adicionais.

## 5. Preparar diretórios operacionais

Exemplo de layout:

```bash
sudo mkdir -p /opt/lineops
sudo chown -R $USER:$USER /opt/lineops
cd /opt/lineops
```

## 6. Clonar o projeto

```bash
git clone -b integration-meow https://github.com/andresouza701/lineops.git
cd lineops
```

## 7. Preparar variáveis de ambiente de QA

Copiar o exemplo:

```bash
cp .env.qa.example .env.qa
```

Editar `.env.qa`:

```env
APP_ENV=prod
DEBUG=False
SECRET_KEY=<gerar-valor-forte>
APP_VERSION=1.1.0-qa
ALLOWED_HOSTS=qa.seu-dominio.com,<IP_DO_SERVIDOR>,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://qa.seu-dominio.com
DJANGO_SETTINGS_MODULE=config.settings_qa
USE_X_FORWARDED_PROTO=True
SECURE_SSL_REDIRECT=True
HEALTHCHECK_REQUIRE_AUTH=False

DB_NAME=lineops
DB_USER=lineops
DB_PASSWORD=<senha-forte>
DB_HOST=db
DB_PORT=5432

WHATSAPP_MEOW_TIMEOUT_SECONDS=5

TLS_CERT_PATH=./certs/qa-fullchain.pem
TLS_KEY_PATH=./certs/qa-privkey.pem
```

## 8. Instalar certificados TLS

O compose de QA espera os certificados dentro do repositório nestes caminhos:

- `certs/qa-fullchain.pem`
- `certs/qa-privkey.pem`

Se os arquivos vierem de outro local:

```bash
mkdir -p certs
cp /caminho/do/fullchain.pem certs/qa-fullchain.pem
cp /caminho/do/privkey.pem certs/qa-privkey.pem
chmod 600 certs/qa-privkey.pem
```

## 9. Validar o compose antes da subida

```bash
docker compose --env-file .env.qa -f docker-compose.qa.yml config > /tmp/lineops-qa-compose.rendered.yml
```

Se isso falhar, normalmente é:

- variável ausente no `.env.qa`
- caminho inválido de certificado
- erro de sintaxe no arquivo de ambiente

## 10. Subir o stack de QA

```bash
docker compose --env-file .env.qa -f docker-compose.qa.yml down
docker compose --env-file .env.qa -f docker-compose.qa.yml up -d --build
```

Validar:

```bash
docker compose --env-file .env.qa -f docker-compose.qa.yml ps
docker compose --env-file .env.qa -f docker-compose.qa.yml logs web --tail=100
docker compose --env-file .env.qa -f docker-compose.qa.yml logs nginx --tail=100
docker compose --env-file .env.qa -f docker-compose.qa.yml logs db --tail=100
```

## 11. Validar aplicação

Health:

```bash
curl -I http://localhost
curl -k https://localhost/health/
```

Teste externo:

```bash
curl -k https://qa.seu-dominio.com/health/
```

Esperado:

- `HTTP 200` em `/health/`
- redirect de `http` para `https`

## 12. Criar usuário administrativo inicial

```bash
docker compose --env-file .env.qa -f docker-compose.qa.yml exec web python manage.py createsuperuser
```

Depois ajustar role:

```bash
docker compose --env-file .env.qa -f docker-compose.qa.yml exec web python manage.py shell -c "from users.models import SystemUser; u=SystemUser.objects.get(email='seu-email@dominio.com'); u.role=SystemUser.Role.ADMIN; u.save(update_fields=['role']); print(u.email, u.role)"
```

## 13. Comandos operacionais úteis

Parar:

```bash
docker compose --env-file .env.qa -f docker-compose.qa.yml down
```

Rebuild:

```bash
docker compose --env-file .env.qa -f docker-compose.qa.yml up -d --build
```

Logs do web:

```bash
docker compose --env-file .env.qa -f docker-compose.qa.yml logs -f web
```

Rodar migrações manualmente:

```bash
docker compose --env-file .env.qa -f docker-compose.qa.yml exec web python manage.py migrate
```

Abrir shell Django:

```bash
docker compose --env-file .env.qa -f docker-compose.qa.yml exec web python manage.py shell
```

## 14. Capacidade recomendada para este host

Para este servidor de QA, a configuração atual do projeto foi ajustada para:

- Gunicorn com `3 workers`
- Gunicorn com `2 threads`
- PostgreSQL com tuning moderado

Isso é deliberadamente mais conservador que produção. O compose de produção usa mais workers e não deve ser reutilizado neste host sem reavaliação.

## 15. Checklist final de QA

- Docker e Compose instalados
- Firewall com `80/443` liberados
- `.env.qa` preenchido
- certificados válidos copiados
- `docker compose ... config` sem erro
- containers `db`, `web`, `nginx` saudáveis
- `/health/` respondendo
- login administrativo validado

## 16. Próxima validação antes da Sprint 2

Antes de seguir para o fluxo de sessão WhatsApp, validar no QA:

- conectividade do servidor LineOps para os endpoints das instâncias MEOW
- DNS ou IPs das instâncias MEOW
- timeout de rede aceitável entre LineOps e MEOW
- política de acesso entre QA e os 5 MEOWs
