import pytest
from pod_mqtt_tbot import config


def test_load_settings():
    expected = {"host": "localhost", "port": 80, "name": "unknown", "tg_token": "123"}
    returned_value = config.load_settings()

    assert expected.keys() == returned_value.keys()


def test_get_settings_correct_setting():
    incorrect_settings = {}
    incorrect_parameter = ""

    with pytest.raises(config.SettingsError):
        config.get_settings(incorrect_settings, "unknown")
        config.get_settings(incorrect_parameter, "unknown")


def test_get_settings_correct_return():
    expected = {"host": "localhost"}

    returned_value = config.get_settings(expected, "host")
    assert returned_value == "localhost"
