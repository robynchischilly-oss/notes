#include "stdafx.h"
#include "RemoteMonitor.h"
#include <sstream>

namespace
{
    enum RemoteControlId
    {
        IDC_RM_ENABLE = 2001,
        IDC_RM_HOST,
        IDC_RM_USER,
        IDC_RM_PORT,
        IDC_RM_KEY,
        IDC_RM_INTERVAL,
        IDC_RM_SHOW_UPLOAD,
        IDC_RM_SHOW_DOWNLOAD,
        IDC_RM_SHOW_UPTIME,
        IDC_RM_SHOW_TEMP,
        IDC_RM_SHOW_DISK,
        IDC_RM_SHOW_CPU
    };

    struct RemoteSettingsState
    {
        RemoteMonitorConfig config;
        bool accepted{};
    };

    std::wstring ReadIniString(const std::wstring& file, const wchar_t* key, const wchar_t* def = L"")
    {
        wchar_t buf[2048]{};
        ::GetPrivateProfileStringW(L"RemoteMonitor", key, def, buf, static_cast<DWORD>(_countof(buf)), file.c_str());
        return buf;
    }

    int ClampInt(int value, int low, int high)
    {
        if (value < low)
            return low;
        if (value > high)
            return high;
        return value;
    }

    std::wstring QuoteArg(const std::wstring& value)
    {
        if (value.find_first_of(L" \t\"") == std::wstring::npos)
            return value;
        std::wstring out = L"\"";
        for (wchar_t ch : value)
        {
            if (ch == L'\"')
                out += L"\\\"";
            else
                out += ch;
        }
        out += L"\"";
        return out;
    }

    bool ToUInt64(const std::string& value, unsigned long long& out)
    {
        char* end{};
        const unsigned long long v = _strtoui64(value.c_str(), &end, 10);
        if (end == value.c_str())
            return false;
        out = v;
        return true;
    }

    std::wstring GetControlText(HWND wnd, int id)
    {
        HWND control = ::GetDlgItem(wnd, id);
        if (control == nullptr)
            return {};
        const int length = ::GetWindowTextLengthW(control);
        std::wstring text(static_cast<size_t>(length) + 1, L'\0');
        ::GetWindowTextW(control, text.data(), length + 1);
        text.resize(wcslen(text.c_str()));
        return text;
    }

    void SetControlText(HWND wnd, int id, const std::wstring& value)
    {
        if (HWND control = ::GetDlgItem(wnd, id))
            ::SetWindowTextW(control, value.c_str());
    }

    bool GetCheck(HWND wnd, int id)
    {
        return ::SendDlgItemMessageW(wnd, id, BM_GETCHECK, 0, 0) == BST_CHECKED;
    }

    void SetCheck(HWND wnd, int id, bool checked)
    {
        ::SendDlgItemMessageW(wnd, id, BM_SETCHECK, checked ? BST_CHECKED : BST_UNCHECKED, 0);
    }

    HWND AddStatic(HWND parent, const wchar_t* text, int x, int y, int w, int h)
    {
        return ::CreateWindowExW(0, L"STATIC", text, WS_CHILD | WS_VISIBLE,
            x, y, w, h, parent, nullptr, AfxGetInstanceHandle(), nullptr);
    }

