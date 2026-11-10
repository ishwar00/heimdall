"""Priority, Open PRs and the day sections."""
import datetime

from . import core
from .state import edited_state


def edit(e):
    """Save Priority's order after you drag a row: keys, top first, as you left them."""
    with edited_state() as state:
        state['order'] = [k for k in e['keys'] if isinstance(k, str)]


def sectioned(rows):
    """Positions are learned, so rows never swap on their own:
    Priority holds threads with activity in the last 2 h, in the order their current run of activity began,
    so a thread that becomes active (new or not) joins at the bottom. A thread leaves after 2 h with no
    activity, whatever its state, which is also what ends a run, so its slot can't change while it stays.
    Day sections sort by your last message, which can't change there: a new message makes a thread active,
    and it moves to Priority.
    The order is saved, so a row you drag keeps its place."""
    def hot(r):
        return core.NOW - r.get('active', 0) < core.IDLE_OUT
    with edited_state() as state:
        natural = sorted((r for r in rows if hot(r)), key=lambda r: r.get('entered') or r.get('created') or r['ts'])
        # threads keep their slot while in Priority; one that leaves loses it, and any that join (new or back
        # after idle) go below the rest, in the order they began
        keys = {r['key'] for r in natural}
        kept = [k for k in state['order'] if k in keys]
        state['order'] = kept + [r['key'] for r in natural if r['key'] not in set(kept)]
        rank = {k: i for i, k in enumerate(state['order'])}
        priority = sorted(natural, key=lambda r: rank[r['key']])
    # an idle thread with an open PR isn't done: it waits here, oldest PR first, until the PR closes
    prs = sorted((r for r in rows if not hot(r) and r.get('pr')), key=lambda r: r['pr_since'])
    # the 7-day window applies to sort time (your last message), which can be older than a source's file mtime
    recent = sorted((r for r in rows if not hot(r) and not r.get('pr') and r['ts'] >= core.CUTOFF), key=lambda r: -r['ts'])
    for r in priority:
        r['section'] = 'Priority'
    for r in prs:
        r['section'] = 'Open PRs'
    for r in recent:
        day = datetime.date.fromtimestamp(r['ts'])
        r['section'] = ('Today' if day == core.TODAY else 'Yesterday' if (core.TODAY - day).days == 1
                        else day.strftime('%A'))
    return priority + prs + recent
