from pathlib import Path
import sys
root = Path(sys.argv[1]).resolve()
tm = root / 'TrafficMonitor'

# Header
p=tm/'RemoteMonitor.h'; s=p.read_text(encoding='utf-8-sig')
s=s.replace('    std::wstring key_path;\n', '    std::wstring key_path;\n    std::wstring password;\n',1)
s=s.replace('    bool ShowSettings(HWND parent);\n', '    bool ShowSettings(HWND parent);\n    static bool HandleAskPassIfNeeded();\n',1)
s=s.replace('    std::wstring m_key_path;\n', '    std::wstring m_key_path;\n    std::wstring m_password;\n',1)
p.write_text(s,encoding='utf-8-sig')

# Remote cpp
p=tm/'RemoteMonitor.cpp'; s=p.read_text(encoding='utf-8-sig')
s=s.replace('#include <vector>\n', '#include <vector>\n#include <wincrypt.h>\n#pragma comment(lib, "Crypt32.lib")\n',1)
s=s.replace('''        IDC_RM_KEY,\n        IDC_RM_INTERVAL,''','''        IDC_RM_KEY,\n        IDC_RM_PASSWORD,\n        IDC_RM_INTERVAL,''',1)
anchor='    std::wstring GetControlText(HWND wnd, int id)\n'
helper=r'''    std::wstring BytesToHex(const BYTE* data, DWORD size)
    {
        static const wchar_t hex[] = L"0123456789ABCDEF";
        std::wstring result;
        result.reserve(static_cast<size_t>(size) * 2);
        for (DWORD i = 0; i < size; ++i)
        {
            result.push_back(hex[(data[i] >> 4) & 0x0F]);
            result.push_back(hex[data[i] & 0x0F]);
        }
        return result;
    }

    bool HexToBytes(const std::wstring& text, std::vector<BYTE>& bytes)
    {
        if (text.size() % 2 != 0)
            return false;
        auto value = [](wchar_t ch) -> int {
            if (ch >= L'0' && ch <= L'9') return ch - L'0';
            if (ch >= L'a' && ch <= L'f') return ch - L'a' + 10;
            if (ch >= L'A' && ch <= L'F') return ch - L'A' + 10;
            return -1;
        };
        bytes.clear();
        bytes.reserve(text.size() / 2);
        for (size_t i = 0; i < text.size(); i += 2)
        {
            int hi = value(text[i]);
            int lo = value(text[i + 1]);
            if (hi < 0 || lo < 0)
                return false;
            bytes.push_back(static_cast<BYTE>((hi << 4) | lo));
        }
        return true;
    }

    std::wstring ProtectPassword(const std::wstring& password)
    {
        if (password.empty())
            return {};
        DATA_BLOB in{};
        in.pbData = reinterpret_cast<BYTE*>(const_cast<wchar_t*>(password.data()));
        in.cbData = static_cast<DWORD>(password.size() * sizeof(wchar_t));
        DATA_BLOB out{};
        if (!::CryptProtectData(&in, L"TrafficMonitor SSH password", nullptr, nullptr, nullptr,
            CRYPTPROTECT_UI_FORBIDDEN, &out))
            return {};
        std::wstring encrypted = BytesToHex(out.pbData, out.cbData);
        ::LocalFree(out.pbData);
        return encrypted;
    }

    std::wstring UnprotectPassword(const std::wstring& encrypted)
    {
        std::vector<BYTE> bytes;
        if (encrypted.empty() || !HexToBytes(encrypted, bytes))
            return {};
        DATA_BLOB in{};
        in.pbData = bytes.data();
        in.cbData = static_cast<DWORD>(bytes.size());
        DATA_BLOB out{};
        if (!::CryptUnprotectData(&in, nullptr, nullptr, nullptr, nullptr,
            CRYPTPROTECT_UI_FORBIDDEN, &out))
            return {};
        std::wstring password;
        if (out.cbData > 0 && out.cbData % sizeof(wchar_t) == 0)
            password.assign(reinterpret_cast<wchar_t*>(out.pbData), out.cbData / sizeof(wchar_t));
        ::SecureZeroMemory(out.pbData, out.cbData);
        ::LocalFree(out.pbData);
        return password;
    }

    struct EnvValue
    {
        std::wstring name;
        std::wstring value;
        bool existed{};
    };

    EnvValue CaptureEnv(const wchar_t* name)
    {
        EnvValue env;
        env.name = name;
        DWORD needed = ::GetEnvironmentVariableW(name, nullptr, 0);
        if (needed > 0)
        {
            env.existed = true;
            std::wstring value(needed, L'\0');
            DWORD written = ::GetEnvironmentVariableW(name, value.data(), needed);
            value.resize(written);
            env.value = std::move(value);
        }
        return env;
    }

    void RestoreEnv(const EnvValue& env)
    {
        ::SetEnvironmentVariableW(env.name.c_str(), env.existed ? env.value.c_str() : nullptr);
    }

'''
if helper.strip() not in s: s=s.replace(anchor,helper+anchor,1)
anchor='''    HWND AddCheck(HWND parent, int id, const wchar_t* text, int x, int y, int w, int h)\n'''
helper2=r'''    HWND AddPasswordEdit(HWND parent, int id, int x, int y, int w, int h)
    {
        return ::CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | ES_AUTOHSCROLL | ES_PASSWORD,
            x, y, w, h, parent, reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)), AfxGetInstanceHandle(), nullptr);
    }

'''
s=s.replace(anchor,helper2+anchor,1)
s=s.replace('''            AddStatic(wnd, L"Private key", 16, 114, 115, 20);\n            AddEdit(wnd, IDC_RM_KEY, 138, 111, 320, 24);\n            AddStatic(wnd, L"Refresh (ms)", 16, 146, 115, 20);\n            AddEdit(wnd, IDC_RM_INTERVAL, 138, 143, 100, 24);\n\n            AddStatic(wnd, L"Remote rows", 16, 186, 115, 20);\n            AddCheck(wnd, IDC_RM_SHOW_UPLOAD, L"Upload", 138, 181, 92, 24);\n            AddCheck(wnd, IDC_RM_SHOW_DOWNLOAD, L"Download", 235, 181, 100, 24);\n            AddCheck(wnd, IDC_RM_SHOW_UPTIME, L"Uptime", 340, 181, 90, 24);\n            AddCheck(wnd, IDC_RM_SHOW_TEMP, L"Temperature", 138, 211, 110, 24);\n            AddCheck(wnd, IDC_RM_SHOW_DISK, L"Disk", 255, 211, 80, 24);\n            AddCheck(wnd, IDC_RM_SHOW_CPU, L"CPU", 340, 211, 80, 24);\n\n            AddStatic(wnd, L"Authentication: Windows OpenSSH private key or ssh-agent.", 16, 254, 442, 20);\n            AddStatic(wnd, L"The Linux server does not need a monitoring agent.", 16, 276, 442, 20);\n\n            ::CreateWindowExW(0, L"BUTTON", L"Save", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON,\n                286, 316, 82, 28, wnd, reinterpret_cast<HMENU>(static_cast<INT_PTR>(IDOK)), AfxGetInstanceHandle(), nullptr);\n            ::CreateWindowExW(0, L"BUTTON", L"Cancel", WS_CHILD | WS_VISIBLE | WS_TABSTOP,\n                376, 316, 82, 28, wnd, reinterpret_cast<HMENU>(static_cast<INT_PTR>(IDCANCEL)), AfxGetInstanceHandle(), nullptr);''','''            AddStatic(wnd, L"Private key", 16, 114, 115, 20);\n            AddEdit(wnd, IDC_RM_KEY, 138, 111, 320, 24);\n            AddStatic(wnd, L"SSH password", 16, 146, 115, 20);\n            AddPasswordEdit(wnd, IDC_RM_PASSWORD, 138, 143, 320, 24);\n            AddStatic(wnd, L"Refresh (ms)", 16, 178, 115, 20);\n            AddEdit(wnd, IDC_RM_INTERVAL, 138, 175, 100, 24);\n\n            AddStatic(wnd, L"Remote rows", 16, 218, 115, 20);\n            AddCheck(wnd, IDC_RM_SHOW_UPLOAD, L"Upload", 138, 213, 92, 24);\n            AddCheck(wnd, IDC_RM_SHOW_DOWNLOAD, L"Download", 235, 213, 100, 24);\n            AddCheck(wnd, IDC_RM_SHOW_UPTIME, L"Uptime", 340, 213, 90, 24);\n            AddCheck(wnd, IDC_RM_SHOW_TEMP, L"Temperature", 138, 243, 110, 24);\n            AddCheck(wnd, IDC_RM_SHOW_DISK, L"Disk", 255, 243, 80, 24);\n            AddCheck(wnd, IDC_RM_SHOW_CPU, L"CPU", 340, 243, 80, 24);\n\n            AddStatic(wnd, L"Authentication: private key / ssh-agent / password (DPAPI protected).", 16, 286, 442, 20);\n            AddStatic(wnd, L"The Linux server does not need a monitoring agent.", 16, 308, 442, 20);\n\n            ::CreateWindowExW(0, L"BUTTON", L"Save", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON,\n                286, 348, 82, 28, wnd, reinterpret_cast<HMENU>(static_cast<INT_PTR>(IDOK)), AfxGetInstanceHandle(), nullptr);\n            ::CreateWindowExW(0, L"BUTTON", L"Cancel", WS_CHILD | WS_VISIBLE | WS_TABSTOP,\n                376, 348, 82, 28, wnd, reinterpret_cast<HMENU>(static_cast<INT_PTR>(IDCANCEL)), AfxGetInstanceHandle(), nullptr);''',1)
s=s.replace('                SetControlText(wnd, IDC_RM_KEY, state->config.key_path);\n', '                SetControlText(wnd, IDC_RM_KEY, state->config.key_path);\n                SetControlText(wnd, IDC_RM_PASSWORD, state->config.password);\n',1)
s=s.replace('                state->config.key_path = GetControlText(wnd, IDC_RM_KEY);\n', '                state->config.key_path = GetControlText(wnd, IDC_RM_KEY);\n                state->config.password = GetControlText(wnd, IDC_RM_PASSWORD);\n',1)
s=s.replace('    config.key_path = m_key_path;\n','    config.key_path = m_key_path;\n    config.password = m_password;\n',1)
s=s.replace('    m_key_path = config.key_path;\n','    m_key_path = config.key_path;\n    m_password = config.password;\n',1)
s=s.replace('RECT window_rect{ 0, 0, 480, 370 };','RECT window_rect{ 0, 0, 480, 405 };',1)
s=s.replace('        ::WritePrivateProfileStringW(L"RemoteMonitor", L"KeyPath", L"", file.c_str());\n','        ::WritePrivateProfileStringW(L"RemoteMonitor", L"KeyPath", L"", file.c_str());\n        ::WritePrivateProfileStringW(L"RemoteMonitor", L"PasswordProtected", L"", file.c_str());\n',1)
s=s.replace('    m_key_path = ReadIniString(file, L"KeyPath");\n','    m_key_path = ReadIniString(file, L"KeyPath");\n    m_password = UnprotectPassword(ReadIniString(file, L"PasswordProtected"));\n',1)
s=s.replace('    ::WritePrivateProfileStringW(L"RemoteMonitor", L"KeyPath", m_key_path.c_str(), file.c_str());\n','    ::WritePrivateProfileStringW(L"RemoteMonitor", L"KeyPath", m_key_path.c_str(), file.c_str());\n    const std::wstring protected_password = ProtectPassword(m_password);\n    ::WritePrivateProfileStringW(L"RemoteMonitor", L"PasswordProtected", protected_password.c_str(), file.c_str());\n',1)
old='    command += L" -T -o ConnectTimeout=8 -o ConnectionAttempts=1 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new -o BatchMode=yes -p ";\n'
new='''    command += L" -T -o ConnectTimeout=8 -o ConnectionAttempts=1 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new ";\n    if (m_password.empty())\n        command += L"-o BatchMode=yes ";\n    else\n        command += L"-o BatchMode=no -o PreferredAuthentications=password,keyboard-interactive -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 ";\n    command += L"-p ";\n'''
if old not in s: raise RuntimeError('client auth anchor missing')
s=s.replace(old,new,1)
old='''    BOOL created = ::CreateProcessW(nullptr, cmd.data(), nullptr, nullptr, TRUE,\n        CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT, nullptr, nullptr, &si, &pi);\n    ::CloseHandle(output_write);\n'''
new=r'''    EnvValue old_askpass = CaptureEnv(L"SSH_ASKPASS");
    EnvValue old_askpass_require = CaptureEnv(L"SSH_ASKPASS_REQUIRE");
    EnvValue old_display = CaptureEnv(L"DISPLAY");
    EnvValue old_tm_askpass = CaptureEnv(L"TM_REMOTE_ASKPASS");
    if (!m_password.empty())
    {
        wchar_t module[MAX_PATH]{};
        ::GetModuleFileNameW(nullptr, module, MAX_PATH);
        ::SetEnvironmentVariableW(L"SSH_ASKPASS", module);
        ::SetEnvironmentVariableW(L"SSH_ASKPASS_REQUIRE", L"force");
        ::SetEnvironmentVariableW(L"DISPLAY", L"TrafficMonitor");
        ::SetEnvironmentVariableW(L"TM_REMOTE_ASKPASS", L"1");
    }

    BOOL created = ::CreateProcessW(nullptr, cmd.data(), nullptr, nullptr, TRUE,
        CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT, nullptr, nullptr, &si, &pi);

    if (!m_password.empty())
    {
        RestoreEnv(old_askpass);
        RestoreEnv(old_askpass_require);
        RestoreEnv(old_display);
        RestoreEnv(old_tm_askpass);
    }
    ::CloseHandle(output_write);
'''
if old not in s: raise RuntimeError('CreateProcess anchor missing')
s=s.replace(old,new,1)
anchor='CString CRemoteMonitor::FormatSpeed(double bytes_per_second) const\n'
ask=r'''bool CRemoteMonitor::HandleAskPassIfNeeded()
{
    wchar_t flag[16]{};
    if (::GetEnvironmentVariableW(L"TM_REMOTE_ASKPASS", flag, _countof(flag)) == 0 || wcscmp(flag, L"1") != 0)
        return false;

    CRemoteMonitor& monitor = Instance();
    monitor.LoadConfig();
    std::wstring password = monitor.m_password;
    std::string utf8 = WideToUtf8(password);
    utf8.push_back('\n');

    HANDLE output = ::GetStdHandle(STD_OUTPUT_HANDLE);
    if (output != nullptr && output != INVALID_HANDLE_VALUE)
        WriteAll(output, utf8.data(), utf8.size());

    if (!password.empty())
        ::SecureZeroMemory(password.data(), password.size() * sizeof(wchar_t));
    if (!utf8.empty())
        ::SecureZeroMemory(utf8.data(), utf8.size());
    return true;
}

'''
s=s.replace(anchor,ask+anchor,1)
p.write_text(s,encoding='utf-8-sig')

# TrafficMonitor.cpp early askpass
p=tm/'TrafficMonitor.cpp'; s=p.read_text(encoding='utf-8-sig')
if '#include "RemoteMonitor.h"' not in s:
    s=s.replace('#include "SettingsHelper.h"\n','#include "SettingsHelper.h"\n#include "RemoteMonitor.h"\n',1)
needle='BOOL CTrafficMonitorApp::InitInstance()\n{\n'
if 'HandleAskPassIfNeeded' not in s:
    s=s.replace(needle,needle+'    if (CRemoteMonitor::HandleAskPassIfNeeded())\n        return FALSE;\n\n',1)
p.write_text(s,encoding='utf-8-sig')
print('password support patched')
