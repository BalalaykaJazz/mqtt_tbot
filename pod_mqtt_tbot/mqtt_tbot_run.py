"""
Создается телеграм бот, который получает сообщения от пользователей
и отправляет их в сокет для сервиса mqtt_publisher.
Сообщениями можно управлять своими устройствами или получать от них информацию.
"""
import json
import ssl
import socket
import re
import telebot  # type: ignore
from user_auth import encode_password  # type: ignore
from telebot import types  # type: ignore
from requests.exceptions import ReadTimeout  # type: ignore
from config import get_settings  # type: ignore
import requests
from influxdb_client import InfluxDBClient, rest
from urllib3.exceptions import NewConnectionError, LocationParseError

# Является ли сообщение пользователя командой
IS_CMD = re.compile(r"/\w+")
IS_CMD_SET = re.compile(r"/set\s+")
IS_CMD_SHOW = re.compile(r"/sh\s+")
IS_CMD_SEND = re.compile(r"/send\s+")
IS_CMD_CREATE_MSG = re.compile(r"/create_message")

IS_CMD_AUTH = re.compile(r"/auth\s+")
CMD_AUTH_USER = re.compile(r"/auth (\w+)\s*:\s*\w+")
CMD_AUTH_PASSWORD = re.compile(r"/auth \w+\s*:\s*(\w+)")
CMD_SET_DEVICE = re.compile(r"dev\s+(\w+)")

SUCCESSFUL_MESSAGE = "OK"
FAILED_MESSAGE = "Failed"
UNKNOWN_COMMAND = "Неизвестная команда"
MESSAGE_CONNECTION_LOST = "Потеряно соединение с сервисом mqtt publisher"
AUTH_FORMAT_ERROR = "Некорректный формат команды /auth\n" \
                    "Требуемый формат: /auth user:password"
SOCKET_TIMEOUT = 30
WELCOME_MESSAGE = "Доступные команды:\n" \
                  "/create_message - помощник ввода сообщений.\n" \
                  "/sign_in - помощник авторизации пользователя.\n" \
                  "/set auth user:password - имя пользователя и пароль," \
                  "доступные для подключения к mqtt_publisher.\n" \
                  "После ввода команды происходит проверка введенных данных" \
                  "на валидность.\n" \
                  "/set dev *** - устройство для отправки сообщений.\n" \
                  "/send *** - отправить сообщение в mqtt_publisher." \
                  "топик сообщения формируется автоматически в формате:\n" \
                  "/<user>/<device>/in/params\n" \
                  "/sh auth, /sh dev, /sh topic - проверка введенных данных."

clients_state: dict = {}
bot = telebot.TeleBot(get_settings("tg_token"))


class CurrentUserState:
    """
    Класс отражает состояние работы с пользователем на текущий момент.

    selected_topic - выбранный пользователем топик для отправки в mqtt.
    expected_text - введенный пользователем текст сообщения для отправки.
    user и password - логин и пароль текущего пользователя.
    """

    def __init__(self):
        self.selected_topic = ""
        self.expected_text = ""
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
        self.expected_text = ""

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


def create_common_buttons(chat_id: int) -> types.ReplyKeyboardMarkup:
    """
    Создаются основные кнопки для взаимодействия с пользователем.
    Возвращаемое значение: набор кнопок
    """

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)

    cur_state = get_user_state(chat_id)
    if cur_state.user:
        keyboard.add(types.KeyboardButton("/create_message"))

    keyboard.add(types.KeyboardButton("/sign_in"))
    keyboard.add(types.KeyboardButton("/help"))

    return keyboard


def create_topic_buttons() -> types.InlineKeyboardMarkup:
    """
    Создаются кнопки для быстрого ввода доступных топиков mqtt.
    Пользователь можно выбрать ручной режим и ввести данные самостоятельно.
    Возвращаемое значение: набор кнопок (выводится под сообщением бота).
    """

    keyboard = types.InlineKeyboardMarkup()
    for topic in get_settings("topic_templates"):
        keyboard.add(types.InlineKeyboardButton(topic, callback_data=topic))

    keyboard.add(types.InlineKeyboardButton("manual", callback_data="manual"))
    return keyboard


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message: telebot.types.Message):
    """
    Выводится стартовая информация с подсказками пользователю,
    а так же основные кнопки управления.
    """

    bot.send_message(message.from_user.id,
                     WELCOME_MESSAGE,
                     reply_markup=create_common_buttons(message.from_user.id))


