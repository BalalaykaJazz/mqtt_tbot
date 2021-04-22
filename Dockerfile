FROM python:3.7-alpine3.8

RUN pip install pyTelegramBotAPI

# COPY ./requirements.txt /src/
COPY ./pod_mqtt_tbot /src/

CMD ["python", "/src/mqtt_tbot_run.py"]