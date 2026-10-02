#!/bin/sh
set -eu
if [ ! -f /data/options.json ]; then echo 'options.json is required' >&2; exit 1; fi
APP_TIMEZONE=$(python -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("timezone", "America/Sao_Paulo"))')
FINANCE_V2_UI_TOKEN=$(python -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("ui_token", ""))')
FINANCE_V2_EXTERNAL_CLIENTS_JSON=$(python -c 'import json; print(json.dumps(json.load(open("/data/options.json", encoding="utf-8")).get("external_clients", {}), separators=(",", ":")))')
: "${APP_TIMEZONE:=America/Sao_Paulo}"
: "${FINANCE_V2_UI_TOKEN:?ui_token option is required}"
export APP_TIMEZONE FINANCE_V2_UI_TOKEN FINANCE_V2_EXTERNAL_CLIENTS_JSON
export FINANCE_V2_DATABASE_PATH=/data/finance_v2.sqlite3
export FINANCE_V2_HOST=0.0.0.0
export FINANCE_V2_PORT=8766
export FINANCE_V2_SCHEDULER_INTERVAL_SECONDS=3600
if [ ! -d /data ]; then echo '/data is required' >&2; exit 1; fi
if [ ! -f "$FINANCE_V2_DATABASE_PATH" ]; then
  python -m finance_v2 migrate
else
  db_version=$(python -c 'import sqlite3; print(sqlite3.connect("/data/finance_v2.sqlite3").execute("PRAGMA user_version").fetchone()[0])')
  if [ "$db_version" != 6 ]; then echo "unsupported database user_version=$db_version; run explicit migration" >&2; exit 1; fi
fi
python -m finance_v2 serve &
api_pid=$!
python -m finance_v2 scheduler &
scheduler_pid=$!
cleanup(){ trap - TERM INT EXIT; kill -TERM "$api_pid" "$scheduler_pid" 2>/dev/null || true; wait "$api_pid" 2>/dev/null || true; wait "$scheduler_pid" 2>/dev/null || true; }
trap cleanup TERM INT EXIT
while :; do
  if ! kill -0 "$api_pid" 2>/dev/null; then echo 'api process exited' >&2; exit 1; fi
  if ! kill -0 "$scheduler_pid" 2>/dev/null; then echo 'scheduler process exited' >&2; exit 1; fi
  sleep 1
done
