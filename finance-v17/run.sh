#!/bin/sh
set -eu
# Keep signal handling non-reentrant, including the fork/$! startup window.
stop_requested=0
startup_pid=
api_pid=
scheduler_pid=
trap 'stop_requested=1' TERM INT

alive(){ kill -0 "$1" 2>/dev/null; }
cleanup(){
  cleanup_status=0
  forced=0
  # Only direct children recorded by this wrapper; no process-group signalling.
  set -- ${startup_pid:+"$startup_pid"} ${api_pid:+"$api_pid"} ${scheduler_pid:+"$scheduler_pid"}
  for child_pid do
    if alive "$child_pid"; then
      if kill -TERM "$child_pid"; then :; elif alive "$child_pid"; then
        echo "lifecycle: TERM failed pid=$child_pid" >&2
        cleanup_status=1
      fi
    fi
  done
  remaining=3
  while [ "$remaining" -gt 0 ]; do
    running=0
    for child_pid do if alive "$child_pid"; then running=1; fi; done
    [ "$running" -eq 1 ] || break
    sleep 1
    remaining=$((remaining - 1))
  done
  for child_pid do
    if alive "$child_pid"; then
      forced=1
      echo "lifecycle: forced KILL pid=$child_pid" >&2
      if kill -KILL "$child_pid"; then :; elif alive "$child_pid"; then
        echo "lifecycle: KILL failed pid=$child_pid" >&2
        cleanup_status=1
      fi
    fi
  done
  remaining=2
  while [ "$remaining" -gt 0 ]; do
    running=0
    for child_pid do if alive "$child_pid"; then running=1; fi; done
    [ "$running" -eq 1 ] || break
    sleep 1
    remaining=$((remaining - 1))
  done
  for child_pid do
    if alive "$child_pid"; then
      echo "lifecycle: child still live pid=$child_pid" >&2
      cleanup_status=125
    else
      # wait is called only after death is observed; never mask its status.
      if wait "$child_pid"; then child_status=0; else child_status=$?; fi
      echo "lifecycle: reaped pid=$child_pid status=$child_status" >&2
      case "$child_status" in
        0|143) : ;; # Successful child, or normal termination by forwarded TERM.
        137) if [ "$forced" -ne 1 ]; then cleanup_status=1; fi ;;
        *) cleanup_status=1 ;;
      esac
    fi
  done
  if [ "$forced" -eq 1 ] && [ "$cleanup_status" -eq 0 ]; then cleanup_status=124; fi
}
finish(){
  final_status=$1
  trap '' TERM INT
  trap - EXIT
  cleanup
  if [ "$final_status" -eq 0 ]; then final_status=$cleanup_status; fi
  echo "lifecycle: stopped status=$final_status" >&2
  exit "$final_status"
}
trap 'finish "$?"' EXIT
check_stop(){
  if [ "$stop_requested" -eq 1 ]; then
    echo 'lifecycle: stop requested' >&2
    finish 0
  fi
}
run_startup(){
  check_stop
  "$@" &
  startup_pid=$!
  check_stop
  if wait "$startup_pid"; then startup_status=0; else startup_status=$?; fi
  check_stop
  startup_pid=
  if [ "$startup_status" -ne 0 ]; then exit "$startup_status"; fi
}
if [ ! -f /data/options.json ]; then echo 'options.json is required' >&2; exit 1; fi
FINANCE_V2_PLUGGY_CONNECTIONS_JSON=$(python -m finance_v2.ha_pluggy_options /data/options.json)
export FINANCE_V2_PLUGGY_CONNECTIONS_JSON
APP_TIMEZONE=$(python -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("timezone", "America/Sao_Paulo"))')
FINANCE_V2_UI_TOKEN=$(python -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("ui_token", ""))')
FINANCE_V2_EXTERNAL_CLIENTS_JSON=$(python -c 'import json; value=json.load(open("/data/options.json", encoding="utf-8")).get("external_clients", "{}"); print(value if isinstance(value, str) else json.dumps(value, separators=(",", ":")))')
FINANCE_V2_OAUTH_CLIENTS_JSON=$(python -c 'import json; value=json.load(open("/data/options.json", encoding="utf-8")).get("oauth_clients", "{}"); print(value if isinstance(value, str) else json.dumps(value, separators=(",", ":")))')
: "${APP_TIMEZONE:=America/Sao_Paulo}"
: "${FINANCE_V2_UI_TOKEN:?ui_token option is required}"
export APP_TIMEZONE FINANCE_V2_UI_TOKEN FINANCE_V2_EXTERNAL_CLIENTS_JSON FINANCE_V2_OAUTH_CLIENTS_JSON
export FINANCE_V2_DATABASE_PATH=/data/finance_v2.sqlite3
export FINANCE_V2_HOST=0.0.0.0
export FINANCE_V2_PORT=8766
export FINANCE_V2_SCHEDULER_INTERVAL_SECONDS=3600
if [ ! -d /data ]; then echo '/data is required' >&2; exit 1; fi
run_startup python -m finance_v2 migrate
run_startup python -c 'from pathlib import Path; from finance_v2.migrations import require_current_schema; require_current_schema(Path("/data/finance_v2.sqlite3"))'
python -m finance_v2 serve &
api_pid=$!
check_stop
python -m finance_v2 scheduler &
scheduler_pid=$!
check_stop
while :; do
  check_stop
  if ! kill -0 "$api_pid" 2>/dev/null; then echo 'api process exited' >&2; exit 1; fi
  if ! kill -0 "$scheduler_pid" 2>/dev/null; then echo 'scheduler process exited' >&2; exit 1; fi
  sleep 1
done
