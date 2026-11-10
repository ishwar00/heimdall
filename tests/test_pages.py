"""Saved pages: add, remove to Recently removed, pin back; and the favicon fetch's guard on where it may go."""
import http.server
import json
import os
import subprocess
import tempfile
import threading
import unittest
import urllib.request

from heimdall import core, pages, state


class Pages(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for module, name, value in ((state, 'STATE', os.path.join(tmp.name, 'state.json')),
                                    (pages, 'favicon', lambda url, key: None)):  # no network here
            self.addCleanup(setattr, module, name, getattr(module, name))
            setattr(module, name, value)

    def saved(self):
        with open(state.STATE) as fh:
            return json.load(fh)

    def add(self, **page):
        pages.pages_edit({'op': 'add', 'page': page})

    def test_add(self):
        self.add(bundle='com.example.chat', app='Chat', name='Chat', evil=1)
        self.add(bundle=pages.ARC, app='Arc', name='Inbox', tab='T1', url='https://mail.example.com/', space='S1')
        self.add(bundle='com.example.chat')  # no name: the app couldn't show it
        saved = self.saved()['pages']
        self.assertEqual([p['name'] for p in saved], ['Chat', 'Inbox'])
        self.assertNotIn('evil', saved[0])
        self.assertEqual(len({p['id'] for p in saved}), 2)

    def test_remove_and_restore(self):
        for i in range(3):
            self.add(id=f'p{i}', bundle='b', name=f'n{i}')
        pages.pages_edit({'op': 'remove', 'id': 'p0'})
        pages.pages_edit({'op': 'remove', 'id': 'p1'})
        self.assertEqual([p['id'] for p in self.saved()['pages']], ['p2'])
        self.assertEqual([p['id'] for p in self.saved()['recent_pages']], ['p1', 'p0'])  # newest first
        for _ in range(2):  # twice: no duplicate
            pages.pages_edit({'op': 'restore', 'id': 'p0'})
        self.assertEqual([p['id'] for p in self.saved()['pages']], ['p2', 'p0'])
        self.assertEqual([p['id'] for p in self.saved()['recent_pages']], ['p1'])

    def test_reorder(self):
        for i in range(4):
            self.add(id=f'p{i}', bundle='b', name=f'n{i}')
        pages.pages_edit({'op': 'order', 'ids': ['p2', 'p0', 'gone', 7]})  # p1, p3 not in it: after, in their order
        self.assertEqual([p['id'] for p in self.saved()['pages']], ['p2', 'p0', 'p1', 'p3'])

    def test_recently_removed_is_capped(self):
        for i in range(12):
            self.add(id=f'q{i}', bundle='b', name='x')
            pages.pages_edit({'op': 'remove', 'id': f'q{i}'})
        self.assertEqual(len(self.saved()['recent_pages']), pages.RECENT_PAGES)


class FrontApp(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, pages, 'run', pages.run)

    def apps(self, front, visible, info):
        def run(cmd, **kw):
            if cmd[1] == 'front':
                return front + '\n'
            if cmd[1] == 'visibleProcessList':
                return ' '.join(f'{asn}-"x":' for asn in visible)
            bundle, kind = info[cmd[-1]]
            return f'"CFBundleIdentifier"="{bundle}"\n"LSDisplayName"="{bundle}"\n"ApplicationType"="{kind}"\n'
        pages.run = run

    def test_the_app_you_are_in(self):
        self.apps('ASN:0x0-0x2', ['ASN:0x0-0x2'], {'ASN:0x0-0x2': ('com.example.chat', 'Foreground')})
        self.assertEqual(pages.front_app(), ('com.example.chat', 'com.example.chat'))

    def test_windowless_system_app_in_front_is_skipped(self):
        # after a click on the desktop macOS can report WindowManager in front; saving it opened nothing
        self.apps('ASN:0x0-0x1', ['ASN:0x0-0x2', 'ASN:0x0-0x3'],
                  {'ASN:0x0-0x1': ('com.apple.WindowManager', 'UIElement'),
                   'ASN:0x0-0x2': ('com.example.chat', 'Foreground'), 'ASN:0x0-0x3': ('com.example.mail', 'Foreground')})
        self.assertEqual(pages.front_app()[0], 'com.example.chat')

    def test_no_app(self):
        self.apps('ASN:0x0-0x1', [], {'ASN:0x0-0x1': ('com.apple.dock', 'UIElement')})
        self.assertEqual(pages.front_app(), (None, None))


class OpenPage(unittest.TestCase):
    """A saved Arc tab is reopened only when Arc says no window has it, never because the lookup failed."""
    PAGE = {'tab': 'T1', 'space': 'S1', 'url': 'https://mail.example.com/', 'bundle': pages.ARC, 'name': 'Mail'}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.opened = []
        for module, name, value in ((core, 'JUMPS', os.path.join(tmp.name, 'jumps.log')),
                                    (pages, 'checked', lambda cmd: self.opened.append(cmd))):
            self.addCleanup(setattr, module, name, getattr(module, name))
            setattr(module, name, value)

    def arc(self, stdout, stderr=''):
        self.addCleanup(setattr, pages.subprocess, 'run', pages.subprocess.run)
        pages.subprocess.run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0 if stdout else 1, stdout, stderr)
        return pages.open_page(self.PAGE)

    def test_open_tab_is_selected(self):
        self.assertIsNone(self.arc('ok\n'))
        self.assertEqual(self.opened, [])

    def test_closed_tab_is_opened_again(self):
        self.arc('missing\n')
        self.assertEqual(self.opened, [['open', '-b', pages.ARC, self.PAGE['url']]])

    def test_failed_lookup_opens_nothing(self):
        # Arc busy, or still restoring its windows after a launch: the tab may well be open
        self.assertEqual(self.arc('', 'Arc got an error: AppleEvent timed out. (-1712)'),
                         'Arc got an error: AppleEvent timed out. (-1712)')
        self.assertEqual(self.opened, [])
        with open(core.JUMPS) as fh:
            self.assertIn('AppleEvent timed out', fh.read())


