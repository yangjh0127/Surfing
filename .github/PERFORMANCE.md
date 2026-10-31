# Network event overhead: first optimization batch

## Changes and expected effects

- Network and routing-table watches subscribe to `w` (close after writing) rather
  than every event. Both handlers already restrict their main work to `w`.
  Opening, reading and metadata changes no longer spawn those handlers.
  Reference: https://www.busybox.net/downloads/BusyBox.html#inotifyd
- `net.inotify` rejects other events before sourcing configuration/firewall code.
  `ctr.inotify` exits successfully instead of attempting a top-level `return`.
- When SSID filtering and diagnostic logging are both off, the controller skips
  `cmd wifi status` and its possible fallback `dumpsys wifi`. BSSID acquisition
  remains necessary to distinguish WiFi from cellular service.
- When `netfilt_logs=false`, the controller skips the date/awk/copy operations that
  prune diagnostic logs. Existing logs are pruned when diagnostics are enabled.
- Connection cleanup has a 2-second connect timeout and a 5-second total timeout,
  so a stalled local controller cannot block that callback indefinitely.
- The network handler explicitly exits successfully after handling an event.

## Validation

Run `python3 -m unittest discover -s .github/tests -v` with Bash available.
On Windows, set `SURFING_TEST_BASH` to the Git Bash executable first.
The six tests execute handlers against temporary configuration and mock Android
commands. They cover ignored events, optional SSID acquisition, log retention,
authenticated connection cleanup arguments, and burst suppression.
Syntax checks: `bash -n` on the three changed scripts.

These checks do not emulate Android Binder, real inotify delivery, iptables,
BusyBox ash or the mihomo process. No device CPU, RSS or battery improvement
percentage has been measured. The APKs in this repository do not include their
application source; this batch changes the module scripts only.

## Device acceptance and comparison

Use the same phone, core version, subscription and configuration for both builds.
Restart the module or reboot after installing so the new watch masks take effect.

1. Confirm proxy startup, DNS, TCP and UDP connectivity in the configured mode.
2. Test WiFi/cellular transitions with network control disabled and enabled.
3. With control enabled, test SSID and MAC whitelist/blacklist decisions, logging
   on/off, and the module disable switch. Confirm manual stop remains respected.
4. Enable diagnostics and confirm SSID output and old-log pruning still work.
5. Stop or stall the local controller and verify subsequent events are processed
   after the cleanup request times out. Confirm ordinary cleanup still works.
6. Compare equal idle and repeated network-switch workloads. Record `top`,
   `/proc/<pid>/status` for the core and persistent watchers, and `dumpsys
   batterystats` under the same screen/network conditions. Count handler starts
   with temporary instrumentation if tracing tools are unavailable.

Rollback by reinstalling the previous module and restarting/rebooting. Existing
routing policies and mihomo defaults are unchanged by this batch.

## 第二批：事件合并、日志 I/O 与可选省电配置

网络与控制回调先标记待处理事件，再异步获取 flock 文件锁。获得锁的工作进程
等待一秒、合并期间的事件后读取当前状态。处理期间的新事件会触发后续一轮；
释放锁附近的事件也会重新检查，避免简单限流漏掉最后一次变化。

内部刷新跳过原来的两秒时间门限，连接清理的十五秒限流保留。两个处理器各自
串行化，没有常驻轮询。flock 不可用时回退到原有同步流程；锁由文件描述符持有，
进程退出时释放。启动时的六十秒等待改为独立定时任务，不阻塞正常事件；没有
flock 时保留旧行为。

`box.service status/stop` 和重复 start 不再扫描日志。真正启动前才清理，且只
遍历 run 与核心 log 目录。

### 可选省电配置

`box_bll/scripts/power-profile.sh` 读取现有配置，向标准输出生成完整配置，不会
自行覆盖或启用。针对仓库使用的块状 YAML 格式，只调整：

- `find-process-mode: strict`：按需识别进程，保留 PROCESS-NAME 规则。
- health-check 下大于零且小于 900 秒的数字 interval 提升至 900 秒。零、较长
  间隔、非数字配置保留；订阅更新间隔不变。

代价是面板可能显示较少的进程信息，以及健康检查发现故障更慢。默认 config.yaml
未修改。不要把输出重定向到输入文件本身。

在手机 Root shell 中进入 `/data/adb/box_bll` 后运行：

```sh
sh scripts/power-profile.sh > clash/config.powersave.yaml
bin/clash -t -d clash -f clash/config.powersave.yaml
```

确认校验通过后，先备份原配置，再选择是否替换并重启模块服务；恢复备份即可
回退。使用 SurfingTile 配置覆写时需同步检查覆写项。订阅配置更新后应重新生成，
不要把旧生成文件覆盖到后续更新的配置上。

字段依据：[进程识别](https://github.com/MetaCubeX/Meta-Docs/blob/main/docs/config/general.md)、
[健康检查](https://wiki.metacubex.one/config/proxy-providers/)。

### 验证范围

Linux flock 测试覆盖短时事件合并、处理期间的最新状态重放。其他新增测试覆盖
省电配置最小差异、长间隔和停用检查保留、status 无日志扫描。主机测试不代表
Android 真机验证。安装后仍需检查 WiFi/蜂窝频繁切换、模块开关、手动停止、
SSID/MAC 过滤，以及延迟约一秒的策略更新是否可接受。
