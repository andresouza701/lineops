from .settings import *  # noqa
from .settings import env

# Overrides for desenvolvimento
APP_ENV = "dev"
DEBUG = True
ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "testserver"]
)
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
DJANGO_SETTINGS_MODULE = "config.settings_dev"
