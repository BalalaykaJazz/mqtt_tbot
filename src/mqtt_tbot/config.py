"""
Модуль используется для загрузки настроек, необходимых для корректной работы сервиса.
"""
import os
from pydantic import BaseSettings

SSL_KEYFILE_PATH = "settings/server_cert.pem"


def get_full_path(file_name: str) -> str:
    """Возвращает полный путь к файлу."""

    return os.path.join(os.path.dirname(__file__), file_name)


class Settings(BaseSettings):  # pylint: disable = too-few-public-methods
    """
    Параметры подключения к внешним ресурсам.

    telegram - подключение к боту для получения команд от пользователя.
    bot_name - имя телеграм бота в свободной форме.
    bot_token - уникальный токен для телеграм бота. Токен известен создателю бота.
     .
    mqtt_publisher - микросервис для приема команд от пользователя и отправки их в mqtt брокер.
    server_host - ip адрес сокета, к которому происходит подключение.
    server_port - порт сокета, к которому происходит подключение.
    use_ssl - признак использования ssl для соединения с сокетом.

    database - подключение к базе данных для получения ответа на команду пользователя.
    db_url - адрес базы данных
    db_token - токен или логин/пароль для доступа к базе
    db_org - организация, которой принадлежит база данных.
    """

    # mqtt_publisher
    server_host: str = "127.0.0.1"
    server_port: int = 5000
    use_ssl: bool = False
    ssl_keyfile_path: str = SSL_KEYFILE_PATH

    # telegram
    bot_name: str = "unknown bot name"
    bot_token: str = ""

    # database
    db_url: str = ""
    db_token: str = ""
    db_org: str = ""


def is_main_settings_correct(_settings: Settings) -> bool:
    """
    Проверяет корректность настроек для подключения к
    telegram bot и mqtt_publisher, без которых работа сервиса невозможна."""

    if _settings.use_ssl and not os.path.exists(_settings.ssl_keyfile_path):
        return False

    if not _settings.bot_token:
        return False

    return True


settings = Settings(_env_file=get_full_path(".env"),
                    _env_file_encoding="utf-8")

if not os.path.exists("logs"):
    os.mkdir("logs")
