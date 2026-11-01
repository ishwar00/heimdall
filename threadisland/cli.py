"""Entry point: `threads` lists every thread as JSON; flags run one action (jump, edit, pages)."""
import json
import sys

from . import core
from .core import ago, processes
from .terminals import ghostty_ttys, jump
from .codex import codex_rows
from .claude import claude_desktop_rows, live_sessions, claude_cli_rows
from .pages import capture_page, open_page, pages_edit
from .prs import attach_prs
from .state import edited_state
from .sections import edit, sectioned


def main():
    if '--jump' in sys.argv:
        try:
            error = jump(json.load(sys.stdin))
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

    procs = processes()
    gtty = ghostty_ttys()
    sessions = live_sessions()
    rows = []
    # each source reads private files that an app update can change; report a broken one instead of hiding it
    for name, source in (('Codex', lambda: codex_rows(procs, gtty)), ('Claude app', lambda: claude_desktop_rows(sessions)),
                         ('Claude CLI', lambda: claude_cli_rows(procs, gtty, sessions))):
        try:
            rows += source()
        except Exception as e:  # noqa: BLE001 - any failure here is shown in the panel
            core.ERRORS.append(f'{name}: {type(e).__name__}: {e}')
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
