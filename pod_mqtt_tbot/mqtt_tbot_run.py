"""
A telegram bot service that receives a message and sends it to socket
"""

import json
import socket
import telebot  # type: ignore
from config import get_settings

bot = telebot.TeleBot(get_settings("tg_token"))

WELCOME_MESSAGE = 'Нужно отправить мне текст в формате json, чтобы я переправил его в MQTT. \n' \
                  'Формат файла следующий: \n' \
                  '{"topic": <топик-получатель сообщения>, "message": <Само сообщение>}'


class FormatError(Exception):
    """Common class for received file format errors"""


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message: telebot.types.Message) -> None:
    """Displays a tip to the user if a start or help command is received"""

    bot.send_message(message.from_user.id, WELCOME_MESSAGE)


def check_message(message: str) -> bool:
    """The message is checked against the required format"""

    try:
        json_message = json.loads(message)
        if "topic" not in json_message or "message" not in json_message:
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
    server_socket.connect((get_settings("host"), get_settings("port")))

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

    except FormatError:
        message_answer = "Полученное сообщение не соответствует требуемому формату"
    except ConnectionRefusedError:
        message_answer = "Сервис 'MQTT publisher' не запущен"

    bot.send_message(message.from_user.id, message_answer)
    print(message_answer)


if __name__ == "__main__":
    print("Сервис 'sensors_alarm_bot' запущен")
    bot.polling(none_stop=True)
