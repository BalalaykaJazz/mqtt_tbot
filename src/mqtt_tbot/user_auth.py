"""
Процедуры для авторизации в mqtt_publisher
"""

import hashlib


def encode_password(client_password: str, salt_hash: str) -> str:
    """
    Возвращает соль и хэш введенного пользователем пароля для доступа в mqtt_publisher.
    """

    password_hash = hashlib.pbkdf2_hmac("sha256",
                                        client_password.encode(),
                                        salt_hash.encode(),
                                        100000)

    return salt_hash + password_hash.hex()
