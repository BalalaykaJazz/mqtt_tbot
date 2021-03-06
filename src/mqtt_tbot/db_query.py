"""Модуль для взаимодействия с базой данных"""
from datetime import timedelta
from influxdb_client import InfluxDBClient, rest
from urllib3.exceptions import NewConnectionError, LocationParseError
from .config import settings  # pylint: disable = import-error
from .event_logger import get_info_logger, get_error_logger  # pylint: disable = import-error

event_log = get_info_logger("INFO_db_query")
error_log = get_error_logger("ERR_db_query")


def connect_db() -> InfluxDBClient:
    """Подключение к базе данных"""

    client = InfluxDBClient(url=settings.db_url,
                            token=settings.db_token,
                            org=settings.db_org)
    return client


def get_response_from_db(db_client: InfluxDBClient, query: str) -> list:
    """
    Возвращает результат запроса в виде списка. Если в ходе получения запроса произошла ошибка,
    то возвращается пустой список.
    """

    try:
        answer = db_client.query_api().query(org=settings.db_org,
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

    if not db_name:
        return []

    db_client = connect_db()

    query = f'from(bucket:"{db_name}")\
    |> range(start: -24h)\
    |> filter(fn: (r) => r._measurement == "sys_online")\
    |> group(columns: ["_value"], mode: "by")\
    |> last()'

    devices: list = []

    try:
        answer = get_response_from_db(db_client, query)
    except Exception as err:  # pylint: disable = broad-except
        event_log.info(str(err))
        return devices

    for table in answer:
        for record in table.records:
            timestamp = record.get_time() + timedelta(hours=3)
            last_time = timestamp.strftime("%d.%m.%Y %H:%M:%S")
            device_name = record.values.get("_value")
            devices.append(f"device: {device_name}, last time: {last_time}")

    return devices
