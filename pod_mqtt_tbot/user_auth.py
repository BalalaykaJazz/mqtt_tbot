"""
Процедуры для авторизации в mqtt_publisher
"""

import hashlib
import os

CODE = "latin_1"


def encode_password(client_password: str) -> str:
    """
    Пароль пользователя хешируется и отправляется в mqtt_publisher
    """

    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", client_password.encode(CODE), salt, 100000)
    token = salt + key

    return token.decode(CODE)
