"""Opening rows: Warp Tab Config strings, finding Warp, and a failed jump reported back to the panel."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

from threadisland import cli, core, terminals

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


class JumpRecheck(unittest.TestCase):
    """A row that would open a new terminal is checked again at the click: the panel's copy can be a refresh old."""
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.jumped = []
        for module, name, value in ((core, 'JUMPS', os.path.join(tmp.name, 'jumps.log')),
                                    (cli, 'jump', lambda row: self.jumped.append(row)),
                                    (sys, 'argv', ['threads', '--jump']), (sys, 'stdout', io.StringIO())):
            self.addCleanup(setattr, module, name, getattr(module, name))
            setattr(module, name, value)

    def click(self, row, now):
        self.addCleanup(setattr, cli, 'thread_rows', cli.thread_rows)
        cli.thread_rows = lambda: now
        self.addCleanup(setattr, sys, 'stdin', sys.stdin)
        sys.stdin = io.StringIO(json.dumps(row))
        cli.main()
        return self.jumped[-1]

    STALE = {'key': 'job1', 'src': 'claude-bg', 'action': 'tab', 'arg': 'claude attach job1', 'cwd': '/w'}

    def test_attached_since_goes_to_its_terminal(self):
        now = [dict(self.STALE, action='url', arg='warp://session/abc')]
        self.assertEqual(self.click(self.STALE, now)['arg'], 'warp://session/abc')
        with open(core.JUMPS) as fh:
            self.assertIn('opened since the last refresh', fh.read())

    def test_still_closed_opens_a_tab(self):
        self.assertEqual(self.click(self.STALE, [dict(self.STALE)])['action'], 'tab')

    def test_gone_from_the_list_opens_as_clicked(self):
        self.assertEqual(self.click(self.STALE, [])['action'], 'tab')


if __name__ == '__main__':
    unittest.main()
