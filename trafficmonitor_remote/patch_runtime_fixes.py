from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
tm = root / 'TrafficMonitor'

def read(path):
    return path.read_text(encoding='utf-8-sig')

def write(path, text):
    path.write_text(text, encoding='utf-8-sig')

# TrafficMonitorDlg.cpp
p = tm / 'TrafficMonitorDlg.cpp'
s = read(p)
msg = '    ON_COMMAND(ID_OPTIONS, &CTrafficMonitorDlg::OnOptions)\n'
if 'ON_COMMAND(ID_REMOTE_MONITOR_SETTINGS' not in s:
    if msg not in s:
        raise RuntimeError('message-map anchor not found')
    s = s.replace(msg, msg + '    ON_COMMAND(ID_REMOTE_MONITOR_SETTINGS, &CTrafficMonitorDlg::OnRemoteMonitorSettings)\n', 1)

start = s.index('void CTrafficMonitorDlg::SetAlwaysOnTop()')
end = s.index('void CTrafficMonitorDlg::SetMousePenetrate()', start)
s = s[:start] + r'''void CTrafficMonitorDlg::SetAlwaysOnTop()
{
    if (theApp.m_cfg_data.m_hide_main_window)
        return;
    if (theApp.m_main_wnd_data.hide_main_wnd_when_fullscreen && m_is_foreground_fullscreen)
        return;

    ::SetWindowPos(
        GetSafeHwnd(),
        theApp.m_main_wnd_data.m_always_on_top ? HWND_TOPMOST : HWND_NOTOPMOST,
        0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
}

''' + s[end:]

start = s.index('void CTrafficMonitorDlg::SetItemPosition()')
end = s.index('bool CTrafficMonitorDlg::LoadSkinLayout()', start)
s = s[:start] + r'''void CTrafficMonitorDlg::SetItemPosition()
{
    const int remote_extra_height = CRemoteMonitor::Instance().ExtraRows() * m_skin.GetLayoutInfo().text_height;
    const CSkinFile::Layout& layout = theApp.m_cfg_data.m_show_more_info
        ? m_skin.GetLayoutInfo().layout_l
        : m_skin.GetLayoutInfo().layout_s;

    HWND insert_after = theApp.m_main_wnd_data.m_always_on_top ? HWND_TOPMOST : HWND_NOTOPMOST;
    ::SetWindowPos(GetSafeHwnd(), insert_after, 0, 0,
        layout.width, layout.height + remote_extra_height,
        SWP_NOMOVE | SWP_NOACTIVATE);
}

''' + s[end:]

