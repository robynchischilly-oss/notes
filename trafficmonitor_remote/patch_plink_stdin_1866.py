from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
p = root / 'TrafficMonitor' / 'RemoteMonitor.cpp'
s = p.read_text(encoding='utf-8-sig')

# Build marker/log version.
s = s.replace('Tailscale / SSH Server [1.86.5]', 'Tailscale / SSH Server [1.86.6]')
s = s.replace('remote monitor 1.86.5 start', 'remote monitor 1.86.6 start')

# Plink's collector stdin must be an inheritable Win32 handle because the child
# is launched with bInheritHandles=TRUE and STARTF_USESTDHANDLES. 1.86.5 opened
# NUL with lpSecurityAttributes=nullptr, creating a non-inheritable handle. The
# child therefore received an invalid stdin handle and exited with
# "Unable to read from standard input" before producing any TM frame.
old = '''        HANDLE nul_input = ::CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,\n            nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);\n'''
new = '''        HANDLE nul_input = ::CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,\n            &sa, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);\n        if (nul_input != INVALID_HANDLE_VALUE)\n            ::SetHandleInformation(nul_input, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT);\n'''
if old not in s:
    raise RuntimeError('collector NUL stdin anchor not found')
s = s.replace(old, new, 1)

# Deterministic diagnostic: this must appear in the log before collector launch.
anchor = '        si.hStdInput = nul_input == INVALID_HANDLE_VALUE ? ::GetStdHandle(STD_INPUT_HANDLE) : nul_input;\n'
replacement = anchor + '''        if (nul_input == INVALID_HANDLE_VALUE)\n            AppendRemoteLog("collector: stdin=fallback");\n        else\n            AppendRemoteLog("collector: stdin=inheritable NUL");\n'''
if anchor not in s:
    raise RuntimeError('collector stdin assignment anchor not found')
s = s.replace(anchor, replacement, 1)

p.write_text(s, encoding='utf-8-sig')
print('TrafficMonitor 1.86.6 inheritable Plink stdin fix applied')
