"""Claude Code threads: the desktop Code tab, background jobs and live CLI sessions."""
import glob
import json
import os
import re

from . import core
from .core import row, epoch
from .logs import scan_log, logged
from .terminals import focus_target


def claude_desktop_rows(sessions):
    busy = {d.get('sessionId') for d in sessions if d.get('status') == 'busy'}
    rows = []
    pattern = f'{core.HOME}/Library/Application Support/Claude/claude-code-sessions/*/*/local_*.json'
    for f in glob.glob(pattern):
        try:
            if os.path.getmtime(f) < core.CUTOFF:  # files are large; mtime >= lastActivityAt, so skip unparsed
                continue
            try:
                d = json.load(open(f))
            except ValueError:  # being rewritten right now; next refresh reads it
                continue
            # your last message, like Codex's recency_at; lastActivityAt moves with every agent step
            ts = (d.get('latestUserFrameAt') or d.get('lastActivityAt') or 0) / 1000
            if d.get('isArchived') or ts < core.CUTOFF:
                continue
            summary = d.get('postTurnSummary') or {}
            # a turn in progress wins over the previous turn's summary
            state = ('working' if d.get('cliSessionId') in busy
                     else 'needs you' if summary.get('status_category') == 'blocked' else '')
            path = transcript_path(d.get('cliSessionId'))
            log = scan_log('claude', path) if path else {}
            r = row(d['sessionId'], ts, 'claude-app', state, d.get('title') or '(untitled)',
                    summary.get('status_detail') or d.get('cwd', ''),
                    'url', f"claude://code/continue?session={d['sessionId']}")
            r['created'] = (d.get('createdAt') or 0) / 1000
            rows.append(logged(r, log, (d.get('lastActivityAt') or 0) / 1000, ('claude', path)))
        except Exception as e:  # noqa: BLE001
            core.ERRORS.append(f'Claude app {os.path.basename(f)}: {type(e).__name__}: {e}')
    return rows


def transcript_path(session_id):
    paths = glob.glob(f'{core.HOME}/.claude/projects/*/{session_id}.jsonl') if session_id else []
    return paths[0] if paths else None


def live_sessions():
    """Claude Code session records whose process is still running."""
    out = []
    for f in glob.glob(f'{core.HOME}/.claude/sessions/*.json'):
        try:
            d = json.load(open(f))
            os.kill(d['pid'], 0)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        out.append(d)
    return out


def claude_cli_rows(procs, gtty, sessions):
    proc = {p['pid']: p for p in procs}
    attached = {}  # job name/id -> where its `claude attach` runs
    for p in procs:
        m = re.search(r'\bclaude\b.*\battach\s+(\S+)', p['args'])
        if m and p['tty'] != '/dev/??':
            target = focus_target(p, gtty, proc)
            if target:
                attached[m.group(1)] = target

    live, busy_jobs = [], set()
    for d in sessions:
        if d.get('kind') == 'interactive':
            live.append(d)
        elif d.get('jobId') and d.get('status') == 'busy':
            busy_jobs.add(d['jobId'])
    # A window in agent view parks its own session as a job; an unnamed parked job is that empty window, not a thread
    parked = {d['parkedJobId'] for d in live if d.get('parkedJobId')}

    rows, seen = [], set()
    for f in glob.glob(f'{core.HOME}/.claude/jobs/*/state.json'):
        jid = os.path.basename(os.path.dirname(f))
        try:
            try:
                d = json.load(open(f))
            except ValueError:  # being rewritten right now; next refresh reads it
                continue
            mtime = os.path.getmtime(f)
            if (jid in parked and not d.get('name')) or mtime < core.CUTOFF:
                continue
            seen.add(d.get('sessionId'))
            path = transcript_path(d.get('sessionId'))
            log = scan_log('claude', path, sent=True) if path else {}
            # state.json lags a reply (stays 'blocked' until the next summary); a busy live session wins, as in `claude agents`
            state = 'working' if jid in busy_jobs else {'blocked': 'needs you'}.get(d.get('state'), d.get('state') or '')
            title = d.get('name') or d.get('displayIntent') or d.get('intent') or jid
            target = next((attached[k] for k in (jid, d.get('name'), d.get('sessionId')) if k in attached), None)
            if target:
                r = row(jid, log.get('sent') or mtime, 'claude-bg', state, title, d.get('detail') or '', *target)
            else:
                r = row(jid, log.get('sent') or mtime, 'claude-bg', state, title, d.get('detail') or '', 'tab',
                        f'claude attach {jid}', d.get('cwd') or core.HOME)
            r['created'] = epoch(d['createdAt']) if d.get('createdAt') else mtime
            rows.append(logged(r, log, mtime, ('claude', path)))
        except Exception as e:  # noqa: BLE001
            core.ERRORS.append(f'Claude job {jid}: {type(e).__name__}: {e}')

    for d in live:
        # agent-view windows aren't threads; the jobs they show are listed above
        if d.get('sessionId') in seen or d.get('parkedJobId'):
            continue
        # no terminal, no terminal session: the desktop app's own engine (listed as its desktop row) or a
        # headless `claude -p` another agent started (nothing to jump to)
        p = proc.get(d['pid'])
        if not p or p['tty'] == '/dev/??':
            continue
        try:
            path = transcript_path(d['sessionId'])
            log = scan_log('claude', path, sent=True, title=True) if path else {}
            updated = (d.get('updatedAt') or d.get('startedAt') or 0) / 1000
            state = 'working' if d.get('status') == 'busy' else ''
            title = d.get('name') if d.get('nameSource') == 'user' else None
            title = title or log.get('title') or d.get('name') or d['sessionId']
            target = focus_target(proc[d['pid']], gtty, proc) if d['pid'] in proc else None
            # other terminals (Terminal.app, iTerm2, ...) aren't supported yet: the row shows but doesn't jump
            r = row(d['sessionId'], log.get('sent') or updated, 'claude-cli', state, title, d.get('cwd', ''),
                    *(target or ('none', '')))
            r['created'] = (d.get('startedAt') or 0) / 1000
            rows.append(logged(r, log, updated, ('claude', path)))
        except Exception as e:  # noqa: BLE001
            core.ERRORS.append(f'Claude session {d.get("sessionId")}: {type(e).__name__}: {e}')
    return rows