    HWND AddEdit(HWND parent, int id, int x, int y, int w, int h)
    {
        return ::CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | ES_AUTOHSCROLL,
            x, y, w, h, parent, reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)), AfxGetInstanceHandle(), nullptr);
    }

    HWND AddCheck(HWND parent, int id, const wchar_t* text, int x, int y, int w, int h)
    {
        return ::CreateWindowExW(0, L"BUTTON", text,
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_AUTOCHECKBOX,
            x, y, w, h, parent, reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)), AfxGetInstanceHandle(), nullptr);
    }

    BOOL CALLBACK SetChildFontProc(HWND child, LPARAM font)
    {
        ::SendMessageW(child, WM_SETFONT, static_cast<WPARAM>(font), TRUE);
        return TRUE;
    }

    LRESULT CALLBACK RemoteSettingsWndProc(HWND wnd, UINT message, WPARAM wParam, LPARAM lParam)
    {
        RemoteSettingsState* state = reinterpret_cast<RemoteSettingsState*>(::GetWindowLongPtrW(wnd, GWLP_USERDATA));

        if (message == WM_NCCREATE)
        {
            auto create = reinterpret_cast<CREATESTRUCTW*>(lParam);
            state = static_cast<RemoteSettingsState*>(create->lpCreateParams);
            ::SetWindowLongPtrW(wnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(state));
        }

        switch (message)
        {
        case WM_CREATE:
        {
            AddCheck(wnd, IDC_RM_ENABLE, L"Enable Tailscale / SSH server monitor", 16, 14, 330, 22);

            AddStatic(wnd, L"Host / Tailscale IP", 16, 50, 115, 20);
            AddEdit(wnd, IDC_RM_HOST, 138, 47, 320, 24);
            AddStatic(wnd, L"SSH user", 16, 82, 115, 20);
            AddEdit(wnd, IDC_RM_USER, 138, 79, 200, 24);
            AddStatic(wnd, L"Port", 348, 82, 42, 20);
            AddEdit(wnd, IDC_RM_PORT, 392, 79, 66, 24);
            AddStatic(wnd, L"Private key", 16, 114, 115, 20);
            AddEdit(wnd, IDC_RM_KEY, 138, 111, 320, 24);
            AddStatic(wnd, L"Refresh (ms)", 16, 146, 115, 20);
            AddEdit(wnd, IDC_RM_INTERVAL, 138, 143, 100, 24);

            AddStatic(wnd, L"Remote rows", 16, 186, 115, 20);
            AddCheck(wnd, IDC_RM_SHOW_UPLOAD, L"Upload", 138, 181, 92, 24);
            AddCheck(wnd, IDC_RM_SHOW_DOWNLOAD, L"Download", 235, 181, 100, 24);
            AddCheck(wnd, IDC_RM_SHOW_UPTIME, L"Uptime", 340, 181, 90, 24);
            AddCheck(wnd, IDC_RM_SHOW_TEMP, L"Temperature", 138, 211, 110, 24);
            AddCheck(wnd, IDC_RM_SHOW_DISK, L"Disk", 255, 211, 80, 24);
            AddCheck(wnd, IDC_RM_SHOW_CPU, L"CPU", 340, 211, 80, 24);

            AddStatic(wnd, L"Authentication: Windows OpenSSH private key or ssh-agent.", 16, 254, 442, 20);
            AddStatic(wnd, L"The Linux server does not need a monitoring agent.", 16, 276, 442, 20);

            ::CreateWindowExW(0, L"BUTTON", L"Save", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON,
                286, 316, 82, 28, wnd, reinterpret_cast<HMENU>(static_cast<INT_PTR>(IDOK)), AfxGetInstanceHandle(), nullptr);
            ::CreateWindowExW(0, L"BUTTON", L"Cancel", WS_CHILD | WS_VISIBLE | WS_TABSTOP,
                376, 316, 82, 28, wnd, reinterpret_cast<HMENU>(static_cast<INT_PTR>(IDCANCEL)), AfxGetInstanceHandle(), nullptr);

            if (state != nullptr)
            {
                SetCheck(wnd, IDC_RM_ENABLE, state->config.enabled);
                SetControlText(wnd, IDC_RM_HOST, state->config.host);
                SetControlText(wnd, IDC_RM_USER, state->config.user);
                SetControlText(wnd, IDC_RM_PORT, std::to_wstring(state->config.port));
                SetControlText(wnd, IDC_RM_KEY, state->config.key_path);
                SetControlText(wnd, IDC_RM_INTERVAL, std::to_wstring(state->config.interval_ms));
                SetCheck(wnd, IDC_RM_SHOW_UPLOAD, state->config.show_upload);
                SetCheck(wnd, IDC_RM_SHOW_DOWNLOAD, state->config.show_download);
                SetCheck(wnd, IDC_RM_SHOW_UPTIME, state->config.show_uptime);
                SetCheck(wnd, IDC_RM_SHOW_TEMP, state->config.show_temperature);
                SetCheck(wnd, IDC_RM_SHOW_DISK, state->config.show_disk);
                SetCheck(wnd, IDC_RM_SHOW_CPU, state->config.show_cpu);
            }

            HFONT font = static_cast<HFONT>(::GetStockObject(DEFAULT_GUI_FONT));
            ::EnumChildWindows(wnd, SetChildFontProc, reinterpret_cast<LPARAM>(font));
            return 0;
        }
        case WM_COMMAND:
            if (LOWORD(wParam) == IDOK && state != nullptr)
            {
                state->config.enabled = GetCheck(wnd, IDC_RM_ENABLE);
                state->config.host = GetControlText(wnd, IDC_RM_HOST);
                state->config.user = GetControlText(wnd, IDC_RM_USER);
                state->config.key_path = GetControlText(wnd, IDC_RM_KEY);
                state->config.port = ClampInt(_wtoi(GetControlText(wnd, IDC_RM_PORT).c_str()), 1, 65535);
                state->config.interval_ms = ClampInt(_wtoi(GetControlText(wnd, IDC_RM_INTERVAL).c_str()), 1000, 60000);
                state->config.show_upload = GetCheck(wnd, IDC_RM_SHOW_UPLOAD);
                state->config.show_download = GetCheck(wnd, IDC_RM_SHOW_DOWNLOAD);
                state->config.show_uptime = GetCheck(wnd, IDC_RM_SHOW_UPTIME);
                state->config.show_temperature = GetCheck(wnd, IDC_RM_SHOW_TEMP);
                state->config.show_disk = GetCheck(wnd, IDC_RM_SHOW_DISK);
                state->config.show_cpu = GetCheck(wnd, IDC_RM_SHOW_CPU);
                state->accepted = true;
                ::DestroyWindow(wnd);
                return 0;
            }
            if (LOWORD(wParam) == IDCANCEL)
            {
                ::DestroyWindow(wnd);
                return 0;
            }
            break;
        case WM_CLOSE:
            ::DestroyWindow(wnd);
            return 0;
        }

        return ::DefWindowProcW(wnd, message, wParam, lParam);
    }
}

