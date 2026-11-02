"""Reading a thread's log: what counts as activity, the current run, Codex's turn and questions, titles."""
import os
import tempfile
import unittest

from fixtures import (H, agent_step, ai_title, big_output, custom_title, exit_command, human, question, reply,
                      settings_sync, system_notice, tool_call, tool_definitions, tool_output, tool_result,
                      turn_complete, turn_started, user_message)
from threadisland import core, logs
from threadisland.codex import codex_turn

NOW = core.NOW


class Logs(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def log(self, *lines):
        path = os.path.join(self.dir.name, f'{len(os.listdir(self.dir.name))}.jsonl')
        with open(path, 'w') as fh:
            fh.write(''.join(line + '\n' for line in lines))
        return path

    def claude(self, *lines, **kw):
        return logs.scan_log('claude', self.log(*lines), **kw)

    def codex(self, *lines):
        return logs.scan_log('codex', self.log(*lines))

    def assertTime(self, got, want):
        self.assertEqual(round(got), round(want))

    # --- the current run of activity
    def test_long_turn_keeps_its_start(self):
        times = [NOW - 3 * H + i * 600 for i in range(19)]
        out = self.claude(human(times[0]), *(reply(t) for t in times[1:]))
        self.assertTime(out['entered'], times[0])

    def test_gap_starts_a_new_run(self):
        out = self.claude(human(NOW - 10 * H), reply(NOW - 9 * H), human(NOW - H), reply(NOW - 60), sent=True)
        self.assertTime(out['entered'], NOW - H)
        self.assertTime(out['sent'], NOW - H)

    def test_idle_thread_has_no_run(self):
        out = self.claude(human(NOW - 5 * H), reply(NOW - 3 * H))
        self.assertNotIn('entered', out)
        self.assertTime(out['active'], NOW - 3 * H)

    def test_lines_straddling_read_chunks(self):
        whole = logs.lines_back
        logs.lines_back = lambda path, chunk=97: whole(path, chunk)
        self.addCleanup(setattr, logs, 'lines_back', whole)
        out = self.claude(human(NOW - 6 * H, 'x' * 300), human(NOW - 100 * 60, 'x' * 250),
                          reply(NOW - 50 * 60, 'x' * 333), reply(NOW - 10, 'x' * 10), sent=True)
        self.assertTime(out['entered'], NOW - 100 * 60)
        self.assertTime(out['sent'], NOW - 100 * 60)

    # --- bookkeeping isn't activity
    def test_claude_system_notice_and_exit_are_not_activity(self):
        out = self.claude(human(NOW - 16 * H), reply(NOW - 15 * H), system_notice(NOW - 120), exit_command(NOW - 60))
        self.assertTime(out['active'], NOW - 15 * H)
        self.assertNotIn('entered', out)

    def test_claude_tool_result_is_activity(self):
        self.assertTime(self.claude(human(NOW - 600), tool_result(NOW - 120))['active'], NOW - 120)

    def test_codex_automation_and_settings_sync_are_not_activity(self):
        out = self.codex(turn_started(NOW - 5 * H), agent_step(NOW - 5 * H + 60), turn_complete(NOW - 5 * H + 120),
                         turn_started(NOW - 3 * H, 'automation_heartbeat_scheduled'), agent_step(NOW - 600),
                         turn_complete(NOW - 300), settings_sync(NOW - 30))
        self.assertTime(out['active'], NOW - 5 * H + 120)
        self.assertNotIn('entered', out)

    def test_codex_your_turn_after_automation_counts(self):
        out = self.codex(turn_started(NOW - 3 * H, 'automation_heartbeat_scheduled'), agent_step(NOW - 3 * H + 60),
                         turn_started(NOW - 600), agent_step(NOW - 300))
        self.assertTime(out['entered'], NOW - 600)

    # --- Codex turn state
    def test_codex_turn_and_run(self):
        out = self.codex(turn_started(NOW - 8 * H), turn_started(NOW - 30 * 60), agent_step(NOW - 20 * 60),
                         turn_complete(NOW - 10 * 60))
        self.assertEqual(out['turn']['type'], 'task_complete')
        self.assertTime(out['entered'], NOW - 30 * 60)

    def test_codex_turn_found_past_a_huge_tool_output(self):
        out = self.codex(turn_started(NOW - 20 * 60), big_output(NOW - 5, 3_000_000))
        self.assertEqual(out['turn']['type'], 'task_started')

    def test_codex_unanswered_question_needs_you(self):
        path = self.log(turn_started(NOW - 600), user_message(NOW - 590), question(NOW - 300, 'Which **domain**?'),
                        agent_step(NOW - 100))
        out = logs.scan_log('codex', path)
        self.assertEqual(out['asked'], 'Which domain?')
        self.assertEqual(codex_turn(out['turn'], path, out['asked']), ('needs you', 'Which domain?'))

    def test_codex_answered_question(self):
        out = self.codex(turn_started(NOW - 600), question(NOW - 300, 'q'), user_message(NOW - 200), agent_step(NOW - 100))
        self.assertNotIn('asked', out)

    def test_codex_tool_definition_is_not_a_question(self):
        self.assertNotIn('asked', self.codex(tool_definitions(), turn_started(NOW - 600)))

    def test_codex_open_tool_call(self):
        out = self.codex(turn_started(NOW - 600), tool_call(NOW - 120, 'js'))
        self.assertEqual(out['call'][0], 'js')
        self.assertTime(out['call'][1], NOW - 120)

    def test_codex_tool_call_that_returned(self):
        self.assertNotIn('call', self.codex(turn_started(NOW - 600), tool_call(NOW - 120, 'js'), tool_output(NOW - 100),
                                            agent_step(NOW - 90)))

    # --- titles
    def test_latest_rename_wins(self):
        path = self.log(custom_title('old name'), ai_title('ai name'), custom_title('new name'), human(NOW - 60))
        self.assertEqual(logs.scan_log('claude', path, title=True)['title'], 'new name')
        self.assertIsNone(logs.scan_log('claude', path).get('title'))

    def test_ai_title_when_never_renamed(self):
        self.assertEqual(self.claude(ai_title('ai name'), human(NOW - 60), title=True)['title'], 'ai name')


if __name__ == '__main__':
    unittest.main()
