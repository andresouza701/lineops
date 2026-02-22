from .settings import *  # noqa

# Overrides for desenvolvimento
DEBUG = True
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[
                         'localhost', '127.0.0.1', 'testserver'])
