"""Host-side regression tests; run with python -m unittest discover -s .github/tests.

Uses Bash to model shell control flow. Android BusyBox, Binder and firewall
integration still require a rooted device.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
def shell_path(path):
    value = path.as_posix()
    if len(value) > 1 and value[1] == ':':
        return '/' + value[0].lower() + value[2:]
    return value


BASH = os.environ.get('SURFING_TEST_BASH') or shutil.which('bash')


@unittest.skipUnless(BASH, 'Bash is required')
class NetworkEvents(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Git Bash accepts forward-slash Windows paths in script contents.
        self.root = Path(self.temp.name)
        self.path = shell_path(self.root)
        self.calls = self.root / 'calls'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        (self.root / 'run').mkdir()
        self.stub('dumpsys', 'echo dumpsys >> "$CALLS"\necho "mWifiInfo BSSID: aa:bb:cc:dd:ee:ff, SSID: TestWifi,"')
        self.stub('cmd', 'echo cmd >> "$CALLS"\necho "Wifi is connected to TestWifi"')
        self.stub('ip', 'echo "inet 192.168.1.2/24"')
        self.stub('iptables', 'exit 1')
        self.stub('curl', 'printf "%s\\n" "$*" >> "$CALLS"')
        self.stub('sleep', 'exit 0')
        self.stub('pidof', 'exit 1')
        self.stub('awk', 'command /usr/bin/awk "$@"')

    def stub(self, name, body):
        target = self.bin / name
        target.write_text('#!/bin/sh\n' + body + '\n', encoding='utf-8', newline='\n')
        target.chmod(0o755)

    def prepare(self, name, config):
        source = (ROOT / 'box_bll/scripts' / name).read_text(encoding='utf-8')
        source = source.replace('#!/system/bin/sh', '#!/bin/bash', 1)
        source = source.replace('/data/adb/box_bll', self.path)
        source = source.replace('/data/adb/modules/Surfing', self.path + '/module')
        source = source.replace('/dev/tmp', self.path)
        source = source.replace('/system/bin/ip6tables', shell_path(self.bin) + '/iptables')
        source = source.replace('/system/bin/iptables', shell_path(self.bin) + '/iptables')
        source = source.replace('/system/bin/ip"', shell_path(self.bin) + '/ip"')
        target = self.root / name
        target.write_text(source, encoding='utf-8', newline='\n')
        target.chmod(0o755)
        (self.root / 'network.events').write_text(
            (ROOT / 'box_bll/scripts/network.events').read_text(encoding='utf-8'),
            encoding='utf-8', newline='\n',
        )
        (self.root / 'box.config').write_text(
            'box_path="' + self.path + '"\nrun_path="${box_path}/run"\n' + config,
            encoding='utf-8', newline='\n',
        )
        (self.root / 'box.iptables').write_text(':\n', encoding='utf-8', newline='\n')
        return target

    def run_script(self, target, event):
        env = dict(os.environ, CALLS=shell_path(self.calls), NETWORK_EVENT_DIR=self.path)
        # Set PATH inside Bash, so Git Bash does not reinterpret a Windows PATH.
        result = subprocess.run(
            [BASH, '-c', 'export PATH="$1:$PATH"; bash "$2" "$3"',
             'test', shell_path(self.bin), shell_path(target), event],
            env=env, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_unrelated_net_event_exits_before_loading_helpers(self):
        script = self.prepare('net.inotify', 'exit 99\n')
        self.run_script(script, 'r')
        self.assertFalse(self.calls.exists())

    def test_unrelated_control_event_exits_cleanly(self):
        script = self.prepare('ctr.inotify', 'exit 99\n')
        self.run_script(script, 'r')
        self.assertFalse(self.calls.exists())

    @unittest.skipUnless(os.name == 'posix' and shutil.which('flock'), 'Linux flock required')
    def test_control_write_reaches_worker_without_requeueing(self):
        script = self.prepare('ctr.inotify', 'echo loaded >> "$CALLS"\nexit 0\n')
        self.run_script(script, 'w')
        deadline = time.monotonic() + 3
        while not self.calls.exists():
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.01)
        self.assertEqual(self.calls.read_text(), 'loaded\n')

    def test_connection_cleanup_has_bounded_time(self):
        script = self.prepare('net.inotify', 'bin_name=clash\nipv6=enable\n')
        (self.root / 'boot_stable.flag').touch()
        clash = self.root / 'clash'
        clash.mkdir()
        (clash / 'config.yaml').write_text('external-controller: 127.0.0.1:9090\nsecret: test\n')
        self.run_script(script, '__network_worker')
        calls = self.calls.read_text()
        self.assertIn('--connect-timeout 2 --max-time 5', calls)
        self.assertIn('Authorization: Bearer test', calls)
        self.assertIn('http://127.0.0.1:9090/connections', calls)
        # A burst inside the existing debounce interval must not issue another DELETE.
        self.run_script(script, '__network_worker')
        self.assertEqual(self.calls.read_text(), calls)

    def check_control(self, filtering, logging):
        script = self.prepare('ctr.inotify', '\n'.join([
            'enable_network_service_control=true',
            'bypass_via_iptables=true', 'enable_wifi_proxy=true',
            'enable_mac_filter=false', f'enable_ssid_filter={filtering}',
            f'netfilt_logs={logging}', 'use_wifi_list_mode=blacklist',
            'blacklist_wifi_ssids=OtherWifi',
        ]) + '\n')
        log = self.root / 'run/net_debug.log'
        log.write_text('2000-01-01 00:00:00 - old entry\n')
        self.run_script(script, '__network_worker')
        return self.calls.read_text(), log.read_text()

    def test_unused_ssid_and_disabled_logs_do_no_extra_work(self):
        calls, log = self.check_control('false', 'false')
        self.assertEqual(calls.splitlines(), ['dumpsys'])
        self.assertIn('old entry', log)

    def test_ssid_filter_still_queries_ssid(self):
        calls, _ = self.check_control('true', 'false')
        self.assertEqual(calls.splitlines(), ['dumpsys', 'cmd'])

    def test_diagnostics_still_query_ssid_and_prune_logs(self):
        calls, log = self.check_control('false', 'true')
        self.assertEqual(calls.splitlines(), ['dumpsys', 'cmd'])
        self.assertNotIn('old entry', log)
        self.assertIn('TestWifi', log)


if __name__ == '__main__':
    unittest.main()
