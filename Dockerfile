FROM python:3.8

RUN pip install pyTelegramBotAPI

# COPY ./requirements.txt /tmp/
COPY ./pod_mqtt_tbot /tmp/

CMD ["python", "/tmp/mqtt_tbot_run.py"]