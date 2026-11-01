"""A synthetic home folder in the shapes Codex and Claude Code write, for tests.

Every past bug is a record here: a system notice in an idle Claude session, a /exit from attaching to look,
Codex's settings sync and scheduled automation turns, an unanswered Codex question, an unread finished turn,
PRs created from both tools, a headless `claude -p`. Synthetic on purpose: real logs hold private work and
this repo is public.
"""
import datetime
import json
import os
import sqlite3

H = 3600


def iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


def jline(rec):
    return json.dumps(rec, separators=(',', ':'))


def write(path, lines, mtime):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        fh.write(''.join(line + '\n' for line in lines))
    os.utime(path, (mtime, mtime))


# --- Claude Code transcript records (top-level key order as Claude writes them: timestamp after message)
def human(t, text='hi'):
    return jline({'type': 'user', 'message': {'role': 'user', 'content': text}, 'origin': {'kind': 'human'},
                  'timestamp': iso(t)})


def reply(t, text='done'):
    return jline({'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': text}]},
                  'timestamp': iso(t)})


def tool_result(t):
    return jline({'type': 'user', 'message': {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 't1'}]},
                  'timestamp': iso(t)})


def system_notice(t):
    return jline({'type': 'system', 'subtype': 'informational', 'content': 'notice', 'isMeta': True, 'timestamp': iso(t)})


def exit_command(t):
    return jline({'type': 'user', 'message': {'role': 'user', 'content': '<command-name>/exit</command-name>'},
                  'timestamp': iso(t)})


def pr_created(t, url):
    return jline({'type': 'user', 'message': {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 't2'}]},
                  'toolUseResult': {'stdout': url, 'gitOperation': {'pr': {'url': url, 'action': 'created'}}},
                  'timestamp': iso(t)})


def custom_title(title):
    return jline({'type': 'custom-title', 'customTitle': title})


# --- Codex rollout records (timestamp first)
def cx(t, typ, payload):
    return jline({'timestamp': iso(t), 'type': typ, 'payload': payload})


def turn_started(t, trigger='composer'):
    return cx(t, 'event_msg', {'type': 'task_started', 'turn_attribution': {'turn_trigger': trigger}})


def turn_complete(t, message='finished'):
    return cx(t, 'event_msg', {'type': 'task_complete', 'last_agent_message': message})


def agent_step(t):
    return cx(t, 'response_item', {'type': 'message', 'role': 'assistant'})


def user_message(t):
    return cx(t, 'event_msg', {'type': 'item_completed', 'item': {'type': 'UserMessage'}})


def settings_sync(t):
    return cx(t, 'event_msg', {'type': 'thread_settings_applied'})


def question(t, title):
    return cx(t, 'response_item', {'type': 'function_call', 'name': 'request_user_input_async',
                                   'arguments': json.dumps({'questions': [{'title': title}]})})


def gh_pr_create(t, url, code=0):
    return cx(t, 'event_msg', {'type': 'item_completed', 'item': {
        'type': 'CommandExecution', 'command': ['/bin/zsh', '-lc', 'gh pr create --fill'],
        'exit_code': code, 'aggregated_output': url}})


PR_CLAUDE = 'https://github.com/acme/app/pull/101'
PR_CODEX = 'https://github.com/acme/app/pull/202'
PR_MERGED = 'https://github.com/acme/app/pull/303'


