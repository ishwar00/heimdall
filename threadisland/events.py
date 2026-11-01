"""What the agents' own hooks reported (hooks/ti-event): which turns are running and which wait on your approval.

The hooks add what the logs can't show: a Codex turn waiting for you to approve a command, a Claude permission
prompt, a turn that runs a long command without writing anything. Threads with no hook events (before the
hooks were installed, or where they don't fire) keep the state read from their logs.
"""
import os

from . import core

EVENTS = f'{core.HOME}/Library/Application Support/ThreadIsland/events.jsonl'
ROTATE_AT = 512 * 1024  # then it moves to events.jsonl.1, replacing the previous one; only recent events matter
# an unfinished turn counts as running this long after its last event; one that died without a Stop then clears
OPEN_FOR = 30 * 60
WAIT_FOR = 24 * 3600
# a log written this soon after an approval request was already being written when it came (Codex: the tool
# call's usage record, measured at most 0.4 s after the hook), not an answer
WRITE_SLACK = 1.5
ENDS = ('Stop', 'Interrupt', 'SessionEnd')
WAITS = ('PermissionRequest', 'permission_prompt', 'elicitation_dialog')


def sessions():
    """(tool, session id) -> {'last': time of its last event, 'open': a turn started and hasn't ended,
    'wait': when it asked for your approval, if nothing has happened since}."""
    if os.path.exists(EVENTS) and os.path.getsize(EVENTS) > ROTATE_AT:
        os.replace(EVENTS, EVENTS + '.1')  # a hook writing right now appends to the old file, which is read below
    out = {}
    for path in (EVENTS + '.1', EVENTS):
        try:
            with open(path, 'rb') as fh:
                lines = fh.read().split(b'\n')
        except OSError:
            continue
        for line in lines:
            e = core.loads(line) if line else {}
            event, session, t = e.get('event'), e.get('session'), e.get('t')
            if not (isinstance(event, str) and isinstance(session, str) and isinstance(t, (int, float))):
                continue
            if event == 'Notification' and e.get('type') not in WAITS or event == 'SessionStart':
                continue  # Claude's "waiting for input" reminder, a session opening: no turn activity
            s = out.setdefault((e.get('tool'), session), {'last': 0, 'open': False, 'wait': None})
            s['last'] = t
            s['open'] = event not in ENDS
            s['wait'] = t if event in WAITS or e.get('type') in WAITS else None
    return out


def hooked(s, approval=True):
    """'needs you', 'working' or None for one session's events. approval: its wait is really on you (a Codex
    turn whose reviewer is you, not Codex's automatic reviewer)."""
    if not s:
        return None
    if s['wait'] and approval and core.NOW - s['wait'] < WAIT_FOR:
        return 'needs you'
    if s['open'] and core.NOW - s['last'] < OPEN_FOR:
        return 'working'
    return None


APPROVAL = 'Waiting for your approval'


