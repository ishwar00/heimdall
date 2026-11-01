"""Finding the terminal a live session runs in (Ghostty by TTY, Warp by session URL) and opening rows."""
import glob
import os
import re

from . import core
from .core import run, checked


def ghostty_ttys():
    if not run(['pgrep', '-x', 'ghostty']):
        return set()
    out = run(['osascript', '-e', 'tell application "Ghostty" to get tty of every terminal'])
    return {t.strip() for t in out.split(',') if t.strip()}


WARP_EXE = re.compile(r'^\S*/Warp\.app/Contents/MacOS/')


def focus_target(p, gtty, by_pid):
    """(action, arg) that focuses the terminal a live session runs in: its Ghostty terminal by TTY, else its
    Warp tab via the WARP_FOCUS_URL Warp exports to every session (warpdotdev/warp PR #11130), else None."""
    if p['tty'] in gtty:
        return 'focus', p['tty']
    # The URL is inherited by everything a Warp tab starts, including Claude's background-job daemon and its
    # workers (which get their own TTYs), so trust it only when a Warp executable is an ancestor of the session.
    a, hops = by_pid.get(p['ppid']), 0
    while a and not WARP_EXE.match(a['args']) and hops < 30:
        a, hops = by_pid.get(a['ppid']), hops + 1
    if a:
        for tok in run(['ps', 'eww', '-o', 'command=', '-p', str(p['pid'])], timeout=3).split():
            if tok.startswith('WARP_FOCUS_URL=warp://session/'):
                return 'url', tok.split('=', 1)[1]
    return None


GHOSTTY_FOCUS = '''on run argv
    tell application "Ghostty"
        focus (first terminal whose tty is (item 1 of argv))
        activate
    end tell
end run'''

GHOSTTY_TAB = '''on run argv
    tell application "Ghostty"
        set cfg to new surface configuration
        set initial working directory of cfg to (item 1 of argv)
        set initial input of cfg to (item 2 of argv) & linefeed
        new window with configuration cfg
        activate
    end tell
end run'''


def new_session_terminal():
    """Terminal for a session that isn't open anywhere: the one you were just in (the island never takes
    focus), else whichever is running (Ghostty first), else Ghostty."""
    front = run(['lsappinfo', 'info', '-only', 'name', run(['lsappinfo', 'front']).strip()])
    for app in ('Warp', 'Ghostty'):
        if f'"{app}"' in front:
            return app
    if run(['pgrep', '-x', 'ghostty']):
        return 'Ghostty'
    return 'Warp' if run(['pgrep', '-f', '/Applications/Warp.app/Contents/MacOS/stable$']) else 'Ghostty'


def toml_str(s):
    """A TOML basic string; quotes, backslashes and control characters as \\uXXXX escapes."""
    return '"' + ''.join(c if c not in '"\\' and 0x1f < ord(c) != 0x7f else f'\\u{ord(c):04x}' for c in s) + '"'


def warp_open(cwd, command, key):
    """Open a Warp tab in cwd running command. The URI scheme can't run commands; a Tab Config can, and Warp
    re-reads the file on every open (https://docs.warp.dev/terminal/sessions/tab-configs). A new window
    would also get an empty default tab, so this opens a tab in the front Warp window. One config per
    thread, written atomically, so two quick clicks can't open the same thread twice."""
    folder = f'{core.HOME}/.warp/tab_configs'
    os.makedirs(folder, exist_ok=True)
    for old in glob.glob(f'{folder}/threadisland*.toml'):  # they show in Warp's + menu; keep a day's worth
        if core.NOW - os.path.getmtime(old) > 86400:
            os.remove(old)
    name = 'threadisland-' + re.sub(r'[^A-Za-z0-9-]', '', key)[:40]
    with open(f'{folder}/.{name}.tmp', 'w') as fh:
        fh.write(f'name = "ThreadIsland"\n\n[[panes]]\nid = "main"\ntype = "terminal"\n'
                 f'directory = {toml_str(cwd)}\ncommands = [{toml_str(command)}]\n')
    os.replace(f'{folder}/.{name}.tmp', f'{folder}/{name}.toml')
    return checked(['open', f'warp://tab_config/{name}'])


def jump(r):
    if r['action'] == 'url':
        return checked(['open', r['arg']])
    if r['action'] == 'focus':
        return checked(['osascript', '-', r['arg']], GHOSTTY_FOCUS)
    if r['action'] == 'tab':
        if new_session_terminal() == 'Warp':
            return warp_open(r['cwd'] or core.HOME, r['arg'], r['key'])
        return checked(['osascript', '-', r['cwd'] or core.HOME, r['arg']], GHOSTTY_TAB)
    return None
