"""
Создается телеграм бот, который получает сообщения от пользователей
и отправляет их в сокет для сервиса mqtt_publisher.
Сообщениями можно управлять своими устройствами или получать от них информацию.
"""
import json
import ssl
import socket
import re
from user_auth import encode_password  # type: ignore
from requests.exceptions import ReadTimeout  # type: ignore
from config import settings, is_main_settings_correct  # type: ignore
import requests
from event_logger import get_info_logger, get_error_logger
from db_query import get_online
from aiogram import Bot, Dispatcher, executor, types

# Является ли сообщение пользователя командой
IS_CMD_SET = re.compile(r"set\s+")
IS_CMD_SHOW = re.compile(r"sh\s+")
IS_CMD_SEND = re.compile(r"send\s+")

IS_CMD_AUTH = re.compile(r"auth\s+")
CMD_AUTH_USER = re.compile(r"auth (\w+)\s*:\s*\w+")
CMD_AUTH_PASSWORD = re.compile(r"auth \w+\s*:\s*(\w+)")
CMD_SET_DEVICE = re.compile(r"dev\s+(\w+)")

SUCCESSFUL_MESSAGE = "OK"
FAILED_MESSAGE = "Failed"
UNKNOWN_COMMAND = "Неизвестная команда"
MESSAGE_CONNECTION_LOST = "Потеряно соединение с сервисом mqtt publisher"
AUTH_FORMAT_ERROR = "Некорректный формат команды /auth\n" \
                    "Требуемый формат: /auth user:password"
WELCOME_MESSAGE = "Доступные команды:\n" \
                  "set auth user:password - имя пользователя и пароль," \
                  "доступные для подключения к mqtt_publisher.\n" \
                  "После ввода команды происходит проверка введенных данных" \
                  "на валидность.\n" \
                  "set dev *** - устройство для отправки сообщений.\n" \
                  "send *** - отправить сообщение в mqtt_publisher." \
                  "топик сообщения формируется автоматически в формате:\n" \
                  "/<user>/<device>/in/params\n" \
                  "sh auth, sh dev, sh topic - проверка введенных данных."
SOCKET_TIMEOUT = 30

clients_state: dict = {}
bot = Bot(token=settings.bot_token)
dp = Dispatcher(bot)
event_log = get_info_logger("INFO__listener__")
error_log = get_error_logger("ERR__listener__")


class CurrentUserState:
    """
    Класс отражает состояние работы с пользователем на текущий момент.

    selected_topic - выбранный пользователем топик для отправки в mqtt.
    user и password - логин и пароль текущего пользователя.
    """

    def __init__(self):
        self.selected_topic = ""
        self.user = ""
        self.password = ""
        self.device = ""

    def set_state(self, state_name: str, value: str):
        """Записывается новое состояние."""
        setattr(self, state_name, value)

    def set_device_from_topic(self):
        """Получение устройства из топика."""
        new_topic = self.selected_topic.split(sep="/")
        self.set_state("device", new_topic[2])

    def update_topic(self):
        """Обновить топик из-за изменения устройства."""

        if self.user and self.device:
            new_topic = f"/{self.user}/{self.device}/in/params"
            self.set_state("selected_topic", new_topic)

    def reset_messages(self):
        """Сбросить состояния для ввода новых сообщений"""
        self.selected_topic = ""

    def reset_user_auth(self):
        """Сброс логина и пароля"""
        self.user = ""
        self.password = ""


class FormatError(Exception):
    """Исключение для ошибок в формате полученных сообщений."""


def get_user_state(chat_id: int) -> CurrentUserState:
    """
    Если это новый пользователь, то создается новый экземпляр класса с
    пустыми полями. В противном случае берется существующий из словаря.
    Ключ словаря: chat_id - чат с определенным пользователем.
    Возвращаемое значение: экземпляр класса.
    """

    chat_id_str = str(chat_id)

    if clients_state.get(chat_id_str) is None:
        clients_state[chat_id_str] = CurrentUserState()

    return clients_state[chat_id_str]


