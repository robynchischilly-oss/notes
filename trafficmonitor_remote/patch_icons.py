from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
p = root / "TrafficMonitor" / "SkinFile.cpp"
text = p.read_text(encoding="utf-8-sig")

start_marker = "static void DrawRemoteMonitorRows"
end_marker = "void CSkinFile::DrawInfo(CDC* pDC, bool show_more_info)"
start = text.find(start_marker)
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise RuntimeError("remote monitor draw helper not found")

helper = r'''enum class RemoteVectorIcon
{
    Upload,
    Download,
    Uptime,
    Temperature,
    Disk,
    Cpu
};

static void DrawRemoteVectorIcon(IDrawCommon& drawer, RemoteVectorIcon icon, CRect rect, COLORREF color)
{
    int size = rect.Height();
    if (size < 7)
        size = 7;
    if (size > 13)
        size = 13;

    int x = rect.left + (rect.Width() - size) / 2;
    int y = rect.top + (rect.Height() - size) / 2;
    if (x < rect.left)
        x = rect.left;
    if (y < rect.top)
        y = rect.top;

    const int stroke = size >= 11 ? 2 : 1;

    switch (icon)
    {
    case RemoteVectorIcon::Upload:
    {
        const int cx = x + size / 2;
        const int head = (std::max)(2, size / 3);
        drawer.FillRect(CRect(cx, y + 1, cx + stroke, y + size - 1), color);
        for (int i = 0; i < head; ++i)
        {
            drawer.FillRect(CRect(cx - i, y + 1 + i, cx + i + stroke, y + 2 + i), color);
        }
        break;
    }
    case RemoteVectorIcon::Download:
    {
        const int cx = x + size / 2;
        const int head = (std::max)(2, size / 3);
        drawer.FillRect(CRect(cx, y + 1, cx + stroke, y + size - 1), color);
        for (int i = 0; i < head; ++i)
        {
            drawer.FillRect(CRect(cx - i, y + size - 2 - i, cx + i + stroke, y + size - 1 - i), color);
        }
        break;
    }
    case RemoteVectorIcon::Uptime:
    {
        const int inset = 1;
        CRect body(x + inset, y + inset, x + size - inset, y + size - inset);
        drawer.DrawRectOutLine(body, color, stroke);
        const int cx = x + size / 2;
        const int cy = y + size / 2;
        drawer.FillRect(CRect(cx, y + 3, cx + stroke, cy + 1), color);
        drawer.FillRect(CRect(cx, cy, x + size - 3, cy + stroke), color);
        break;
    }
    case RemoteVectorIcon::Temperature:
    {
        int cx = x + size / 2;
        int bulb = size >= 11 ? 5 : 4;
        int stem_top = y;
        int stem_bottom = y + size - bulb + 1;
        drawer.DrawRectOutLine(CRect(cx - 1, stem_top, cx + 2, stem_bottom), color, stroke);
        drawer.FillRect(CRect(cx, stem_top + 2, cx + stroke, stem_bottom), color);
        drawer.FillRect(CRect(cx - bulb / 2, y + size - bulb, cx - bulb / 2 + bulb, y + size), color);
        break;
    }
    case RemoteVectorIcon::Disk:
    {
        int top = y + 1;
        int bottom = y + size - 1;
        drawer.DrawRectOutLine(CRect(x, top, x + size, bottom), color, stroke);
        drawer.FillRect(CRect(x + 2, bottom - 3, x + size - 2, bottom - 2), color);
        drawer.FillRect(CRect(x + size - 4, bottom - 5, x + size - 2, bottom - 3), color);
        break;
    }
    case RemoteVectorIcon::Cpu:
    {
        int body_left = x + 2;
        int body_top = y + 2;
        int body_right = x + size - 2;
        int body_bottom = y + size - 2;
        drawer.DrawRectOutLine(CRect(body_left, body_top, body_right, body_bottom), color, stroke);
        drawer.FillRect(CRect(body_left + 2, body_top + 2, body_right - 2, body_bottom - 2), color);

        int pin1 = x + size / 3;
        int pin2 = x + (size * 2) / 3;
        drawer.FillRect(CRect(pin1, y, pin1 + 1, body_top), color);
        drawer.FillRect(CRect(pin2, y, pin2 + 1, body_top), color);
        drawer.FillRect(CRect(pin1, body_bottom, pin1 + 1, y + size), color);
        drawer.FillRect(CRect(pin2, body_bottom, pin2 + 1, y + size), color);
        drawer.FillRect(CRect(x, y + size / 3, body_left, y + size / 3 + 1), color);
        drawer.FillRect(CRect(x, y + (size * 2) / 3, body_left, y + (size * 2) / 3 + 1), color);
        drawer.FillRect(CRect(body_right, y + size / 3, x + size, y + size / 3 + 1), color);
        drawer.FillRect(CRect(body_right, y + (size * 2) / 3, x + size, y + (size * 2) / 3 + 1), color);
        break;
    }
    }
}

static void DrawRemoteMonitorRows(IDrawCommon& drawer, CFont& font, int width, int top, int row_height, COLORREF color)
{
    CRemoteMonitor& remote = CRemoteMonitor::Instance();
    if (remote.ExtraRows() == 0)
        return;

    const RemoteMonitorSnapshot data = remote.GetSnapshot();

    // IMPORTANT: use the exact same CFont object as TrafficMonitor's normal
    // DrawItemsInfo pass. No remote font, size, weight or style override.
    drawer.SetFont(&font);

    const int col_w = width / 3;
    auto cell_rect = [&](int row, int col)
    {
        const int left = col * col_w;
        const int right = (col == 2 ? width : (col + 1) * col_w);
        return CRect(left, top + row * row_height, right, top + (row + 1) * row_height);
    };

    auto draw_icon_value = [&](int row, int col, RemoteVectorIcon icon, const CString& value)
    {
        if (value.IsEmpty())
            return;

        CRect cell = cell_rect(row, col);
        int icon_size = row_height - 6;
        if (icon_size < 7)
            icon_size = 7;
        if (icon_size > 13)
            icon_size = 13;

        const int gap = (std::max)(2, row_height / 8);
        int text_width = drawer.GetTextWidth(value);
        if (text_width <= 0)
            text_width = row_height * 2;

        int total_width = icon_size + gap + text_width;
        if (total_width > cell.Width() - 2)
            total_width = cell.Width() - 2;

        int left = cell.left + (cell.Width() - total_width) / 2;
        if (left < cell.left + 1)
            left = cell.left + 1;

        const int icon_top = cell.top + (cell.Height() - icon_size) / 2;
        CRect icon_rect(left, icon_top, left + icon_size, icon_top + icon_size);
        DrawRemoteVectorIcon(drawer, icon, icon_rect, color);

        const int text_left = left + icon_size + gap;
        if (text_left < cell.right)
        {
            CRect text_rect(text_left, cell.top, cell.right - 1, cell.bottom);
            drawer.DrawWindowText(text_rect, value, color, IDrawCommon::Alignment::LEFT);
        }
    };

    CString up = L"--";
    CString down = L"--";
    CString uptime = L"--";
    CString temperature = L"--";
    CString disk = L"--";
    CString cpu = L"--";

    if (data.has_data)
    {
        if (remote.ShowUpload())
            up = remote.FormatSpeed(data.upload_bps);
        if (remote.ShowDownload())
            down = remote.FormatSpeed(data.download_bps);
        if (remote.ShowUptime())
            uptime = remote.FormatUptime(data.uptime_seconds);
        if (remote.ShowTemperature() && data.temperature_c >= 0)
            temperature.Format(L"%d°", data.temperature_c);
        if (remote.ShowDisk())
            disk.Format(L"%d%%", data.disk_usage);
        if (remote.ShowCpu())
            cpu.Format(L"%d%%", data.cpu_usage);
    }

    if (!remote.ShowUpload()) up.Empty();
    if (!remote.ShowDownload()) down.Empty();
    if (!remote.ShowUptime()) uptime.Empty();
    if (!remote.ShowTemperature()) temperature.Empty();
    if (!remote.ShowDisk()) disk.Empty();
    if (!remote.ShowCpu()) cpu.Empty();

    // Vector symbols avoid Unicode fallback fonts. All actual text therefore
    // comes from TrafficMonitor's own skin font and has identical size/weight.
    draw_icon_value(0, 0, RemoteVectorIcon::Upload, up);
    draw_icon_value(0, 1, RemoteVectorIcon::Download, down);
    draw_icon_value(0, 2, RemoteVectorIcon::Uptime, uptime);
    draw_icon_value(1, 0, RemoteVectorIcon::Temperature, temperature);
    draw_icon_value(1, 1, RemoteVectorIcon::Disk, disk);
    draw_icon_value(1, 2, RemoteVectorIcon::Cpu, cpu);
}

'''

text = text[:start] + helper + text[end:]
p.write_text(text, encoding="utf-8-sig")
print("TrafficMonitor remote rows now reuse the exact main skin font/style")
