FROM python

WORKDIR /app

#RUN pip install aiogram
#RUN pip install influxdb_client
#RUN pip install requests
#RUN pip install pydantic
#RUN pip install python-dotenv

COPY mqtt_tbot_run.py /app
COPY requirements.txt /app
COPY src /app/src

RUN pip install -r /app/requirements.txt
RUN ["mkdir", "/app/src/mqtt_tbot/logs"]
CMD ["python", "mqtt_tbot_run.py"]