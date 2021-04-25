"""Тестируется файл config.py"""
import pytest
from pod_mqtt_tbot import config


def test_load_settings():
    """При считывании настроек должен возвращаться словарь с обязательным набором ключей"""

    expected = {"host": "localhost", "port": 80, "name": "unknown", "tg_token": "123"}
    returned_value = config.load_settings()

    assert expected.keys() == returned_value.keys()


@pytest.mark.parametrize('test_example', [{}, ""])
def test_get_settings_correct_setting(test_example):
    """Если настройки считаны некорректно, то функция get_settings должна бросать исключения"""

    with pytest.raises(config.SettingsError):
        config.get_settings(test_example, "unknown")


def test_get_settings_correct_return():
    """Функция должна возвращать строку"""

    expected = {"host": "localhost", "name": "test"}

    returned_value = config.get_settings(expected, "host")
    assert returned_value == "localhost"
