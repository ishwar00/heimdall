"""Saved pages: capture where you are (an Arc tab or an app), open it again, fetch a saved tab's icon."""
import contextlib
import http.client
import ipaddress
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from . import core
from .core import run, checked
from .state import edited_state


ARC = 'company.thebrowser.Browser'
# Arc's scripting: https://resources.arc.net/hc/en-us/articles/19212718608151-Arc-for-macOS-AppleScript-API
# fields joined by the unit separator (0x1F), which titles and URLs don't contain
ARC_CAPTURE = '''set d to ASCII character 31
tell application "Arc" to tell front window
    return (id of active tab) & d & (title of active tab) & d & (URL of active tab) & d & (id of active space) & d & (title of active space)
end tell'''
ARC_SELECT = '''on run argv
    tell application "Arc"
        activate
        tell front window
            try
                tell (first space whose id is (item 2 of argv)) to focus
            end try
            try
                tell (first tab whose id is (item 1 of argv)) to select
                return "ok"
            end try
            repeat with s in spaces
                try
                    tell (first tab of s whose id is (item 1 of argv)) to select
                    return "ok"
                end try
            end repeat
            -- Arc can give a tab a new id (after a restart); the same page still open counts
            repeat with s in spaces
                try
                    tell (first tab of s whose URL is (item 3 of argv)) to select
                    return "ok"
                end try
            end repeat
        end tell
    end tell
    return "missing"
end run'''


def front_app():
    """(bundle id, name) of the app you're in; the island never takes that from it. macOS can report a
    windowless system agent as in front (WindowManager after a click on the desktop, the Dock): then the
    frontmost regular app, from the visible apps listed front to back."""
    visible = re.findall(r'ASN:0x[0-9a-f]+-0x[0-9a-f]+', run(['lsappinfo', 'visibleProcessList']))
    for asn in [run(['lsappinfo', 'front']).strip()] + visible:
        info = run(['lsappinfo', 'info', '-only', 'bundleid', '-only', 'name', '-only', 'ApplicationType', asn])
        bundle = re.search(r'"CFBundleIdentifier"="([^"]*)"', info)
        if bundle and '"ApplicationType"="Foreground"' in info:
            name = re.search(r'"LSDisplayName"="([^"]*)"', info)
            return bundle.group(1), (name.group(1) if name else None)
    return None, None


