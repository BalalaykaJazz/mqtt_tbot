"""
Процедуры для авторизации в mqtt_publisher
"""

import hashlib
import base64

CODE = "ascii"


def encode_password(client_password: str, salt_b64: str) -> str:
    """
    Пароль пользователя хешируется и отправляется в mqtt_publisher
    """

    salt = base64.b64decode(salt_b64)
    password_hash = hashlib.pbkdf2_hmac("sha256", client_password.encode(CODE), salt, 100000)
    token_hash = salt + password_hash

    token = base64.b64encode(token_hash).decode(CODE)

    return token
