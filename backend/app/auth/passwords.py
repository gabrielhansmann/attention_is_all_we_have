"""Password hashing with scrypt from the standard library (no extra dependency).

Stored form: scrypt$N$r$p$salt$hash (base64). Parameters are read back from the stored string, so they can be
raised later without invalidating existing hashes. Comparison is constant time.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

N, R, P = 2**15, 8, 1          # about 32 MiB and ~100 ms per hash
DKLEN = 32
MAXMEM = 128 * 1024 * 1024
MIN_LENGTH, MAX_LENGTH = 12, 256

_b64 = lambda b: base64.b64encode(b).decode()


def check_policy(password: str) -> None:
    """Raises ValueError with a message the person can act on."""
    if len(password) < MIN_LENGTH:
        raise ValueError(f"the password must be at least {MIN_LENGTH} characters")
    if len(password) > MAX_LENGTH:
        raise ValueError(f"the password must be at most {MAX_LENGTH} characters")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, maxmem=MAXMEM, dklen=DKLEN)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    """False for a wrong password and for any malformed stored value; never raises."""
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        expected_b = base64.b64decode(expected)
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                            maxmem=MAXMEM, dklen=len(expected_b))
        return hmac.compare_digest(dk, expected_b)
    except Exception:
        return False


_dummy: str | None = None


def burn_time() -> None:
    """Spend the same time as a real check, so an unknown email is not faster to reject than a known one."""
    global _dummy
    if _dummy is None:
        _dummy = hash_password("not-a-real-account-password")
    verify_password("another-wrong-password", _dummy)
