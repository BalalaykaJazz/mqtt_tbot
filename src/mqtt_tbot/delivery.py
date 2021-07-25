"""Процедуры доставки сообщений в mqtt_publisher"""
import json
import socket
import ssl
from .config import settings  # pylint: disable = import-error

SOCKET_TIMEOUT = 30


def deliver_message(message: dict) -> str:
    """
    Введенное пользователем сообщение отправляется в сокет - для сервиса MQTT publisher.
    Возвращаемое значение: признак успеха отправки.
    """

    text_message = json.dumps(message)

    socket.setdefaulttimeout(SOCKET_TIMEOUT)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if settings.use_ssl:
        server_socket = ssl.wrap_socket(server_socket,  # pylint: disable = deprecated-method
                                        cert_reqs=ssl.CERT_REQUIRED,
                                        ca_certs=settings.ssl_keyfile_path)

    try:
        server_socket.connect((settings.server_host, settings.server_port))

        if text_message:
            server_socket.send(text_message.encode())
            answer = server_socket.recv(1024).decode("utf-8")
            server_socket.close()
            return answer

    except socket.timeout:
        server_socket.close()
        return "Превышено время ожидания ответа"

    server_socket.close()
    return "Неизвестная ошибка отправки сообщения"
