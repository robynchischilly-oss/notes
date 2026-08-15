from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
p = root / 'TrafficMonitor' / 'RemoteMonitor.cpp'
s = p.read_text(encoding='utf-8-sig')

if '::PeekNamedPipe(output_read' in s:
    print('RemoteMonitor runtime fixes already present')
    raise SystemExit(0)

s = s.replace('#include <sstream>\n', '#include <sstream>\n#include <algorithm>\n#include <vector>\n', 1)

anchor = '    bool ToUInt64(const std::string& value, unsigned long long& out)\n'
helper = r'''    std::string WideToUtf8(const std::wstring& value)
    {
        if (value.empty())
            return {};
        const int required = ::WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
        if (required <= 0)
            return {};
        std::string result(static_cast<size_t>(required), '\0');
        ::WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), result.data(), required, nullptr, nullptr);
        return result;
    }

    bool WriteAll(HANDLE handle, const void* data, size_t size)
    {
        const BYTE* current = static_cast<const BYTE*>(data);
        while (size > 0)
        {
            DWORD written{};
            const DWORD chunk = static_cast<DWORD>((std::min)(size, static_cast<size_t>(64 * 1024)));
            if (!::WriteFile(handle, current, chunk, &written, nullptr) || written == 0)
                return false;
            current += written;
            size -= written;
        }
        return true;
    }

'''
if anchor not in s:
    raise RuntimeError('RemoteMonitor helper anchor not found')
s = s.replace(anchor, helper + anchor, 1)

start = s.index('void CRemoteMonitor::Start()')
end = s.index('int CRemoteMonitor::ExtraRows() const', start)
s = s[:start] + r'''void CRemoteMonitor::Start()
{
    LoadConfig();
    if (!m_enabled || m_host.empty())
    {
        m_started = false;
        return;
    }

    bool expected = false;
    if (!m_started.compare_exchange_strong(expected, true))
        return;

    m_stop = false;
    try
    {
        m_thread = std::thread(&CRemoteMonitor::Worker, this);
    }
    catch (...)
    {
        m_started = false;
        throw;
    }
}

void CRemoteMonitor::Stop()
{
    m_stop = true;
    {
        std::lock_guard<std::mutex> lock(m_process_mutex);
        if (m_process != nullptr)
            ::TerminateProcess(m_process, 0);
    }

    if (m_thread.joinable())
    {
        HANDLE thread_handle = static_cast<HANDLE>(m_thread.native_handle());
        if (thread_handle != nullptr)
            ::CancelSynchronousIo(thread_handle);
        m_thread.join();
    }
    m_started = false;
}

''' + s[end:]

start = s.index('std::wstring CRemoteMonitor::BuildRemoteCommand() const')
end = s.index('void CRemoteMonitor::Worker()', start)
s = s[:start] + r'''std::wstring CRemoteMonitor::BuildRemoteCommand() const
{
    const int candidate = (m_interval_ms + 999) / 1000;
    const int interval_seconds = candidate < 1 ? 1 : candidate;
    std::wstringstream ss;
    ss << L"export LC_ALL=C\\n"
       << L"while :; do\\n"
       << L"  set -- $(head -n 1 /proc/stat 2>/dev/null)\\n"
       << L"  u=${2:-0}; n=${3:-0}; sy=${4:-0}; id=${5:-0}; wa=${6:-0}; ir=${7:-0}; si=${8:-0}; st=${9:-0}\\n"
       << L"  total=$((u+n+sy+id+wa+ir+si+st)); idle=$((id+wa))\\n"
       << L"  if [ -r /sys/class/net/tailscale0/statistics/rx_bytes ] && [ -r /sys/class/net/tailscale0/statistics/tx_bytes ]; then\\n"
       << L"    rx=$(cat /sys/class/net/tailscale0/statistics/rx_bytes 2>/dev/null); tx=$(cat /sys/class/net/tailscale0/statistics/tx_bytes 2>/dev/null)\\n"
       << L"  else\\n"
       << L"    rx=0; tx=0\\n"
       << L"    for f in /sys/class/net/*/statistics/rx_bytes; do [ -r \"$f\" ] || continue; case \"$f\" in */lo/*) continue;; esac; v=$(cat \"$f\" 2>/dev/null); case \"$v\" in ''|*[!0-9]*) v=0;; esac; rx=$((rx+v)); done\\n"
       << L"    for f in /sys/class/net/*/statistics/tx_bytes; do [ -r \"$f\" ] || continue; case \"$f\" in */lo/*) continue;; esac; v=$(cat \"$f\" 2>/dev/null); case \"$v\" in ''|*[!0-9]*) v=0;; esac; tx=$((tx+v)); done\\n"
       << L"  fi\\n"
       << L"  case \"$rx\" in ''|*[!0-9]*) rx=0;; esac; case \"$tx\" in ''|*[!0-9]*) tx=0;; esac\\n"
       << L"  up=$(cut -d. -f1 /proc/uptime 2>/dev/null); case \"$up\" in ''|*[!0-9]*) up=0;; esac\\n"
       << L"  t=-1\\n"
       << L"  for f in /sys/class/thermal/thermal_zone*/temp /sys/class/hwmon/hwmon*/temp*_input; do\\n"
       << L"    [ -r \"$f\" ] || continue; v=$(cat \"$f\" 2>/dev/null); case \"$v\" in ''|*[!0-9]*) continue;; esac\\n"
       << L"    [ \"$v\" -gt 1000 ] || v=$((v*1000)); if [ \"$v\" -gt 0 ] && [ \"$v\" -lt 150000 ] && [ \"$v\" -gt \"$t\" ]; then t=$v; fi\\n"
       << L"  done\\n"
       << L"  dp=$(df -Pk / 2>/dev/null | awk 'NR==2 {gsub(/%/,\"\",$5); print $5; exit}'); case \"$dp\" in ''|*[!0-9]*) dp=0;; esac\\n"
       << L"  mt=$(awk '/^MemTotal:/ {print $2; exit}' /proc/meminfo 2>/dev/null); case \"$mt\" in ''|*[!0-9]*) mt=0;; esac\\n"
       << L"  ma=$(awk '/^MemAvailable:/ {print $2; exit}' /proc/meminfo 2>/dev/null); case \"$ma\" in ''|*[!0-9]*) ma=0;; esac\\n"
       << L"  c=$(getconf _NPROCESSORS_ONLN 2>/dev/null); case \"$c\" in ''|*[!0-9]*) c=1;; esac\\n"
       << L"  printf 'TM|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s\\n' \"$total\" \"$idle\" \"$rx\" \"$tx\" \"$up\" \"$t\" \"$dp\" \"$mt\" \"$ma\" \"$c\"\\n"
       << L"  sleep " << interval_seconds << L"\\n"
       << L"done\\n";
    return ss.str();
}

std::wstring CRemoteMonitor::BuildClientCommand() const
{
    std::wstring command = QuoteArg(ResolveExecutable(m_transport));
    command += L" -T -o ConnectTimeout=8 -o ConnectionAttempts=1 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new -o BatchMode=yes -p ";
    command += std::to_wstring(m_port);
    if (!m_key_path.empty())
    {
        command += L" -i ";
        command += QuoteArg(m_key_path);
        command += L" -o IdentitiesOnly=yes";
    }
    command += L" ";
    if (!m_user.empty())
        command += m_user + L"@";
    command += m_host;
    command += L" sh -s";
    return command;
}

''' + s[end:]