def display_selection_buttons(chat_id: int):
    """
    Отправляется сообщение от бота с предложенными топиками для отправки в mqtt.
    Manual - ручной ввод топика и сообщения.
    """

    bot.send_message(chat_id, "Выберите топик или введите информацию вручную",
                     reply_markup=create_topic_buttons())

    cur_state = get_user_state(chat_id)
    cur_state.reset_messages()


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call) -> None:
    """
    Выполняются действия после выбора топика пользователем (нажатие на кнопки).
    Сами кнопки скрываются для защиты от повторого нажатия.
    """

    bot.delete_message(call.from_user.id, call.message.id)

    cur_state = get_user_state(call.from_user.id)
    if call.data == "manual":
        # Выбран ручной режим ввода.
        # Пользователь должен будет ввести топик, а затем само сообщение.
        cur_state.set_state("expected_text", "topic")
        answer_for_client = "Введите топик для отправки сообщения"
    else:
        # Топик выбран из предложенного списка.
        # Пользователь должен будет ввести сообщение для отправки.
        cur_state.set_state("expected_text", "message")
        cur_state.set_state("selected_topic", call.data)
        cur_state.set_device_from_topic()

        answer_for_client = "Введите сообщение для отправки"

    send_response_to_user(call.from_user.id, answer_for_client)


def deliver_message(message: str) -> str:
    """
    Введенное пользователем сообщение отправляется в сокет - для сервиса MQTT publisher.
    Возвращаемое значение: признак успеха отправки.
    """

    socket.setdefaulttimeout(SOCKET_TIMEOUT)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if get_settings("use_ssl"):
        server_socket = ssl.wrap_socket(server_socket,
                                        cert_reqs=ssl.CERT_REQUIRED,
                                        ca_certs=get_settings("SSL_KEYFILE_PATH"))

    try:
        server_socket.connect((get_settings("host"), get_settings("port")))

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


def is_message_correct(message: dict) -> bool:
    """
    Возвращается признак корректности введенного сообщения.
    """

    required_fields = ("topic", "message", "user", "password")
    for field in required_fields:
        if field not in message:
            print(f"Сообщение не содержит обязательного поля {field}")
            return False

    return True


def message_processing(message: str, id_message: int, chat_id: int) -> dict:
    """
    Обработка ввода сообщения пользователем.
    Происходит обновление словаря с текущими состояними сообщений.

    Возвращаемое значение: заполненный словарь, если введены все необходимые данные.
    В противном случае возвращается пустой словарь.
    """

    current_message = {}
    cur_state = get_user_state(chat_id)
    if cur_state.expected_text == "topic":
        # Пользователь ввел топик. Предложим ввести само сообщение.
        cur_state.set_state("selected_topic", message)
        cur_state.set_state("expected_text", "message")
        send_response_to_user(id_message, "Введите сообщение для отправки")

    elif cur_state.expected_text == "message":
        # Пользователь ввел сообщение. Вернем словарь с введенными пользователем полями.
        current_message = make_message(message, cur_state)
        cur_state.reset_messages()

    elif cur_state.expected_text == "user":
        # Пользователь ввел логин. Предложим ввести пароль.
        cur_state.set_state("user", message)
        cur_state.set_state("expected_text", "password")
        send_response_to_user(id_message, "Введите пароль для подключения к mqtt_publisher")

    elif cur_state.expected_text == "password":
        # Пользователь ввел пароль. Проверим корректность введенных данных и завершим авторизацию.

        hash_password, answer_for_client = make_password_hash(cur_state.user, message)
        cur_state.set_state("password", hash_password)
        answer_for_client = check_auth(cur_state.user, cur_state.password)
        cur_state.update_topic()

        bot.send_message(id_message,
                         answer_for_client,
                         reply_markup=create_common_buttons(chat_id))
        cur_state.set_state("expected_text", "")

    return current_message


def send_response_to_user(chat_id: int, message: str):
    """Отправляет в чат телеграмма сообщение для пользователя"""

    bot.send_message(chat_id, message)


def run_action_create_message(chat_id: int, cur_state: CurrentUserState) -> str:
    """
    Обработка команды создания сообщения (/create_message).
    Если логин и пароль не были предварительно введены пользователем,
    то обработка команды не выполняется.
    """

    # Проверить необходимость ввода логина и пароля.
    if cur_state.user:
        # Вывод кнопок для быстрого ввода топика для отправки.
        display_selection_buttons(chat_id)
        answer_for_client = ""
    else:
        answer_for_client = "Перед вводом сообщения нужно пройти авторизацию"

    return answer_for_client


