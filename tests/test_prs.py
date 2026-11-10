"""PRs a thread created, read incrementally from its log, and their labels."""
import os
import tempfile
import unittest

from fixtures import gh_pr_create, jline, mcp_pr_create, pr_created, reply
from heimdall import prs

U = 'https://github.com/acme/app/pull/'


class CreatedPRs(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, 'log.jsonl')

    def append(self, text):
        with open(self.path, 'a') as fh:
            fh.write(text)

    def test_claude_created_counts_mention_does_not(self):
        self.append(reply(0, f'see {U}9, then gh pr create') + '\n' + pr_created(0, U + '7') + '\n')
        self.assertEqual(prs.created_prs('claude', self.path, {}), [U + '7'])

    def test_codex_failed_create_ignored(self):
        self.append(gh_pr_create(0, U + '3', code=1) + '\n' + gh_pr_create(0, U + '4') + '\n')
        self.assertEqual(prs.created_prs('codex', self.path, {}), [U + '4'])

    def test_codex_github_app(self):
        self.append(mcp_pr_create(U + '5', status='failed') + '\n' + mcp_pr_create(U + '6') + '\n')
        self.assertEqual(prs.created_prs('codex', self.path, {}), [U + '6'])

    def test_reads_only_what_was_added(self):
        seen = {}
        self.append(gh_pr_create(0, U + '4') + '\n')
        self.assertEqual(prs.created_prs('codex', self.path, seen), [U + '4'])
        self.append(gh_pr_create(0, U + '5'))  # still being written: no newline yet
        self.assertEqual(prs.created_prs('codex', self.path, seen), [U + '4'])
        self.append('\n' + gh_pr_create(0, U + '6') + '\n')
        self.assertEqual(prs.created_prs('codex', self.path, seen), [U + '4', U + '5', U + '6'])

    def test_rewritten_log_is_read_again(self):
        seen = {}
        self.append(gh_pr_create(0, U + '4') + '\n' + jline({'pad': 'x' * 500}) + '\n')
        prs.created_prs('codex', self.path, seen)
        with open(self.path, 'w') as fh:
            fh.write(gh_pr_create(0, U + '8') + '\n')
        self.assertEqual(prs.created_prs('codex', self.path, seen), [U + '8'])


class Label(unittest.TestCase):
    def test_labels(self):
        base = {'draft': False, 'checks': 'SUCCESS', 'review': None}
        for change, want in (({'draft': True}, 'draft'), ({'checks': 'FAILURE'}, 'checks failing'),
                             ({'review': 'CHANGES_REQUESTED'}, 'changes requested'), ({'review': 'APPROVED'}, 'approved'),
                             ({}, 'in review')):
            self.assertEqual(prs.pr_label(U + '5', dict(base, **change)), f'#5 {want}')


if __name__ == '__main__':
    unittest.main()
