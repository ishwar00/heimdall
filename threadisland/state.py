"""ThreadIsland's saved state: Priority's order, pages and recently removed pages."""
import contextlib
import fcntl
import json
import os

from . import core


STATE = f'{core.HOME}/Library/Application Support/ThreadIsland/state.json'


@contextlib.contextmanager
def edited_state():
    """Priority's order: 'order' is its keys, top first, so a row you dragged keeps its place.
    Locked, so a refresh pruning it can't undo a drag saved at the same moment; written only if changed."""
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE + '.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = json.load(open(STATE))
        except (OSError, ValueError):
            state = {}
        state.setdefault('order', [])
        state.pop('removed', None)  # from a removed feature
        before = json.dumps(state, sort_keys=True)
        yield state
        if json.dumps(state, sort_keys=True) != before:
            with open(STATE + '.tmp', 'w') as fh:
                json.dump(state, fh)
            os.replace(STATE + '.tmp', STATE)
