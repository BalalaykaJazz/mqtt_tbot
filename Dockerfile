FROM python

WORKDIR /app

COPY requirements.txt /app
COPY src /app/src

RUN pip install -r /app/requirements.txt
RUN ["mkdir", "/app/src/mqtt_tbot/logs"]
CMD ["python", "/app/src/mqtt_tbot_run.py"]