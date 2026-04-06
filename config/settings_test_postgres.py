import os


os.environ["USE_SQLITE_TEST_DB"] = "False"

from .settings_dev import *  # noqa


DJANGO_SETTINGS_MODULE = "config.settings_test_postgres"
