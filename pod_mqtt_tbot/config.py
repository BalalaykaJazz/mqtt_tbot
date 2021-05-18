"""
Модуль используется для считывания файлов, необходимых для корректной работы сервиса.
"""
import os
import json
from typing import Any

MAIN_SETTINGS_PATH = "settings/settings.json"
TOPICS_PATH = "settings/topics.json"
SSL_KEYFILE_PATH = "settings/server_cert.pem"


class SettingsError(Exception):
    """Исключение для ошибок в конфигурационном файле."""


def get_full_path(file_name: str) -> str:
    """Возвращает полный путь к файлу."""
    return os.path.join(os.path.dirname(__file__), file_name)


def read_file(file_name: str) -> dict:
    """
    Функция читает указанный в file_name файл и возвращает словарь с полученными полями.
    """

    try:
        with open(get_full_path(file_name), encoding="utf-8") as file:
            loaded_settings = json.load(file)
    except FileNotFoundError as err:
        print(f"Не найден файл {file_name}.")
        raise SettingsError from err
    except json.decoder.JSONDecodeError as err:
        print(f"файл {file_name} имеет некорректный формат.")
        raise SettingsError from err

    return loaded_settings


def load_settings() -> dict:
    """Возвращает настройки полученные из конфигурационных файлов."""

    try:
        main_settings = read_file(MAIN_SETTINGS_PATH)
        topic_templates = read_file(TOPICS_PATH)
    except SettingsError:
        return {"correctly": False}

    main_settings["topic_templates"] = [t for t in topic_templates.values()]

    if main_settings.get("use_ssl"):
        main_settings["SSL_KEYFILE_PATH"] = get_full_path(SSL_KEYFILE_PATH)

    try:
        check_settings(main_settings)
    except SettingsError:
        main_settings = {"correctly": False}

    main_settings["correctly"] = True
    return main_settings


def check_settings(main_settings: dict):
    """Проверка загруженных настроек."""

    required_fields = ("host", "port", "name", "tg_token", "use_ssl")
    for field in required_fields:
        if field not in main_settings:
            print(f"Конфигурационный файл должен содержать поле {field}")
            raise SettingsError

    for field, value in main_settings.items():
        if not value and not isinstance(value, bool):
            print(f"В конфигурационном файле не указано значение поля {field}")
            raise SettingsError

    if main_settings.get("use_ssl") and not os.path.exists(main_settings.get("SSL_KEYFILE_PATH")):
        print(f"Не найден файл {SSL_KEYFILE_PATH}")
        raise SettingsError


def get_settings(setting_name: str) -> Any:
    """Возвращает запрошенные в параметре setting_name настройки."""

    try:
        if setting_name == "socket":
            return _settings["host"], _settings["port"]

        return _settings[setting_name]

    except KeyError as err:
        print(f"Конфигурационный файл должен содержать поле {setting_name}")
        raise SettingsError from err
    except TypeError as err:
        print("Конфигурационный файл имеет некорректный формат")
        raise SettingsError from err


_settings = load_settings()
