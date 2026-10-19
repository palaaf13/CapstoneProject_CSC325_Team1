"""Account-related business operations."""

from django.conf import settings
from django.core.mail import send_mail

from apps.accounts.models import User, validate_college_email


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
    send_mail(
        subject="Confirm your RamHub account",
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
