"""
Создается телеграм бот, который получает сообщения от пользователей
и отправляет их в сокет для сервиса mqtt_publisher.
Сообщениями можно управлять своими устройствами или получать от них информацию.
"""

import requests
from aiogram import Bot, Dispatcher, executor, types
from src.mqtt_tbot.app import execute_command  # pylint: disable = import-error
from src.mqtt_tbot.config import settings, is_main_settings_correct  # pylint: disable = import-error
from src.mqtt_tbot.event_logger import get_info_logger, get_error_logger  # pylint: disable = import-error

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

bot = Bot(token=settings.bot_token)
dp = Dispatcher(bot)
event_log = get_info_logger("INFO__listener__")
error_log = get_error_logger("ERR__listener__")


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


async def send_response_to_user(chat_id: int, message: str):
    """Отправляет в чат телеграмма сообщение для пользователя"""

    await bot.send_message(chat_id, message)


@dp.message_handler(content_types=['text'])
async def get_message(message: types.Message) -> None:
    """
    Обрабатывается полученное от пользователя сообщение.
    Сообщение должно иметь следующий формат:
    '<имя команды> <текст сообщения>'
    """

    text_message = message.text.lower()
    chat_id = message.chat.id

    answer_for_client = execute_command(text_message, chat_id)

    if answer_for_client:
        await send_response_to_user(chat_id, answer_for_client)


def start_pooling():
    """Бесконечный цикл работы с ботом"""

    try:
        executor.start_polling(dp, skip_updates=True)
    except (requests.exceptions.ReadTimeout,
            requests.exceptions.ConnectTimeout):
        start_pooling()


if __name__ == "__main__":
    if not is_main_settings_correct(settings):
        error_log.error("Ошибка при загрузке настроек")
        raise SystemExit("Работа программы завершена")

    event_log.info("Сервис запущен. Подключен бот %s", settings.bot_name)
    start_pooling()
