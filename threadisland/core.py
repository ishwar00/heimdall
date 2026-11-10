"""Shared by every module: home, the clock, the 7-day window, the errors shown in the panel, small helpers."""
import datetime
import json
import os
import re
import subprocess
import time


HOME = os.path.expanduser('~')
WINDOW_DAYS = 7
# THREADISLAND_NOW pins the clock for tests (tests/test_golden.py); unset in normal use
NOW = float(os.environ.get('THREADISLAND_NOW') or time.time())
TODAY = datetime.date.fromtimestamp(NOW)
# Same window as Codex's activity view: today plus the previous 6 local days
CUTOFF = time.mktime((TODAY - datetime.timedelta(days=WINDOW_DAYS - 1)).timetuple())
# A thread is in Priority while it has had activity in the last 2 h; 2 h without any activity ends its run
IDLE_OUT = 2 * 3600
# one bad record (a transcript that vanished, a file mid-write) is reported here and skipped, not the whole source
ERRORS = []


def run(cmd, stdin=None, timeout=10):
    try:
        return subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ''


def ago(ts):
    s = max(0, NOW - ts)
    for unit, n in (('d', 86400), ('h', 3600), ('m', 60)):
        if s >= n:
            return f'{int(s // n)}{unit}'
    return 'now'


def processes():
    rows = []
    for line in run(['ps', '-axo', 'pid=,ppid=,tty=,args=']).splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            rows.append({'pid': int(parts[0]), 'ppid': int(parts[1]), 'tty': '/dev/' + parts[2], 'args': parts[3]})
    return rows


def row(key, ts, src, state, title, detail, action, arg, cwd=''):
    # key is stable across refreshes (thread/job/session id); ts is your last message (day sections sort on
    # it); each source then sets 'active' (last activity), 'entered' (start of the current run) and 'created'
    return {'key': key, 'ts': ts, 'src': src, 'state': state, 'title': title, 'detail': detail,
            'action': action, 'arg': arg, 'cwd': cwd}


def plain(md):
    """One-line Markdown as plain text: [label](url) -> label, drop ** and backticks."""
    return re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', md).replace('**', '').replace('`', '')


def read_json(path):
    with open(path) as fh:
        return json.load(fh)


def loads(line):
    try:
        return json.loads(line)
    except ValueError:
        return {}


def epoch(iso):
    return datetime.datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp()


def checked(cmd, stdin=None):
    """Run a jump command; None on success, else what went wrong (shown in the panel)."""
    p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=30)
    return None if p.returncode == 0 else (p.stderr.strip() or f'{cmd[0]} exited with {p.returncode}')


JUMPS = f'{HOME}/Library/Application Support/ThreadIsland/jumps.log'


def log_jump(kind, what, outcome):
    """One line per click, so a jump that opened the wrong thing says why afterwards; kept to about 64 KB."""
    try:
        if os.path.exists(JUMPS) and os.path.getsize(JUMPS) > 64 * 1024:
            os.replace(JUMPS, JUMPS + '.1')
        with open(JUMPS, 'a') as fh:
            fh.write(f'{datetime.datetime.now().isoformat(timespec="seconds")}\t{kind}\t{what}\t{outcome}\n')
    except OSError:
        pass
