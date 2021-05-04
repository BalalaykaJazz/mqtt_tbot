"""
A telegram bot service that receives a message and sends it to socket
"""

import json
from socket import socket, AF_INET, SOCK_STREAM
import ssl
import sys
import telebot  # type: ignore
from telebot import types  # type: ignore
from requests.exceptions import ReadTimeout
from config import get_settings, load_settings, SettingsError  # type: ignore

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
current_state = {"selected_topic": "", "expected_text": ""}


class FormatError(Exception):
    """Common class for received file format errors"""


def get_current_state() -> dict:
    """Return current state of user input"""
    # global current_state
    return current_state


def create_common_buttons() -> types.ReplyKeyboardMarkup:
    """Create main buttons to help user"""

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("create_message"), types.KeyboardButton("/help"))
    return keyboard


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message: telebot.types.Message) -> None:
    """Displays a tip to the user if a start or help command is received"""

    bot.send_message(message.from_user.id, WELCOME_MESSAGE, reply_markup=create_common_buttons())


def create_topic_buttons() -> types.InlineKeyboardMarkup:
    """Create buttons with available topics"""

    keyboard = types.InlineKeyboardMarkup()
    for topic in get_settings(_settings, "topic_templates"):
        keyboard.add(types.InlineKeyboardButton(topic, callback_data=topic))

    keyboard.add(types.InlineKeyboardButton("manual", callback_data="manual"))
    return keyboard


def display_selection_buttons(chat_id: int) -> None:
    """Send message with buttons and reset current status"""

    bot.send_message(chat_id, "Выберите топик или введите информацию вручную",
                     reply_markup=create_topic_buttons())

    cur_state = get_current_state()
    cur_state["selected_topic"] = ""
    cur_state["expected_text"] = ""


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call) -> None:
    """Actions after choose topic or manual input mode"""

    # delete buttons after touch
    bot.delete_message(call.from_user.id, call.message.id)

    cur_state = get_current_state()
    if call.data == "manual":  # Manual mode is selected, now need topic than message
        cur_state["expected_text"] = "topic"
        bot.send_message(call.from_user.id, "Введите топик для отправки сообщения")
    else:  # Topic is selected, now need message
        cur_state["expected_text"] = "message"
        cur_state["selected_topic"] = call.data
        bot.send_message(call.from_user.id, "Введите сообщение для отправки")


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

    server_socket = socket(AF_INET, SOCK_STREAM)

    if get_settings(_settings, "use_ssl"):
        server_socket = ssl.wrap_socket(server_socket,
                                        cert_reqs=ssl.CERT_REQUIRED,
                                        ca_certs=get_settings(_settings, "SSL_KEYFILE_PATH"))

    server_socket.connect((get_settings(_settings, "host"), get_settings(_settings, "port")))

    if message:
        server_socket.send(message.encode())
        answer = server_socket.recv(1024).decode("utf-8")
        server_socket.close()
        return answer == "HTTP/1.1 200 OK"

    server_socket.close()
    return False


def prepare_message(message: str, id_message: int) -> str:
    """Prepare message and update state. Return"""

    cur_state = get_current_state()
    if cur_state["expected_text"] == "topic":  # user reported topic
        cur_state["selected_topic"] = message
        bot.send_message(id_message, "Введите сообщение для отправки")
        cur_state["expected_text"] = "message"
        text_message = ""
    elif cur_state["expected_text"] == "message":  # user reported message
        data = {"topic": cur_state["selected_topic"], "message": message}
        text_message = json.dumps(data)
        cur_state["expected_text"] = ""
        cur_state["selected_topic"] = ""
    else:  # user reported topic and message in json format
        text_message = message

    return text_message


@bot.message_handler(content_types=['text'])
def get_message(message: telebot.types.Message) -> None:
    """The received message is forwarded to the 'MQTT publisher' service"""

    if message.text == "create_message":  # Button click handling
        display_selection_buttons(message.chat.id)
    else:
        ready_text_message = prepare_message(message.text, message.from_user.id)

        if ready_text_message:
            try:
                if check_message(ready_text_message):
                    result = send_message(ready_text_message)
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
        bot_name = get_settings(_settings, "name")
    except SettingsError:
        bot_name = "unknown"

    print(f"Сервис запущен. Подключен бот {bot_name}")

    try:
        bot.polling(none_stop=True)
    except ReadTimeout:
        print("Read timed out")
        exit(1)
