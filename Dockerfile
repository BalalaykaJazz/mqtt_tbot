FROM python:3

RUN apt update; apt upgrade; \
  # apt install -y python3 python3-venv; \
  apt install -y python3-venv; \
  useradd -m -s /bin/bash mqtt;

COPY ./requirements.txt /home/mqtt/
RUN cd ~mqtt; \
  su mqtt -c "python3 -m venv venv"; \
  #su mqtt -c "./venv/bin/pip install wheel"; \
  #su mqtt -c "./venv/bin/pip install chardet \"idna<3\" influxdb \
   #           msgpack requests setuptools
  su mqtt -c "./venv/bin/pip install -r requirements.txt"; \
  mkdir ~mqtt/mqtt_tbot;

COPY ./pod_mqtt_tbot /home/mqtt/mqtt_tbot/
COPY ./scripts/autorun.sh /home/mqtt/mqtt_tbot/
RUN  chown -R mqtt\: ~mqtt/mqtt_tbot

USER mqtt

CMD ["/usr/bin/bash", "/home/mqtt/mqtt_tbot/autorun.sh"]
