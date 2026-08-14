# TrafficMonitor Remote Monitor Extension

目标：在原 TrafficMonitor 主窗口内部增加远程服务器监控，不创建额外窗口。

支持：

- SSH / Tailscale 网络
- CPU
- 内存
- 网络上传下载
- uptime
- 温度
- 磁盘占用

设计：

RemoteMonitor 后台线程采集数据，TrafficMonitor 原绘制流程负责显示。

数据来源：

```bash
/proc/stat
/proc/net/dev
/proc/uptime
/proc/meminfo
df /
/sys/class/thermal
```