start = s.index('bool CRemoteMonitor::RunStreamingSession()')
end = s.index('void CRemoteMonitor::HandleLine', start)
s = s[:start] + r'''bool CRemoteMonitor::RunStreamingSession()
{
    SECURITY_ATTRIBUTES sa{};
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;

    HANDLE output_read{}, output_write{};
    HANDLE input_read{}, input_write{};
    if (!::CreatePipe(&output_read, &output_write, &sa, 0))
        return false;
    if (!::SetHandleInformation(output_read, HANDLE_FLAG_INHERIT, 0))
    {
        ::CloseHandle(output_read);
        ::CloseHandle(output_write);
        return false;
    }
    if (!::CreatePipe(&input_read, &input_write, &sa, 0))
    {
        ::CloseHandle(output_read);
        ::CloseHandle(output_write);
        return false;
    }
    ::SetHandleInformation(input_write, HANDLE_FLAG_INHERIT, 0);

    STARTUPINFOW si{};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdOutput = output_write;
    si.hStdError = output_write;
    si.hStdInput = input_read;

    PROCESS_INFORMATION pi{};
    std::wstring command = BuildClientCommand();
    std::vector<wchar_t> cmd(command.begin(), command.end());
    cmd.push_back(L'\0');

    BOOL created = ::CreateProcessW(nullptr, cmd.data(), nullptr, nullptr, TRUE,
        CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT, nullptr, nullptr, &si, &pi);
    ::CloseHandle(output_write);
    ::CloseHandle(input_read);

    if (!created)
    {
        ::CloseHandle(output_read);
        ::CloseHandle(input_write);
        return false;
    }

    {
        std::lock_guard<std::mutex> lock(m_process_mutex);
        m_process = pi.hProcess;
    }
    ::CloseHandle(pi.hThread);

    const std::string script = WideToUtf8(BuildRemoteCommand());
    if (!script.empty())
        WriteAll(input_write, script.data(), script.size());
    ::CloseHandle(input_write);

    std::string pending;
    char buffer[4096];
    while (!m_stop)
    {
        DWORD available{};
        if (!::PeekNamedPipe(output_read, nullptr, 0, nullptr, &available, nullptr))
            break;
        if (available > 0)
        {
            DWORD got{};
            const DWORD to_read = (std::min)(available, static_cast<DWORD>(sizeof(buffer)));
            if (!::ReadFile(output_read, buffer, to_read, &got, nullptr) || got == 0)
                break;
            pending.append(buffer, got);
            size_t pos{};
            while ((pos = pending.find('\n')) != std::string::npos)
            {
                std::string line = pending.substr(0, pos);
                pending.erase(0, pos + 1);
                if (!line.empty() && line.back() == '\r')
                    line.pop_back();
                HandleLine(line);
            }
            continue;
        }
        if (::WaitForSingleObject(pi.hProcess, 0) == WAIT_OBJECT_0)
            break;
        ::Sleep(50);
    }

    if (m_stop && ::WaitForSingleObject(pi.hProcess, 0) != WAIT_OBJECT_0)
        ::TerminateProcess(pi.hProcess, 0);
    ::CloseHandle(output_read);
    ::WaitForSingleObject(pi.hProcess, 1000);
    {
        std::lock_guard<std::mutex> lock(m_process_mutex);
        if (m_process == pi.hProcess)
            m_process = nullptr;
    }
    ::CloseHandle(pi.hProcess);
    return true;
}

''' + s[end:]

p.write_text(s, encoding='utf-8-sig')
print('RemoteMonitor runtime fixes applied')