CRemoteMonitor& CRemoteMonitor::Instance()
{
    static CRemoteMonitor instance;
    return instance;
}

CRemoteMonitor::~CRemoteMonitor()
{
    Stop();
}

void CRemoteMonitor::Start()
{
    if (m_started.exchange(true))
        return;

    LoadConfig();
    if (!m_enabled || m_host.empty())
        return;

    m_stop = false;
    m_thread = std::thread(&CRemoteMonitor::Worker, this);
}

void CRemoteMonitor::Stop()
{
    if (!m_started.exchange(false))
        return;

    m_stop = true;
    {
        std::lock_guard<std::mutex> lock(m_process_mutex);
        if (m_process != nullptr)
            ::TerminateProcess(m_process, 0);
    }

    if (m_thread.joinable())
        m_thread.join();
}

int CRemoteMonitor::ExtraRows() const
{
    return m_enabled && !m_host.empty() ? 2 : 0;
}

RemoteMonitorSnapshot CRemoteMonitor::GetSnapshot() const
{
    std::lock_guard<std::mutex> lock(m_data_mutex);
    return m_snapshot;
}

RemoteMonitorConfig CRemoteMonitor::GetConfig() const
{
    RemoteMonitorConfig config;
    config.enabled = m_enabled;
    config.host = m_host;
    config.user = m_user;
    config.key_path = m_key_path;
    config.port = m_port;
    config.interval_ms = m_interval_ms;
    config.show_upload = m_show_upload;
    config.show_download = m_show_download;
    config.show_uptime = m_show_uptime;
    config.show_temperature = m_show_temperature;
    config.show_disk = m_show_disk;
    config.show_cpu = m_show_cpu;
    return config;
}

void CRemoteMonitor::ApplyConfig(const RemoteMonitorConfig& config)
{
    Stop();

    m_enabled = config.enabled;
    m_host = config.host;
    m_user = config.user;
    m_key_path = config.key_path;
    m_port = ClampInt(config.port, 1, 65535);
    m_interval_ms = ClampInt(config.interval_ms, 1000, 60000);
    m_show_upload = config.show_upload;
    m_show_download = config.show_download;
    m_show_uptime = config.show_uptime;
    m_show_temperature = config.show_temperature;
    m_show_disk = config.show_disk;
    m_show_cpu = config.show_cpu;

    m_prev_cpu_total = 0;
    m_prev_cpu_idle = 0;
    m_prev_rx = 0;
    m_prev_tx = 0;
    m_prev_tick = 0;
    {
        std::lock_guard<std::mutex> lock(m_data_mutex);
        m_snapshot = RemoteMonitorSnapshot{};
    }

    SaveConfig();
    Start();
}