start = s.index('void CTrafficMonitorDlg::LoadBackGroundImage()')
end = s.index('void CTrafficMonitorDlg::SetTextFont()', start)
s = s[:start] + r'''void CTrafficMonitorDlg::LoadBackGroundImage()
{
    const CSkinFile::Layout& layout = theApp.m_cfg_data.m_show_more_info
        ? m_skin.GetLayoutInfo().layout_l
        : m_skin.GetLayoutInfo().layout_s;
    const CSize base_size(layout.width, layout.height);
    const int remote_extra_height = CRemoteMonitor::Instance().ExtraRows() * m_skin.GetLayoutInfo().text_height;
    const CSize image_size(base_size.cx, base_size.cy + remote_extra_height);

    CImage source_mask;
    if (theApp.m_cfg_data.m_show_more_info)
        source_mask.Load((theApp.m_skin_path + CSkinManager::Instance().GetSkinName(m_skin_selected) + BACKGROUND_MASK_L).c_str());
    else
        source_mask.Load((theApp.m_skin_path + CSkinManager::Instance().GetSkinName(m_skin_selected) + BACKGROUND_MASK_S).c_str());

    CRgn wnd_rgn;
    if (!source_mask.IsNull())
    {
        CImage base_mask;
        CDrawCommon::BitmapStretch(&source_mask, &base_mask, base_size);

        if (remote_extra_height > 0 && !base_mask.IsNull())
        {
            CImage extended_mask;
            extended_mask.Create(image_size.cx, image_size.cy, 24);
            HDC dc = extended_mask.GetDC();
            ::PatBlt(dc, 0, 0, image_size.cx, image_size.cy, BLACKNESS);

            base_mask.Draw(dc, 0, 0, base_size.cx, base_size.cy,
                0, 0, base_mask.GetWidth(), base_mask.GetHeight());

            const int src_strip_y = (std::max)(0, base_mask.GetHeight() - 3);
            base_mask.Draw(dc, 0, base_size.cy, base_size.cx, remote_extra_height,
                0, src_strip_y, base_mask.GetWidth(), 1);

            base_mask.Draw(dc, 0, image_size.cy - 1, base_size.cx, 1,
                0, (std::max)(0, base_mask.GetHeight() - 1), base_mask.GetWidth(), 1);
            extended_mask.ReleaseDC();

            CBitmap bitmap;
            bitmap.Attach(extended_mask);
            CDrawCommon::GetRegionFromImage(wnd_rgn, bitmap, 128);
            bitmap.Detach();
        }
        else
        {
            CBitmap bitmap;
            bitmap.Attach(base_mask);
            CDrawCommon::GetRegionFromImage(wnd_rgn, bitmap, 128);
            bitmap.Detach();
        }
    }
    else
    {
        wnd_rgn.CreateRectRgnIndirect(CRect(CPoint(0, 0), image_size));
    }

    CRgn empty_rgn;
    empty_rgn.CreateRectRgnIndirect(CRect{});
    if (wnd_rgn.EqualRgn(&empty_rgn))
        wnd_rgn.SetRectRgn(CRect(CPoint(0, 0), image_size));

    SetWindowRgn(wnd_rgn, TRUE);
    wnd_rgn.DeleteObject();
    empty_rgn.DeleteObject();
}

''' + s[end:]

rb = s.index('void CTrafficMonitorDlg::OnRButtonUp(UINT nFlags, CPoint point)')
remote_start = s.index('    // Remote monitor is part of TrafficMonitor itself: add its settings entry to the existing context menu.', rb)
remote_end = s.index('    CDialog::OnRButtonUp(nFlags, point1);', remote_start)
s = s[:remote_start] + r'''    if (pContextMenu->GetMenuState(ID_REMOTE_MONITOR_SETTINGS, MF_BYCOMMAND) == static_cast<UINT>(-1))
    {
        int options_pos = CCommon::GetMenuItemPosition(pContextMenu, ID_OPTIONS);
        if (options_pos >= 0)
            pContextMenu->InsertMenu(options_pos, MF_BYPOSITION | MF_STRING, ID_REMOTE_MONITOR_SETTINGS, _T("Tailscale / SSH Server..."));
        else
            pContextMenu->AppendMenu(MF_STRING, ID_REMOTE_MONITOR_SETTINGS, _T("Tailscale / SSH Server..."));
    }

    pContextMenu->TrackPopupMenu(TPM_LEFTALIGN | TPM_RIGHTBUTTON, point1.x, point1.y, this);

''' + s[remote_end:]

handler = r'''void CTrafficMonitorDlg::OnRemoteMonitorSettings()
{
    if (CRemoteMonitor::Instance().ShowSettings(GetSafeHwnd()))
    {
        SetItemPosition();
        LoadBackGroundImage();
        CheckWindowPos();
        SetAlwaysOnTop();
        RedrawWindow(nullptr, nullptr, RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN);
    }
    else
    {
        SetAlwaysOnTop();
    }
}

'''
if 'void CTrafficMonitorDlg::OnRemoteMonitorSettings()' not in s:
    anchor = 'void CTrafficMonitorDlg::OnLButtonDown(UINT nFlags, CPoint point)\n'
    if anchor not in s:
        raise RuntimeError('OnLButtonDown anchor not found')
    s = s.replace(anchor, handler + anchor, 1)

