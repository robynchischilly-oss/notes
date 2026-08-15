from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
p = root / 'TrafficMonitor' / 'RemoteMonitor.cpp'
s = p.read_text(encoding='utf-8-sig')

old = r'''  # Network: prefer tailscale0; otherwise fall back to all non-loopback interfaces.
  rx=0; tx=0
  if [ -r /sys/class/net/tailscale0/statistics/rx_bytes ] && [ -r /sys/class/net/tailscale0/statistics/tx_bytes ]; then
    rx=$(cat /sys/class/net/tailscale0/statistics/rx_bytes 2>/dev/null)
    tx=$(cat /sys/class/net/tailscale0/statistics/tx_bytes 2>/dev/null)
  elif [ -r /proc/net/dev ]; then
    set -- $(awk -F'[: ]+' '$2 != "lo" && NF >= 11 {rx += $3; tx += $11} END {print rx+0, tx+0}' /proc/net/dev 2>/dev/null)
    rx=${1:-0}; tx=${2:-0}
  fi
  case "$rx" in ''|*[!0-9]*) rx=0;; esac
  case "$tx" in ''|*[!0-9]*) tx=0;; esac
'''
new = r'''  # Tailscale traffic is intentionally independent from every other interface.
  # Never aggregate eth0/enp*/wlan*/docker*/etc into the remote Tailscale row.
  rx=0; tx=0
  if [ -r /sys/class/net/tailscale0/statistics/rx_bytes ] && [ -r /sys/class/net/tailscale0/statistics/tx_bytes ]; then
    rx=$(cat /sys/class/net/tailscale0/statistics/rx_bytes 2>/dev/null)
    tx=$(cat /sys/class/net/tailscale0/statistics/tx_bytes 2>/dev/null)
  fi
  case "$rx" in ''|*[!0-9]*) rx=0;; esac
  case "$tx" in ''|*[!0-9]*) tx=0;; esac
'''
if old not in s:
    raise RuntimeError('ServerBox network fallback block not found')
s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8-sig')
print('Tailscale-only independent traffic counters applied')