bool CRemoteMonitor::ShowSettings(HWND parent)
{
    static const wchar_t* class_name = L"TrafficMonitorRemoteSettingsWindow";
    HINSTANCE instance = AfxGetInstanceHandle();

    WNDCLASSEXW wc{};
    wc.cbSize = sizeof(wc);
    if (!::GetClassInfoExW(instance, class_name, &wc))
    {
        wc.cbSize = sizeof(wc);
        wc.lpfnWndProc = RemoteSettingsWndProc;
        wc.hInstance = instance;
        wc.hCursor = ::LoadCursorW(nullptr, IDC_ARROW);
        wc.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
        wc.lpszClassName = class_name;
        if (!::RegisterClassExW(&wc))
            return false;
    }

    RemoteSettingsState state;
    state.config = GetConfig();

    RECT window_rect{ 0, 0, 480, 370 };
    ::AdjustWindowRectEx(&window_rect, WS_CAPTION | WS_SYSMENU | WS_POPUP, FALSE, WS_EX_DLGMODALFRAME | WS_EX_CONTROLPARENT);
    int width = window_rect.right - window_rect.left;
    int height = window_rect.bottom - window_rect.top;

    RECT owner_rect{};
    if (parent != nullptr)
        ::GetWindowRect(parent, &owner_rect);
    else
        ::SystemParametersInfoW(SPI_GETWORKAREA, 0, &owner_rect, 0);
    const int x = owner_rect.left + ((owner_rect.right - owner_rect.left) - width) / 2;
    const int y = owner_rect.top + ((owner_rect.bottom - owner_rect.top) - height) / 2;

    HWND wnd = ::CreateWindowExW(WS_EX_DLGMODALFRAME | WS_EX_CONTROLPARENT, class_name,
        L"TrafficMonitor - Tailscale / SSH Server",
        WS_CAPTION | WS_SYSMENU | WS_POPUP,
        x, y, width, height, parent, nullptr, instance, &state);
    if (wnd == nullptr)
        return false;

    if (parent != nullptr)
        ::EnableWindow(parent, FALSE);
    ::ShowWindow(wnd, SW_SHOW);
    ::UpdateWindow(wnd);

    MSG msg{};
    bool quit = false;
    while (::IsWindow(wnd))
    {
        const BOOL result = ::GetMessageW(&msg, nullptr, 0, 0);
        if (result <= 0)
        {
            quit = result == 0;
            break;
        }
        if (!::IsDialogMessageW(wnd, &msg))
        {
            ::TranslateMessage(&msg);
            ::DispatchMessageW(&msg);
        }
    }

    if (parent != nullptr)
    {
        ::EnableWindow(parent, TRUE);
        ::SetActiveWindow(parent);
    }
    if (quit)
        ::PostQuitMessage(static_cast<int>(msg.wParam));

    if (state.accepted)
    {
        ApplyConfig(state.config);
        return true;
    }
    return false;
}

CString CRemoteMonitor::FormatSpeed(double bytes_per_second) const
{
    CString text;
    if (bytes_per_second < 1024.0)
        text.Format(L"%.0fB/s", bytes_per_second);
    else if (bytes_per_second < 1024.0 * 1024.0)
        text.Format(L"%.1fK/s", bytes_per_second / 1024.0);
    else if (bytes_per_second < 1024.0 * 1024.0 * 1024.0)
        text.Format(L"%.1fM/s", bytes_per_second / (1024.0 * 1024.0));
    else
        text.Format(L"%.1fG/s", bytes_per_second / (1024.0 * 1024.0 * 1024.0));
    return text;
}

CString CRemoteMonitor::FormatUptime(unsigned long long seconds) const
{
    const unsigned long long days = seconds / 86400;
    const unsigned long long hours = (seconds % 86400) / 3600;
    const unsigned long long mins = (seconds % 3600) / 60;
    CString text;
    if (days > 0)
        text.Format(L"%llud%lluh", days, hours);
    else if (hours > 0)
        text.Format(L"%lluh%llum", hours, mins);
    else
        text.Format(L"%llum", mins);
    return text;
}

