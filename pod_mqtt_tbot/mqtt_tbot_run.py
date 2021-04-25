"""
A telegram bot service that receives a message and sends it to socket
"""

import json
import socket
import sys
import telebot  # type: ignore
from telebot import types  # type: ignore
from pod_mqtt_tbot.config import get_settings, load_settings, SettingsError  # type: ignore


class FormatError(Exception):
    """Common class for received file format errors"""


WELCOME_MESSAGE = 'Нужно отправить мне текст в формате json, чтобы я переправил его в MQTT. \n' \
                  'Формат файла следующий: \n' \
                  '{"topic": <топик-получатель сообщения>, "message": <Само сообщение>}'

try:
    _settings = load_settings()
    _tg_token = get_settings(_settings, "tg_token")
except SettingsError:
    print("Работа программы завершена")
    sys.exit(1)

bot = telebot.TeleBot(_tg_token)


def create_buttons() -> types.ReplyKeyboardMarkup:
    """Create buttons to help user"""

    keyboard = types.ReplyKeyboardMarkup()
    keyboard.add(types.KeyboardButton("/help"))
    return keyboard


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message: telebot.types.Message) -> None:
    """Displays a tip to the user if a start or help command is received"""

    bot.send_message(message.from_user.id, WELCOME_MESSAGE, reply_markup=create_buttons())


def check_message(message: str) -> bool:
    """Return whether the message is valid"""

    try:
        json_message = json.loads(message)
        required_fields = ("topic", "message")
        for field in required_fields:
            if field not in json_message:
                print(f"Сообщение не содержит обязательного поля {field}")
                raise FormatError

    except AttributeError as err:
        raise FormatError from err
    except json.decoder.JSONDecodeError as err:
        raise FormatError from err
    except TypeError as err:
        raise FormatError from err

    return True


def send_message(message: str) -> bool:
    """Sending received message to service MQTT publisher"""

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.connect((get_settings(_settings, "host"), get_settings(_settings, "port")))

    if message:
        server_socket.send(message.encode())
        answer = server_socket.recv(1024).decode("utf-8")
        server_socket.close()
        return answer == "HTTP/1.1 200 OK"

    server_socket.close()
    return False


@bot.message_handler(content_types=['text'])
def get_message(message: telebot.types.Message) -> None:
    """The received message is forwarded to the 'MQTT publisher' service"""

    try:
        if check_message(message.text):
            result = send_message(message.text)
            message_answer = f"Send message successful: {result}"
        else:
            message_answer = ""

    except FormatError:
        message_answer = "Полученное сообщение не соответствует требуемому формату"
    except ConnectionRefusedError:
        message_answer = "Сервис 'MQTT publisher' не запущен"

    bot.send_message(message.from_user.id, message_answer)
    print(message_answer)


if __name__ == "__main__":

    try:
        bot_name = get_settings(_settings, 'name')
    except SettingsError:
        bot_name = "unknown"

    print(f"Сервис запущен. Подключен бот {bot_name}")
    bot.polling(none_stop=True)
