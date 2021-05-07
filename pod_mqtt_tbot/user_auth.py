"""
Процедуры для авторизации в mqtt_publisher
"""

import hashlib
import os


def encode_password(client_password: str) -> str:
    """
    Пароль пользователя хешируется и отправляется в mqtt_publisher
    """

    # salt = os.urandom(32)
    salt = b'8\xbaU\x19\xb9\xca\xf6\xdb`Q\xb4\x88]\xdc\x81M\xbb\xd3\xbd%\x19\xdd\x80\xae\xb1\xf8\x01\x03\x92\x11\xb5Z'
    key = hashlib.pbkdf2_hmac("sha256", client_password.encode("UTF-8"), salt, 100000)
    token = salt + key

    return token.decode("cp1251")
