"""
Создается телеграм бот, который получает сообщения от пользователей
и отправляет их в сокет для сервиса mqtt_publisher.
"""

import json
import ssl
from socket import socket, AF_INET, SOCK_STREAM
import telebot  # type: ignore
from user_auth import encode_password
from telebot import types  # type: ignore
from requests.exceptions import ReadTimeout
from config import get_settings, load_settings, SettingsError  # type: ignore


class FormatError(Exception):
    """Общий класс для ошибок в формате полученных сообщений."""


def read_settings() -> dict:
    """
    Считываются основные настройки программы. В случае некорректных настроек программа завершается.
    Возвращаемое значение: словарь с настройками подключения к боту и сокету.
    """

    try:
        loaded_settings = load_settings()
    except SettingsError:
        raise SystemExit("Работа программы завершена")
    return loaded_settings


def create_bot() -> telebot:
    """Создается телеграм бот"""
    return telebot.TeleBot(get_settings(_settings, "tg_token"))


def get_current_state(chat_id: int) -> dict:
    """
    Возвращаемое значение: словарь с текущими состояниями сообщений.
    Если пользователь отправляет сообщение впервые, то создается словарь с пустыми значениями.
    Ключ словаря: chat_id - чат с определенным пользователем.
    Значение словаря: словарь с ключами selected_topic и expected_text.
    selected_topic - выбранный пользователем топик для отправки в mqtt.
    expected_text - введенный пользователем текст сообщения для отправки.
    """

    chat_id_str = str(chat_id)

    if current_states.get(chat_id_str) is None:
        current_states[chat_id_str] = {"selected_topic": "",
                                       "expected_text": "",
                                       "user": "",
                                       "password": ""}

    return current_states[chat_id_str]


_settings = read_settings()
bot = create_bot()
current_states: dict = {}

WELCOME_MESSAGE = "Сначала нужно авторизироваться через кнопку sign in. \n" \
                  "Для начала ввода сообщения воспользуйтесь кнопкой create_message. \n"


def create_common_buttons(chat_id: int) -> types.ReplyKeyboardMarkup:
    """
    Создаются основные кнопки для взаимодействия с пользователем.
    Возвращаемое значение: набор кнопок
    """

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)

    cur_state = get_current_state(chat_id)
    if cur_state["user"]:
        keyboard.add(types.KeyboardButton("create_message"))

    keyboard.add(types.KeyboardButton("sign_in"))
    keyboard.add(types.KeyboardButton("/help"))
    return keyboard


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message: telebot.types.Message) -> None:
    """Выводится стартовая информация с подсказками пользователю."""

    bot.send_message(message.from_user.id,
                     WELCOME_MESSAGE,
                     reply_markup=create_common_buttons(message.from_user.id))


def create_topic_buttons() -> types.InlineKeyboardMarkup:
    """
    Создаются кнопки для быстрого ввода доступных топиков mqtt.
    Пользователь можно выбрать ручной режим и ввести данные самостоятельно.
    Возвращаемое значение: набор кнопок (выводится под сообщением бота).
    """

    keyboard = types.InlineKeyboardMarkup()
    for topic in get_settings(_settings, "topic_templates"):
        keyboard.add(types.InlineKeyboardButton(topic, callback_data=topic))

    keyboard.add(types.InlineKeyboardButton("manual", callback_data="manual"))
    return keyboard


def display_selection_buttons(chat_id: int) -> None:
    """
    Отправляется сообщение от бота с предложенными топиками для отправки в mqtt.
    Manual - ручной ввод топика и сообщения.
    """

    bot.send_message(chat_id, "Выберите топик или введите информацию вручную",
                     reply_markup=create_topic_buttons())

    cur_state = get_current_state(chat_id)
    cur_state["selected_topic"] = ""
    cur_state["expected_text"] = ""


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call) -> None:
    """
    Выполняются действия после выбора топика пользователем (нажатие на кнопки).
    Сами кнопки скрываются для защиты от повторого нажатия.
    """

    bot.delete_message(call.from_user.id, call.message.id)

    cur_state = get_current_state(call.from_user.id)
    if call.data == "manual":
        # Выбран ручной режим ввода.
        # Пользователь должен будет ввести топик, а затем само сообщение.
        cur_state["expected_text"] = "topic"
        bot.send_message(call.from_user.id, "Введите топик для отправки сообщения")
    else:
        # Топик выбран из предложенного списка.
        # Пользователь должен будет ввести сообщение для отправки.
        cur_state["expected_text"] = "message"
        cur_state["selected_topic"] = call.data
        bot.send_message(call.from_user.id, "Введите сообщение для отправки")


