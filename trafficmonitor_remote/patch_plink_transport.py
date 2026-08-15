from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
tm = root / 'TrafficMonitor'

# Header: allow the SSH command builder to receive a temporary password-file path.
p = tm / 'RemoteMonitor.h'
s = p.read_text(encoding='utf-8-sig')
old = '    std::wstring BuildClientCommand() const;\n'
new = '    std::wstring BuildClientCommand(const std::wstring& password_file = L"") const;\n'
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise RuntimeError('BuildClientCommand declaration anchor not found')
p.write_text(s, encoding='utf-8-sig')

p = tm / 'RemoteMonitor.cpp'
s = p.read_text(encoding='utf-8-sig')

# Helpers for bundled Plink, a short-lived password file, and diagnostics.
if 'GetBundledPlinkPath()' not in s:
    anchor = '    bool ToUInt64(const std::string& value, unsigned long long& out)\n'
    if anchor not in s:
        raise RuntimeError('ToUInt64 anchor not found')
    helper = r'''    std::wstring GetModuleDirectory()
    {
        wchar_t module[MAX_PATH]{};
        ::GetModuleFileNameW(nullptr, module, MAX_PATH);
        std::wstring path = module;
        const size_t pos = path.find_last_of(L"\\/");
        if (pos != std::wstring::npos)
            path.resize(pos);
        return path;
    }

    bool FileExists(const std::wstring& path)
    {
        const DWORD attr = ::GetFileAttributesW(path.c_str());
        return attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY) == 0;
    }

    std::wstring GetBundledPlinkPath()
    {
        return GetModuleDirectory() + L"\\plink.exe";
    }

    bool CreatePasswordFile(const std::wstring& password, std::wstring& path)
    {
        if (password.empty())
            return false;

        wchar_t temp_dir[MAX_PATH]{};
        const DWORD len = ::GetTempPathW(MAX_PATH, temp_dir);
        if (len == 0 || len >= MAX_PATH)
            return false;

        wchar_t temp_file[MAX_PATH]{};
        if (::GetTempFileNameW(temp_dir, L"tmr", 0, temp_file) == 0)
            return false;

        HANDLE file = ::CreateFileW(temp_file, GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS,
            FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_TEMPORARY, nullptr);
        if (file == INVALID_HANDLE_VALUE)
        {
            ::DeleteFileW(temp_file);
            return false;
        }

        std::string utf8 = WideToUtf8(password);
        utf8 += "\r\n";
        const bool ok = WriteAll(file, utf8.data(), utf8.size());
        ::FlushFileBuffers(file);
        ::CloseHandle(file);
        if (!utf8.empty())
            ::SecureZeroMemory(utf8.data(), utf8.size());

        if (!ok)
        {
            ::DeleteFileW(temp_file);
            return false;
        }

        path = temp_file;
        return true;
    }

    void SecureDeletePasswordFile(const std::wstring& path)
    {
        if (path.empty())
            return;

        HANDLE file = ::CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file != INVALID_HANDLE_VALUE)
        {
            LARGE_INTEGER size{};
            if (::GetFileSizeEx(file, &size) && size.QuadPart > 0 && size.QuadPart < 1024 * 1024)
            {
                std::vector<char> zeros(static_cast<size_t>(size.QuadPart), 0);
                DWORD written{};
                ::SetFilePointer(file, 0, nullptr, FILE_BEGIN);
                ::WriteFile(file, zeros.data(), static_cast<DWORD>(zeros.size()), &written, nullptr);
                ::FlushFileBuffers(file);
            }
            ::CloseHandle(file);
        }
        ::DeleteFileW(path.c_str());
    }

    void AppendRemoteLog(const std::string& line)
    {
        if (line.empty())
            return;

        wchar_t appdata[MAX_PATH]{};
        DWORD len = ::GetEnvironmentVariableW(L"APPDATA", appdata, MAX_PATH);
        if (len == 0 || len >= MAX_PATH)
            return;

        std::wstring dir(appdata, len);
        dir += L"\\TrafficMonitor";
        ::CreateDirectoryW(dir.c_str(), nullptr);
        const std::wstring file_name = dir + L"\\remote_monitor.log";

        HANDLE file = ::CreateFileW(file_name.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
            nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file == INVALID_HANDLE_VALUE)
            return;

        SYSTEMTIME st{};
        ::GetLocalTime(&st);
        char prefix[64]{};
        sprintf_s(prefix, "[%04u-%02u-%02u %02u:%02u:%02u] ", st.wYear, st.wMonth, st.wDay,
            st.wHour, st.wMinute, st.wSecond);
        DWORD written{};
        ::WriteFile(file, prefix, static_cast<DWORD>(strlen(prefix)), &written, nullptr);
        ::WriteFile(file, line.data(), static_cast<DWORD>(line.size()), &written, nullptr);
        const char eol[] = "\r\n";
        ::WriteFile(file, eol, 2, &written, nullptr);
        ::CloseHandle(file);
    }

'''
    s = s.replace(anchor, helper + anchor, 1)

