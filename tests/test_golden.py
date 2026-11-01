"""End to end: `threads` over the synthetic home in fixtures.py, compared with golden.json.

A change that moves any row, section, state or detail fails here. If the change is intended, regenerate
with UPDATE_GOLDEN=1 and review the diff of golden.json like code.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

import fixtures

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(ROOT, 'tests', 'golden.json')
NOW = 1793172600.0  # 2026-10-28 13:00 in Asia/Kolkata


def listing(home):
    env = {'HOME': home, 'TZ': 'Asia/Kolkata', 'THREADISLAND_NOW': str(NOW), 'PATH': f'{home}/bin:/usr/bin:/bin'}
    p = subprocess.run([sys.executable, '-B', os.path.join(ROOT, 'threads')], env=env, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise AssertionError(p.stderr)
    return json.loads(p.stdout.replace(home, '~'))


class Golden(unittest.TestCase):
    def test_listing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.realpath(tmp)
            fixtures.build(home, NOW, os.getpid(), os.getppid())
            first = listing(home)
            second = listing(home)  # reads the PR logs from the offsets the first run saved
        if os.environ.get('UPDATE_GOLDEN'):
            with open(GOLDEN, 'w') as fh:
                json.dump(first, fh, indent=1, sort_keys=True)
                fh.write('\n')
        with open(GOLDEN) as fh:
            golden = json.load(fh)
        self.assertEqual(first, golden)
        self.assertEqual(second, golden)


if __name__ == '__main__':
    unittest.main()
