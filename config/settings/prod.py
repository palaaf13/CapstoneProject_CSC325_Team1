"""Production settings. Every secret must come from the environment."""

from .base import *  # noqa: F403
from .base import env

DEBUG = False

# No default: deploy fails fast rather than running on a known key.
SECRET_KEY = env.str("SECRET_KEY")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# Production account verification must use a configured SMTP relay and sender.
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": env.str("EMAIL_HOST"),
            "port": env.int("EMAIL_PORT", default=587),
            "username": env.str("EMAIL_HOST_USER", default=""),
            "password": env.str("EMAIL_HOST_PASSWORD", default=""),
            "use_tls": env.bool("EMAIL_USE_TLS", default=True),
        },
    }
}
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL")

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
