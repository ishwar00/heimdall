"""Reading Codex rollouts and Claude Code transcripts backwards: activity, the current run, turn state, questions."""
import json
import os

from . import core
from .core import plain, loads, epoch


def lines_back(path, chunk=256 * 1024):
    """Lines of a file, newest first, read from the end in chunks that double up to 4 MB: most answers are
    in the last few hundred KB. Memory is a chunk plus the longest line."""
    with open(path, 'rb') as fh:
        pos, carry = os.path.getsize(path), b''
        while pos > 0:
            n = min(chunk, pos)
            chunk = min(chunk * 2, 4 * 1024 * 1024)
            pos -= n
            fh.seek(pos)
            lines = (fh.read(n) + carry).split(b'\n')
            carry = lines.pop(0) if pos > 0 else b''  # may continue in the previous chunk
            for line in reversed(lines):
                if line:
                    yield line


def line_time(line, last):
    """A log line's timestamp without decoding the line: Codex puts it first, Claude after the message."""
    i = line.rfind(b'"timestamp":"') if last else line.find(b'"timestamp":"')
    if i < 0:
        return None
    try:
        return epoch(line[i + 13:line.find(b'"', i + 13)].decode())
    except ValueError:
        return None


def is_activity(line, claude):
    """Conversation records only: not the bookkeeping both tools write into idle threads (Claude's system
    notices, bridge records and local commands like /exit, Codex's settings sync when the app loads a thread)."""
    if claude:
        # replies, your messages, tool results; not other user-typed records such as a /exit when you only
        # attached to look, or local command output
        return (b'"type":"assistant"' in line
                or b'"type":"user"' in line and (b'"kind":"human"' in line or b'"tool_use_id"' in line))
    return (b'"type":"response_item"' in line or b'"type":"event_msg"' in line) and b'"thread_settings_applied"' not in line


def scan_log(kind, path, sent=False, title=False):
    """Read a Codex rollout or Claude transcript backwards, only as far as needed, for:
    active  - its newest entry;
    entered - the start of its current run of activity (the oldest entry with no IDLE_OUT gap after it),
              only while the thread is in Priority; the same rule that puts it there, so a long turn or a
              long wait on you can't reorder Priority without the thread leaving it;
    turn    - Codex: its latest turn event; sent, title - Claude, when asked: your last message, its name;
    asked   - Codex: the question it asked you (request_user_input) if you haven't answered since."""
    out = {}
    claude = kind == 'claude'
    need_run, need_sent, need_title, need_turn, need_ask = True, sent, title, not claude, not claude
    run_start = ai = None
    scanned = 0
    turn_times = []  # Codex: activity times newer than the last task_started seen, kept until we know who started it

    def feed(t):
        nonlocal need_run, run_start
        if 'active' not in out:
            out['active'] = t
            need_run = core.NOW - t < core.IDLE_OUT
        elif run_start - t >= core.IDLE_OUT:
            out['entered'], need_run = run_start, False
        run_start = t if need_run else run_start

    for line in lines_back(path):
        scanned += len(line) + 1
        if need_run and is_activity(line, claude):
            t = line_time(line, claude)
            if t is not None:
                if claude:
                    feed(t)
                else:
                    turn_times.append(t)
        if need_run and not claude and b'"task_started"' in line:
            payload = loads(line).get('payload') or {}
            trigger = (payload.get('turn_attribution') or {}).get('turn_trigger') or ''
            # a scheduled automation turn runs on its own, sometimes for hours; it isn't you working on the thread
            for t in ([] if trigger.startswith('automation') else turn_times):
                if need_run:
                    feed(t)
            turn_times = []
        if need_sent and b'"kind":"human"' in line:
            rec = loads(line)
            if rec.get('type') == 'user' and (rec.get('origin') or {}).get('kind') == 'human':
                out['sent'], need_sent = epoch(rec['timestamp']), False
        if need_title:
            if b'"type":"custom-title"' in line:
                out['title'], need_title = loads(line).get('customTitle'), False
            elif ai is None and b'"type":"ai-title"' in line:
                ai = loads(line).get('aiTitle')
            if scanned > 8 * 1024 * 1024:  # renames are re-logged often; an older one isn't the latest
                need_title = False
        if need_turn and (b'"task_' in line or b'"turn_aborted"' in line):
            payload = loads(line).get('payload') or {}
            if payload.get('type') in ('task_started', 'task_complete', 'turn_aborted'):
                out['turn'], need_turn = payload, False
        if need_ask and b'"type":"UserMessage"' in line:  # your message or answer; anything older is answered
            need_ask = False
        elif need_ask and b'"name":"request_user_input' in line:  # also listed in tool definitions
            payload = loads(line).get('payload') or {}
            if payload.get('type') == 'function_call':
                try:
                    questions = json.loads(payload.get('arguments') or '{}').get('questions') or [{}]
                except ValueError:
                    questions = [{}]
                out['asked'], need_ask = plain(questions[0].get('title') or questions[0].get('question') or '') or 'Asked you a question', False
        if not (need_run or need_sent or need_title or need_turn or need_ask):
            break
    for t in turn_times:  # before the first turn started
        if need_run:
            feed(t)
    if need_run and run_start is not None:  # the run reaches back to the first entry
        out['entered'] = run_start
    if not out.get('title'):
        out['title'] = ai
    return out


def logged(r, log, fallback_active, source=None):
    """Fill a row's activity fields from its log, falling back to the source's own timestamps.
    source: (kind, log path), read again for the PRs the thread created."""
    if source and source[1]:
        r['log'] = source
    # a log with no conversation records in reach has no activity; the source's own times include bookkeeping
    r['active'] = log.get('active', 0) if log else fallback_active
    if log.get('entered'):
        r['entered'] = log['entered']
    return r
