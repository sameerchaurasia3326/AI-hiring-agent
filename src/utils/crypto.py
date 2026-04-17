from cryptography.fernet import Fernet
from loguru import logger
from src.config import settings

_cipher = None

def _get_cipher():
    global _cipher
    if _cipher is None:
        try:
            key = settings.encryption_key.encode("utf-8")
            _cipher = Fernet(key)
        except Exception as e:
            logger.error(f"Failed to initialize Fernet encryption (Ensure encryption_key is 32 url-safe base64-encoded bytes): {e}")
            raise e
    return _cipher

def encrypt_token(plain_text: str) -> str:
    if not plain_text:
        return plain_text
    try:
        cipher = _get_cipher()
        return cipher.encrypt(plain_text.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to encrypt token: {e}")
        return plain_text

def decrypt_token(cipher_text: str) -> str:
    if not cipher_text:
        return cipher_text
    try:
        cipher = _get_cipher()
        return cipher.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception:
        # If it's already plain text or invalid, gracefully fallback
        # so existing database tokens don't break during migration phase.
        return cipher_text
