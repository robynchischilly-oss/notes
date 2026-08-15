from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
p = root / 'TrafficMonitor' / 'RemoteMonitor.cpp'
s = p.read_text(encoding='utf-8-sig')

# Build marker/log version.
s = s.replace('Tailscale / SSH Server [1.86.4]', 'Tailscale / SSH Server [1.86.5]')
s = s.replace('remote monitor 1.86.4 start', 'remote monitor 1.86.5 start')

# The user's server host key was observed in the diagnostic log over the
# Tailscale connection. Pin it explicitly so Plink never waits for an
# interactive first-use trust prompt.
anchor = '    const bool password_auth = !m_password.empty();\n'
insert = '''    const bool password_auth = !m_password.empty();\n\n    // Verified from the server preflight log. PuTTY -hostkey pins the exact\n    // SSH server identity and bypasses the interactive Registry cache prompt.\n    const std::wstring pinned_host_key =\n        (m_host == L"100.122.159.72")\n        ? L"SHA256:oETUWcNxt9RPbgqIP7O2XNwDlVq4djCdURO46nO08H0"\n        : L"";\n'''
if anchor not in s:
    raise RuntimeError('password_auth anchor not found')
s = s.replace(anchor, insert, 1)

# Preflight: for the pinned server use -batch + -hostkey, so there is no
# interactive y/n prompt at all. Other hosts retain the previous behaviour.
old = '''        std::wstring probe_command = QuoteArg(plink);\n        probe_command += L" -v -ssh -no-antispoof -P ";\n        probe_command += std::to_wstring(m_port);\n'''
new = '''        std::wstring probe_command = QuoteArg(plink);\n        probe_command += L" -v ";\n        if (!pinned_host_key.empty())\n        {\n            probe_command += L"-batch -hostkey ";\n            probe_command += QuoteArg(pinned_host_key);\n            probe_command += L" ";\n            AppendRemoteLog("preflight: using pinned host key " + WideToUtf8(pinned_host_key));\n        }\n        probe_command += L"-ssh -no-antispoof -P ";\n        probe_command += std::to_wstring(m_port);\n'''
if old not in s:
    raise RuntimeError('probe command anchor not found')
s = s.replace(old, new, 1)

# Collector must use the same pinned identity. Otherwise the second Plink
# process would still fail in -batch mode even after a successful preflight.
old = '''        std::wstring command = QuoteArg(plink);\n        command += L" -batch -ssh -T -no-antispoof -P ";\n        command += std::to_wstring(m_port);\n'''
new = '''        std::wstring command = QuoteArg(plink);\n        command += L" -batch ";\n        if (!pinned_host_key.empty())\n        {\n            command += L"-hostkey ";\n            command += QuoteArg(pinned_host_key);\n            command += L" ";\n        }\n        command += L"-ssh -T -no-antispoof -P ";\n        command += std::to_wstring(m_port);\n'''
if old not in s:
    raise RuntimeError('collector command anchor not found')
s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8-sig')
print('TrafficMonitor 1.86.5 pinned-host-key fix applied')
