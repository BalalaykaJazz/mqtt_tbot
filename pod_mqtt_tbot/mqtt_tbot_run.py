"""
Создается телеграм бот, который получает сообщения от пользователей
и отправляет их в сокет для сервиса mqtt_publisher.
Сообщениями можно управлять своими устройствами или получать от них информацию.
"""
import json
import ssl
import socket
import telebot  # type: ignore
from user_auth import encode_password  # type: ignore
from telebot import types  # type: ignore
from requests.exceptions import ReadTimeout  # type: ignore
from config import get_settings  # type: ignore

MESSAGE_STATUS_SUCCESSFUL = "OK"
MESSAGE_AUTH_SUCCESSFUL = "Авторизация завершена"
MESSAGE_AUTH_DENIED = "Неверные имя пользователя или пароль"
MESSAGE_CONNECTION_LOST = "Потеряно соединение с сервисом mqtt publisher"
SOCKET_TIMEOUT = 10
WELCOME_MESSAGE = "Сначала нужно авторизироваться через кнопку sign in. \n" \
                  "Для начала ввода сообщения воспользуйтесь кнопкой create_message. \n"


def start_bot() -> telebot:
    """Создание телеграм бота"""

    return telebot.TeleBot(get_settings("tg_token"))


clients_state: dict = {}
bot = start_bot()


class CurrentUserState:
    """
    Класс отражает состояние работы с пользователем на текущий момент.

    selected_topic - выбранный пользователем топик для отправки в mqtt.
    expected_text - введенный пользователем текст сообщения для отправки.
    user и password - логин и пароль текущего пользователя.
    salt - соль для хеширования пароля пользователя.
    """

    def __init__(self):
        self.selected_topic = ""
        self.expected_text = ""
        self.user = ""
        self.password = ""
        self.salt = ""

    def set_state(self, state_name: str, value: str):
        """Записывается новое состояние."""
        setattr(self, state_name, value)

    def reset_messages(self):
        """Сбросить состояния для ввода новых сообщений"""
        self.selected_topic = ""
        self.expected_text = ""

    def reset_user_auth(self):
        """Сброс логина и пароля"""
        self.user = ""
        self.password = ""
        self.salt = ""


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
        keyboard.add(types.KeyboardButton("create_message"))

    keyboard.add(types.KeyboardButton("sign_in"))
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
        bot.send_message(call.from_user.id, "Введите топик для отправки сообщения")
    else:
        # Топик выбран из предложенного списка.
        # Пользователь должен будет ввести сообщение для отправки.
        cur_state.set_state("expected_text", "message")
        cur_state.set_state("selected_topic", call.data)
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


def send_message(message: str) -> str:
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

    Возвращаемое значение: кортеж с результатом отправки сообщения и солью.
    """

    get_salt_message = {"action": "/get_salt",
                        "user": user}
    try:
        received_salt = send_message(json.dumps(get_salt_message))
    except ConnectionRefusedError:
        return MESSAGE_CONNECTION_LOST, ""

    check_auth_message = {"user": user,
                          "password": encode_password(password, received_salt),
                          "action": "/check_auth"}
    try:
        state = send_message(json.dumps(check_auth_message))
    except ConnectionRefusedError:
        return MESSAGE_CONNECTION_LOST, ""

    answer_for_client = MESSAGE_AUTH_SUCCESSFUL if state == MESSAGE_STATUS_SUCCESSFUL else MESSAGE_AUTH_DENIED

    return answer_for_client, received_salt


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
        bot.send_message(id_message, "Введите сообщение для отправки")

    elif cur_state.expected_text == "message":
        # Пользователь ввел сообщение. Вернем словарь с введенными пользователем полями.
        current_message = {"topic": cur_state.selected_topic,
                           "message": message,
                           "user": cur_state.user,
                           "password": encode_password(cur_state.password,
                                                       cur_state.salt)}

        cur_state.reset_messages()

    elif cur_state.expected_text == "user":
        # Пользователь ввел логин. Предложим ввести пароль.
        cur_state.set_state("user", message)
        cur_state.set_state("expected_text", "password")
        bot.send_message(id_message, "Введите пароль для подключения к mqtt_publisher")

    elif cur_state.expected_text == "password":
        # Пользователь ввел пароль. Проверим корректность введенных данных и завершим авторизацию.
        cur_state.set_state("password", message)
        answer_for_client, salt = check_user_password(cur_state.user, cur_state.password)
        cur_state.set_state("salt", salt)

        bot.send_message(id_message,
                         answer_for_client,
                         reply_markup=create_common_buttons(chat_id))
        cur_state.set_state("expected_text", "")

    return current_message


def create_message_handling(chat_id: int, user_id: int) -> None:
    """
    Обработка команды создания сообщения.
    Если логин и пароль не были предварительно введены пользователем,
    то обработка команды не выполняется.
    """

    # Проверить необходимость ввода логина и пароля.
    cur_state = get_user_state(chat_id)
    if cur_state.user:
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

    cur_state = get_user_state(chat_id)
    cur_state.reset_user_auth()
    cur_state.set_state("expected_text", "user")

    message_answer = "Введите логин для подключения к mqtt_publisher"
    bot.send_message(user_id, message_answer)


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
                    message_answer = f"Ответ сервиса: {result}"
                else:
                    message_answer = ""

            except FormatError:
                message_answer = "Полученное сообщение не соответствует требуемому формату"
            except ConnectionRefusedError:
                message_answer = "Сервис 'MQTT publisher' не запущен"

            bot.send_message(message.from_user.id, message_answer)
            print(message_answer)


if __name__ == "__main__":

    if not get_settings("correctly"):
        raise SystemExit("Ошибка при загрузке настроек. Работа программы завершена")

    print(f"Сервис запущен. Подключен бот {get_settings('name')}")

    try:
        bot.polling(none_stop=True)
    except ReadTimeout:
        raise SystemExit("Read timed out")
