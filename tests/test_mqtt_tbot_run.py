import pytest
from pod_mqtt_tbot import mqtt_tbot_run


def test_check_message_exception():
    # Json format
    with pytest.raises(mqtt_tbot_run.FormatError):
        mqtt_tbot_run.check_message("test")

    with pytest.raises(mqtt_tbot_run.FormatError):
        mqtt_tbot_run.check_message(42)

    with pytest.raises(mqtt_tbot_run.FormatError):
        mqtt_tbot_run.check_message('{"without_topic": "test", "message": "test"}')


def test_check_message_return():
    correct = '{"topic": "test", "message": "test"}'
    returned_value = mqtt_tbot_run.check_message(correct)
    assert returned_value is True
