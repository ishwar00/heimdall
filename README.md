# ThreadIsland

A Dynamic Island for your coding agents. ThreadIsland sits in the MacBook notch and lists your recent
**Codex** and **Claude Code** threads in one place. Hover to see them, click one to jump straight to it.

If you switch between Codex and Claude Code all day, you know the problem: the thread you want is in
one of four apps or a dozen terminal tabs. ThreadIsland puts all of them in one list, ordered the way
Codex's own activity view orders them.

## What you see

- **Collapsed:** a black pill around the notch. The left side counts threads that need you,
  the right side counts threads that are working.
- **Expanded (hover):** a **Priority** section first, then **Today**, **Yesterday** and one section per
  weekday for the last 7 days. Rows never swap places, so positions stay where you learned them:
  - **Priority** holds threads with conversation activity (yours or the agent's) in the last 2 hours.
    A thread that becomes active, new or old, joins at the bottom; after 2 hours with no activity,
    whatever its state, it drops into its day. Bookkeeping the apps write into idle threads and Codex's
    scheduled automation turns don't count as activity.
  - **Rearrange:** hover a Priority row and drag its six-dot grip (right edge) to move it. Your order is kept in
    `~/Library/Application Support/ThreadIsland/state.json`; threads that join still go to the bottom.
  - **Open PRs** holds idle threads that created a PR that's still open, oldest PR first, with its number
    and status (draft, checks failing, changes requested, approved, in review). A thread leaves when its
    PRs are merged or closed. Only PRs the thread created count, not ones it mentions or reviews.
  - **Day sections** sort by when you last sent a message.

  Each row starts with the app icon, so you can scan for "the Codex one", and shows its age.
- **Pages:** save any place you keep coming back to and jump back with one click. Open the island while
  you're there and press **+** (or swipe over to **Pages** and pick "Save where you are"), then name it.
  In Arc it saves the exact tab; in other apps, the app (and so its window and Space). Saved pages show
  as chips above your threads and as full rows in the Pages view; swipe left or right with two fingers
  anywhere on the island to switch views. The chips wrap onto more lines when there are many; drag one onto another's place to reorder them. To remove a page, hover it in the Pages view for its remove button (or right-click it). Removed pages wait under Recently removed (the last 8), where hovering one shows a pin button to put it back. The first Arc page asks to let
  ThreadIsland control Arc. A closed tab opens again from its URL. A saved tab shows the site's own icon, fetched once from the site when you save it (no third-party favicon service). The fetch only goes to the page's own host or to public addresses, so a page can't point it at your machine or local network.
- **Design:** one calm look: a lit lamp at the left edge of a row shows its state (orange needs you,
  green working). Nothing moves unless you hover. Right-click the island for Appearance (System, Light or
  Dark; the strip at the notch stays black so it merges with the notch) or to quit.
- **Health:** each source reads files that an app update can change. If a source breaks, a red line in
  the panel (and a triangle on the pill) says which one, so the list never silently shrinks. One
  unreadable thread is reported and skipped; the rest of its source still shows. A click that fails to
  open its thread says why in the same place.

## Where threads come from, and where a click takes you

| Source | Read from | Click |
|---|---|---|
| Codex app | `~/.codex/state_*.sqlite` + the thread's rollout file (status, last reply) | `codex://threads/<id>` |
| Codex CLI | same | focuses its Ghostty window or Warp tab, else `codex resume <id>` in a new session (see below) |
| Claude desktop (Code tab) | `~/Library/Application Support/Claude/claude-code-sessions` | `claude://code/continue?session=<id>` |
| Claude Code background jobs | `~/.claude/jobs/*/state.json` + live `~/.claude/sessions` | focuses the Ghostty window or Warp tab it is attached in, else `claude attach <id>` in a new session (see below) |
| Claude Code CLI sessions | `~/.claude/sessions` | focuses its Ghostty window or Warp tab |

Ghostty terminals are found by TTY through Ghostty's AppleScript dictionary (Ghostty 1.3+). Warp tabs are
found by the `WARP_FOCUS_URL` (`warp://session/<id>`) Warp puts in every session's environment, read only
from sessions that Warp itself started.

A new session opens in the terminal you were just using: a Ghostty window, or a Warp tab (through a
Warp Tab Config, `~/.warp/tab_configs/threadisland-<id>.toml`, since Warp's URLs can't run a command;
configs older than a day are deleted). If you
were in neither, it uses whichever is running, Ghostty first.

## Install

Needs macOS 14+, Xcode Command Line Tools (`xcode-select --install`) and the system Python 3.

```sh
git clone https://github.com/ishwar00/thread-island.git ~/.local/share/thread-island
~/.local/share/thread-island/build.sh
open ~/Applications/ThreadIsland.app
```

On the first jump into Ghostty, macOS asks whether ThreadIsland may control Ghostty. Allow it.
To start it at login, add `~/Applications/ThreadIsland.app` in System Settings → General → Login Items.
Right-click the island to quit.

Optional, recommended: let Claude Code and Codex tell ThreadIsland when a turn starts, ends or waits for your
approval. Without it, a Codex thread waiting for you to approve a command shows as working.

```sh
~/.local/share/thread-island/hooks/install            # --remove takes it out again
```

It adds one hook command to `~/.claude/settings.json` and `~/.codex/hooks.json`, keeping your own hooks
(the first run saves each file as `<file>.threadisland-backup`). Codex asks once whether to run new hooks
("Review hooks"): allow them, and restart Codex. The hook writes only the event, session, turn and time to
`~/Library/Application Support/ThreadIsland/events.jsonl`, never what you or the agent wrote.

## How it works

`threads` (Python, standard library only) gathers every source into one JSON list, and `threads --jump`
opens one row. The Swift app is only the UI: a borderless panel at the notch that runs `threads` every
32 s (every 4 s while open, and right away when you open it). It never pops up on its own: you look when you want to.

Run `threads` yourself to see the raw data.

| Path | What's there |
|---|---|
| `threads` | the command the app runs; starts `threadisland.cli` |
| `threadisland/` | `codex.py`, `claude.py` (sources), `logs.py` (reading their logs), `events.py` (what the hooks reported), `prs.py`, `sections.py`, `pages.py`, `terminals.py` (finding and opening terminals), `state.py`, `core.py` |
| `hooks/` | `ti-event`, the hook the agents run, and `install` |
| `app/` | the SwiftUI panel: `Model`, `Store`, `Design`, `Icons`, `IslandView`, `Rows`, `Panel`, and `main.swift` to start it |
| `tests/` | `fixtures.py` builds a synthetic home folder in the apps' file shapes, one record per past bug; `test_golden.py` runs `threads` over it against `golden.json` |

Tests (no network, nothing read from your real home folder):

```sh
/usr/bin/python3 -m unittest discover tests
```

After an intended change to the listing, regenerate the expected output with `UPDATE_GOLDEN=1` and review
the diff of `tests/golden.json`. Fixtures are synthetic on purpose: real transcripts hold private work.

## Limits

- PR status comes from GitHub through `gh` (`gh auth login` once), fetched at most every 5 minutes, so a
  merge can take that long to show. A thread drops out of the list after 7 days without your messages,
  even with an open PR.
- Codex and Claude Code don't publish these file formats. An update can break a source; the health line
  tells you when.
- A Codex thread shows "needs you" when it asked you a question (its `request_user_input` tool) that you
  haven't answered yet, with the question as its detail line. A wait for a command approval shows only
  with the hooks installed, and only when you review that thread's approvals (with Codex's automatic
  review it isn't waiting on you). Codex writes nothing while an approved command runs, so a long command
  you approved keeps showing "needs you" until it finishes. Without the hooks, a turn with no writes for 10 minutes stops counting
  as working.
- Live sessions in terminals other than Ghostty and Warp show in the list but can't be jumped to.