def connect_db() -> InfluxDBClient:
    """Подключение к базе данных"""

    client = InfluxDBClient(url=get_settings("db_url"),
                            token=get_settings("db_token"),
                            org=get_settings("db_org"))
    return client


def get_response_from_db(db_client: InfluxDBClient, query: str) -> list:
    """
    Возвращает результат запроса в виде списка. Если в ходе получения запроса произошла ошибка,
    то возвращается пустой список.
    """

    try:
        answer = db_client.query_api().query(org=get_settings("db_org"),
                                             query=query)
        return answer

    except (rest.ApiException, NewConnectionError, LocationParseError, IndexError):
        return []


def get_online(db_name: str) -> list:
    """
    Возвращает список всех девайсов, которые отправляли данные последние 30 дней,
    а так же время последнего полученного сообщения.
    Если таких девайсов нет, то список будет пустым.
    """

    db_client = connect_db()

    query = f'from(bucket:"{db_name}")\
    |> range(start: -30d)\
    |> sort(columns: ["_time"], desc: true)\
    |> limit(n: 1)'

    answer = get_response_from_db(db_client, query)

    devices = []
    for table in answer:
        for record in table.records:
            last_time = record.get_time().strftime("%d.%m.%Y %H:%M:%S")
            device_name = record.values.get("device")
            devices.append(f"device: {device_name}, last time: {last_time}")

    return devices


def run_action_set(message: str, cur_state: CurrentUserState) -> str:
    """
    Обработка команды установки параметров (/set).
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
    Обработка команды вывода данных пользователю (/sh).
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
    Обработка команды отправки сообщений в mqtt_publisher (/send).
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
    Команда должна иметь формат: /auth user:password
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


def run_command(text_message: str, chat_id: int):
    """
    Выполнение команд введенных пользователем. Командой считается
    сообщение начинающееся с символа /.
    """

    cur_state = get_user_state(chat_id)

    if IS_CMD_AUTH.match(text_message):
        answer_for_client = run_action_auth(text_message, cur_state)
    elif IS_CMD_SET.match(text_message):
        answer_for_client = run_action_set(text_message, cur_state)
    elif IS_CMD_SHOW.match(text_message):
        answer_for_client = run_action_show(text_message, cur_state)
    elif IS_CMD_SEND.match(text_message):
        answer_for_client = run_action_send(text_message, cur_state)
    elif IS_CMD_CREATE_MSG.match(text_message):
        answer_for_client = run_action_create_message(chat_id, cur_state)
    else:
        answer_for_client = UNKNOWN_COMMAND

    if answer_for_client:
        send_response_to_user(chat_id, answer_for_client)


@bot.message_handler(content_types=['text'])
def get_message(message: telebot.types.Message) -> None:
    """
    Обрабатывается полученное сообщение.
    Если сообщение введено полностью, то оно проверяется
    на наличие всех необходимых полей и отправляется в сокет.
    """

    text_message = message.text.lower()

    if IS_CMD.match(text_message):
        run_command(text_message, message.chat.id)
    else:

        # Обработка ввода сообщения пользователем.
        current_message = message_processing(text_message, message.from_user.id, message.chat.id)

        if current_message:
            # Пользователь ввел сообщение полностью.
            try:
                if is_message_correct(current_message):
                    # Сообщение преобразовывается в строку и отправляется.
                    result = deliver_message(json.dumps(current_message))
                    cur_state = get_user_state(message.chat.id)
                    sender_name = cur_state.device if cur_state.device else "Server"
                    message_answer = f"{sender_name}: {result}"
                else:
                    message_answer = "Полученное сообщение не соответствует требуемому формату"

            except ConnectionRefusedError:
                message_answer = "Сервис 'MQTT publisher' не запущен"

            send_response_to_user(message.from_user.id, message_answer)


def start_pooling():
    """Бесконечный цикл работы с ботом"""

    try:
        bot.polling(none_stop=True)
    except (ReadTimeout, requests.exceptions.ConnectTimeout):
        start_pooling()


if __name__ == "__main__":

    if not get_settings("correctly"):
        raise SystemExit("Ошибка при загрузке настроек. Работа программы завершена")

    print(f"Сервис запущен. Подключен бот {get_settings('name')}")
    start_pooling()
