"""This module is used to prepare settings"""
import os
import json

MAIN_SETTINGS_PATH = "settings/settings.json"


def get_full_path(file_name: str) -> str:
    """Return full path to file"""
    return os.path.join(os.path.dirname(__file__), file_name)


def get_settings(setting_name: str) -> str:
    """Return settings for connecting to telegram bot or socket"""
    with open(get_full_path(MAIN_SETTINGS_PATH), encoding="utf-8") as file:
        settings = json.load(file)

    requested_settings = settings.get(setting_name.lower())

    return requested_settings
