from __future__ import annotations

import hmac


def is_admin_authenticated(configured_password: str | None, entered_password: str | None) -> bool:
    """Return True if *entered_password* matches the configured admin password.

    Uses ``hmac.compare_digest`` to prevent timing-based side-channel attacks
    that could reveal password length or content via response-time differences.
    """
    if not configured_password or not entered_password:
        return False
    return hmac.compare_digest(configured_password, entered_password)
