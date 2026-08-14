"""Hashing and recovery-code helpers for the optional application lock.

Uses only ``hashlib.scrypt`` from the standard library. This local lock limits
opportunistic access but does not encrypt the disk: ``trackr.db`` remains stored
in plain text.
"""
import hashlib
import secrets

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LEN = 32
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # Ambiguous characters excluded (0/O, 1/I/L).


def _derive(secret: str, salt: bytes) -> bytes:
    return hashlib.scrypt(secret.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_KEY_LEN)


def hash_secret(secret: str) -> tuple[str, str]:
    """Return ``(salt_hex, hash_hex)`` for a new secret."""
    salt = secrets.token_bytes(16)
    return salt.hex(), _derive(secret, salt).hex()


def verify_secret(secret: str, salt_hex: str, hash_hex: str) -> bool:
    if not salt_hex or not hash_hex:
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    return secrets.compare_digest(_derive(secret, salt), expected)


def generate_recovery_code() -> str:
    """Generate an easy-to-copy single-use recovery code."""
    groups = ["".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4)) for _ in range(3)]
    return "-".join(groups)
