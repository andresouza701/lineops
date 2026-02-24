from .settings import *  # noqa
from .settings import env

# Overrides for desenvolvimento
DEBUG = True
ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "testserver"]
)
