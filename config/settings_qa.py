import os

os.environ["APP_ENV"] = "prod"

from .settings_prod import *  # noqa
from .settings import env

APP_ENV = "qa"

# QA should stay close to production, but without sticky HSTS behavior.
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Keep HTTPS support configurable for internal QA environments.
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
