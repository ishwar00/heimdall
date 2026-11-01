"""Codex threads, desktop app and CLI, from its state database and rollout files."""
import glob
import os
import re
import sqlite3

from . import core
from .core import run, row, plain
from .events import APPROVAL, WRITE_SLACK, hooked
from .logs import scan_log, logged
from .terminals import focus_target


def codex_turn(turn, rollout, asked=None):
    """(state, last reply) from a Codex rollout's latest turn event: a started turn that is still being
    written is working; task_complete carries the reply shown in Codex's sidebar. An unanswered question
    wins: the agent keeps polling while it waits for your answer, which would otherwise read as working."""
    if asked:
        return 'needs you', asked
    kind = (turn or {}).get('type')
    if kind == 'task_started':
        # Codex writes nothing while a turn waits on approval or hangs, so only a fresh write counts as working
        return ('working' if core.NOW - os.path.getmtime(rollout) < 600 else ''), None
    if kind == 'task_complete':
        return '', plain((turn.get('last_agent_message') or '').strip().split('\n')[0]) or None
    return '', None


def codex_rows(procs, gtty, events):
    dbs = sorted(glob.glob(f'{core.HOME}/.codex/state_*.sqlite'),
                 key=lambda p: int(re.search(r'state_(\d+)', p).group(1)))
    if not dbs:
        return []
    # unread: Codex's blue dot, a finished turn you haven't opened yet; cleared when you open the thread
    query = """select id, coalesce(name, title), cwd, source, recency_at_ms, updated_at_ms, created_at_ms, rollout_path,
                      {unread}
               from threads
               where archived = 0 and coalesce(thread_source, 'user') = 'user'
                 and source in ('vscode', 'cli') and recency_at_ms >= ?"""
    receipts = """exists(select 1 from thread_read_receipts r where r.thread_id = threads.id
                                and r.first_unread_turn is not null)"""
    # not mode=ro: a read-only open fails whenever Codex has just checkpointed the WAL to 0 bytes.
    # A normal connection joins WAL locking like any reader; query_only forbids writes from here.
    con = sqlite3.connect(dbs[-1], timeout=2)
    try:
        con.execute('pragma query_only = 1')
        has_receipts = con.execute("select 1 from sqlite_master where name = 'thread_read_receipts'").fetchone()
        found = con.execute(query.format(unread=receipts if has_receipts else '0'), (core.CUTOFF * 1000,)).fetchall()
    finally:
        con.close()

    # live Codex CLI in a terminal: match the rollout file it holds open
    live, by_pid = {}, {p['pid']: p for p in procs}
    for p in procs:
        if p['tty'] != '/dev/??' and re.search(r'(^|/)codex(\s|$)', p['args']):
            target = None
            for name in run(['lsof', '-p', str(p['pid']), '-Fn'], timeout=3).splitlines():
                if name.startswith('n') and 'rollout-' in name:
                    live[name[1:]] = target = target or focus_target(p, gtty, by_pid)

    rows = []
    for tid, title, cwd, source, rec_ms, upd_ms, created_ms, rollout, unread in found:
        try:
            log = scan_log('codex', rollout) if rollout and os.path.exists(rollout) else {}
            src = 'codex' if source == 'vscode' else 'codex-cli'
            state, reply = codex_turn(log.get('turn'), rollout, log.get('asked')) if log else ('', None)
            s = events.get(('codex', tid))
            # Codex writes nothing to the rollout while it waits for an approval, so a write since the request
            # means it was answered; with its automatic reviewer the request never waits on you
            waits_on_you = bool(s and s['wait'] and log.get('reviewer') == 'user'
                                and os.path.getmtime(rollout) <= s['wait'] + WRITE_SLACK)
            hook = hooked(s, waits_on_you)
            if state != 'needs you' and hook == 'needs you':
                state, reply = 'needs you', APPROVAL
            elif not state and hook == 'working':  # a long command writes nothing until it ends
                state = 'working'
            if unread and not state:  # finished and not yet read: your turn, like a finished Claude thread
                state = 'needs you'
            detail = reply or os.path.basename(cwd)
            if live.get(rollout):
                r = row(tid, rec_ms / 1000, src, state, title, detail, *live[rollout])
            elif source == 'vscode':
                r = row(tid, rec_ms / 1000, src, state, title, detail, 'url', f'codex://threads/{tid}')
            else:
                r = row(tid, rec_ms / 1000, src, state, title, detail, 'tab', f'codex resume {tid}', cwd)
            r['created'] = (created_ms or rec_ms) / 1000
            rows.append(logged(r, log, (upd_ms or rec_ms) / 1000, ('codex', rollout)))
        except Exception as e:  # noqa: BLE001
            core.ERRORS.append(f'Codex thread {tid}: {type(e).__name__}: {e}')
    return rows
