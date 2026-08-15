from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
p = root / 'TrafficMonitor' / 'RemoteMonitor.cpp'
s = p.read_text(encoding='utf-8-sig')

# Rebuild the remote collector with a real multiline shell script.
# The previous implementation accidentally emitted literal "\\n" between shell
# statements. When piped to `sh -s` those were not line breaks, so no TM frames
# were produced. This follows ServerBox's approach of reading standard Linux
# sources independently and tolerating unavailable metrics.
start = s.index('std::wstring CRemoteMonitor::BuildRemoteCommand() const')
end = s.index('std::wstring CRemoteMonitor::BuildClientCommand(', start)
replacement = r'''std::wstring CRemoteMonitor::BuildRemoteCommand() const
{
    const int candidate = (m_interval_ms + 999) / 1000;
    const int interval_seconds = candidate < 1 ? 1 : candidate;

    std::wstringstream ss;
    ss << LR"TM_SCRIPT(export LC_ALL=C
while :; do
  # CPU: same source used by ServerBox (/proc/stat)
  set -- $(head -n 1 /proc/stat 2>/dev/null)
  u=${2:-0}; n=${3:-0}; sy=${4:-0}; id=${5:-0}; wa=${6:-0}; ir=${7:-0}; si=${8:-0}; st=${9:-0}
  total=$((u+n+sy+id+wa+ir+si+st)); idle=$((id+wa))

  # Network: prefer tailscale0; otherwise fall back to all non-loopback interfaces.
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

  # Uptime: prefer /proc/uptime because it is locale independent.
  up=$(cut -d. -f1 /proc/uptime 2>/dev/null)
  case "$up" in ''|*[!0-9]*) up=0;; esac

  # Temperature: thermal first, hwmon fallback/extension. -1 means unavailable.
  t=-1
  for f in /sys/class/thermal/thermal_zone*/temp /sys/class/hwmon/hwmon*/temp*_input; do
    [ -r "$f" ] || continue
    v=$(cat "$f" 2>/dev/null)
    case "$v" in ''|*[!0-9]*) continue;; esac
    [ "$v" -gt 1000 ] || v=$((v*1000))
    if [ "$v" -gt 0 ] && [ "$v" -lt 150000 ] && [ "$v" -gt "$t" ]; then t=$v; fi
  done

  # Root filesystem usage.
  dp=$(df -Pk / 2>/dev/null | awk 'NR==2 {gsub(/%/,"",$5); print $5; exit}')
  case "$dp" in ''|*[!0-9]*) dp=-1;; esac

  # Memory and core count are collected for diagnostics/future display.
  mt=$(awk '/^MemTotal:/ {print $2; exit}' /proc/meminfo 2>/dev/null)
  ma=$(awk '/^MemAvailable:/ {print $2; exit}' /proc/meminfo 2>/dev/null)
  case "$mt" in ''|*[!0-9]*) mt=0;; esac
  case "$ma" in ''|*[!0-9]*) ma=0;; esac
  c=$(getconf _NPROCESSORS_ONLN 2>/dev/null)
  case "$c" in ''|*[!0-9]*) c=1;; esac

  printf 'TM|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s\n' "$total" "$idle" "$rx" "$tx" "$up" "$t" "$dp" "$mt" "$ma" "$c"
  sleep )TM_SCRIPT" << interval_seconds << LR"TM_SCRIPT(
done
)TM_SCRIPT";
    return ss.str();
}

'''
s = s[:start] + replacement + s[end:]

# Make frame parsing tolerant like ServerBox: a missing optional metric must not
# discard the entire refresh. CPU/net/uptime are parsed independently and the
# last good value is retained where possible.
start = s.index('void CRemoteMonitor::ParseFrame(const std::vector<std::string>& f)')
# ParseFrame is the final function in the current file; replace through EOF.
replacement = r'''void CRemoteMonitor::ParseFrame(const std::vector<std::string>& f)
{
    if (f.size() < 11 || f[0] != "TM")
        return;

    unsigned long long total{}, idle{}, rx{}, tx{}, uptime{}, mt{}, ma{};
    const bool total_ok = ToUInt64(f[1], total);
    const bool idle_ok = ToUInt64(f[2], idle);
    const bool rx_ok = ToUInt64(f[3], rx);
    const bool tx_ok = ToUInt64(f[4], tx);
    const bool uptime_ok = ToUInt64(f[5], uptime);
    const bool mt_ok = ToUInt64(f[8], mt);
    const bool ma_ok = ToUInt64(f[9], ma);

    char* temp_end{};
    const long temp_mc_long = strtol(f[6].c_str(), &temp_end, 10);
    const bool temp_ok = temp_end != f[6].c_str();
    const int temp_mc = temp_ok ? static_cast<int>(temp_mc_long) : -1;

    char* disk_end{};
    const long disk_long = strtol(f[7].c_str(), &disk_end, 10);
    const bool disk_ok = disk_end != f[7].c_str() && disk_long >= 0 && disk_long <= 100;
    const int disk = disk_ok ? static_cast<int>(disk_long) : -1;

    const int parsed_cores = atoi(f[10].c_str());
    const int cores = parsed_cores < 1 ? 1 : parsed_cores;
    const ULONGLONG now = ::GetTickCount64();

    int cpu = -1;
    if (total_ok && idle_ok && m_prev_cpu_total > 0 && total >= m_prev_cpu_total && idle >= m_prev_cpu_idle)
    {
        const unsigned long long dt = total - m_prev_cpu_total;
        const unsigned long long di = idle - m_prev_cpu_idle;
        if (dt > 0)
        {
            const unsigned long long safe_idle = di < dt ? di : dt;
            const int calculated = static_cast<int>((dt - safe_idle) * 100ULL / dt);
            cpu = ClampInt(calculated, 0, 100);
        }
    }

    double down = -1.0;
    double up = -1.0;
    if (rx_ok && tx_ok && m_prev_tick > 0 && now > m_prev_tick)
    {
        const double seconds = static_cast<double>(now - m_prev_tick) / 1000.0;
        if (seconds > 0.0)
        {
            if (rx >= m_prev_rx)
                down = static_cast<double>(rx - m_prev_rx) / seconds;
            if (tx >= m_prev_tx)
                up = static_cast<double>(tx - m_prev_tx) / seconds;
        }
    }

    if (total_ok && idle_ok)
    {
        m_prev_cpu_total = total;
        m_prev_cpu_idle = idle;
    }
    if (rx_ok && tx_ok)
    {
        m_prev_rx = rx;
        m_prev_tx = tx;
        m_prev_tick = now;
    }

    std::lock_guard<std::mutex> lock(m_data_mutex);
    m_snapshot.has_data = true;
    m_snapshot.online = true;
    if (up >= 0.0)
        m_snapshot.upload_bps = up;
    if (down >= 0.0)
        m_snapshot.download_bps = down;
    if (cpu >= 0)
        m_snapshot.cpu_usage = cpu;
    if (temp_ok)
        m_snapshot.temperature_c = temp_mc >= 0 ? (temp_mc + 500) / 1000 : -1;
    if (disk_ok)
        m_snapshot.disk_usage = disk;
    if (uptime_ok)
        m_snapshot.uptime_seconds = uptime;
    if (mt_ok)
        m_snapshot.mem_total_kb = mt;
    if (ma_ok)
        m_snapshot.mem_available_kb = ma;
    m_snapshot.cpu_cores = cores;
    m_snapshot.ssh_user = m_user.c_str();
}
'''
s = s[:start] + replacement
p.write_text(s, encoding='utf-8-sig')
print('ServerBox-style status collector applied')