std::wstring CRemoteMonitor::GetConfigPath() const
{
    wchar_t appdata[MAX_PATH]{};
    DWORD len = ::GetEnvironmentVariableW(L"APPDATA", appdata, MAX_PATH);
    std::wstring dir;
    if (len > 0 && len < MAX_PATH)
        dir.assign(appdata, len);
    else
    {
        wchar_t module[MAX_PATH]{};
        ::GetModuleFileNameW(nullptr, module, MAX_PATH);
        dir = module;
        const size_t pos = dir.find_last_of(L"\\/");
        if (pos != std::wstring::npos)
            dir.resize(pos);
    }

    dir += L"\\TrafficMonitor";
    ::CreateDirectoryW(dir.c_str(), nullptr);
    return dir + L"\\remote_monitor.ini";
}

void CRemoteMonitor::LoadConfig()
{
    const std::wstring file = GetConfigPath();
    if (::GetFileAttributesW(file.c_str()) == INVALID_FILE_ATTRIBUTES)
    {
        ::WritePrivateProfileStringW(L"RemoteMonitor", L"Enabled", L"0", file.c_str());
        ::WritePrivateProfileStringW(L"RemoteMonitor", L"Host", L"", file.c_str());
        ::WritePrivateProfileStringW(L"RemoteMonitor", L"User", L"", file.c_str());
        ::WritePrivateProfileStringW(L"RemoteMonitor", L"Port", L"22", file.c_str());
        ::WritePrivateProfileStringW(L"RemoteMonitor", L"KeyPath", L"", file.c_str());
        ::WritePrivateProfileStringW(L"RemoteMonitor", L"IntervalMs", L"1000", file.c_str());
        ::WritePrivateProfileStringW(L"RemoteMonitor", L"ShowUpload", L"1", file.c_str());
        ::WritePrivateProfileStringW(L"RemoteMonitor", L"ShowDownload", L"1", file.c_str());
        ::WritePrivateProfileStringW(L"RemoteMonitor", L"ShowUptime", L"1", file.c_str());
        ::WritePrivateProfileStringW(L"RemoteMonitor", L"ShowTemperature", L"1", file.c_str());
        ::WritePrivateProfileStringW(L"RemoteMonitor", L"ShowDisk", L"1", file.c_str());
        ::WritePrivateProfileStringW(L"RemoteMonitor", L"ShowCpu", L"1", file.c_str());
    }

    m_enabled = ::GetPrivateProfileIntW(L"RemoteMonitor", L"Enabled", 0, file.c_str()) != 0;
    m_host = ReadIniString(file, L"Host");
    m_user = ReadIniString(file, L"User");
    m_key_path = ReadIniString(file, L"KeyPath");
    m_port = ClampInt(static_cast<int>(::GetPrivateProfileIntW(L"RemoteMonitor", L"Port", 22, file.c_str())), 1, 65535);
    m_interval_ms = ClampInt(static_cast<int>(::GetPrivateProfileIntW(L"RemoteMonitor", L"IntervalMs", 1000, file.c_str())), 1000, 60000);
    m_show_upload = ::GetPrivateProfileIntW(L"RemoteMonitor", L"ShowUpload", 1, file.c_str()) != 0;
    m_show_download = ::GetPrivateProfileIntW(L"RemoteMonitor", L"ShowDownload", 1, file.c_str()) != 0;
    m_show_uptime = ::GetPrivateProfileIntW(L"RemoteMonitor", L"ShowUptime", 1, file.c_str()) != 0;
    m_show_temperature = ::GetPrivateProfileIntW(L"RemoteMonitor", L"ShowTemperature", 1, file.c_str()) != 0;
    m_show_disk = ::GetPrivateProfileIntW(L"RemoteMonitor", L"ShowDisk", 1, file.c_str()) != 0;
    m_show_cpu = ::GetPrivateProfileIntW(L"RemoteMonitor", L"ShowCpu", 1, file.c_str()) != 0;
}

