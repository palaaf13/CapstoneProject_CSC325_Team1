"""Account-related business operations."""

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
    )