ICON = b'\x89PNG\r\n\x1a\n'


def serve(routes, hits=None):
    """A local HTTP server answering path -> (content type, body); 404 otherwise. Returns its origin.
    hits, if given, collects every path asked for."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if hits is not None:
                hits.append(self.path)
            hit = routes.get(self.path)
            self.send_response(200 if hit else 404)
            self.send_header('Content-Type', hit[0] if hit else 'text/plain')
            self.end_headers()
            self.wfile.write(hit[1] if hit else b'')

        def log_message(self, *args):
            pass
    server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f'http://127.0.0.1:{server.server_port}'


def stop(server):
    server.shutdown()
    server.server_close()


class Favicon(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, pages, 'FAVICONS', pages.FAVICONS)
        pages.FAVICONS = tmp.name
        # a proxy from the environment would take these requests away from the local servers
        self.addCleanup(setattr, urllib.request, 'getproxies', urllib.request.getproxies)
        urllib.request.getproxies = dict
        self.other_hits = []
        self.other, other_url = serve({'/icon.png': ('image/png', ICON)}, self.other_hits)
        self.addCleanup(stop, self.other)
        self.other_icon = other_url + '/icon.png'

    def page(self, html, extra=None):
        server, url = serve(dict({'/': ('text/html', html.encode())}, **(extra or {})))
        self.addCleanup(stop, server)
        return url + '/'

    def test_own_site_icon(self):
        url = self.page('<link rel="icon" href="/i.png">', {'/i.png': ('image/png', ICON)})
        path = pages.favicon(url, 'p1')
        with open(path, 'rb') as fh:
            self.assertEqual(fh.read(), ICON)

    def test_page_cant_point_the_fetch_at_your_machine(self):
        page_hits = []
        server, url = serve({'/': ('text/html', f'<link rel="icon" href="{self.other_icon}">'.encode())}, page_hits)
        self.addCleanup(stop, server)
        self.assertIsNone(pages.favicon(url + '/', 'p1'))
        self.assertEqual(page_hits, ['/', '/favicon.ico'])  # it did read the page
        self.assertEqual(self.other_hits, [])

    def test_redirect_to_your_machine_refused(self):
        class Redirect(http.server.BaseHTTPRequestHandler):
            def do_GET(handler):
                handler.send_response(302)
                handler.send_header('Location', self.other_icon)
                handler.end_headers()

            def log_message(handler, *args):
                pass
        server = http.server.HTTPServer(('127.0.0.1', 0), Redirect)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(stop, server)
        self.assertIsNone(pages.favicon(f'http://127.0.0.1:{server.server_port}/', 'p1'))
        self.assertEqual(self.other_hits, [])

    def test_not_a_web_page(self):
        self.assertIsNone(pages.favicon('file:///etc/hosts', 'p1'))


if __name__ == '__main__':
    unittest.main()
