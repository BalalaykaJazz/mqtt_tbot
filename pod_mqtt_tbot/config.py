"""This module is used to prepare settings"""
import os
import json

MAIN_SETTINGS_PATH = "settings/settings.json"
TOPICS_PATH = "settings/topics.json"
SSL_KEYFILE_PATH = "settings/server_cert.pem"


class SettingsError(Exception):
    """Common class for settings file errors"""


def get_full_path(file_name: str) -> str:
    """Return full path to file"""
    return os.path.join(os.path.dirname(__file__), file_name)


def load_settings() -> dict:
    """Return loaded settings from settings.json"""

    try:
        with open(get_full_path(MAIN_SETTINGS_PATH), encoding="utf-8") as file:
            loaded_settings = json.load(file)

            required_fields = ("host", "port", "name", "tg_token", "use_ssl")
            for field in required_fields:
                if field not in loaded_settings:
                    print(f"Конфигурационный файл должен содержать поле {field}")
                    raise SettingsError

            for field, value in loaded_settings.items():
                if not value and not isinstance(value, bool):
                    print(f"В конфигурационном файле не указано значение поля {field}")
                    raise SettingsError

            if loaded_settings.get("use_ssl"):
                loaded_settings["SSL_KEYFILE_PATH"] = get_full_path(SSL_KEYFILE_PATH)

    except FileNotFoundError as err:
        print("Ненайден конфигурационный файл settings.json")
        raise SettingsError from err
    except json.decoder.JSONDecodeError as err:
        print("Конфигурационный файл имеет некорректный формат")
        raise SettingsError from err

    try:
        with open(get_full_path(TOPICS_PATH), encoding="utf-8") as file:
            ready_topics = json.load(file)
            loaded_settings["topic_templates"] = ready_topics.values() if isinstance(ready_topics, dict) else []

    except FileNotFoundError:
        print("Ненайден файл topics.json")
        loaded_settings["topic_templates"] = []
    except json.decoder.JSONDecodeError:
        print("Файл topics.json имеет некорректный формат")
        loaded_settings["topic_templates"] = []

    return loaded_settings


def get_settings(settings: dict, setting_name: str) -> str:
    """Return required settings"""

    try:
        return settings[setting_name]
    except KeyError as err:
        print(f"Конфигурационный файл должен содержать поле {setting_name}")
        raise SettingsError from err
    except TypeError as err:
        print("Конфигурационный файл имеет некорректный формат")
        raise SettingsError from err
