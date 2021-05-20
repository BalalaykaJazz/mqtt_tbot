"""Тестируется файл config.py"""
import pytest
from pod_mqtt_tbot import config  # type: ignore


def test_read_file():
    """Проверка корректности чтения файла"""

    with pytest.raises(config.SettingsError):
        config.read_file("no_file")

    returned_value = config.read_file(config.MAIN_SETTINGS_PATH)

    assert isinstance(returned_value, dict)


def test_load_settings():
    """При считывании настроек должен возвращаться словарь с обязательным набором ключей"""

    expected = {"host": "localhost", "port": 80,
                "name": "unknown", "tg_token": "123",
                "topic_templates": [],
                "use_ssl": False,
                "correctly": True}

    returned_value = config.load_settings()

    assert expected.keys() == returned_value.keys()


@pytest.mark.parametrize('test_example', [{}, ""])
def test_get_settings_exc(test_example):
    """Если настройки считаны некорректно, то функция get_settings должна бросать исключения"""

    _settings = config.load_settings()

    with pytest.raises(config.SettingsError):
        config.get_settings("unknown")


def test_get_settings_correct_return():
    """Функция должна возвращать корректные значения"""

    _settings = {"host": "localhost", "port": 80}
    returned_value = config.get_settings("host")
    assert returned_value == "localhost"

    returned_value = config.get_settings("socket")
    assert isinstance(returned_value, tuple)
