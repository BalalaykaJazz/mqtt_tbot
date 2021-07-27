FROM python:3.7-alpine3.8

RUN pip install pyTelegramBotAPI
RUN pip install influxdb_client

# COPY ./requirements.txt /src/
COPY ./mqtt_tbot /src/

CMD ["python", "/src/mqtt_tbot_run.py"]