def create_common_buttons() -> types.ReplyKeyboardMarkup:
    """
    Создаются основные кнопки для взаимодействия с пользователем.
    Возвращаемое значение: набор кнопок
    """

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("/help"))

    return keyboard


@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    """
    Выводится стартовая информация с подсказками пользователю,
    а так же основные кнопки управления.
    """

    await bot.send_message(message.from_user.id,
                           WELCOME_MESSAGE,
                           reply_markup=create_common_buttons())


def deliver_message(message: str) -> str:
    """
    Введенное пользователем сообщение отправляется в сокет - для сервиса MQTT publisher.
    Возвращаемое значение: признак успеха отправки.
    """

    socket.setdefaulttimeout(SOCKET_TIMEOUT)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if settings.use_ssl:
        server_socket = ssl.wrap_socket(server_socket,
                                        cert_reqs=ssl.CERT_REQUIRED,
                                        ca_certs=settings.ssl_keyfile_path)

    try:
        server_socket.connect((settings.server_host, settings.server_port))

        if message:
            server_socket.send(message.encode())
            answer = server_socket.recv(1024).decode("utf-8")
            server_socket.close()
            return answer

    except socket.timeout:
        server_socket.close()
        return "Превышено время ожидания ответа"

    server_socket.close()
    return "Неизвестная ошибка отправки сообщения"


def make_message(message: str, cur_state: CurrentUserState) -> dict:
    """Возвращает сообщение пользователя в требуемом формате"""

    return {"topic": cur_state.selected_topic,
            "message": message,
            "user": cur_state.user,
            "password": cur_state.password}


async def send_response_to_user(chat_id: int, message: str):
    """Отправляет в чат телеграмма сообщение для пользователя"""

    await bot.send_message(chat_id, message)


def run_action_set(message: str, cur_state: CurrentUserState) -> str:
    """
    Обработка команды установки параметров (set).
    """

    device_name = re.findall(CMD_SET_DEVICE, message)

    if device_name:
        cur_state.set_state("device", device_name[0])
        cur_state.update_topic()
        answer_for_client = SUCCESSFUL_MESSAGE
    else:
        answer_for_client = FAILED_MESSAGE

    return answer_for_client


def run_action_show(message: str, cur_state: CurrentUserState) -> str:
    """
    Обработка команды вывода данных пользователю (sh).
    """

    text = re.sub(IS_CMD_SHOW, "", message).strip().lower()

    if text == "topic":
        answer_for_client = cur_state.selected_topic
    elif text == "dev":
        answer_for_client = cur_state.device
    elif text == "user":
        answer_for_client = cur_state.user
    elif text == "auth":
        answer_for_client = check_auth(cur_state.user, cur_state.password)
    elif text == "online":
        answer_for_client = get_online(db_name=cur_state.user)
        answer_for_client = "\n".join(answer_for_client)
    else:
        answer_for_client = UNKNOWN_COMMAND

    if not answer_for_client:
        answer_for_client = "Нет данных"

    return answer_for_client


def run_action_send(message: str, cur_state: CurrentUserState) -> str:
    """
    Обработка команды отправки сообщений в mqtt_publisher (send).
    """

    if check_auth(cur_state.user, cur_state.password) != SUCCESSFUL_MESSAGE:
        answer_for_client = "Перед отправкой сообщения нужно пройти авторизацию"
    elif not cur_state.device:
        answer_for_client = "Невозможно отправить сообщение, т.к." \
                            "не указано устройство-получатель."
    else:
        cur_state.update_topic()

        text = re.sub(IS_CMD_SEND, "", message).strip()
        current_message = make_message(text, cur_state)
        answer_for_client = deliver_message(json.dumps(current_message))

    return answer_for_client


