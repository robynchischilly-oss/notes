#pragma once
#include <atomic>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

constexpr UINT ID_REMOTE_MONITOR_SETTINGS = 0xE9F1;

struct RemoteMonitorSnapshot
{
    bool has_data{};
    bool online{};
    double upload_bps{};
    double download_bps{};
    int cpu_usage{};
    int temperature_c{ -1 };
    int disk_usage{};
    unsigned long long uptime_seconds{};
    unsigned long long mem_total_kb{};
    unsigned long long mem_available_kb{};
    int cpu_cores{};
    CString ssh_user;
};

struct RemoteMonitorConfig
{
    bool enabled{};
    std::wstring host;
    std::wstring user;
    std::wstring key_path;
    int port{ 22 };
    int interval_ms{ 1000 };
    bool show_upload{ true };
    bool show_download{ true };
    bool show_uptime{ true };
    bool show_temperature{ true };
    bool show_disk{ true };
    bool show_cpu{ true };
};

class CRemoteMonitor
{
public:
    static CRemoteMonitor& Instance();

    void Start();
    void Stop();

    bool IsEnabled() const { return m_enabled; }
    int ExtraRows() const;

    bool ShowUpload() const { return m_show_upload; }
    bool ShowDownload() const { return m_show_download; }
    bool ShowUptime() const { return m_show_uptime; }
    bool ShowTemperature() const { return m_show_temperature; }
    bool ShowDisk() const { return m_show_disk; }
    bool ShowCpu() const { return m_show_cpu; }

    RemoteMonitorSnapshot GetSnapshot() const;
    RemoteMonitorConfig GetConfig() const;
    void ApplyConfig(const RemoteMonitorConfig& config);
    bool ShowSettings(HWND parent);

    CString FormatSpeed(double bytes_per_second) const;
    CString FormatUptime(unsigned long long seconds) const;

private:
    CRemoteMonitor() = default;
    ~CRemoteMonitor();
    CRemoteMonitor(const CRemoteMonitor&) = delete;
    CRemoteMonitor& operator=(const CRemoteMonitor&) = delete;

    void LoadConfig();
    void SaveConfig() const;
    void Worker();
    bool RunStreamingSession();
    void HandleLine(const std::string& line);
    void ParseFrame(const std::vector<std::string>& fields);

    std::wstring GetConfigPath() const;
    std::wstring ResolveExecutable(const std::wstring& transport) const;
    std::wstring BuildRemoteCommand() const;
    std::wstring BuildClientCommand() const;

private:
    std::atomic_bool m_stop{ false };
    std::atomic_bool m_started{ false };
    std::thread m_thread;

    mutable std::mutex m_data_mutex;
    RemoteMonitorSnapshot m_snapshot;

    mutable std::mutex m_process_mutex;
    HANDLE m_process{ nullptr };

    bool m_enabled{};
    bool m_show_upload{ true };
    bool m_show_download{ true };
    bool m_show_uptime{ true };
    bool m_show_temperature{ true };
    bool m_show_disk{ true };
    bool m_show_cpu{ true };

    std::wstring m_transport{ L"ssh" };
    std::wstring m_host;
    std::wstring m_user;
    std::wstring m_key_path;
    int m_port{ 22 };
    int m_interval_ms{ 1000 };

    unsigned long long m_prev_cpu_total{};
    unsigned long long m_prev_cpu_idle{};
    unsigned long long m_prev_rx{};
    unsigned long long m_prev_tx{};
    ULONGLONG m_prev_tick{};
};
