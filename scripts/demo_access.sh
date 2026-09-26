#!/usr/bin/env bash
# User-service listeners on the Tailscale interface; no sudo or public bind.
set -euo pipefail
cd "$(dirname "$0")/.."
demo_root="$PWD/runtime/demo"
unit="da-vinci-demo.service"
check_owner() {
  existing_exec=$(systemctl --user show "$unit" -p ExecStart --value)
  if [ -n "$existing_exec" ] && [[ "$existing_exec" != *"$PWD/scripts/demo_server.mjs"* ]]; then
    echo "The service name is already owned by another command; preserving it."
    exit 1
  fi
}
case "${1:-status}" in
  up)
    test -s "$demo_root/index.html" || { echo "Build first: .venv/bin/python -m scripts.demo_report"; exit 1; }
    curl --silent --fail --max-time 10 http://127.0.0.1:3215/ -o /dev/null || {
      echo "Start the app first: bash scripts/dev.sh --production"; exit 1;
    }
    check_owner
    if systemctl --user is-active --quiet "$unit"; then
      echo "Demo service already running."
    else
      systemd-run --user --unit="$unit" --collect --working-directory="$PWD" \
        --property=Restart=on-failure --property=RestartSec=3 \
        --property="StandardOutput=append:$demo_root/server.log" \
        --property="StandardError=append:$demo_root/server.log" \
        "$(command -v node)" "$PWD/scripts/demo_server.mjs"
      sleep 1
    fi
    demo_ip=$(tailscale ip -4)
    curl --silent --fail --max-time 10 "http://$demo_ip:8085/" -o /dev/null
    echo "Report: http://computer:8085 (or http://$demo_ip:8085)"
    echo "Workbench: http://computer:8086 (or http://$demo_ip:8086)"
    ;;
  status)
    systemctl --user show "$unit" -p ActiveState -p SubState -p MainPID
    ;;
  down)
    check_owner
    systemctl --user stop "$unit"
    echo "Stopped this demo's listeners. Application and Tailscale settings are unchanged."
    ;;
  *) echo "Usage: bash scripts/demo_access.sh [up|status|down]"; exit 2 ;;
esac
