"""Account-related business operations."""

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import EmailMessage, mailers

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
