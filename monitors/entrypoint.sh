#!/usr/bin/env bash
set -euo pipefail

# El heartbeat_monitor corre como proceso separado en el mismo contenedor
# que el proxy de egress: comparten imagen, pero son senales independientes.
python3 /app/heartbeat_monitor.py &

exec mitmdump --mode regular -p 8080 -s /app/egress_monitor.py \
  --set confdir=/tmp/mitmproxy --set flow_detail=0
