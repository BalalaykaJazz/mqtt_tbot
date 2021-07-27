"""Тестируется файл app.py"""

import re
import pytest
from src.mqtt_tbot.app import search_by_template

events_to_try = [
    ("without command", ""),
    ("set", ""),
    ("set command", "set"),
    ("/set command", "set")]

event_ids = ["Message without command",
             "Command without text",
             "set",
             "/set"]


@pytest.mark.parametrize("message, expected", events_to_try, ids=event_ids)
def test_search_by_template(message: str, expected: str):
    """Функция должна возвращать результат поиска в виде строки или пустую строку"""

    is_cmd_set = re.compile(r"set\s+")
    assert search_by_template(is_cmd_set, message) == expected
