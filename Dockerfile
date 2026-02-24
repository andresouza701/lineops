# Imagem base enxuta
FROM python:3.11-slim

# Evita arquivos .pyc e bufferização
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Diretório de trabalho
WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    && apt-get clean

# Criar usuário não-root
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Copiar requirements primeiro (melhora cache)
COPY requirements.txt /app/

# Instalar dependências Python
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copiar restante do código
COPY . /app/

# Ajustar permissões
RUN chown -R appuser:appgroup /app

# Trocar para usuário não-root
USER appuser

# Expor porta interna
EXPOSE 8000

# Comando padrão
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]