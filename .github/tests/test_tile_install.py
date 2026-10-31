"""Installer regression tests use mocked package-manager commands only."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == 'posix' and shutil.which('bash'), 'Linux Bash required')
class TileInstallTests(unittest.TestCase):
    def run_install(self, package='', choice=0, direct=False):
        source = (ROOT / 'customize.sh').read_text(encoding='utf-8')
        functions = []
        for name in ['install_surfingtile_apk', 'tile_is_installed', 'install_surfingtile_if_needed']:
            match = re.search(r'^' + name + r'\(\) \{\n.*?^\}', source, re.M | re.S)
            self.assertIsNotNone(match, name)
            functions.append(match.group())
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'calls'
            harness = '''
print_lang() { :; }
choose_volume_key() { return "$CHOICE"; }
pm() {
    if [ "$1" = path ]; then [ "$2" = "$INSTALLED" ]; return; fi
    printf '%s\\n' "$*" >> "$CALLS"
}
unzip() { : > "$INSTALL_DIR/com.github.surfing.apk"; }
''' + '\n'.join(functions)
            harness += '\n' + ('install_surfingtile_apk' if direct else 'install_surfingtile_if_needed')
            result = subprocess.run(['bash', '-c', harness], capture_output=True, text=True,
                                    env=dict(os.environ, INSTALLED=package, CHOICE=str(choice),
                                             CALLS=str(state), INSTALL_DIR=tmp, SURFING_TILE_ZIP='fixture.zip'))
            self.assertEqual(result.returncode, 0, result.stderr)
            return state.read_text() if state.exists() else ''

    def test_module_upgrade_preserves_existing_new_app(self):
        self.assertEqual(self.run_install('com.github.surfing'), '')

    def test_module_upgrade_preserves_existing_legacy_app(self):
        self.assertEqual(self.run_install('com.surfing.tile'), '')

    def test_fresh_module_install_also_preserves_existing_app(self):
        self.assertEqual(self.run_install('com.github.surfing', direct=True), '')

    def test_missing_app_can_be_skipped(self):
        self.assertEqual(self.run_install(choice=1), '')

    def test_missing_app_installs_without_replace_flag(self):
        calls = self.run_install()
        self.assertTrue(calls.startswith('install '), calls)
        self.assertNotIn('install -r', calls)
        self.assertNotIn('uninstall', calls)


    def test_build_packages_custom_apk_and_matching_metadata(self):
        source = (ROOT / 'build.sh').read_text(encoding='utf-8')
        packaging = source[source.index('APK_DIR='):source.index('version=$(grep')]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apk_dir = root / 'app/version/com.github.surfing'
            apk_dir.mkdir(parents=True)
            (apk_dir / 'SurfingTile_7.0.0_release.apk').write_text('original')
            (apk_dir / 'SurfingTile_7.0.0_no_update.apk').write_text('custom')
            (apk_dir / 'release.json').write_text('[{"versionCode": 99999999,"versionName":"future"}]')
            harness = 'zip() { cp com.github.surfing.apk "$RESULT"; cp version "$METADATA"; }\n'
            result = subprocess.run(['bash', '-c', harness + packaging], cwd=root,
                                    capture_output=True, text=True,
                                    env=dict(os.environ, RESULT=str(root / 'result'),
                                             METADATA=str(root / 'metadata')))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / 'result').read_text(), 'custom')
            self.assertEqual((root / 'metadata').read_text(),
                             'versionCode=26101301\nversionName=7.0.0-no-update\n')


if __name__ == '__main__':
    unittest.main()
