#!/usr/bin/env bash
# Keep the private workbench alive independently of an interactive agent session.
set -euo pipefail
cd "$(dirname "$0")/.."
unit="da-vinci-workbench.service"
node_bin=$(command -v node)
node_major=$("$node_bin" -p 'process.versions.node.split(".")[0]')
if (( node_major < 22 )); then echo "Use Node 22+ before starting the workbench service."; exit 1; fi
existing_exec=$(systemctl --user show "$unit" -p ExecStart --value 2>/dev/null || true)
if [[ -n "$existing_exec" && "$existing_exec" != *"$PWD/scripts/dev.sh"* ]]; then
  echo "Service name belongs to another command; preserving it."
  exit 1
fi
case "${1:-status}" in
  up)
    mkdir -p runtime/demo
    if systemctl --user is-active --quiet "$unit"; then
      echo "Workbench service already running."
    else
      if curl --silent --fail --max-time 3 http://127.0.0.1:3215/ -o /dev/null; then
        echo "A workbench already owns port 3215; stop that process before starting the service."
        exit 1
      fi
      systemd-run --user --unit="$unit" --collect --working-directory="$PWD" \
        --property=Restart=on-failure --property=RestartSec=3 --property=TimeoutStopSec=15 \
        --property=StartLimitBurst=3 --property=StartLimitIntervalSec=60 \
        --setenv="PATH=$(dirname "$node_bin"):/usr/local/bin:/usr/bin:/bin" \
        --property="StandardOutput=append:$PWD/runtime/demo/workbench.log" \
        --property="StandardError=append:$PWD/runtime/demo/workbench.log" \
        /bin/bash "$PWD/scripts/dev.sh" --production
    fi
    for attempt in {1..20}; do
      if curl --silent --fail --max-time 2 http://127.0.0.1:3215/ -o /dev/null; then
        echo "Workbench ready on localhost:3215."
        exit 0
      fi
      sleep 1
    done
    echo "Workbench did not become ready; inspect runtime/demo/workbench.log."
    exit 1
    ;;
  down) systemctl --user stop "$unit" ;;
  status) systemctl --user show "$unit" -p ActiveState -p SubState -p MainPID ;;
  *) echo "Usage: bash scripts/app_service.sh [up|down|status]"; exit 2 ;;
esac
