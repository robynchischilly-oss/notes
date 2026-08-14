from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
tm = root / "TrafficMonitor"


def read(path):
    return path.read_text(encoding="utf-8-sig")


def write(path, text):
    path.write_text(text, encoding="utf-8-sig")


def replace_once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"patch anchor not found: {label}")
    return text.replace(old, new, 1)

# TrafficMonitorDlg.cpp: lifetime + same-window height extension.
p = tm / "TrafficMonitorDlg.cpp"
s = read(p)
s = replace_once(s,
    '#include "SkinManager.h"\n',
    '#include "SkinManager.h"\n#include "RemoteMonitor.h"\n',
    "TrafficMonitorDlg include")
s = replace_once(s,
    '    m_desktop_dc = ::GetDC(NULL);\n}',
    '    m_desktop_dc = ::GetDC(NULL);\n    CRemoteMonitor::Instance().Start();\n}',
    "remote monitor startup")
s = replace_once(s,
    'CTrafficMonitorDlg::~CTrafficMonitorDlg()\n{\n    free(m_pIfTable);',
    'CTrafficMonitorDlg::~CTrafficMonitorDlg()\n{\n    CRemoteMonitor::Instance().Stop();\n    free(m_pIfTable);',
    "remote monitor shutdown")

old_setpos = '''void CTrafficMonitorDlg::SetItemPosition()\n{\n    if (theApp.m_cfg_data.m_show_more_info)\n    {\n        SetWindowPos(nullptr, 0, 0, m_skin.GetLayoutInfo().layout_l.width, m_skin.GetLayoutInfo().layout_l.height, SWP_NOMOVE | SWP_NOZORDER);\n    }\n    else\n    {\n        SetWindowPos(nullptr, 0, 0, m_skin.GetLayoutInfo().layout_s.width, m_skin.GetLayoutInfo().layout_s.height, SWP_NOMOVE | SWP_NOZORDER);\n    }\n}\n'''
new_setpos = '''void CTrafficMonitorDlg::SetItemPosition()\n{\n    const int remote_extra_height = CRemoteMonitor::Instance().ExtraRows() * m_skin.GetLayoutInfo().text_height;\n    if (theApp.m_cfg_data.m_show_more_info)\n    {\n        SetWindowPos(nullptr, 0, 0, m_skin.GetLayoutInfo().layout_l.width, m_skin.GetLayoutInfo().layout_l.height + remote_extra_height, SWP_NOMOVE | SWP_NOZORDER);\n    }\n    else\n    {\n        SetWindowPos(nullptr, 0, 0, m_skin.GetLayoutInfo().layout_s.width, m_skin.GetLayoutInfo().layout_s.height + remote_extra_height, SWP_NOMOVE | SWP_NOZORDER);\n    }\n}\n'''
s = replace_once(s, old_setpos, new_setpos, "SetItemPosition")

old_image = '''    if (theApp.m_cfg_data.m_show_more_info)\n    {\n        image_size.SetSize(m_skin.GetLayoutInfo().layout_l.width, m_skin.GetLayoutInfo().layout_l.height);\n    }\n    else\n    {\n        image_size.SetSize(m_skin.GetLayoutInfo().layout_s.width, m_skin.GetLayoutInfo().layout_s.height);\n    }\n\n    //创建窗口区域\n'''
new_image = '''    if (theApp.m_cfg_data.m_show_more_info)\n    {\n        image_size.SetSize(m_skin.GetLayoutInfo().layout_l.width, m_skin.GetLayoutInfo().layout_l.height);\n    }\n    else\n    {\n        image_size.SetSize(m_skin.GetLayoutInfo().layout_s.width, m_skin.GetLayoutInfo().layout_s.height);\n    }\n    image_size.cy += CRemoteMonitor::Instance().ExtraRows() * m_skin.GetLayoutInfo().text_height;\n\n    //创建窗口区域\n'''
s = replace_once(s, old_image, new_image, "LoadBackGroundImage size")
write(p, s)

# SkinFile.cpp: render the two server rows in TrafficMonitor's own paint pass.
p = tm / "SkinFile.cpp"
s = read(p)
s = replace_once(s,
    '#include "SkinManager.h"\n',
    '#include "SkinManager.h"\n#include "RemoteMonitor.h"\n',
    "SkinFile include")

