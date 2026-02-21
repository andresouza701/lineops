# Base image
FROM python:3.12-slim

# Evita que Python cree archivos .pyc
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt /app/

# Install dependencies
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Copy project files
COPY . /app/

# Expose the port the app runs on
EXPOSE 8000

# Run the application
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]