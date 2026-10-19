"""Local development settings. Used by manage.py and pytest."""

from .base import *  # noqa: F403
from .base import env

DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "testserver"]

# Show registration confirmation messages in the runserver terminal.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Show template and DB errors loudly while developing.
INTERNAL_IPS = ["127.0.0.1"]
