"""Local development settings. Used by manage.py and pytest."""

from .base import *  # noqa: F403
from .base import env

DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "testserver"]

# Print emails (like sign-up confirmations) in the runserver terminal, unless
# .env sets EMAIL_HOST — then base.py's SMTP settings send them for real.
if not env.str("EMAIL_HOST", default=""):
    MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.console.EmailBackend",
        }
    }

# Show template and DB errors loudly while developing.
INTERNAL_IPS = ["127.0.0.1"]
