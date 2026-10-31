"""Linux regression tests for queueing, optional profiles and service I/O."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
BASH = os.environ.get('SURFING_TEST_BASH') or shutil.which('bash')


@unittest.skipUnless(os.name == 'posix' and shutil.which('flock'), 'Linux flock required')
class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.handler = self.root / 'handler'
        self.handler.write_text('''#!/bin/sh
cat "$NETWORK_EVENT_DIR/state" >> "$NETWORK_EVENT_DIR/results"
: > "$NETWORK_EVENT_DIR/ready"
sleep 0.2
''')
        self.handler.chmod(0o755)
        (self.root / 'state').write_text('first\n')
        self.env = dict(os.environ, NETWORK_EVENT_DIR=str(self.root))

    def queue(self, count=1):
        return subprocess.Popen(
            [BASH, '-c', '. "$1"; for ((i=0;i<$3;i++)); do queue_network_event "$2" test; done; wait',
             'test', str(ROOT / 'box_bll/scripts/network.events'), str(self.handler), str(count)],
            env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

    def finish(self, process):
        out, err = process.communicate(timeout=8)
        self.assertEqual(process.returncode, 0, out + err)

    def test_burst_is_coalesced(self):
        self.finish(self.queue(20))
        self.assertEqual((self.root / 'results').read_text(), 'first\n')

    def test_event_during_processing_replays_latest_state(self):
        process = self.queue()
        try:
            deadline = time.monotonic() + 5
            while not (self.root / 'ready').exists():
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
            (self.root / 'state').write_text('latest\n')
            self.finish(self.queue())
            self.finish(process)
            self.assertEqual((self.root / 'results').read_text(), 'first\nlatest\n')
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


@unittest.skipUnless(BASH, 'Bash required')
class ProfileAndServiceTests(unittest.TestCase):
    def test_profile_changes_only_intended_defaults(self):
        source = ROOT / 'box_bll/clash/config.yaml'
        before = source.read_text(encoding='utf-8')
        result = subprocess.run([BASH, str(ROOT / 'box_bll/scripts/power-profile.sh'), str(source)],
                                capture_output=True, text=True, check=True)
        expected = before.replace('find-process-mode: always', 'find-process-mode: strict')
        expected = expected.replace('    interval: 300', '    interval: 900')
        self.assertEqual(result.stdout, expected)
        self.assertEqual(source.read_text(encoding='utf-8'), before)

    def test_profile_preserves_disabled_and_longer_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'config.yaml'
            original = ('find-process-mode: always\nhealth-check:\n  interval: 0\n'
                        'provider:\n  health-check:\n    interval: 1800\n  interval: 60\n')
            source.write_text(original)
            result = subprocess.run([BASH, str(ROOT / 'box_bll/scripts/power-profile.sh'), str(source)],
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, original.replace('always', 'strict'))

    def test_status_does_not_scan_log_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = (ROOT / 'box_bll/scripts/box.service').read_text(encoding='utf-8')
            source = source.replace('/data/adb/box_bll/bin:', '')
            target = root / 'box.service'
            target.write_text(source)
            (root / 'box.config').write_text(
                f'box_path="{root}"\nrun_path="${{box_path}}/run"\nbin_name=clash\n')
            for name, body in [('pidof', 'exit 1'), ('find', 'echo scanned > "$SCAN"')]:
                stub = root / name
                stub.write_text('#!/bin/sh\n' + body + '\n')
                stub.chmod(0o755)
            result = subprocess.run([BASH, str(target), 'status'], capture_output=True, text=True,
                                    env=dict(os.environ, PATH=str(root) + ':' + os.environ['PATH'],
                                             SCAN=str(root / 'scan')))
            self.assertIn('clash', result.stdout)
            self.assertFalse((root / 'scan').exists())


if __name__ == '__main__':
    unittest.main()