needle = '        if (theApp.m_main_wnd_data.m_always_on_top && !theApp.m_cfg_data.m_hide_main_window)\n        {\n'
if needle in s and '            SetAlwaysOnTop();\n            //每隔1秒钟就判断一下前台窗口是否全屏' not in s:
    s = s.replace(needle, needle + '            SetAlwaysOnTop();\n', 1)
write(p, s)

# TrafficMonitorDlg.h
p = tm / 'TrafficMonitorDlg.h'
h = read(p)
if 'afx_msg void OnRemoteMonitorSettings();' not in h:
    anchor = '    afx_msg void OnOptions();\n'
    if anchor not in h:
        raise RuntimeError('header anchor not found')
    h = h.replace(anchor, anchor + '    afx_msg void OnRemoteMonitorSettings();\n', 1)
write(p, h)

# SkinFile.cpp
p = tm / 'SkinFile.cpp'
s = read(p)
marker = 'void CSkinFile::DrawInfo(CDC* pDC, bool show_more_info)\n'
helpers = r'''static void DrawExtendedPngSkinBackground(CDrawCommonEx& drawer, Gdiplus::Image* image,
    int width, int base_height, int extra_height)
{
    if (image == nullptr)
        return;

    drawer.DrawImage(image, CPoint(0, 0), CSize(width, base_height), IDrawCommon::StretchMode::STRETCH);
    if (extra_height <= 0)
        return;

    Gdiplus::Graphics* graphics = drawer.GetGraphics();
    if (graphics == nullptr || image->GetWidth() == 0 || image->GetHeight() == 0)
        return;

    const int src_y = (std::max)(0, static_cast<int>(image->GetHeight()) - 3);
    graphics->DrawImage(image,
        Gdiplus::Rect(0, base_height, width, extra_height),
        0, src_y, static_cast<INT>(image->GetWidth()), 1, Gdiplus::UnitPixel);
    graphics->DrawImage(image,
        Gdiplus::Rect(0, base_height + extra_height - 1, width, 1),
        0, static_cast<INT>(image->GetHeight()) - 1,
        static_cast<INT>(image->GetWidth()), 1, Gdiplus::UnitPixel);
}

static void DrawExtendedBmpSkinBackground(IDrawCommon& drawer, CImage& image,
    int width, int base_height, int extra_height)
{
    if (image.IsNull())
        return;

    drawer.DrawBitmap(image, CPoint(0, 0), CSize(width, base_height));
    if (extra_height <= 0 || drawer.GetDC() == nullptr)
        return;

    HDC dc = drawer.GetDC()->GetSafeHdc();
    const int src_y = (std::max)(0, image.GetHeight() - 3);
    image.Draw(dc, 0, base_height, width, extra_height,
        0, src_y, image.GetWidth(), 1);
    image.Draw(dc, 0, base_height + extra_height - 1, width, 1,
        0, (std::max)(0, image.GetHeight() - 1), image.GetWidth(), 1);
}

'''
if 'DrawExtendedPngSkinBackground' not in s:
    if marker not in s:
        raise RuntimeError('DrawInfo marker not found')
    s = s.replace(marker, helpers + marker, 1)

old_png = '        gdiplus_drawer.DrawImage(background_image, CPoint(0, 0), rect.Size(), CDrawCommon::StretchMode::FILL);'
if old_png in s:
    s = s.replace(old_png, '        DrawExtendedPngSkinBackground(gdiplus_drawer, background_image, layout.width, layout.height, remote_extra_height);', 1)
old_bmp = '        draw.DrawBitmap(background_image, CPoint(0, 0), rect.Size());'
if old_bmp in s:
    s = s.replace(old_bmp, '        DrawExtendedBmpSkinBackground(draw, background_image, layout.width, layout.height, remote_extra_height);', 1)
write(p, s)

print('runtime fixes applied')
