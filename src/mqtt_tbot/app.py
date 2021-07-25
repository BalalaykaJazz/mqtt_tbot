"""Процедуры с обработкой команд пользователя"""
import re
from .delivery import deliver_message  # pylint: disable = import-error
from .db_query import get_online  # pylint: disable = import-error
from .event_logger import get_info_logger, get_error_logger  # pylint: disable = import-error
from .user_auth import encode_password  # pylint: disable = import-error

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

clients_state: dict = {}
event_log = get_info_logger("INFO__app__")
error_log = get_error_logger("ERR__app__")


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


def search_by_template(template: re.Pattern, message: str) -> str:
    """
    Выполняет поиск в сообщении от пользователя по шаблону.
    Возвращаемое значение: результат поиска или пустая строка.
    """

    found = re.findall(template, message)

    return "" if not found else found[0].strip()


def execute_command(text_message: str, chat_id: int) -> str:
    """
    Выполнение команды пользователя.
    Возвращает ответ сервера в виде строки.
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
    else:
        answer_for_client = UNKNOWN_COMMAND
        error_log.warning("Неизвестная команда %s", text_message)

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

    _user = search_by_template(CMD_AUTH_USER, message)
    _password = search_by_template(CMD_AUTH_PASSWORD, message)

    if _user and _password:
        cur_state.set_state("user", _user)
        hash_password, answer_for_client = make_password_hash(cur_state.user,
                                                              _password)
        cur_state.set_state("password", hash_password)
        answer_for_client = check_auth(cur_state.user, cur_state.password)
        cur_state.update_topic()
    else:
        answer_for_client = AUTH_FORMAT_ERROR

    return answer_for_client


def make_password_hash(user: str, password: str) -> tuple:
    """
    Хеширование введенного пользователем пароля для отправки в mqtt_publisher.
    Соль для хеширования предоставляет mqtt_publisher по имени пользователя.

    Возвращаемое значение: кортеж из хэша пароля и статуса операции
    """

    get_salt_message = make_message(message="/get_salt", user=user)

    try:
        received_salt = deliver_message(get_salt_message)

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


def run_action_set(message: str, cur_state: CurrentUserState) -> str:
    """
    Обработка команды установки параметров set.
    """

    device_name = search_by_template(CMD_SET_DEVICE, message)

    if device_name:
        cur_state.set_state("device", device_name)
        cur_state.update_topic()
        answer_for_client = SUCCESSFUL_MESSAGE
    else:
        answer_for_client = FAILED_MESSAGE

    return answer_for_client


def run_action_show(message: str, cur_state: CurrentUserState) -> str:
    """
    Обработка команды вывода данных пользователю sh.
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
        current_message = make_message(text,
                                       cur_state.selected_topic,
                                       cur_state.user,
                                       cur_state.password)
        answer_for_client = deliver_message(current_message)

    return answer_for_client


def make_message(message: str = "", topic: str = "",
                 user: str = "", password: str = "") -> dict:
    """Возвращает сообщение пользователя в требуемом формате"""

    return {"topic": topic,
            "message": message,
            "user": user,
            "password": password}


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
        check_auth_message = make_message(message="/check_auth",
                                          user=user,
                                          password=password)
        try:
            state = deliver_message(check_auth_message)
            answer_for_client = SUCCESSFUL_MESSAGE \
                if state == SUCCESSFUL_MESSAGE\
                else FAILED_MESSAGE
        except ConnectionRefusedError:
            answer_for_client = MESSAGE_CONNECTION_LOST

    return answer_for_client
