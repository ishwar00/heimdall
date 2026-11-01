"""hooks/ti-event and hooks/install, run as the agents and you would run them, against a temporary home folder."""
import json
import os
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, 'hooks', 'ti-event')
INSTALL = os.path.join(ROOT, 'hooks', 'install')


class Hooks(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = tmp.name
        self.env = {'HOME': self.home, 'PATH': '/usr/bin:/bin'}

    def run_hook(self, tool, payload):
        return subprocess.run([HOOK, tool], input=payload, env=self.env, capture_output=True, text=True, timeout=30)

    def test_event_recorded_without_text(self):
        p = self.run_hook('claude', json.dumps({'hook_event_name': 'Notification', 'session_id': 's1', 'turn_id': 't1',
                                                'notification_type': 'permission_prompt', 'prompt': 'private words',
                                                'last_assistant_message': 'private reply'}))
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, '', ''))  # Claude adds a hook's output to the chat
        with open(f'{self.home}/Library/Application Support/ThreadIsland/events.jsonl') as fh:
            rec = json.loads(fh.read())
        self.assertEqual({k: v for k, v in rec.items() if k != 't'},
                         {'tool': 'claude', 'event': 'Notification', 'session': 's1', 'turn': 't1', 'type': 'permission_prompt'})

    def test_bad_input_never_fails_the_agent(self):
        p = self.run_hook('codex', 'not json')
        self.assertEqual((p.returncode, p.stdout), (0, ''))

    def install(self, *args):
        p = subprocess.run([INSTALL, *args], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)

    def read(self, path):
        with open(os.path.join(self.home, path)) as fh:
            return json.load(fh)

    def test_install_keeps_your_settings_and_removes_cleanly(self):
        mine = {'model': 'opus', 'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'afplay done.aiff'}]}],
                                           'PreToolUse': [{'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'guard'}]}]}}
        os.makedirs(f'{self.home}/.claude')
        with open(f'{self.home}/.claude/settings.json', 'w') as fh:
            json.dump(mine, fh)
        self.install()
        self.install()  # twice: no duplicates
        claude, codex = self.read('.claude/settings.json'), self.read('.codex/hooks.json')
        self.assertEqual(claude['model'], 'opus')
        self.assertEqual([len(claude['hooks'][e]) for e in ('Stop', 'PreToolUse', 'UserPromptSubmit', 'Notification', 'SessionEnd')],
                         [2, 1, 1, 1, 1])
        self.assertEqual(sorted(codex['hooks']), ['Interrupt', 'PermissionRequest', 'SessionEnd', 'Stop', 'UserPromptSubmit'])
        self.assertTrue(all(HOOK in g['hooks'][0]['command'] for g in codex['hooks']['Stop']))
        self.install('--remove')
        self.assertEqual(self.read('.claude/settings.json'), mine)
        self.assertFalse(os.path.exists(f'{self.home}/.codex/hooks.json'))  # install made it; nothing else was in it
        self.assertEqual(self.read('.claude/settings.json.threadisland-backup'), mine)


if __name__ == '__main__':
    unittest.main()