def is_message_correct(message: dict) -> bool:
    """
    Возвращается признак корректности введенного сообщения.
    Если есть ошибки, то вызывается исключение.
    """

    try:
        required_fields = ("topic", "message", "user", "password")
        for field in required_fields:
            if field not in message:
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
    """
    Введенное пользователем сообщение отправляется в сокет - для сервиса MQTT publisher.
    Возвращаемое значение: признак успеха отправки.
    """

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


def message_processing(message: str, id_message: int, chat_id: int) -> dict:
    """
    Обработка ввода сообщения пользователем.
    Происходит обновление словаря с текущими состояними сообщений.

    Возвращаемое значение: заполненный словарь, если введены все необходимые данные.
    В противном случае возвращается пустой словарь.
    """

    current_message = {}
    cur_state = get_current_state(chat_id)
    if cur_state["expected_text"] == "topic":
        # Пользователь ввел топик. Предложим ввести само сообщение.
        cur_state["selected_topic"] = message
        bot.send_message(id_message, "Введите сообщение для отправки")
        cur_state["expected_text"] = "message"

    elif cur_state["expected_text"] == "message":
        # Пользователь ввел сообщение. Вернем словарь с введенными пользователем полями.
        current_message = {"topic": cur_state["selected_topic"],
                           "message": message,
                           "user": cur_state["user"],
                           "password": encode_password(cur_state["password"])}

        cur_state["expected_text"] = ""
        cur_state["selected_topic"] = ""

    elif cur_state["expected_text"] == "user":
        # Пользователь ввел логин. Предложим ввести пароль.
        cur_state["user"] = message
        bot.send_message(id_message, "Введите пароль для подключения к mqtt_publisher")
        cur_state["expected_text"] = "password"

    elif cur_state["expected_text"] == "password":
        # Пользователь ввел пароль. Завершим авторизацию.
        cur_state["password"] = message
        bot.send_message(id_message,
                         "Авторизация завершена.",
                         reply_markup=create_common_buttons(chat_id))
        cur_state["expected_text"] = ""

    return current_message


def create_message_handling(chat_id: int, user_id: int) -> None:
    """
    Обработка команды создания сообщения.
    Если логин и пароль не были предварительно введены пользователем,
    то обработка команды не выполняется.
    """

    # Проверить необходимость ввода логина и пароля.
    cur_state = get_current_state(chat_id)
    if cur_state["user"]:
        # Вывод кнопок для быстрого ввода топика для отправки.
        display_selection_buttons(chat_id)
    else:
        message_answer = "Перед вводом сообщения нужно пройти авторизацию"
        bot.send_message(user_id, message_answer)


def sign_in_handling(chat_id: int, user_id: int) -> None:
    """
    Обработка команды sign in.
    Производится очистка текущих значений user/password.
    Пользователю отправляется запрос на ввод учетных данных.
    """

    cur_state = get_current_state(chat_id)
    cur_state["user"] = ""
    cur_state["password"] = ""

    message_answer = "Введите логин для подключения к mqtt_publisher"
    bot.send_message(user_id, message_answer)
    cur_state["expected_text"] = "user"


@bot.message_handler(content_types=['text'])
def get_message(message: telebot.types.Message) -> None:
    """
    Обрабатывается полученное сообщение.
    Если сообщение введено полностью, то оно проверяется
    на наличие всех необходимых полей и отправляется в сокет.
    """

    if message.text == "create_message":
        create_message_handling(message.chat.id, message.from_user.id)

    elif message.text == "sign_in":
        sign_in_handling(message.chat.id, message.from_user.id)

    else:
        # Обработка ввода сообщения пользователем.
        current_message = message_processing(message.text, message.from_user.id, message.chat.id)

        if current_message:
            # Пользователь ввел сообщение полностью.
            try:
                if is_message_correct(current_message):
                    # Сообщение преобразовывается в строку и отправляется.
                    result = send_message(json.dumps(current_message))
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
        BOT_NAME = get_settings(_settings, "name")
    except SettingsError:
        BOT_NAME = "unknown"

    print(f"Сервис запущен. Подключен бот {BOT_NAME}")

    try:
        bot.polling(none_stop=True)
    except ReadTimeout:
        raise SystemExit("Read timed out")
