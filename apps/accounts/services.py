"""Account-related business operations."""

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.cache import cache
from django.core.mail import EmailMessage, mailers
from django.http import HttpRequest

from apps.accounts.models import User, validate_college_email


class EmailConfirmationTokenGenerator(PasswordResetTokenGenerator):
    """Issue tokens only for RamHub email verification, not password resets."""

    def _make_hash_value(self, user: User, timestamp: int) -> str:
        return f"email-confirmation:{super()._make_hash_value(user, timestamp)}:{user.is_active}"


email_confirmation_token = EmailConfirmationTokenGenerator()


class EmailDeliveryError(RuntimeError):
    """Raised when the configured backend does not accept the confirmation email."""


def register_user(
    *,
    username: str,
    email: str,
    display_name: str,
    password: str,
) -> User:
    """Create an account only for an address at the configured college domain."""
    normalized_email = email.strip().casefold()
    validate_college_email(normalized_email)
    return User.objects.create_user(
        username=username,
        email=normalized_email,
        display_name=display_name.strip(),
        password=password,
        is_active=False,
    )


def activate_user(user: User, token: str) -> bool:
    """Activate an inactive account if its email-confirmation token is valid."""
    if user.is_active or not email_confirmation_token.check_token(user, token):
        return False

    user.is_active = True
    user.save(update_fields=["is_active"])
    return True


def authenticate_by_email(request: HttpRequest, email: str, password: str) -> User | None:
    """Return the active account matching this email and password, or None.

    Students sign in with their college email, but Django's ModelBackend looks
    accounts up by username, so the email is translated first. An unknown email
    still goes through authenticate() so it costs the same password-hash time
    as a wrong password and doesn't reveal which emails have accounts.
    """
    user = User.objects.filter(email=email.strip().casefold()).first()
    username = user.username if user else ""
    return authenticate(request, username=username, password=password)


def is_unconfirmed_account(email: str, password: str) -> bool:
    """True when the email and password are right but the email isn't confirmed yet."""
    user = User.objects.filter(email=email.strip().casefold(), is_active=False).first()
    return user is not None and user.check_password(password)


# Failed sign-ins allowed from one IP before it is locked out, and for how
# long. The failure count also resets on its own after the lockout window, so
# five typos spread over a day don't add up to a lockout.
SIGN_IN_MAX_FAILURES = 5
SIGN_IN_LOCKOUT_SECONDS = 5 * 60


def _sign_in_failures_key(ip: str) -> str:
    return f"accounts:sign-in-failures:{ip}"


def _sign_in_lockout_key(ip: str) -> str:
    return f"accounts:sign-in-locked:{ip}"


def client_ip(request: HttpRequest) -> str:
    """The address the request came from.

    This is REMOTE_ADDR only. X-Forwarded-For is not read, because a client can
    set it to anything and use that to dodge the lockout. Behind a proxy in
    production, REMOTE_ADDR is the proxy's address and this needs revisiting.
    """
    return request.META.get("REMOTE_ADDR", "")


def is_sign_in_locked(ip: str) -> bool:
    """True while this IP is serving a lockout for too many failed sign-ins."""
    return cache.get(_sign_in_lockout_key(ip)) is not None


def record_failed_sign_in(ip: str) -> bool:
    """Count one failed sign-in from this IP. Returns True if it is now locked out."""
    failures_key = _sign_in_failures_key(ip)
    cache.add(failures_key, 0, timeout=SIGN_IN_LOCKOUT_SECONDS)
    try:
        failures = cache.incr(failures_key)
    except ValueError:
        # The counter expired between add() and incr(); this is the first failure.
        cache.set(failures_key, 1, timeout=SIGN_IN_LOCKOUT_SECONDS)
        failures = 1

    if failures >= SIGN_IN_MAX_FAILURES:
        cache.set(_sign_in_lockout_key(ip), True, timeout=SIGN_IN_LOCKOUT_SECONDS)
        cache.delete(failures_key)
        return True
    return False


def clear_failed_sign_ins(ip: str) -> None:
    """Forget earlier failures once this IP signs in successfully."""
    cache.delete(_sign_in_failures_key(ip))


def send_registration_confirmation(user: User, confirmation_url: str) -> None:
    """Email an activation link to a newly registered, inactive student."""
    greeting = user.display_name or user.username
    message = (
        f"Hi {greeting},\n\n"
        "Confirm your RamHub student account by opening this link:\n"
        f"{confirmation_url}\n\n"
        "This link expires after a limited time. If you did not request this "
        "account, you can ignore this email."
    )
    email = EmailMessage(
        "Confirm your RamHub account",
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )
    sent_count = mailers.default.send_messages([email])
    if sent_count != 1:
        raise EmailDeliveryError(
            "The registration confirmation email was not accepted for delivery."
        )


PROFILE_FIELDS = ("display_name", "major", "grad_year", "bio", "is_profile_public")


def update_profile(user: User, changes: dict) -> User:
    """Save a student's own profile edits.

    Only the fields in PROFILE_FIELDS are applied; anything else in
    ``changes`` is ignored, so this can never change an email, role, or
    password.
    """
    for field in PROFILE_FIELDS:
        if field in changes:
            setattr(user, field, changes[field])
    user.save(update_fields=list(PROFILE_FIELDS))
    return user


# Password-reset emails one IP may trigger per window, so the form can't be
# used to flood someone's inbox. Past the limit the visitor sees the same
# "check your email" page, but nothing is sent.
RESET_MAX_REQUESTS = 3
RESET_WINDOW_SECONDS = 15 * 60


def _reset_requests_key(ip: str) -> str:
    return f"accounts:reset-requests:{ip}"


def allow_password_reset_email(ip: str) -> bool:
    """Count one reset request from this IP. False once it is over the limit."""
    key = _reset_requests_key(ip)
    cache.add(key, 0, timeout=RESET_WINDOW_SECONDS)
    try:
        requests = cache.incr(key)
    except ValueError:
        # The counter expired between add() and incr(); this is the first request.
        cache.set(key, 1, timeout=RESET_WINDOW_SECONDS)
        requests = 1
    return requests <= RESET_MAX_REQUESTS
