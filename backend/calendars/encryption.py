"""Шифрование токенов — Fernet (symmetric, AES-128-CBC + HMAC-SHA256)."""

import os

from cryptography.fernet import Fernet, InvalidToken

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Ленивая инициализация Fernet из переменной окружения."""
    global _fernet
    if _fernet is not None:
        return _fernet

    key = os.environ.get("ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY environment variable is required. "
            'Generate: python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    _fernet = Fernet(key.encode())
    return _fernet


def encrypt_token(plaintext: str) -> str:
    """Зашифровать строку (token / password) → base64-строка."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Расшифровать → исходная строка."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError(
            "Token decryption failed — key may have been rotated"
        )


def generate_encryption_key() -> str:
    """Сгенерировать новый Fernet-ключ (для .env)."""
    return Fernet.generate_key().decode()
