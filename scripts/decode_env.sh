#!/bin/bash
# Декодирование настроек

sops --hc-vault-transit $VAULT_ADDR/v1/sops/keys/iot  --verbose -d -i ../src/mqtt_tbot/settings/.env