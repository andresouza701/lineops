#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env.qa"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.qa.yml"
LOG_DIR="${PROJECT_ROOT}/logs/ops"

if [[ $# -lt 1 ]]; then
  echo "Uso: $0 <manage_command> [args...]" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Arquivo .env.qa nao encontrado em ${ENV_FILE}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}"

cd "${PROJECT_ROOT}"

docker compose \
  --env-file "${ENV_FILE}" \
  -f "${COMPOSE_FILE}" \
  exec -T web python manage.py "$@"
