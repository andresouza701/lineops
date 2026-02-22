from .settings import *  # noqa

# Overrides para produção
DEBUG = False
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default='localhost')

# Exemplos de flags seguras adicionais (ajuste conforme infraestrutura):
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
