FROM ubuntu:20.04

RUN apt update; apt upgrade; \
  apt install -y python3 python3-venv; \
  useradd -m -s /bin/bash mqtt;

COPY ./requirements.txt /home/mqtt/
RUN cd ~mqtt; \
  su mqtt -c "python3 -m venv venv"; \
  #su mqtt -c "./venv/bin/pip install wheel"; \
  #su mqtt -c "./venv/bin/pip install chardet \"idna<3\" influxdb \
   #           msgpack requests setuptools
  su mqtt -c "./venv/bin/pip install -r requirements.txt"; \
  mkdir ~mqtt/tsender;

COPY ./pod_tele_sender   /home/mqtt/tsender/
COPY ./scripts/autorun.sh /home/mqtt/tsender/
#COPY ./settings.json      /home/mqtt/mqttPublisher/
RUN  chown -R mqtt\: ~mqtt/tsender

USER mqtt

CMD ["/usr/bin/bash", "/home/mqtt/tsender/autorun.sh"]
