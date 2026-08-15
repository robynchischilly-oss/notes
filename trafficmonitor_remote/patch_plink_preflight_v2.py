from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
p = root / 'TrafficMonitor' / 'RemoteMonitor.cpp'
s = p.read_text(encoding='utf-8-sig')

# Build marker in the settings window so we can prove which binary is actually running.
s = s.replace(
    'L"TrafficMonitor - Tailscale / SSH Server",',
    'L"TrafficMonitor - Tailscale / SSH Server [1.86.4]",',
    1,
)

# Always create a diagnostic log as soon as remote monitoring starts.
start = s.index('void CRemoteMonitor::Start()')
end = s.index('void CRemoteMonitor::Stop()', start)
s = s[:start] + r'''void CRemoteMonitor::Start()
{
    LoadConfig();

    AppendRemoteLog("=== TrafficMonitor remote monitor 1.86.4 start ===");
    AppendRemoteLog(std::string("config: enabled=") + (m_enabled ? "1" : "0")
        + " host=" + WideToUtf8(m_host)
        + " user=" + WideToUtf8(m_user)
        + " port=" + std::to_string(m_port)
        + " interval_ms=" + std::to_string(m_interval_ms)
        + " password=" + (m_password.empty() ? "no" : "yes")
        + " key=" + (m_key_path.empty() ? "no" : "yes"));

    if (!m_enabled || m_host.empty())
    {
        AppendRemoteLog("worker not started: remote monitor disabled or host empty");
        m_started = false;
        return;
    }

    bool expected = false;
    if (!m_started.compare_exchange_strong(expected, true))
    {
        AppendRemoteLog("worker already running");
        return;
    }

    m_stop = false;
    try
    {
        m_thread = std::thread(&CRemoteMonitor::Worker, this);
        AppendRemoteLog("worker thread started");
    }
    catch (...)
    {
        AppendRemoteLog("worker thread creation failed");
        m_started = false;
        throw;
    }
}

''' + s[end:]

