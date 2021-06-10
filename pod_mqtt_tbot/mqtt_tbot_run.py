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

# Является ли сообщение пользователя командой
IS_CMD = re.compile(r"/\w+")
IS_CMD_SET = re.compile(r"/set\s+")
IS_CMD_SHOW = re.compile(r"/show\s+")
IS_CMD_SEND = re.compile(r"/send\s+")
IS_CMD_SIGN_IN = re.compile(r"/sign_in")
IS_CMD_CREATE_MSG = re.compile(r"/create_message")

# Найти параметры команды
CMD_SET_USR = re.compile(r"user\s+\w+")
CMD_SET_PWRD = re.compile(r"password\s+\w+")
CMD_SET_DEVICE = re.compile(r"device\s+\w+")
CMD_SET_TOPIC = re.compile(r"topic\s+.+")

CMD_SHOW_DEVICES = re.compile(r"devices")

MESSAGE_STATUS_SUCCESSFUL = "OK"
MESSAGE_AUTH_SUCCESSFUL = "Авторизация завершена"
MESSAGE_AUTH_DENIED = "Неверные имя пользователя или пароль"
MESSAGE_CONNECTION_LOST = "Потеряно соединение с сервисом mqtt publisher"
SOCKET_TIMEOUT = 10
WELCOME_MESSAGE = "Доступные команды: \n" \
                  "/create_message - помощник ввода сообщений. \n" \
                  "/sign_in - помощник авторизации пользователя. \n" \
                  "/set user *** - пользователь для авторизации, " \
                  "который должен быть заранее заведен в mqtt_publisher \n" \
                  "/set password *** - пароль для авторизации." \
                  "Перед вводом пароля должен быть указан пользователь." \
                  "После ввода пароля выполняется авторизация в mqtt_publisher \n" \
                  "/set user *** password *** - пользователь и пароль в одной команде \n" \
                  "/set topic *** - топик для отправки данных. \n" \
                  "/set device *** - текущее устройство. Если топик был заполнен ранее," \
                  "то устройство в нем изменяется на новое. \n" \
                  "/send *** - отправить сообщение в mqtt_publisher. \n "

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
        old_topic = self.selected_topic.split(sep="/")
        old_topic[2] = self.device
        new_topic = "/".join(old_topic)
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


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message: telebot.types.Message) -> None:
    """
    Выводится стартовая информация с подсказками пользователю,
    а так же основные кнопки управления.
    """

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
    for topic in get_settings("topic_templates"):
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
        send_response_to_user(call.from_user.id, "Введите топик для отправки сообщения")
    else:
        # Топик выбран из предложенного списка.
        # Пользователь должен будет ввести сообщение для отправки.
        cur_state.set_state("expected_text", "message")
        cur_state.set_state("selected_topic", call.data)
        cur_state.set_device_from_topic()
        send_response_to_user(call.from_user.id, "Введите сообщение для отправки")


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
        return "Превышено время ожидания ответа"

    server_socket.close()
    return "Неизвестная ошибка отправки сообщения"


def check_user_password(user: str, password: str) -> tuple:
    """
    Функция получает соль от сервиса и отправляет ему логин/пароль на проверку.

    Возвращаемое значение: кортеж с результатом отправки сообщения и хешем пароля.
    """

    get_salt_message = {"action": "/get_salt",
                        "user": user}
    try:
        received_salt = deliver_message(json.dumps(get_salt_message))
    except ConnectionRefusedError:
        return MESSAGE_CONNECTION_LOST, ""

    check_auth_message = {"action": "/check_auth",
                          "user": user,
                          "password": encode_password(password, received_salt)}
    try:
        state = deliver_message(json.dumps(check_auth_message))
    except ConnectionRefusedError:
        return MESSAGE_CONNECTION_LOST, ""

    answer_for_client = MESSAGE_AUTH_SUCCESSFUL if state == MESSAGE_STATUS_SUCCESSFUL else MESSAGE_AUTH_DENIED

    return answer_for_client, check_auth_message.get("password")


def prepare_message(message: str, cur_state: CurrentUserState) -> dict:
    """Возвращает сообщение пользователя в требуемом формате"""

    return {"topic": cur_state.selected_topic,
            "message": message,
            "user": cur_state.user,
            "password": cur_state.password}


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
        current_message = prepare_message(message, cur_state)
        cur_state.reset_messages()

    elif cur_state.expected_text == "user":
        # Пользователь ввел логин. Предложим ввести пароль.
        cur_state.set_state("user", message)
        cur_state.set_state("expected_text", "password")
        send_response_to_user(id_message, "Введите пароль для подключения к mqtt_publisher")

    elif cur_state.expected_text == "password":
        # Пользователь ввел пароль. Проверим корректность введенных данных и завершим авторизацию.
        answer_for_client, hash_password = check_user_password(cur_state.user, message)
        cur_state.set_state("password", hash_password)

        bot.send_message(id_message,
                         answer_for_client,
                         reply_markup=create_common_buttons(chat_id))
        cur_state.set_state("expected_text", "")

    return current_message


