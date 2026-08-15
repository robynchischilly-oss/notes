from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
p = root / 'TrafficMonitor' / 'TrafficMonitorDlg.cpp'
s = p.read_text(encoding='utf-8-sig')

# While the integrated remote monitor is enabled, its floating window must stay visible/topmost
# even if TrafficMonitor's legacy 'hide when fullscreen' option is enabled.
start = s.index('void CTrafficMonitorDlg::SetAlwaysOnTop()')
end = s.index('void CTrafficMonitorDlg::SetMousePenetrate()', start)
s = s[:start] + r'''void CTrafficMonitorDlg::SetAlwaysOnTop()
{
    if (theApp.m_cfg_data.m_hide_main_window)
        return;

    const bool remote_monitor_active = CRemoteMonitor::Instance().ExtraRows() > 0;
    if (!remote_monitor_active && theApp.m_main_wnd_data.hide_main_wnd_when_fullscreen && m_is_foreground_fullscreen)
        return;

    const bool should_be_topmost = theApp.m_main_wnd_data.m_always_on_top || remote_monitor_active;
    ::SetWindowPos(
        GetSafeHwnd(),
        should_be_topmost ? HWND_TOPMOST : HWND_NOTOPMOST,
        0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW);
}

''' + s[end:]

# Resizing to 1/3 rows must not accidentally demote the remote monitor from TOPMOST.
start = s.index('void CTrafficMonitorDlg::SetItemPosition()')
end = s.index('bool CTrafficMonitorDlg::LoadSkinLayout()', start)
block = s[start:end]
old = '    HWND insert_after = theApp.m_main_wnd_data.m_always_on_top ? HWND_TOPMOST : HWND_NOTOPMOST;\n'
new = '    const bool remote_monitor_active = CRemoteMonitor::Instance().ExtraRows() > 0;\n    HWND insert_after = (theApp.m_main_wnd_data.m_always_on_top || remote_monitor_active) ? HWND_TOPMOST : HWND_NOTOPMOST;\n'
if old not in block:
    raise RuntimeError('SetItemPosition topmost anchor not found')
block = block.replace(old, new, 1)
s = s[:start] + block + s[end:]

# Replace the per-second fullscreen handling block.
start = s.index('        if (theApp.m_main_wnd_data.m_always_on_top && !theApp.m_cfg_data.m_hide_main_window)')
end = s.index('        if (!m_menu_popuped)', start)
s = s[:start] + r'''        const bool remote_monitor_active = CRemoteMonitor::Instance().ExtraRows() > 0;
        if ((theApp.m_main_wnd_data.m_always_on_top || remote_monitor_active) && !theApp.m_cfg_data.m_hide_main_window)
        {
            CRect rect;
            GetWindowRect(rect);
            HMONITOR h_current_monitor = ::MonitorFromRect(&rect, MONITOR_DEFAULTTONEAREST);
            m_is_foreground_fullscreen = CCommon::IsForegroundFullscreen(h_current_monitor);

            if (theApp.m_main_wnd_data.hide_main_wnd_when_fullscreen && !remote_monitor_active)
            {
                if (m_is_foreground_fullscreen || theApp.m_cfg_data.m_hide_main_window)
                    ShowWindow(SW_HIDE);
                else
                    ShowWindow(SW_SHOWNOACTIVATE);
            }
            else
            {
                // Remote monitor mode is an always-visible overlay: do not hide for fullscreen apps.
                if (!IsWindowVisible())
                    ShowWindow(SW_SHOWNOACTIVATE);
                SetAlwaysOnTop();
            }
        }

''' + s[end:]

p.write_text(s, encoding='utf-8-sig')
print('remote topmost/fullscreen fix applied')
