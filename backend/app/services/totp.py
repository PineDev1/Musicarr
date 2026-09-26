from __future__ import annotations

import pyotp

ISSUER = "Musicarr"


def generate_secret() -> str:
    return pyotp.random_base32()


def otpauth_url(secret: str, username: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=ISSUER)


def verify_code(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    try:
        return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
    except Exception:  # noqa: BLE001
        return False
