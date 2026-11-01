"""threads: Codex + Claude Code threads, recency-sorted, as JSON for the ThreadIsland notch app.

Sources: Codex desktop/CLI (~/.codex/state_*.sqlite), Claude desktop Code tab
(claude-code-sessions/*.json), Claude CLI background jobs (~/.claude/jobs) and
live interactive Claude CLI sessions (~/.claude/sessions).
Jumps: codex:// and claude:// deep links, Ghostty AppleScript (focus tab by tty,
or open a new window running the resume command). `--jump` reads one row's JSON on stdin.
"""
