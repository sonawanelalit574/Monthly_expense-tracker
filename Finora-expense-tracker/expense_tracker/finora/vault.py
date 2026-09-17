from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _fernet(secret_key: str, user_id: int, pin: str) -> Fernet:
    material = hashlib.sha256(f"{secret_key}|{user_id}|{pin}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def encrypt_secret(secret_key: str, user_id: int, pin: str, plaintext: str) -> str:
    token = _fernet(secret_key, user_id, pin).encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(secret_key: str, user_id: int, pin: str, blob: str) -> str:
    try:
        raw = _fernet(secret_key, user_id, pin).decrypt(blob.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("Could not unlock this vault item. Check your PIN.") from exc
    return raw.decode("utf-8")