def build(home, now, live_pid, headless_pid):
    """Write the fake home. live_pid and headless_pid are running processes (the test's own) that stand in for
    a Claude CLI session in a terminal and a headless `claude -p`. `threads` runs ps, osascript, lsof, pgrep
    and lsappinfo by name; stubs in {home}/bin, first on PATH, keep it off the real machine."""
    os.makedirs(f'{home}/bin')
    for name, out in (('ps', f'{live_pid} 1 ttys001 claude\\n{headless_pid} 1 ?? claude -p\\n'),
                      ('osascript', ''), ('lsof', ''), ('pgrep', ''), ('lsappinfo', '')):
        path = f'{home}/bin/{name}'
        with open(path, 'w') as fh:
            fh.write(f"#!/bin/sh\nprintf '{out}'\n")
        os.chmod(path, 0o755)

    # ---------------- Codex: state database + rollouts
    cx_dir = f'{home}/.codex'
    os.makedirs(f'{cx_dir}/sessions', exist_ok=True)
    threads = []

    def codex(tid, title, source, recency, updated, created, lines, mtime, unread=False):
        path = f'{cx_dir}/sessions/rollout-{tid}.jsonl'
        write(path, lines, mtime)
        threads.append((tid, title, source, recency, updated, created, path, unread))
        return path

    # working now: your turn started 10 min ago, still being written
    codex('cx-working', 'parser refactor', 'vscode', now - 600, now - 30, now - 2 * H,
          [user_message(now - 600), turn_started(now - 600), agent_step(now - 300)], now - 30)
    # finished 5 h ago, not opened since: Codex's blue dot
    codex('cx-unread', 'export to csv', 'vscode', now - 5 * H, now - 5 * H + 300, now - 24 * H,
          [user_message(now - 5 * H), turn_started(now - 5 * H), turn_complete(now - 5 * H + 300, 'CSV export ready')],
          now - 5 * H + 300, unread=True)
    # your last turn 6 h ago; since then only a scheduled automation turn and a settings sync: not active
    codex('cx-automation', 'nightly report', 'vscode', now - 6 * H, now - 60, now - 3 * 24 * H,
          [user_message(now - 6 * H), turn_started(now - 6 * H), turn_complete(now - 6 * H + 120),
           turn_started(now - 40 * 60, 'automation_heartbeat_scheduled'), agent_step(now - 30 * 60),
           turn_complete(now - 30 * 60, 'heartbeat'), settings_sync(now - 60)], now - 60)
    # asked you a question 15 min ago and keeps polling: needs you
    codex('cx-question', 'set up mail sender', 'vscode', now - 40 * 60, now - 120, now - 4 * H,
          [user_message(now - 40 * 60), turn_started(now - 40 * 60),
           question(now - 15 * 60, 'Which domain should send the mail?'), agent_step(now - 120)], now - 120)
    # a CLI thread that created a PR a day ago (a failed create before it doesn't count), idle since
    codex('cx-pr', 'retry on timeout', 'cli', now - 26 * H, now - 25 * H, now - 2 * 24 * H,
          [user_message(now - 26 * H), turn_started(now - 26 * H), gh_pr_create(now - 25.5 * H, PR_CODEX + '9', code=1),
           gh_pr_create(now - 25 * H, PR_CODEX), turn_complete(now - 25 * H)], now - 25 * H)
    # not listed: archived, a subagent's thread, one older than the 7-day window
    codex('cx-archived', 'archived one', 'vscode', now - H, now - H, now - H, [user_message(now - H)], now - H)
    codex('cx-subagent', 'subagent one', 'vscode', now - H, now - H, now - H, [user_message(now - H)], now - H)
    codex('cx-old', 'old one', 'vscode', now - 9 * 24 * H, now - 9 * 24 * H, now - 9 * 24 * H,
          [user_message(now - 9 * 24 * H)], now - 9 * 24 * H)
    # its rollout can't be read: reported in errors, the other threads still list
    broken = codex('cx-broken', 'broken rollout', 'vscode', now - 2 * H, now - 2 * H, now - 2 * H, [], now - 2 * H)
    os.remove(broken)
    os.makedirs(broken)

    db = sqlite3.connect(f'{cx_dir}/state_5.sqlite')
    db.execute('''create table threads (id text primary key, rollout_path text, created_at_ms integer, updated_at_ms integer,
                  recency_at_ms integer, source text, cwd text, title text, name text, archived integer,
                  thread_source text)''')
    db.execute('create table thread_read_receipts (thread_id text primary key, first_unread_turn text, revision text not null)')
    for tid, title, source, recency, updated, created, path, unread in threads:
        db.execute('insert into threads values (?,?,?,?,?,?,?,?,?,?,?)',
                   (tid, path, int(created * 1000), int(updated * 1000), int(recency * 1000), source, f'/work/{tid}',
                    title, None, int(tid == 'cx-archived'), 'subagent' if tid == 'cx-subagent' else 'user'))
        db.execute('insert into thread_read_receipts values (?,?,?)', (tid, 'turn-1' if unread else None, 'r'))
    db.commit()
    db.close()

    # ---------------- Claude Code: background jobs + transcripts
    def job(jid, sid, name, state, created, lines, mtime, detail=''):
        write(f'{home}/.claude/projects/-work-{jid}/{sid}.jsonl', lines, mtime)
        write(f'{home}/.claude/jobs/{jid}/state.json',
              [json.dumps({'sessionId': sid, 'name': name, 'state': state, 'createdAt': iso(created),
                           'cwd': f'/work/{jid}', 'detail': detail})], mtime)

    # you wrote 30 min ago, it replied: in Priority
    job('job-live', 'sid-live', 'search ranking', 'done', now - 3 * H,
        [human(now - 30 * 60), tool_result(now - 28 * 60), reply(now - 25 * 60)], now - 25 * 60, 'answered')
    # idle a day; then a system notice and a /exit from attaching to look: neither is activity
    job('job-idle', 'sid-idle', 'flaky test', 'done', now - 3 * 24 * H,
        [human(now - 26 * H), reply(now - 25 * H), system_notice(now - 20 * 60), exit_command(now - 10 * 60)],
        now - 10 * 60, 'fixed')
    # created a PR, idle 3 h, blocked on you
    job('job-pr', 'sid-pr', 'docs rewrite', 'blocked', now - 2 * 24 * H,
        [human(now - 4 * H), pr_created(now - 3.5 * H, PR_CLAUDE), reply(now - 3 * H)], now - 3 * H, 'Push both commits?')
    # its PR is merged: not in Open PRs
    job('job-merged', 'sid-merged', 'old fix', 'done', now - 3 * 24 * H,
        [human(now - 30 * H), pr_created(now - 29 * H, PR_MERGED), reply(now - 29 * H)], now - 29 * H)
    # mid-rewrite: skipped quietly, picked up on the next refresh
    write(f'{home}/.claude/jobs/job-partial/state.json', ['{"sessionId": "sid-'], now - 60)

    # live CLI sessions: one in a terminal (listed, under the name you gave it), a headless `claude -p` and one
    # whose process is gone (neither listed)
    write(f'{home}/.claude/projects/-work-cli/sid-cli.jsonl',
          [human(now - 50 * 60), custom_title('cache warmup'), reply(now - 45 * 60)], now - 45 * 60)
    write(f'{home}/.claude/projects/-work-cli/sid-headless.jsonl', [human(now - 5 * 60)], now - 5 * 60)
    for n, pid, sid in ((1, live_pid, 'sid-cli'), (2, headless_pid, 'sid-headless'), (3, 99999999, 'sid-gone')):
        write(f'{home}/.claude/sessions/{n}.json',
              [json.dumps({'pid': pid, 'sessionId': sid, 'kind': 'interactive', 'status': 'idle', 'cwd': '/work/cli',
                           'startedAt': int((now - H) * 1000), 'updatedAt': int((now - 45 * 60) * 1000)})], now - 60)

    # ---------------- Claude desktop (Code tab)
    write(f'{home}/.claude/projects/-work-desk/desk-cli.jsonl', [human(now - 20 * 60), reply(now - 15 * 60)], now - 15 * 60)
    desktop = f'{home}/Library/Application Support/Claude/claude-code-sessions/a/b'
    write(f'{desktop}/local_desk.json',
          [json.dumps({'sessionId': 'local_desk', 'cliSessionId': 'desk-cli', 'title': 'Dark mode toggle',
                       'latestUserFrameAt': int((now - 20 * 60) * 1000), 'lastActivityAt': int((now - 15 * 60) * 1000),
                       'createdAt': int((now - 5 * H) * 1000), 'cwd': '/work/desk',
                       'postTurnSummary': {'status_category': 'blocked', 'status_detail': 'Should I push?'}})],
          now - 15 * 60)
    write(f'{desktop}/local_old.json',
          [json.dumps({'sessionId': 'local_old', 'title': 'archived', 'isArchived': True,
                       'latestUserFrameAt': int((now - H) * 1000)})], now - H)

    # ---------------- ThreadIsland's own state: a dragged Priority order, saved pages
    write(f'{home}/Library/Application Support/ThreadIsland/state.json',
          [json.dumps({'order': ['job-live', 'cx-working'],
                       'pages': [{'id': 'p1', 'bundle': 'company.thebrowser.Browser', 'app': 'Arc', 'name': 'Inbox',
                                  'tab': 'T1', 'url': 'https://mail.example.com/', 'space': 'S1', 'detail': 'work space'}],
                       'recent_pages': [{'id': 'p0', 'bundle': 'com.apple.ActivityMonitor', 'app': 'Activity Monitor',
                                         'name': 'Activity Monitor'}]})], now - H)
    # PR status as GitHub last reported it, fetched just now (no network in tests)
    write(f'{home}/Library/Caches/ThreadIsland/prs.json',
          [json.dumps({'fetched': now, 'logs': {}, 'status': {
              PR_CLAUDE: {'state': 'OPEN', 'draft': False, 'review': None, 'checks': 'SUCCESS', 'created': now - 3.5 * H},
              PR_CODEX: {'state': 'OPEN', 'draft': True, 'review': None, 'checks': None, 'created': now - 25 * H},
              PR_MERGED: {'state': 'MERGED', 'draft': False, 'review': 'APPROVED', 'checks': 'SUCCESS',
                          'created': now - 29 * H}}})],
          now)


def ai_title(title):
    return jline({'type': 'ai-title', 'aiTitle': title})


def big_output(t, size):
    return cx(t, 'response_item', {'type': 'function_call_output', 'output': 'y' * size})


def tool_definitions():
    return cx(0, 'response_item', {'type': 'additional_tools', 'tools': [{'name': 'request_user_input_async'}]})


def mcp_pr_create(url, status='completed'):
    return cx(0, 'event_msg', {'type': 'item_completed', 'item': {
        'type': 'McpToolCall', 'tool': 'github.create_pull_request', 'status': status, 'result': {'html_url': url}}})