def make_password_hash(user: str, password: str) -> tuple:
    """
    Хеширование введенного пользователем пароля для отправки в mqtt_publisher.
    Соль для хеширования предоставляет mqtt_publisher по имени пользователя.

    Возвращаемое значение: кортеж из хэша пароля и статуса операции
    """

    get_salt_message = {"action": "/get_salt", "user": user}

    try:
        received_salt = deliver_message(json.dumps(get_salt_message))

        if received_salt:
            hash_password = encode_password(password, received_salt)
            answer_for_client = SUCCESSFUL_MESSAGE
        else:
            hash_password = None
            answer_for_client = "Неизвестный пользователь." \
                                "Невозможно хешировать пароль."

    except ConnectionRefusedError:
        hash_password = None
        answer_for_client = MESSAGE_CONNECTION_LOST

    return hash_password, answer_for_client


def check_auth(user: str, password: str) -> str:
    """
    Проверка авторизации пользователя.
    Логин и хэш пароля передаются в mqtt_publisher для проверки.
    Если этих данных нет, значит пользователь еще не был авторизован в системе.

    Возвращаемое значение: текст сообщения для отправки пользователю -
    результат авторизации (успешно/не успешно) или сообщение о проблеме.
    """

    if not user or not password:
        answer_for_client = "Пользователь не авторизован в системе"
    else:
        check_auth_message = {"action": "/check_auth",
                              "user": user,
                              "password": password}
        try:
            state = deliver_message(json.dumps(check_auth_message))
            answer_for_client = SUCCESSFUL_MESSAGE if state == SUCCESSFUL_MESSAGE else FAILED_MESSAGE
        except ConnectionRefusedError:
            answer_for_client = MESSAGE_CONNECTION_LOST

    return answer_for_client


def run_action_auth(message: str, cur_state: CurrentUserState) -> str:
    """
    Обработка авторизации пользователя.
    Команда должна иметь формат: auth user:password
    В случае корректного ввода команды полученный пароль хешируется
    и передается в сервис mqtt_publisher для проверки.

    Возвращаемое значение: текст сообщения для отправки пользователю -
    результат авторизации (успешно/не успешно) или сообщение о неправильном вводе команды
    """

    cur_state.reset_user_auth()

    _user = re.findall(CMD_AUTH_USER, message)
    _password = re.findall(CMD_AUTH_PASSWORD, message)

    if _user and _password:
        cur_state.set_state("user", _user[0])
        hash_password, answer_for_client = make_password_hash(cur_state.user,
                                                              _password[0])
        cur_state.set_state("password", hash_password)
        answer_for_client = check_auth(cur_state.user, cur_state.password)
        cur_state.update_topic()
    else:
        answer_for_client = AUTH_FORMAT_ERROR

    return answer_for_client


@dp.message_handler(content_types=['text'])
async def get_message(message: types.Message) -> None:
    """
    Обрабатывается полученное от пользователя сообщение.
    Сообщение должно иметь следующий формат:
    '<Заголовок> <текст сообщения>'
    Заголовок содержит имя команды: sh, send, set и другие.
    Текст сообщения содержит все необходимые параметры для
    выполнения команды сервером.
    """

    text_message = message.text.lower()
    chat_id = message.chat.id

    cur_state = get_user_state(chat_id)

    if IS_CMD_AUTH.match(text_message):
        answer_for_client = run_action_auth(text_message, cur_state)
    elif IS_CMD_SET.match(text_message):
        answer_for_client = run_action_set(text_message, cur_state)
    elif IS_CMD_SHOW.match(text_message):
        answer_for_client = run_action_show(text_message, cur_state)
    elif IS_CMD_SEND.match(text_message):
        answer_for_client = run_action_send(text_message, cur_state)
    else:
        answer_for_client = UNKNOWN_COMMAND

    if answer_for_client:
        await send_response_to_user(chat_id, answer_for_client)


def start_pooling():
    """Бесконечный цикл работы с ботом"""

    try:
        executor.start_polling(dp, skip_updates=True)
    except (ReadTimeout, requests.exceptions.ConnectTimeout):
        start_pooling()


if __name__ == "__main__":

    if not is_main_settings_correct(settings):
        error_log.error("Ошибка при загрузке настроек")
        raise SystemExit("Работа программы завершена")

    event_log.info("Сервис запущен. Подключен бот %s", settings.bot_name)
    start_pooling()
