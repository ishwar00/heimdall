"""Folding the hooks' events into each session's state: running, waiting for your approval, done."""
import os
import tempfile
import unittest

from fixtures import hook
from threadisland import core, events

NOW = core.NOW


class Events(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, events, 'EVENTS', events.EVENTS)
        events.EVENTS = os.path.join(tmp.name, 'events.jsonl')

    def write(self, *lines, path=None):
        with open(path or events.EVENTS, 'a') as fh:
            fh.write(''.join(line + '\n' for line in lines))

    def state(self, *lines, tool='codex', approval=True):
        self.write(*lines)
        return events.hooked(events.sessions().get((tool, 's')), approval)

    def test_running_turn(self):
        self.assertEqual(self.state(hook(NOW - 60, 'codex', 'UserPromptSubmit', 's')), 'working')

    def test_finished_turn(self):
        for end in ('Stop', 'Interrupt', 'SessionEnd'):
            with self.subTest(end):
                if os.path.exists(events.EVENTS):
                    os.remove(events.EVENTS)
                self.assertIsNone(self.state(hook(NOW - 60, 'codex', 'UserPromptSubmit', 's'),
                                             hook(NOW - 30, 'codex', end, 's')))

    def test_turn_that_died_clears(self):
        self.assertIsNone(self.state(hook(NOW - events.OPEN_FOR - 60, 'codex', 'UserPromptSubmit', 's')))

    def test_approval(self):
        self.assertEqual(self.state(hook(NOW - 60, 'codex', 'PermissionRequest', 's')), 'needs you')

    def test_approval_not_on_you_is_still_running(self):
        self.assertEqual(self.state(hook(NOW - 60, 'codex', 'PermissionRequest', 's'), approval=False), 'working')

    def test_approval_answered_by_a_later_event(self):
        self.assertIsNone(self.state(hook(NOW - 60, 'codex', 'PermissionRequest', 's'), hook(NOW - 5, 'codex', 'Stop', 's')))

    def test_claude_permission_prompt(self):
        self.assertEqual(self.state(hook(NOW - 60, 'claude', 'Notification', 's', 'permission_prompt'), tool='claude'),
                         'needs you')

    def test_idle_reminder_and_session_start_are_not_activity(self):
        self.assertIsNone(self.state(hook(NOW - 60, 'claude', 'UserPromptSubmit', 's'), hook(NOW - 50, 'claude', 'Stop', 's'),
                                     hook(NOW - 5, 'claude', 'Notification', 's', 'idle_prompt'),
                                     hook(NOW - 4, 'claude', 'SessionStart', 's'), tool='claude'))

    def test_tools_and_sessions_kept_apart(self):
        self.write(hook(NOW - 60, 'codex', 'UserPromptSubmit', 's'), hook(NOW - 50, 'claude', 'Stop', 's'),
                   hook(NOW - 40, 'codex', 'Stop', 'other'))
        self.assertEqual(events.hooked(events.sessions()[('codex', 's')]), 'working')

    def test_bad_lines_skipped(self):
        self.assertEqual(self.state('not json', '{"t": "x"}', '', hook(NOW - 60, 'codex', 'UserPromptSubmit', 's')),
                         'working')

    def test_rotation_keeps_reading_the_previous_file(self):
        self.addCleanup(setattr, events, 'ROTATE_AT', events.ROTATE_AT)
        events.ROTATE_AT = 10
        self.write(hook(NOW - 60, 'codex', 'UserPromptSubmit', 's'))
        self.assertEqual(events.hooked(events.sessions()[('codex', 's')]), 'working')  # rotated here
        self.assertTrue(os.path.exists(events.EVENTS + '.1'))
        self.write(hook(NOW - 30, 'codex', 'Stop', 's'))
        self.assertIsNone(events.hooked(events.sessions()[('codex', 's')]))

    def test_no_events_file(self):
        self.assertEqual(events.sessions(), {})


if __name__ == '__main__':
    unittest.main()
