"""PRs a thread created, read from its log, and their status from GitHub."""
import json
import os
import re

from . import core
from .core import run, loads, epoch, read_json


PR_CACHE = f'{core.HOME}/Library/Caches/Heimdall/prs.json'
PR_URL = re.compile(r'https://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)')
PR_TTL = 300  # PR status is fetched at most every 5 min, in one call for all of them


def created_prs(kind, path, seen):
    """PRs a thread created, from its log. seen: what an earlier run found and how far it read, so each
    run reads only what was added since. Claude Code tags a PR it created on the tool result
    (gitOperation.pr, action "created"); Codex logs every shell command with its exit code and output, and
    its GitHub app's calls as McpToolCall items. A PR the thread only mentions or reviews doesn't count."""
    size = os.path.getsize(path)
    if seen.get('size', 0) > size:  # rewritten: read it again
        seen.clear()
    prs, at = seen.setdefault('prs', []), seen.get('offset', 0)

    def found(text):
        urls = [m.group(0) for m in PR_URL.finditer(text)]
        if urls and urls[-1] not in prs:
            prs.append(urls[-1])

    with open(path, 'rb') as fh:
        fh.seek(at)
        carry = b''
        while chunk := fh.read(4 * 1024 * 1024):
            lines = (carry + chunk).split(b'\n')
            carry = lines.pop()  # unfinished; read again next run
            at += len(chunk)
            for line in lines:
                if kind == 'claude':
                    if b'"gitOperation"' in line and b'"action":"created"' in line:
                        pr = ((loads(line).get('toolUseResult') or {}).get('gitOperation') or {}).get('pr') or {}
                        if pr.get('action') == 'created':
                            found(pr.get('url') or '')
                elif b'"CommandExecution"' in line and b'gh pr create' in line:
                    item = (loads(line).get('payload') or {}).get('item') or {}
                    if item.get('exit_code') == 0 and 'gh pr create' in json.dumps(item.get('command')):
                        found(item.get('aggregated_output') or '')
                elif b'"McpToolCall"' in line and b'create_pull_request' in line:
                    item = (loads(line).get('payload') or {}).get('item') or {}
                    if item.get('status') == 'completed' and 'create_pull_request' in (item.get('tool') or ''):
                        found(json.dumps(item.get('result')))
    seen.update(offset=at - len(carry), size=size)
    return prs


def pr_statuses(urls, known):
    """State of each PR from GitHub, one GraphQL call through gh for all of them
    (https://docs.github.com/en/graphql/reference/objects#pullrequest). Merged and closed are final."""
    ask = [u for u in urls if (known.get(u) or {}).get('state') not in ('MERGED', 'CLOSED')]
    gh = next((g for g in ('/opt/homebrew/bin/gh', '/usr/local/bin/gh', '/usr/bin/gh') if os.path.exists(g)), None)
    if not ask or not gh:
        return
    parts = []
    for i, u in enumerate(ask):
        owner, name, number = PR_URL.match(u).groups()
        parts.append(f'p{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ pullRequest(number: {number}) '
                     '{ state isDraft reviewDecision createdAt commits(last: 1) { nodes { commit { statusCheckRollup { state } } } } } }')
    out = run([gh, 'api', 'graphql', '-f', 'query={ ' + ' '.join(parts) + ' }'], timeout=15)
    data = (loads(out.encode()) or {}).get('data')
    if not data:
        raise RuntimeError(f'gh api graphql returned no data: {out.strip()[:200] or "no output"}')
    for i, u in enumerate(ask):
        pr = (data.get(f'p{i}') or {}).get('pullRequest')
        if pr:  # null: deleted, or a repo you can't see
            nodes = pr['commits']['nodes']
            checks = ((nodes[0]['commit'].get('statusCheckRollup') or {}).get('state')) if nodes else None
            known[u] = {'state': pr['state'], 'draft': pr['isDraft'], 'review': pr['reviewDecision'],
                        'checks': checks, 'created': epoch(pr['createdAt'])}


def pr_label(u, s):
    status = ('draft' if s['draft'] else 'checks failing' if s['checks'] in ('FAILURE', 'ERROR')
              else 'changes requested' if s['review'] == 'CHANGES_REQUESTED'
              else 'approved' if s['review'] == 'APPROVED' else 'in review')
    return f'#{PR_URL.match(u).group(3)} {status}'


def attach_prs(rows):
    """Mark rows whose thread has open PRs: 'pr' is the label shown, 'pr_since' when the first one opened."""
    os.makedirs(os.path.dirname(PR_CACHE), exist_ok=True)
    try:
        cache = read_json(PR_CACHE)
    except (OSError, ValueError):
        cache = {}
    logs, known = cache.get('logs', {}), cache.get('status', {})
    by_row, listed = {}, set()
    for r in rows:
        kind, path = r.pop('log', (None, None))
        if path and os.path.exists(path):
            listed.add(path)
            by_row[r['key']] = created_prs(kind, path, logs.setdefault(path, {}))
    urls = sorted({u for us in by_row.values() for u in us})
    try:
        if core.NOW - cache.get('fetched', 0) > PR_TTL or any(u not in known for u in urls):
            pr_statuses(urls, known)
            cache['fetched'] = core.NOW
    except Exception as e:  # noqa: BLE001 - shown in the panel; rows keep the last known status
        core.ERRORS.append(f'GitHub PRs: {type(e).__name__}: {e}')
    for r in rows:
        open_prs = [u for u in by_row.get(r['key'], []) if (known.get(u) or {}).get('state') == 'OPEN']
        if open_prs:
            r['pr'] = pr_label(open_prs[0], known[open_prs[0]]) + (f' +{len(open_prs) - 1}' if len(open_prs) > 1 else '')
            r['pr_since'] = min(known[u]['created'] for u in open_prs)
    # keep only threads still listed, so the cache doesn't grow forever
    cache.update(logs={p: v for p, v in logs.items() if p in listed}, status={u: known[u] for u in urls if u in known})
    with open(PR_CACHE + '.tmp', 'w') as fh:
        json.dump(cache, fh)
    os.replace(PR_CACHE + '.tmp', PR_CACHE)
