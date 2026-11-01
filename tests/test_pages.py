"""Saved pages: add, remove to Recently removed, pin back; and the favicon fetch's guard on where it may go."""
import http.server
import json
import os
import tempfile
import threading
import unittest
import urllib.request

from threadisland import pages, state


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

    def test_recently_removed_is_capped(self):
        for i in range(12):
            self.add(id=f'q{i}', bundle='b', name='x')
            pages.pages_edit({'op': 'remove', 'id': f'q{i}'})
        self.assertEqual(len(self.saved()['recent_pages']), pages.RECENT_PAGES)


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
        self.addCleanup(self.other.shutdown)
        self.other_icon = other_url + '/icon.png'

    def page(self, html, extra=None):
        server, url = serve(dict({'/': ('text/html', html.encode())}, **(extra or {})))
        self.addCleanup(server.shutdown)
        return url + '/'

    def test_own_site_icon(self):
        url = self.page('<link rel="icon" href="/i.png">', {'/i.png': ('image/png', ICON)})
        path = pages.favicon(url, 'p1')
        with open(path, 'rb') as fh:
            self.assertEqual(fh.read(), ICON)

    def test_page_cant_point_the_fetch_at_your_machine(self):
        page_hits = []
        server, url = serve({'/': ('text/html', f'<link rel="icon" href="{self.other_icon}">'.encode())}, page_hits)
        self.addCleanup(server.shutdown)
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
        self.addCleanup(server.shutdown)
        self.assertIsNone(pages.favicon(f'http://127.0.0.1:{server.server_port}/', 'p1'))
        self.assertEqual(self.other_hits, [])

    def test_not_a_web_page(self):
        self.assertIsNone(pages.favicon('file:///etc/hosts', 'p1'))


if __name__ == '__main__':
    unittest.main()
