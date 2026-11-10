"""Entry point: `threads` lists every thread as JSON; flags run one action (jump, edit, pages)."""
import json
import sys

from . import core
from .core import ago, log_jump, processes
from .terminals import ghostty_ttys, jump
from .codex import codex_rows
from .events import sessions as hook_events
from .claude import claude_desktop_rows, live_sessions, claude_cli_rows
from .pages import capture_page, open_page, pages_edit
from .prs import attach_prs
from .state import edited_state
from .sections import edit, sectioned


def thread_rows():
    """Every source's rows, before PRs and sections."""
    procs = processes()
    gtty = ghostty_ttys()
    sessions = live_sessions()
    try:
        events = hook_events()
    except Exception as e:  # noqa: BLE001 - shown in the panel; states then come from the logs alone
        core.ERRORS.append(f'Hook events: {type(e).__name__}: {e}')
        events = {}
    rows = []
    # each source reads private files that an app update can change; report a broken one instead of hiding it
    for name, source in (('Codex', lambda: codex_rows(procs, gtty, events)), ('Claude app', lambda: claude_desktop_rows(sessions, events)),
                         ('Claude CLI', lambda: claude_cli_rows(procs, gtty, sessions, events))):
        try:
            rows += source()
        except Exception as e:  # noqa: BLE001 - any failure here is shown in the panel
            core.ERRORS.append(f'{name}: {type(e).__name__}: {e}')
    return rows


def main():
    if '--jump' in sys.argv:
        try:
            row, how = json.load(sys.stdin), ''
            if row.get('action') == 'tab':
                # the row is as of the last refresh: if the thread has opened in a terminal since, go there
                fresh = next((r for r in thread_rows() if r['key'] == row.get('key')), None)
                if fresh and fresh['action'] != 'tab':
                    row, how = fresh, ' (opened since the last refresh)'
            error = jump(row)
            log_jump(row.get('src'), row.get('key'), f"{row.get('action')}{how}: {error or 'ok'}")
        except Exception as e:  # noqa: BLE001 - shown in the panel
            error = f'{type(e).__name__}: {e}'
        json.dump({'error': error}, sys.stdout)
        return

    if '--edit' in sys.argv:
        edit(json.load(sys.stdin))
        return
    if '--page-capture' in sys.argv:
        json.dump(capture_page(), sys.stdout)
        return
    if '--page-edit' in sys.argv:
        pages_edit(json.load(sys.stdin))
        return
    if '--page-open' in sys.argv:
        try:
            error = open_page(json.load(sys.stdin))
        except Exception as e:  # noqa: BLE001 - shown in the panel
            error = f'{type(e).__name__}: {e}'
        json.dump({'error': error}, sys.stdout)
        return

    rows = thread_rows()
    try:
        attach_prs(rows)
    except Exception as e:  # noqa: BLE001 - shown in the panel; the list still shows, without PRs
        core.ERRORS.append(f'GitHub PRs: {type(e).__name__}: {e}')
    for r in rows:
        r.pop('log', None)
    rows = sectioned(rows)

    for r in rows:
        r['age'] = ago(r['ts'])
    with edited_state() as state:
        pages, recent = state.get('pages', []), state.get('recent_pages', [])
    json.dump({'rows': rows, 'errors': core.ERRORS, 'pages': pages, 'recent': recent}, sys.stdout)


if __name__ == '__main__':
    main()