def send_response_to_user(chat_id: int, message: str):
    """Отправляет в чат телеграмма сообщение для пользователя"""

    bot.send_message(chat_id, message)


def run_action_create_message(chat_id: int, user_id: int) -> None:
    """
    Обработка команды создания сообщения (/create_message).
    Если логин и пароль не были предварительно введены пользователем,
    то обработка команды не выполняется.
    """

    # Проверить необходимость ввода логина и пароля.
    cur_state = get_user_state(chat_id)
    if cur_state.user:
        # Вывод кнопок для быстрого ввода топика для отправки.
        display_selection_buttons(chat_id)
    else:
        send_response_to_user(user_id, "Перед вводом сообщения нужно пройти авторизацию")


def run_action_sign_in(chat_id: int, user_id: int) -> None:
    """
    Обработка команды авторизации (/sign_in).
    Производится очистка текущих значений user/password.
    Пользователю отправляется запрос на ввод учетных данных.
    """

    cur_state = get_user_state(chat_id)
    cur_state.reset_user_auth()
    cur_state.set_state("expected_text", "user")

    send_response_to_user(user_id, "Введите логин для подключения к mqtt_publisher")


def parse_message(command: re.Pattern, message: str, start_position: int) -> str:
    """
    Поиск выполняется c использованием шаблона регулярного выражения.
    Служебное поле (такое как user, password итд) отбрасывается,
    а следующее за ним поле, начинающееся со start_position, возвращается.
    """

    find = command.search(message)
    if find:
        result = find.group(0)[start_position:].strip()
    else:
        result = ""

    return result


def run_action_set(message: str, chat_id: int):
    """
    Обработка команды установки параметров (/set).
    Описание команд приведено в WELCOME_MESSAGE.
    """

    user = parse_message(CMD_SET_USR, message, 4)
    password = parse_message(CMD_SET_PWRD, message, 8)
    cur_state = get_user_state(chat_id)
    answer_for_client = "OK"

    if user:
        cur_state.reset_user_auth()
        cur_state.set_state("user", user)

    if password and cur_state.user:
        answer_for_client, hash_password = check_user_password(cur_state.user, password)
        cur_state.set_state("password", hash_password)
    elif password and not cur_state.user:
        answer_for_client = "Перед вводом пароля требуется указать пользователя"

    device = parse_message(CMD_SET_DEVICE, message, 6)
    if device:
        cur_state.set_state("device", device)

        if cur_state.selected_topic:
            cur_state.update_topic()
            answer_for_client = f"Новый топик: {cur_state.selected_topic}"

    topic = parse_message(CMD_SET_TOPIC, message, 5)
    if topic:
        cur_state.set_state("selected_topic", topic)
        cur_state.set_device_from_topic()
        answer_for_client = f"Новый топик: {topic}"

    send_response_to_user(chat_id, answer_for_client)


def run_action_show(message: str, chat_id: int):
    """
    Обработка команды /show.
    """

    cur_state = get_user_state(chat_id)

    text = re.sub(IS_CMD_SHOW, "", message).strip().lower()

    if text == "topic":
        value = cur_state.selected_topic
    elif text == "device":
        value = cur_state.device
    elif text == "user":
        value = cur_state.user

    send_response_to_user(chat_id, value)


def run_action_send(message: str, chat_id: int, user_id: int):
    """
    Обработка команды /send.
    """

    text = re.sub(IS_CMD_SEND, "", message).strip()
    cur_state = get_user_state(chat_id)
    current_message = prepare_message(text, cur_state)
    result = deliver_message(json.dumps(current_message))
    send_response_to_user(user_id, result)


def run_command(text_message: str, chat_id: int, user_id: int):
    """
    Выполнение команд введенных пользователем. Командой считается
    сообщение начинающееся с символа /.
    """

    if IS_CMD_SET.match(text_message):
        run_action_set(text_message, chat_id)
    elif IS_CMD_SHOW.match(text_message):
        run_action_show(text_message, chat_id)
    elif IS_CMD_SEND.match(text_message):
        run_action_send(text_message, chat_id, user_id)
    elif IS_CMD_CREATE_MSG.match(text_message):
        run_action_create_message(chat_id, user_id)
    elif IS_CMD_SIGN_IN.match(text_message):
        run_action_sign_in(chat_id, user_id)
    else:
        send_response_to_user(chat_id, "Неизвестная команда")


@bot.message_handler(content_types=['text'])
def get_message(message: telebot.types.Message) -> None:
    """
    Обрабатывается полученное сообщение.
    Если сообщение введено полностью, то оно проверяется
    на наличие всех необходимых полей и отправляется в сокет.
    """

    text_message = message.text.lower()

    if IS_CMD.match(text_message):
        run_command(text_message, message.chat.id, message.from_user.id)
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