void CRemoteMonitor::SaveConfig() const
{
    const std::wstring file = GetConfigPath();
    ::WritePrivateProfileStringW(L"RemoteMonitor", L"Enabled", m_enabled ? L"1" : L"0", file.c_str());
    ::WritePrivateProfileStringW(L"RemoteMonitor", L"Host", m_host.c_str(), file.c_str());
    ::WritePrivateProfileStringW(L"RemoteMonitor", L"User", m_user.c_str(), file.c_str());
    ::WritePrivateProfileStringW(L"RemoteMonitor", L"Port", std::to_wstring(m_port).c_str(), file.c_str());
    ::WritePrivateProfileStringW(L"RemoteMonitor", L"KeyPath", m_key_path.c_str(), file.c_str());
    ::WritePrivateProfileStringW(L"RemoteMonitor", L"IntervalMs", std::to_wstring(m_interval_ms).c_str(), file.c_str());
    ::WritePrivateProfileStringW(L"RemoteMonitor", L"ShowUpload", m_show_upload ? L"1" : L"0", file.c_str());
    ::WritePrivateProfileStringW(L"RemoteMonitor", L"ShowDownload", m_show_download ? L"1" : L"0", file.c_str());
    ::WritePrivateProfileStringW(L"RemoteMonitor", L"ShowUptime", m_show_uptime ? L"1" : L"0", file.c_str());
    ::WritePrivateProfileStringW(L"RemoteMonitor", L"ShowTemperature", m_show_temperature ? L"1" : L"0", file.c_str());
    ::WritePrivateProfileStringW(L"RemoteMonitor", L"ShowDisk", m_show_disk ? L"1" : L"0", file.c_str());
    ::WritePrivateProfileStringW(L"RemoteMonitor", L"ShowCpu", m_show_cpu ? L"1" : L"0", file.c_str());
}

std::wstring CRemoteMonitor::ResolveExecutable(const std::wstring&) const
{
    wchar_t path[MAX_PATH]{};
    if (::SearchPathW(nullptr, L"ssh.exe", nullptr, MAX_PATH, path, nullptr) > 0)
        return path;
    return L"ssh.exe";
}

std::wstring CRemoteMonitor::BuildRemoteCommand() const
{
    const int candidate = (m_interval_ms + 999) / 1000;
    const int interval_seconds = candidate < 1 ? 1 : candidate;
    std::wstringstream ss;
    ss << L"sh -c 'while :; do "
       << L"read _ u n s i w q sq st g gn < /proc/stat; total=$((u+n+s+i+w+q+sq+st)); idle=$((i+w)); "
       << L"if [ -r /sys/class/net/tailscale0/statistics/rx_bytes ]; then rx=$(cat /sys/class/net/tailscale0/statistics/rx_bytes); tx=$(cat /sys/class/net/tailscale0/statistics/tx_bytes); "
       << L"else rx=0; tx=0; for f in /sys/class/net/*/statistics/rx_bytes; do case $f in */lo/*) continue;; esac; v=$(cat $f 2>/dev/null || echo 0); rx=$((rx+v)); done; for f in /sys/class/net/*/statistics/tx_bytes; do case $f in */lo/*) continue;; esac; v=$(cat $f 2>/dev/null || echo 0); tx=$((tx+v)); done; fi; "
       << L"up=$(cut -d. -f1 /proc/uptime); t=-1; for f in /sys/class/thermal/thermal_zone*/temp /sys/class/hwmon/hwmon*/temp*_input; do [ -r $f ] || continue; v=$(cat $f 2>/dev/null); case $v in ''|*[!0-9]*) continue;; esac; [ $v -gt 1000 ] || v=$((v*1000)); if [ $v -lt 150000 ] && [ $v -gt $t ]; then t=$v; fi; done; "
       << L"set -- $(df -Pk / | tail -1); dp=${5%\\%}; mt=$(awk '/^MemTotal:/{print $2}' /proc/meminfo); ma=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo); c=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1); "
       << L"printf \"TM|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s\\n\" $total $idle $rx $tx $up $t $dp $mt $ma $c; sleep " << interval_seconds << L"; done'";
    return ss.str();
}

std::wstring CRemoteMonitor::BuildClientCommand() const
{
    std::wstring command = QuoteArg(ResolveExecutable(m_transport));
    command += L" -T -o ConnectTimeout=8 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new -o BatchMode=yes -p ";
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
    command += L" ";
    command += BuildRemoteCommand();
    return command;
}

void CRemoteMonitor::Worker()
{
    while (!m_stop)
    {
        RunStreamingSession();
        {
            std::lock_guard<std::mutex> lock(m_data_mutex);
            m_snapshot.online = false;
        }
        for (int i = 0; i < 30 && !m_stop; ++i)
            ::Sleep(100);
    }
}