marker = 'void CSkinFile::DrawInfo(CDC* pDC, bool show_more_info)\n'
helper = r'''static void DrawRemoteMonitorRows(IDrawCommon& drawer, CFont& font, int width, int top, int row_height, COLORREF color)
{
    CRemoteMonitor& remote = CRemoteMonitor::Instance();
    if (remote.ExtraRows() == 0)
        return;

    const RemoteMonitorSnapshot data = remote.GetSnapshot();
    drawer.SetFont(&font);

    const int col_w = width / 3;
    auto draw_cell = [&](int row, int col, const CString& text)
    {
        const int left = col * col_w;
        const int right = (col == 2 ? width : (col + 1) * col_w);
        CRect rect(left, top + row * row_height, right, top + (row + 1) * row_height);
        drawer.DrawWindowText(rect, text, color, IDrawCommon::Alignment::CENTER);
    };

    CString up = L"↑ --";
    CString down = L"↓ --";
    CString uptime = L"◷ --";
    CString temperature = L"T --";
    CString disk = L"▰ --";
    CString cpu = L"C --";

    if (data.has_data)
    {
        if (remote.ShowUpload())
            up = L"↑ " + remote.FormatSpeed(data.upload_bps);
        if (remote.ShowDownload())
            down = L"↓ " + remote.FormatSpeed(data.download_bps);
        if (remote.ShowUptime())
            uptime = L"◷ " + remote.FormatUptime(data.uptime_seconds);
        if (remote.ShowTemperature() && data.temperature_c >= 0)
            temperature.Format(L"T %d°", data.temperature_c);
        if (remote.ShowDisk())
            disk.Format(L"▰ %d%%", data.disk_usage);
        if (remote.ShowCpu())
            cpu.Format(L"C %d%%", data.cpu_usage);
    }

    if (!remote.ShowUpload()) up.Empty();
    if (!remote.ShowDownload()) down.Empty();
    if (!remote.ShowUptime()) uptime.Empty();
    if (!remote.ShowTemperature()) temperature.Empty();
    if (!remote.ShowDisk()) disk.Empty();
    if (!remote.ShowCpu()) cpu.Empty();

    draw_cell(0, 0, up);
    draw_cell(0, 1, down);
    draw_cell(0, 2, uptime);
    draw_cell(1, 0, temperature);
    draw_cell(1, 1, disk);
    draw_cell(1, 2, cpu);
}

'''
if marker not in s:
    raise RuntimeError("DrawInfo marker not found")
s = s.replace(marker, helper + marker, 1)

s = replace_once(s,
    '    CRect rect(CPoint(0, 0), CSize(layout.width, layout.height));\n',
    '    const int remote_extra_height = CRemoteMonitor::Instance().ExtraRows() * m_layout_info.text_height;\n    CRect rect(CPoint(0, 0), CSize(layout.width, layout.height + remote_extra_height));\n',
    "DrawInfo total rect")

# Both PNG and BMP branches get the same remote text color used by the active skin.
s = replace_once(s,
    '        DrawItemsInfo(gdiplus_drawer, layout, m_font);\n\n        //找出绘制显示项目前不透明，但是绘制后透明的点，并修正其alpha值\n',
    '''        DrawItemsInfo(gdiplus_drawer, layout, m_font);\n        COLORREF remote_color = m_skin_info.TextColor(0);\n        if (!theApp.m_main_wnd_data.text_colors.empty())\n            remote_color = theApp.m_main_wnd_data.text_colors.begin()->second;\n        DrawRemoteMonitorRows(gdiplus_drawer, m_font, layout.width, layout.height, m_layout_info.text_height, remote_color);\n\n        //找出绘制显示项目前不透明，但是绘制后透明的点，并修正其alpha值\n''',
    "PNG remote draw")

s = replace_once(s,
    '        draw.DrawBitmap(background_image, CPoint(0, 0), CSize(layout.width, layout.height));\n\n        DrawItemsInfo(draw, layout, m_font);\n',
    '''        draw.DrawBitmap(background_image, CPoint(0, 0), rect.Size());\n\n        DrawItemsInfo(draw, layout, m_font);\n        COLORREF remote_color = m_skin_info.TextColor(0);\n        if (!theApp.m_main_wnd_data.text_colors.empty())\n            remote_color = theApp.m_main_wnd_data.text_colors.begin()->second;\n        DrawRemoteMonitorRows(draw, m_font, layout.width, layout.height, m_layout_info.text_height, remote_color);\n''',
    "BMP remote draw")
write(p, s)

# Project file: compile the integrated module into TrafficMonitor.exe.
p = tm / "TrafficMonitor.vcxproj"
s = read(p)
s = replace_once(s,
    '    <ClInclude Include="RenderAPISupport.h" />\n',
    '    <ClInclude Include="RemoteMonitor.h" />\n    <ClInclude Include="RenderAPISupport.h" />\n',
    "vcxproj header")
s = replace_once(s,
    '    <ClCompile Include="SelectConnectionsDlg.cpp" />\n',
    '    <ClCompile Include="RemoteMonitor.cpp" />\n    <ClCompile Include="SelectConnectionsDlg.cpp" />\n',
    "vcxproj source")
write(p, s)

print("TrafficMonitor V1.86 patched with integrated remote monitor")
