#!/bin/bash
# Декодирование настроек

sops -d src/mqtt_tbot/settings/enc_env > src/mqtt_tbot/settings/.env