bool CRemoteMonitor::RunStreamingSession()
{
    SECURITY_ATTRIBUTES sa{};
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;

    HANDLE read_pipe{}, write_pipe{};
    if (!::CreatePipe(&read_pipe, &write_pipe, &sa, 0))
        return false;
    ::SetHandleInformation(read_pipe, HANDLE_FLAG_INHERIT, 0);

    STARTUPINFOW si{};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdOutput = write_pipe;
    si.hStdError = write_pipe;
    si.hStdInput = ::GetStdHandle(STD_INPUT_HANDLE);

    PROCESS_INFORMATION pi{};
    std::wstring command = BuildClientCommand();
    std::vector<wchar_t> cmd(command.begin(), command.end());
    cmd.push_back(L'\0');

    BOOL created = ::CreateProcessW(nullptr, cmd.data(), nullptr, nullptr, TRUE,
        CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT, nullptr, nullptr, &si, &pi);
    ::CloseHandle(write_pipe);
    if (!created)
    {
        ::CloseHandle(read_pipe);
        return false;
    }

    {
        std::lock_guard<std::mutex> lock(m_process_mutex);
        m_process = pi.hProcess;
    }
    ::CloseHandle(pi.hThread);

    std::string pending;
    char buffer[4096];
    DWORD got{};
    while (!m_stop && ::ReadFile(read_pipe, buffer, sizeof(buffer), &got, nullptr) && got > 0)
    {
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
    }

    ::CloseHandle(read_pipe);
    ::WaitForSingleObject(pi.hProcess, 1000);
    {
        std::lock_guard<std::mutex> lock(m_process_mutex);
        if (m_process == pi.hProcess)
            m_process = nullptr;
    }
    ::CloseHandle(pi.hProcess);
    return true;
}

void CRemoteMonitor::HandleLine(const std::string& line)
{
    if (line.rfind("TM|", 0) != 0)
        return;

    std::vector<std::string> fields;
    size_t start{};
    while (start <= line.size())
    {
        const size_t end = line.find('|', start);
        fields.push_back(line.substr(start, end == std::string::npos ? std::string::npos : end - start));
        if (end == std::string::npos)
            break;
        start = end + 1;
    }
    ParseFrame(fields);
}

void CRemoteMonitor::ParseFrame(const std::vector<std::string>& f)
{
    if (f.size() < 11 || f[0] != "TM")
        return;

    unsigned long long total{}, idle{}, rx{}, tx{}, uptime{}, mt{}, ma{};
    if (!ToUInt64(f[1], total) || !ToUInt64(f[2], idle) || !ToUInt64(f[3], rx) || !ToUInt64(f[4], tx) || !ToUInt64(f[5], uptime))
        return;
    ToUInt64(f[8], mt);
    ToUInt64(f[9], ma);

    const int temp_mc = atoi(f[6].c_str());
    const int disk = ClampInt(atoi(f[7].c_str()), 0, 100);
    const int parsed_cores = atoi(f[10].c_str());
    const int cores = parsed_cores < 1 ? 1 : parsed_cores;
    const ULONGLONG now = ::GetTickCount64();

    int cpu{};
    if (m_prev_cpu_total > 0 && total >= m_prev_cpu_total && idle >= m_prev_cpu_idle)
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

    double down{};
    double up{};
    if (m_prev_tick > 0 && now > m_prev_tick)
    {
        const double seconds = static_cast<double>(now - m_prev_tick) / 1000.0;
        if (rx >= m_prev_rx)
            down = static_cast<double>(rx - m_prev_rx) / seconds;
        if (tx >= m_prev_tx)
            up = static_cast<double>(tx - m_prev_tx) / seconds;
    }

    m_prev_cpu_total = total;
    m_prev_cpu_idle = idle;
    m_prev_rx = rx;
    m_prev_tx = tx;
    m_prev_tick = now;

    std::lock_guard<std::mutex> lock(m_data_mutex);
    m_snapshot.has_data = true;
    m_snapshot.online = true;
    m_snapshot.upload_bps = up;
    m_snapshot.download_bps = down;
    m_snapshot.cpu_usage = cpu;
    m_snapshot.temperature_c = temp_mc >= 0 ? (temp_mc + 500) / 1000 : -1;
    m_snapshot.disk_usage = disk;
    m_snapshot.uptime_seconds = uptime;
    m_snapshot.mem_total_kb = mt;
    m_snapshot.mem_available_kb = ma;
    m_snapshot.cpu_cores = cores;
    m_snapshot.ssh_user = m_user.c_str();
}