def capture_page():
    """Where you are right now: the Arc tab you're on, or the app (one window per app in practice)."""
    bundle, name = front_app()
    if not bundle:
        return {'error': 'no app in front'}
    page = {'bundle': bundle, 'app': name, 'name': name}
    if bundle == ARC:
        # the first time, macOS asks whether ThreadIsland may control Arc: leave time to answer
        try:
            p = subprocess.run(['osascript', '-e', ARC_CAPTURE], capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return {'error': "Arc didn't answer; try again"}
        parts = p.stdout.rstrip('\n').split('\x1f')
        if p.returncode != 0 or len(parts) != 5:
            # saving plain Arc instead would look like a saved tab and only ever open Arc
            return {'error': 'couldn\'t read the Arc tab: ' + (p.stderr.strip() or 'no tab open')
                    + ('. Allow ThreadIsland in System Settings > Privacy & Security > Automation' if '-1743' in p.stderr else '')}
        tab, title, url, space, space_title = parts
        page.update(tab=tab, url=url, space=space, name=title or name, detail=f'{space_title} space')
    return page


def open_page(page):
    if page.get('tab'):
        p = subprocess.run(['osascript', '-', page['tab'], page.get('space') or '', page.get('url') or ''], input=ARC_SELECT,
                           capture_output=True, text=True, timeout=30)
        if p.stdout.strip() == 'ok':
            return None
        if page.get('url'):  # closed since: open it again
            return checked(['open', '-b', ARC, page['url']])
        return p.stderr.strip() or 'tab not found'
    return checked(['open', '-b', page['bundle']])


FAVICONS = f'{core.HOME}/Library/Caches/ThreadIsland/favicons'
RECENT_PAGES = 8


def favicon(url, key):
    """The site's own icon for a saved tab: its <link rel="icon">, else /favicon.ico. Fetched from the site
    once when you save (no third-party favicon service, which would see every site you save), kept on disk.
    None if there isn't one; the page then shows the browser's icon."""
    if not url.startswith(('http://', 'https://')):
        return None
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh) ThreadIsland'}
    origin = urllib.parse.urlsplit(url)[:2]  # scheme and host:port of the page you saved

    def own(u):
        return urllib.parse.urlsplit(u)[:2] == origin

    def allowed(u):
        """The page's own origin (you saved it), or a public address: a page's HTML picks the icon URL, and
        mustn't make this fetch reach localhost or your network for it. Checked on every redirect too, and
        again on the connected socket, so DNS answering differently the second time doesn't get around it."""
        parts = urllib.parse.urlsplit(u)
        if not parts.hostname or parts.scheme not in ('http', 'https'):
            return False
        if own(u):
            return True
        try:
            ips = {ipaddress.ip_address(a[4][0]) for a in socket.getaddrinfo(parts.hostname, None)}
        except (OSError, ValueError):
            return False
        return bool(ips) and all(ip.is_global for ip in ips)

    def peer_ok(conn, u):
        if not own(u) and not ipaddress.ip_address(conn.sock.getpeername()[0]).is_global:
            raise OSError(f'{u} connected to a non-public address')

    class HTTP(http.client.HTTPConnection):
        def connect(self):
            super().connect()
            peer_ok(self, f'http://{self.host}:{self.port}')

    class HTTPS(http.client.HTTPSConnection):
        def connect(self):
            http.client.HTTPConnection.connect(self)  # plain socket first: check where it went, then TLS
            peer_ok(self, f'https://{self.host}:{self.port}')
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)

    class Handlers(urllib.request.HTTPHandler, urllib.request.HTTPSHandler):
        def http_open(self, req):
            return self.do_open(HTTP, req)

        def https_open(self, req):
            return self.do_open(HTTPS, req)

    class Checked(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            if not allowed(newurl):
                raise urllib.error.URLError(f'redirect to {newurl} not allowed')
            return super().redirect_request(req, fp, code, msg, hdrs, newurl)
    opener = urllib.request.build_opener(Checked, Handlers)

    def get(u, limit):
        if not allowed(u):
            raise ValueError(f'{u} not allowed')
        with opener.open(urllib.request.Request(u, headers=headers), timeout=4) as resp:
            return resp.read(limit), resp.headers.get_content_type()
    candidates = []
    try:
        html = get(url, 512 * 1024)[0].decode('utf-8', 'replace')
        for tag in re.findall(r'<link\b[^>]*>', html, re.I):
            rel = re.search(r'\brel\s*=\s*["\']?([^"\'>]+)', tag, re.I)
            href = re.search(r'\bhref\s*=\s*["\']?([^"\' >]+)', tag, re.I)
            if rel and href and 'icon' in rel.group(1).lower() and 'mask' not in rel.group(1).lower():
                candidates.append(urllib.parse.urljoin(url, href.group(1)))
    except (OSError, ValueError):
        pass
    candidates.append(urllib.parse.urljoin(url, '/favicon.ico'))
    for u in candidates:
        try:
            body, kind = get(u, 1024 * 1024)
        except (OSError, ValueError):
            continue
        if body and kind.startswith('image/'):
            os.makedirs(FAVICONS, exist_ok=True)
            path = os.path.join(FAVICONS, re.sub(r'[^A-Za-z0-9-]', '', key) + '.' + (kind.split('/')[1].split('+')[0] or 'img'))
            with open(path, 'wb') as fh:
                fh.write(body)
            return path
    return None


def pages_edit(e):
    icon = None
    if e['op'] == 'add' and isinstance(e['page'].get('url'), str) and isinstance(e['page'].get('id'), str):
        icon = favicon(e['page']['url'], e['page']['id'])  # before the lock: the network can be slow
    with edited_state() as state:
        pages = state.setdefault('pages', [])
        if e['op'] == 'add':
            page = {k: v for k, v in e['page'].items()
                    if k in ('id', 'bundle', 'app', 'name', 'tab', 'url', 'space', 'detail') and isinstance(v, str)}
            page.setdefault('id', f'{time.time_ns():x}')  # the app sends one, so it can show the page right away
            if icon:
                page['icon'] = icon
            # the app can't read a page without these; one bad entry would blank the whole list
            if page.get('bundle') and page.get('name') and all(p.get('id') != page['id'] for p in pages):
                pages.append(page)
        elif e['op'] == 'remove':
            # kept under Recently removed, newest first, so it can be pinned back
            recent = state.setdefault('recent_pages', [])
            recent[:0] = [p for p in pages if p.get('id') == e['id']]
            state['pages'] = [p for p in pages if p.get('id') != e['id']]
            for p in recent[RECENT_PAGES:]:
                if p.get('icon', '').startswith(FAVICONS):
                    with contextlib.suppress(OSError):
                        os.remove(p['icon'])
            del recent[RECENT_PAGES:]
        elif e['op'] == 'order':  # you dragged the chips; ids top to bottom, any page not in it keeps its place after
            rank = {k: i for i, k in enumerate(e['ids']) if isinstance(k, str)}
            state['pages'] = sorted(pages, key=lambda p: rank.get(p.get('id'), len(rank)))
        elif e['op'] == 'restore':
            recent = state.setdefault('recent_pages', [])
            pages.extend(p for p in recent if p.get('id') == e['id'] and all(q.get('id') != e['id'] for q in pages))
            state['recent_pages'] = [p for p in recent if p.get('id') != e['id']]
