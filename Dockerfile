FROM python

WORKDIR /app

COPY mqtt_tbot_run.py /app
COPY requirements.txt /app
COPY src /app/src

RUN pip install -r /app/requirements.txt
RUN ["mkdir", "/app/src/mqtt_tbot/logs"]
CMD ["python", "mqtt_tbot_run.py"]