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
