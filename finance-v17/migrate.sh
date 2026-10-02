#!/bin/sh
set -eu
if [ ! -f /data/options.json ]; then echo 'options.json is required' >&2; exit 1; fi
APP_TIMEZONE=$(python -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("timezone", "America/Sao_Paulo"))')
: "${APP_TIMEZONE:=America/Sao_Paulo}"
export APP_TIMEZONE FINANCE_V2_DATABASE_PATH=/data/finance_v2.sqlite3
if [ ! -d /data ]; then echo '/data is required' >&2; exit 1; fi
python -m finance_v2 migrate
