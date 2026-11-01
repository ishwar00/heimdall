"""Opening rows: Warp Tab Config strings, finding Warp, and a failed jump reported back to the panel."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from threadisland import terminals

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import tomllib  # 3.11+
except ImportError:
    tomllib = None


class Terminals(unittest.TestCase):
    @unittest.skipIf(tomllib is None, 'needs Python 3.11+ to parse TOML')
    def test_toml_strings_round_trip(self):
        for s in ('plain', 'a"b\\c', 'tab\there', 'nl\nx', 'del\x7f', 'emoji \U0001f642'):
            self.assertEqual(tomllib.loads(f'k = {terminals.toml_str(s)}')['k'], s)

    def test_warp_executable(self):
        self.assertTrue(terminals.WARP_EXE.match('/Applications/Warp.app/Contents/MacOS/stable terminal-server'))
        self.assertFalse(terminals.WARP_EXE.match('vim /tmp/Warp.app/notes'))
        self.assertFalse(terminals.WARP_EXE.match('claude --resume x Warp.app/'))

    def test_failed_jump_is_reported(self):
        with tempfile.TemporaryDirectory() as bin_dir:
            with open(f'{bin_dir}/open', 'w') as fh:  # a failing `open`, so nothing reaches LaunchServices
                fh.write("#!/bin/sh\necho 'no app for that link' >&2\nexit 1\n")
            os.chmod(f'{bin_dir}/open', 0o755)
            row = {'action': 'url', 'arg': 'example://x', 'key': 'k', 'cwd': ''}
            p = subprocess.run([sys.executable, '-B', os.path.join(ROOT, 'threads'), '--jump'], input=json.dumps(row),
                               env={'PATH': f'{bin_dir}:/usr/bin:/bin', 'HOME': bin_dir},
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(json.loads(p.stdout)['error'], 'no app for that link')


if __name__ == '__main__':
    unittest.main()
