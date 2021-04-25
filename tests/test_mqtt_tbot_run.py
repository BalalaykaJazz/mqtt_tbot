"""Тестируется файл mqtt_tbot_run.py"""
import pytest
from pod_mqtt_tbot import mqtt_tbot_run  # type: ignore


@pytest.mark.parametrize('test_example', ["test",
                                          42,
                                          '{"without_topic": "test", "message": "test"}'])
def test_check_message_exception(test_example):
    """Если полученное сообщение имеет некорректный формат, то функция должна бросать исключения"""

    with pytest.raises(mqtt_tbot_run.FormatError):
        mqtt_tbot_run.check_message(test_example)


def test_check_message_return():
    """Если полученное сообщение имеет корректный формат, то функция должна возвращать истину"""

    correct = '{"topic": "test", "message": "test"}'
    returned_value = mqtt_tbot_run.check_message(correct)
    assert returned_value is True
