"""Priority's order: rows never swap on their own, a dragged order is kept, joiners go to the bottom."""
import copy
import json
import os
import tempfile
import unittest

from heimdall import core, sections, state

NOW = core.NOW


def row(key, entered, active=60):
    return {'key': key, 'entered': NOW - entered, 'ts': NOW - entered, 'active': NOW - active}


class Priority(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, state, 'STATE', state.STATE)
        state.STATE = os.path.join(tmp.name, 'state.json')

    def priority(self, rows):
        return [r['key'] for r in sections.sectioned(copy.deepcopy(rows)) if r['section'] == 'Priority']

    def test_order(self):
        base = [row('a', 3000), row('b', 2000), row('c', 1000)]
        self.assertEqual(self.priority(base), ['a', 'b', 'c'])  # in the order their runs began
        sections.edit({'keys': ['c', 'a', 'b']})
        self.assertEqual(self.priority(base), ['c', 'a', 'b'])  # dragged
        self.assertEqual(self.priority(base + [row('d', 10)]), ['c', 'a', 'b', 'd'])  # joins at the bottom
        idle_a = [row('a', 3000, active=3 * 3600), row('b', 2000), row('c', 1000), row('d', 10)]
        self.assertEqual(self.priority(idle_a), ['c', 'b', 'd'])  # left: loses its slot
        back_a = [row('a', 5), row('b', 2000), row('c', 1000), row('d', 10)]
        self.assertEqual(self.priority(back_a), ['c', 'b', 'd', 'a'])  # back: at the bottom

    def test_drag_keeps_pages(self):
        with state.edited_state() as s:
            s['pages'] = [{'id': 'p', 'bundle': 'b', 'name': 'n'}]
        sections.edit({'keys': ['a', 7]})
        with open(state.STATE) as fh:
            saved = json.load(fh)
        self.assertEqual(saved['order'], ['a'])
        self.assertEqual([p['id'] for p in saved['pages']], ['p'])


if __name__ == '__main__':
    unittest.main()