# Replace command builder. Password authentication prefers bundled Plink; key/agent stays on OpenSSH.
start = s.index('std::wstring CRemoteMonitor::BuildClientCommand(')
end = s.index('void CRemoteMonitor::Worker()', start)
replacement = r'''std::wstring CRemoteMonitor::BuildClientCommand(const std::wstring& password_file) const
{
    const std::wstring plink = GetBundledPlinkPath();
    if (!password_file.empty() && FileExists(plink))
    {
        std::wstring command = QuoteArg(plink);
        command += L" -ssh -no-antispoof -P ";
        command += std::to_wstring(m_port);
        if (!m_user.empty())
        {
            command += L" -l ";
            command += QuoteArg(m_user);
        }
        command += L" -pwfile ";
        command += QuoteArg(password_file);
        command += L" ";
        command += QuoteArg(m_host);
        command += L" sh -s";
        return command;
    }

    std::wstring command = QuoteArg(ResolveExecutable(m_transport));
    command += L" -T -o ConnectTimeout=8 -o ConnectionAttempts=1 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new ";
    if (m_password.empty())
        command += L"-o BatchMode=yes ";
    else
        command += L"-o BatchMode=no -o PreferredAuthentications=password,keyboard-interactive -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 ";
    command += L"-p ";
    command += std::to_wstring(m_port);
    if (!m_key_path.empty() && m_password.empty())
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

'''
s = s[:start] + replacement + s[end:]

# Replace streaming session so password login uses Plink and its stdin pipe.
start = s.index('bool CRemoteMonitor::RunStreamingSession()')
end = s.index('void CRemoteMonitor::HandleLine', start)
replacement = r'''bool CRemoteMonitor::RunStreamingSession()
{
    std::wstring password_file;
    const bool plink_available = FileExists(GetBundledPlinkPath());
    const bool use_plink = !m_password.empty() && plink_available && CreatePasswordFile(m_password, password_file);

    SECURITY_ATTRIBUTES sa{};
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;

    HANDLE output_read{}, output_write{};
    HANDLE input_read{}, input_write{};
    if (!::CreatePipe(&output_read, &output_write, &sa, 0))
    {
        SecureDeletePasswordFile(password_file);
        return false;
    }
    if (!::SetHandleInformation(output_read, HANDLE_FLAG_INHERIT, 0))
    {
        ::CloseHandle(output_read);
        ::CloseHandle(output_write);
        SecureDeletePasswordFile(password_file);
        return false;
    }
    if (!::CreatePipe(&input_read, &input_write, &sa, 0))
    {
        ::CloseHandle(output_read);
        ::CloseHandle(output_write);
        SecureDeletePasswordFile(password_file);
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
    std::wstring command = BuildClientCommand(use_plink ? password_file : L"");
    std::vector<wchar_t> cmd(command.begin(), command.end());
    cmd.push_back(L'\0');

    EnvValue old_askpass;
    EnvValue old_askpass_require;
    EnvValue old_display;
    EnvValue old_tm_askpass;
    const bool use_openssh_askpass = !m_password.empty() && !use_plink;
    if (use_openssh_askpass)
    {
        old_askpass = CaptureEnv(L"SSH_ASKPASS");
        old_askpass_require = CaptureEnv(L"SSH_ASKPASS_REQUIRE");
        old_display = CaptureEnv(L"DISPLAY");
        old_tm_askpass = CaptureEnv(L"TM_REMOTE_ASKPASS");
        wchar_t module[MAX_PATH]{};
        ::GetModuleFileNameW(nullptr, module, MAX_PATH);
        ::SetEnvironmentVariableW(L"SSH_ASKPASS", module);
        ::SetEnvironmentVariableW(L"SSH_ASKPASS_REQUIRE", L"force");
        ::SetEnvironmentVariableW(L"DISPLAY", L"TrafficMonitor");
        ::SetEnvironmentVariableW(L"TM_REMOTE_ASKPASS", L"1");
    }

    BOOL created = ::CreateProcessW(nullptr, cmd.data(), nullptr, nullptr, TRUE,
        CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT, nullptr, nullptr, &si, &pi);

    if (use_openssh_askpass)
    {
        RestoreEnv(old_askpass);
        RestoreEnv(old_askpass_require);
        RestoreEnv(old_display);
        RestoreEnv(old_tm_askpass);
    }

    ::CloseHandle(output_write);
    ::CloseHandle(input_read);
    if (!created)
    {
        ::CloseHandle(output_read);
        ::CloseHandle(input_write);
        SecureDeletePasswordFile(password_file);
        AppendRemoteLog("Unable to start SSH transport process.");
        return false;
    }

    {
        std::lock_guard<std::mutex> lock(m_process_mutex);
        m_process = pi.hProcess;
    }
    ::CloseHandle(pi.hThread);

    std::string script = WideToUtf8(BuildRemoteCommand());
    if (use_plink)
    {
        // If this server key has not been cached by PuTTY before, this confirms the first-use prompt.
        // If it is already cached, `y` reaches /bin/sh and is harmless; non-TM output is ignored/logged.
        const char accept_host_key[] = "y\r\n";
        WriteAll(input_write, accept_host_key, sizeof(accept_host_key) - 1);
    }
    if (!script.empty())
        WriteAll(input_write, script.data(), script.size());
    ::CloseHandle(input_write);

    std::string pending;
    char buffer[4096];
    bool got_monitor_frame = false;
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
                    SecureDeletePasswordFile(password_file);
                    password_file.clear();
                }
                HandleLine(line);
            }
            continue;
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
    {
        std::lock_guard<std::mutex> lock(m_process_mutex);
        if (m_process == pi.hProcess)
            m_process = nullptr;
    }
    ::CloseHandle(pi.hProcess);
    SecureDeletePasswordFile(password_file);
    return got_monitor_frame;
}

'''
s = s[:start] + replacement + s[end:]

# Preserve SSH diagnostics instead of silently discarding them.
start = s.index('void CRemoteMonitor::HandleLine(const std::string& line)')
end = s.index('void CRemoteMonitor::ParseFrame', start)
replacement = r'''void CRemoteMonitor::HandleLine(const std::string& line)
{
    if (line.rfind("TM|", 0) != 0)
    {
        AppendRemoteLog(line);
        return;
    }

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

'''
s = s[:start] + replacement + s[end:]

p.write_text(s, encoding='utf-8-sig')
print('Plink password transport applied')
