#!/bin/bash
# Декодирование настроек

scp ../src/mqtt_tbot/settings/enc_env ../src/mqtt_tbot/settings/.env
sops --hc-vault-transit $VAULT_ADDR/v1/sops/keys/iot  --verbose -d -i ../src/mqtt_tbot/settings/.env