# Replace the password/Plink transport with a two-stage connection:
#  1) preflight authentication + first-use host-key confirmation, using a harmless echo command;
#  2) once preflight succeeds, run the collector with -batch and -m script-file.
# This separates PuTTY's interactive host-key prompt from the monitoring script stdin.
start = s.index('bool CRemoteMonitor::RunStreamingSession()')
end = s.index('void CRemoteMonitor::HandleLine', start)
replacement = r'''bool CRemoteMonitor::RunStreamingSession()
{
    AppendRemoteLog("session: begin");

    const std::wstring plink = GetBundledPlinkPath();
    const bool password_auth = !m_password.empty();

    if (password_auth)
    {
        if (!FileExists(plink))
        {
            AppendRemoteLog("session: bundled plink.exe not found at " + WideToUtf8(plink));
            return false;
        }

        std::wstring password_file;
        if (!CreatePasswordFile(m_password, password_file))
        {
            AppendRemoteLog("session: unable to create temporary password file");
            return false;
        }

        AppendRemoteLog("session: password auth via bundled Plink");

        // Preflight. Plink is intentionally NOT in -batch mode here so an unknown
        // host key can be confirmed. The only remote command is echo, so an early
        // 'y' written to stdin is harmless if the key was already cached.
        SECURITY_ATTRIBUTES sa{};
        sa.nLength = sizeof(sa);
        sa.bInheritHandle = TRUE;

        HANDLE probe_out_read{}, probe_out_write{};
        HANDLE probe_in_read{}, probe_in_write{};
        if (!::CreatePipe(&probe_out_read, &probe_out_write, &sa, 0)
            || !::SetHandleInformation(probe_out_read, HANDLE_FLAG_INHERIT, 0)
            || !::CreatePipe(&probe_in_read, &probe_in_write, &sa, 0)
            || !::SetHandleInformation(probe_in_write, HANDLE_FLAG_INHERIT, 0))
        {
            if (probe_out_read) ::CloseHandle(probe_out_read);
            if (probe_out_write) ::CloseHandle(probe_out_write);
            if (probe_in_read) ::CloseHandle(probe_in_read);
            if (probe_in_write) ::CloseHandle(probe_in_write);
            SecureDeletePasswordFile(password_file);
            AppendRemoteLog("preflight: pipe creation failed");
            return false;
        }

        STARTUPINFOW psi{};
        psi.cb = sizeof(psi);
        psi.dwFlags = STARTF_USESTDHANDLES;
        psi.hStdOutput = probe_out_write;
        psi.hStdError = probe_out_write;
        psi.hStdInput = probe_in_read;

        std::wstring probe_command = QuoteArg(plink);
        probe_command += L" -v -ssh -no-antispoof -P ";
        probe_command += std::to_wstring(m_port);
        if (!m_user.empty())
        {
            probe_command += L" -l ";
            probe_command += QuoteArg(m_user);
        }
        probe_command += L" -pwfile ";
        probe_command += QuoteArg(password_file);
        probe_command += L" ";
        probe_command += QuoteArg(m_host);
        probe_command += L" echo __TM_SSH_OK__";

        std::vector<wchar_t> probe_cmd(probe_command.begin(), probe_command.end());
        probe_cmd.push_back(L'\0');
        PROCESS_INFORMATION ppi{};
        const BOOL probe_created = ::CreateProcessW(nullptr, probe_cmd.data(), nullptr, nullptr, TRUE,
            CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT, nullptr, nullptr, &psi, &ppi);
        ::CloseHandle(probe_out_write);
        ::CloseHandle(probe_in_read);

        if (!probe_created)
        {
            ::CloseHandle(probe_out_read);
            ::CloseHandle(probe_in_write);
            SecureDeletePasswordFile(password_file);
            AppendRemoteLog("preflight: CreateProcess failed, win32=" + std::to_string(::GetLastError()));
            return false;
        }

        {
            std::lock_guard<std::mutex> lock(m_process_mutex);
            m_process = ppi.hProcess;
        }
        ::CloseHandle(ppi.hThread);

        const char trust_answer[] = "y\r\n";
        WriteAll(probe_in_write, trust_answer, sizeof(trust_answer) - 1);
        ::CloseHandle(probe_in_write);

        bool auth_ok = false;
        std::string probe_pending;
        char probe_buf[4096];
        const ULONGLONG probe_deadline = ::GetTickCount64() + 12000;

        while (!m_stop && ::GetTickCount64() < probe_deadline)
        {
            DWORD available{};
            if (!::PeekNamedPipe(probe_out_read, nullptr, 0, nullptr, &available, nullptr))
                break;
            if (available > 0)
            {
                DWORD got{};
                const DWORD to_read = (std::min)(available, static_cast<DWORD>(sizeof(probe_buf)));
                if (!::ReadFile(probe_out_read, probe_buf, to_read, &got, nullptr) || got == 0)
                    break;
                probe_pending.append(probe_buf, got);
                if (probe_pending.find("__TM_SSH_OK__") != std::string::npos)
                    auth_ok = true;

                size_t pos{};
                while ((pos = probe_pending.find('\n')) != std::string::npos)
                {
                    std::string line = probe_pending.substr(0, pos);
                    probe_pending.erase(0, pos + 1);
                    if (!line.empty() && line.back() == '\r')
                        line.pop_back();
                    if (!line.empty())
                        AppendRemoteLog("preflight: " + line);
                }
                if (auth_ok)
                    break;
                continue;
            }
            if (::WaitForSingleObject(ppi.hProcess, 0) == WAIT_OBJECT_0)
                break;
            ::Sleep(50);
        }

        if (!probe_pending.empty())
            AppendRemoteLog("preflight: " + probe_pending);

        if (::WaitForSingleObject(ppi.hProcess, 0) != WAIT_OBJECT_0)
            ::TerminateProcess(ppi.hProcess, auth_ok ? 0 : 1);
        ::WaitForSingleObject(ppi.hProcess, 1000);
        DWORD probe_exit{};
        ::GetExitCodeProcess(ppi.hProcess, &probe_exit);
        ::CloseHandle(probe_out_read);
        {
            std::lock_guard<std::mutex> lock(m_process_mutex);
            if (m_process == ppi.hProcess)
                m_process = nullptr;
        }
        ::CloseHandle(ppi.hProcess);

        if (!auth_ok)
        {
            AppendRemoteLog("preflight: FAILED, exit=" + std::to_string(probe_exit));
            SecureDeletePasswordFile(password_file);
            return false;
        }
        AppendRemoteLog("preflight: SSH authentication OK");

        // Write the Linux collector to a temporary local file. Plink -m sends
        // this as the remote command, so the collector no longer shares stdin
        // with any authentication or host-key interaction.
        wchar_t temp_dir[MAX_PATH]{};
        wchar_t script_path_buf[MAX_PATH]{};
        if (::GetTempPathW(MAX_PATH, temp_dir) == 0
            || ::GetTempFileNameW(temp_dir, L"tms", 0, script_path_buf) == 0)
        {
            AppendRemoteLog("collector: unable to create temporary script path");
            SecureDeletePasswordFile(password_file);
            return false;
        }
        std::wstring script_file = script_path_buf;
        HANDLE script_handle = ::CreateFileW(script_file.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS,
            FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_TEMPORARY, nullptr);
        if (script_handle == INVALID_HANDLE_VALUE)
        {
            AppendRemoteLog("collector: unable to open temporary script file");
            ::DeleteFileW(script_file.c_str());
            SecureDeletePasswordFile(password_file);
            return false;
        }
        std::string script_utf8 = WideToUtf8(BuildRemoteCommand());
        const bool script_written = WriteAll(script_handle, script_utf8.data(), script_utf8.size());
        ::FlushFileBuffers(script_handle);
        ::CloseHandle(script_handle);
        if (!script_written)
        {
            AppendRemoteLog("collector: writing temporary script failed");
            ::DeleteFileW(script_file.c_str());
            SecureDeletePasswordFile(password_file);
            return false;
        }

        HANDLE output_read{}, output_write{};
        if (!::CreatePipe(&output_read, &output_write, &sa, 0)
            || !::SetHandleInformation(output_read, HANDLE_FLAG_INHERIT, 0))
        {
            if (output_read) ::CloseHandle(output_read);
            if (output_write) ::CloseHandle(output_write);
            ::DeleteFileW(script_file.c_str());
            SecureDeletePasswordFile(password_file);
            AppendRemoteLog("collector: output pipe creation failed");
            return false;
        }

        HANDLE nul_input = ::CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
            nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);

        STARTUPINFOW si{};
        si.cb = sizeof(si);
        si.dwFlags = STARTF_USESTDHANDLES;
        si.hStdOutput = output_write;
        si.hStdError = output_write;
        si.hStdInput = nul_input == INVALID_HANDLE_VALUE ? ::GetStdHandle(STD_INPUT_HANDLE) : nul_input;

        std::wstring command = QuoteArg(plink);
        command += L" -batch -ssh -T -no-antispoof -P ";
        command += std::to_wstring(m_port);
        if (!m_user.empty())
        {
            command += L" -l ";
            command += QuoteArg(m_user);
        }
        command += L" -pwfile ";
        command += QuoteArg(password_file);
        command += L" -m ";
        command += QuoteArg(script_file);
        command += L" ";
        command += QuoteArg(m_host);

        std::vector<wchar_t> cmd(command.begin(), command.end());
        cmd.push_back(L'\0');
        PROCESS_INFORMATION pi{};
        const BOOL created = ::CreateProcessW(nullptr, cmd.data(), nullptr, nullptr, TRUE,
            CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT, nullptr, nullptr, &si, &pi);
        ::CloseHandle(output_write);
        if (nul_input != INVALID_HANDLE_VALUE)
            ::CloseHandle(nul_input);

        if (!created)
        {
            ::CloseHandle(output_read);
            ::DeleteFileW(script_file.c_str());
            SecureDeletePasswordFile(password_file);
            AppendRemoteLog("collector: CreateProcess failed, win32=" + std::to_string(::GetLastError()));
            return false;
        }

        {
            std::lock_guard<std::mutex> lock(m_process_mutex);
            m_process = pi.hProcess;
        }
        ::CloseHandle(pi.hThread);
        AppendRemoteLog("collector: process started with -batch -m");

        std::string pending;
        char buffer[4096];
        bool got_monitor_frame = false;
        const ULONGLONG first_frame_deadline = ::GetTickCount64() + 15000;

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
                    if (line.rfind("TM|", 0) == 0 && !got_monitor_frame)
                    {
                        got_monitor_frame = true;
                        AppendRemoteLog("collector: first TM frame received");
                        SecureDeletePasswordFile(password_file);
                        password_file.clear();
                        ::DeleteFileW(script_file.c_str());
                        script_file.clear();
                    }
                    HandleLine(line);
                }
                continue;
            }

            if (!got_monitor_frame && ::GetTickCount64() >= first_frame_deadline)
            {
                AppendRemoteLog("collector: timeout waiting for first TM frame");
                ::TerminateProcess(pi.hProcess, 2);
                break;
            }
            if (::WaitForSingleObject(pi.hProcess, 0) == WAIT_OBJECT_0)
                break;
            ::Sleep(50);
        }

        if (!pending.empty())
            HandleLine(pending);

        if (m_stop && ::WaitForSingleObject(pi.hProcess, 0) != WAIT_OBJECT_0)
            ::TerminateProcess(pi.hProcess, 0);
        ::CloseHandle(output_read);
        ::WaitForSingleObject(pi.hProcess, 1000);
        DWORD exit_code{};
        ::GetExitCodeProcess(pi.hProcess, &exit_code);
        {
            std::lock_guard<std::mutex> lock(m_process_mutex);
            if (m_process == pi.hProcess)
                m_process = nullptr;
        }
        ::CloseHandle(pi.hProcess);
        SecureDeletePasswordFile(password_file);
        if (!script_file.empty())
            ::DeleteFileW(script_file.c_str());
        AppendRemoteLog("collector: process ended, exit=" + std::to_string(exit_code)
            + " frame=" + (got_monitor_frame ? "yes" : "no"));
        return got_monitor_frame;
    }

    // Key / ssh-agent path: keep Windows OpenSSH but add deterministic logging
    // and a first-frame timeout so it cannot fail silently forever.
    SECURITY_ATTRIBUTES sa{};
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;

    HANDLE output_read{}, output_write{};
    HANDLE input_read{}, input_write{};
    if (!::CreatePipe(&output_read, &output_write, &sa, 0)
        || !::SetHandleInformation(output_read, HANDLE_FLAG_INHERIT, 0)
        || !::CreatePipe(&input_read, &input_write, &sa, 0)
        || !::SetHandleInformation(input_write, HANDLE_FLAG_INHERIT, 0))
    {
        if (output_read) ::CloseHandle(output_read);
        if (output_write) ::CloseHandle(output_write);
        if (input_read) ::CloseHandle(input_read);
        if (input_write) ::CloseHandle(input_write);
        AppendRemoteLog("openssh: pipe creation failed");
        return false;
    }

    STARTUPINFOW si{};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdOutput = output_write;
    si.hStdError = output_write;
    si.hStdInput = input_read;

    std::wstring command = BuildClientCommand(L"");
    std::vector<wchar_t> cmd(command.begin(), command.end());
    cmd.push_back(L'\0');
    PROCESS_INFORMATION pi{};
    const BOOL created = ::CreateProcessW(nullptr, cmd.data(), nullptr, nullptr, TRUE,
        CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT, nullptr, nullptr, &si, &pi);
    ::CloseHandle(output_write);
    ::CloseHandle(input_read);
    if (!created)
    {
        ::CloseHandle(output_read);
        ::CloseHandle(input_write);
        AppendRemoteLog("openssh: CreateProcess failed, win32=" + std::to_string(::GetLastError()));
        return false;
    }

    {
        std::lock_guard<std::mutex> lock(m_process_mutex);
        m_process = pi.hProcess;
    }
    ::CloseHandle(pi.hThread);
    AppendRemoteLog("openssh: process started");

    const std::string script = WideToUtf8(BuildRemoteCommand());
    if (!script.empty())
        WriteAll(input_write, script.data(), script.size());
    ::CloseHandle(input_write);

    std::string pending;
    char buffer[4096];
    bool got_monitor_frame = false;
    const ULONGLONG first_frame_deadline = ::GetTickCount64() + 15000;
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
                if (line.rfind("TM|", 0) == 0 && !got_monitor_frame)
                {
                    got_monitor_frame = true;
                    AppendRemoteLog("openssh: first TM frame received");
                }
                HandleLine(line);
            }
            continue;
        }
        if (!got_monitor_frame && ::GetTickCount64() >= first_frame_deadline)
        {
            AppendRemoteLog("openssh: timeout waiting for first TM frame");
            ::TerminateProcess(pi.hProcess, 2);
            break;
        }
        if (::WaitForSingleObject(pi.hProcess, 0) == WAIT_OBJECT_0)
            break;
        ::Sleep(50);
    }

    if (!pending.empty())
        HandleLine(pending);
    if (m_stop && ::WaitForSingleObject(pi.hProcess, 0) != WAIT_OBJECT_0)
        ::TerminateProcess(pi.hProcess, 0);
    ::CloseHandle(output_read);
    ::WaitForSingleObject(pi.hProcess, 1000);
    DWORD exit_code{};
    ::GetExitCodeProcess(pi.hProcess, &exit_code);
    {
        std::lock_guard<std::mutex> lock(m_process_mutex);
        if (m_process == pi.hProcess)
            m_process = nullptr;
    }
    ::CloseHandle(pi.hProcess);
    AppendRemoteLog("openssh: process ended, exit=" + std::to_string(exit_code)
        + " frame=" + (got_monitor_frame ? "yes" : "no"));
    return got_monitor_frame;
}

'''
s = s[:start] + replacement + s[end:]

p.write_text(s, encoding='utf-8-sig')
print('Plink preflight v2 + mandatory diagnostics applied')
