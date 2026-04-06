#!/usr/bin/env python3
"""
Desktop Search Bar for Pop OS 24.04
Floating search bar for web (Google) and local file search.
Runs as a background daemon; use --toggle to show/hide from a keyboard shortcut.
"""

import os
import sys
import signal
import socket
import subprocess
import threading
import urllib.parse
import webbrowser

os.environ.setdefault('GIO_USE_VFS', 'local')

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

SOCKET_PATH = '/tmp/.search_bar_daemon.sock'
WINDOW_WIDTH = 700

SEARCH_ENGINES = [
    ('Google',     'https://www.google.com/search?q={}'),
    ('YouTube',    'https://www.youtube.com/results?search_query={}'),
    ('Twitch',     'https://www.twitch.tv/search?term={}'),
    ('Reddit',     'https://www.reddit.com/search/?q={}'),
    ('GitHub',     'https://github.com/search?q={}'),
    ('DuckDuckGo', 'https://duckduckgo.com/?q={}'),
]


# ── IPC helpers ──────────────────────────────────────────────────────────────

def send_command(cmd: bytes) -> bool:
    """Send a command to an existing daemon. Returns True on success."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        sock.connect(SOCKET_PATH)
        sock.send(cmd)
        sock.close()
        return True
    except OSError:
        return False


# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = b"""
* { transition: none; }

window {
    background: transparent;
}

.main-box {
    background: rgba(24, 24, 37, 0.97);
    border-radius: 14px;
    border: 1px solid rgba(255, 255, 255, 0.10);
    box-shadow: 0 12px 40px rgba(0,0,0,0.70);
}

.search-row {
    padding: 4px 6px;
}

.search-icon {
    color: #585b70;
}

.search-entry {
    background: transparent;
    border: none;
    box-shadow: none;
    color: #cdd6f4;
    font-size: 18px;
    padding: 4px 2px;
    caret-color: #cba6f7;
}

.search-entry:focus {
    box-shadow: none;
    outline: none;
}

.engine-combo {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 6px;
    color: #cdd6f4;
    font-size: 12px;
    padding: 0;
    min-height: 0;
}

.engine-combo button,
.engine-combo button.combo {
    background: transparent;
    border: none;
    box-shadow: none;
    color: #cdd6f4;
    padding: 2px 6px;
    min-height: 0;
}

.engine-combo button:hover {
    background: rgba(255,255,255,0.08);
    border-radius: 6px;
}

.engine-sep {
    background: rgba(255,255,255,0.10);
    min-width: 1px;
    margin: 6px 2px;
}

.clear-btn {
    color: #45475a;
    background: transparent;
    border: none;
    border-radius: 50%;
    padding: 0;
    min-width: 26px;
    min-height: 26px;
}

.clear-btn:hover {
    color: #cdd6f4;
    background: rgba(255,255,255,0.08);
}

.divider {
    background: rgba(255,255,255,0.07);
    min-height: 1px;
    margin: 0;
}

.result-row {
    border-radius: 8px;
    margin: 1px 8px;
}

.result-row:hover {
    background: rgba(255,255,255,0.07);
}

.result-row.selected {
    background: rgba(203,166,247,0.17);
}

.result-inner {
    padding: 8px 10px;
}

.result-icon       { color: #7f849c; }
.result-icon.web   { color: #89b4fa; }
.result-icon.image { color: #f5c2e7; }
.result-icon.video { color: #fab387; }
.result-icon.audio { color: #a6e3a1; }
.result-icon.doc   { color: #89dceb; }
.result-icon.code  { color: #cba6f7; }
.result-icon.dir   { color: #f9e2af; }

.result-title {
    color: #cdd6f4;
    font-size: 13px;
}

.result-path {
    color: #585b70;
    font-size: 11px;
}

.badge {
    font-size: 10px;
    font-weight: bold;
    border-radius: 4px;
    padding: 2px 6px;
}

.badge.web  { color: #89b4fa; background: rgba(137,180,250,0.13); }
.badge.file { color: #a6e3a1; background: rgba(166,227,161,0.13); }
.badge.dir  { color: #f9e2af; background: rgba(249,226,175,0.13); }

scrolledwindow undershoot,
scrolledwindow overshoot {
    background: transparent;
}
"""


# ── File helpers ──────────────────────────────────────────────────────────────

_EXT_ICON = {
    # Documents
    '.pdf':  ('application-pdf-symbolic',        'doc'),
    '.doc':  ('x-office-document-symbolic',       'doc'),
    '.docx': ('x-office-document-symbolic',       'doc'),
    '.odt':  ('x-office-document-symbolic',       'doc'),
    '.xls':  ('x-office-spreadsheet-symbolic',    'doc'),
    '.xlsx': ('x-office-spreadsheet-symbolic',    'doc'),
    '.ods':  ('x-office-spreadsheet-symbolic',    'doc'),
    '.ppt':  ('x-office-presentation-symbolic',   'doc'),
    '.pptx': ('x-office-presentation-symbolic',   'doc'),
    '.odp':  ('x-office-presentation-symbolic',   'doc'),
    '.txt':  ('text-x-generic-symbolic',          'doc'),
    '.md':   ('text-x-generic-symbolic',          'doc'),
    '.rtf':  ('text-x-generic-symbolic',          'doc'),
    # Images
    '.png':  ('image-x-generic-symbolic',  'image'),
    '.jpg':  ('image-x-generic-symbolic',  'image'),
    '.jpeg': ('image-x-generic-symbolic',  'image'),
    '.gif':  ('image-x-generic-symbolic',  'image'),
    '.svg':  ('image-x-generic-symbolic',  'image'),
    '.webp': ('image-x-generic-symbolic',  'image'),
    '.bmp':  ('image-x-generic-symbolic',  'image'),
    # Video
    '.mp4':  ('video-x-generic-symbolic',  'video'),
    '.mkv':  ('video-x-generic-symbolic',  'video'),
    '.avi':  ('video-x-generic-symbolic',  'video'),
    '.mov':  ('video-x-generic-symbolic',  'video'),
    '.webm': ('video-x-generic-symbolic',  'video'),
    # Audio
    '.mp3':  ('audio-x-generic-symbolic',  'audio'),
    '.flac': ('audio-x-generic-symbolic',  'audio'),
    '.ogg':  ('audio-x-generic-symbolic',  'audio'),
    '.wav':  ('audio-x-generic-symbolic',  'audio'),
    '.aac':  ('audio-x-generic-symbolic',  'audio'),
    # Code / scripts
    '.py':   ('text-x-script-symbolic',   'code'),
    '.js':   ('text-x-script-symbolic',   'code'),
    '.ts':   ('text-x-script-symbolic',   'code'),
    '.sh':   ('text-x-script-symbolic',   'code'),
    '.c':    ('text-x-script-symbolic',   'code'),
    '.cpp':  ('text-x-script-symbolic',   'code'),
    '.go':   ('text-x-script-symbolic',   'code'),
    '.rs':   ('text-x-script-symbolic',   'code'),
    '.html': ('text-html-symbolic',        'code'),
    '.css':  ('text-x-script-symbolic',   'code'),
    # Archives
    '.zip':  ('package-x-generic-symbolic', None),
    '.tar':  ('package-x-generic-symbolic', None),
    '.gz':   ('package-x-generic-symbolic', None),
    '.7z':   ('package-x-generic-symbolic', None),
}


def file_icon(path: str):
    """Return (icon_name, icon_css_class) for a file path."""
    if os.path.isdir(path):
        return 'folder-symbolic', 'dir'
    ext = os.path.splitext(path)[1].lower()
    icon, cls = _EXT_ICON.get(ext, ('text-x-generic-symbolic', None))
    return icon, cls


# ── Main application ──────────────────────────────────────────────────────────

class SearchApp:
    def __init__(self):
        self._cancel = False
        self.results: list = []
        self.selected: int = -1
        self._focus_guard = False  # prevents immediate close on launch

        self._setup_ipc()
        self._build_window()
        self._apply_css()

    # ── IPC server ────────────────────────────────────────────────────────────

    def _setup_ipc(self):
        try:
            os.unlink(SOCKET_PATH)
        except FileNotFoundError:
            pass
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(SOCKET_PATH)
        self._server.listen(1)
        GLib.io_add_watch(self._server.fileno(), GLib.IO_IN, self._on_ipc)

    def _on_ipc(self, fd, condition):
        conn, _ = self._server.accept()
        try:
            data = conn.recv(64)
        finally:
            conn.close()
        if data == b'toggle':
            if self.win.get_visible():
                self.win.hide()
            else:
                self._show()
        elif data == b'show':
            self._show()
        elif data == b'quit':
            Gtk.main_quit()
        return True  # keep watching

    # ── Window construction ───────────────────────────────────────────────────

    def _build_window(self):
        win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        win.set_title("Search")
        win.set_decorated(False)
        win.set_resizable(False)
        win.set_keep_above(True)
        win.set_skip_taskbar_hint(True)
        win.set_skip_pager_hint(True)
        win.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        win.set_default_size(WINDOW_WIDTH, -1)

        # RGBA for transparency / rounded corners
        screen = win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            win.set_visual(visual)
        win.set_app_paintable(True)

        # ── Layout ────────────────────────────────────────────────────────────
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.get_style_context().add_class('main-box')
        win.add(main_box)

        # Search row
        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        search_row.get_style_context().add_class('search-row')
        search_row.set_margin_start(12)
        search_row.set_margin_end(8)
        search_row.set_margin_top(8)
        search_row.set_margin_bottom(8)
        main_box.pack_start(search_row, False, False, 0)

        search_icon = Gtk.Image.new_from_icon_name(
            'system-search-symbolic', Gtk.IconSize.LARGE_TOOLBAR)
        search_icon.get_style_context().add_class('search-icon')
        search_row.pack_start(search_icon, False, False, 2)

        # Engine dropdown
        self._engine_combo = Gtk.ComboBoxText()
        self._engine_combo.get_style_context().add_class('engine-combo')
        for name, _ in SEARCH_ENGINES:
            self._engine_combo.append_text(name)
        self._engine_combo.set_active(0)
        search_row.pack_start(self._engine_combo, False, False, 2)

        # Thin separator between combo and entry
        vsep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        vsep.get_style_context().add_class('engine-sep')
        search_row.pack_start(vsep, False, False, 0)

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Search files or the web…")
        self.entry.get_style_context().add_class('search-entry')
        self.entry.set_has_frame(False)
        search_row.pack_start(self.entry, True, True, 0)

        # Clear button
        clear_btn = Gtk.Button()
        clear_btn.set_relief(Gtk.ReliefStyle.NONE)
        clear_btn.add(Gtk.Image.new_from_icon_name(
            'edit-clear-symbolic', Gtk.IconSize.SMALL_TOOLBAR))
        clear_btn.get_style_context().add_class('clear-btn')
        clear_btn.set_no_show_all(True)
        clear_btn.connect('clicked', self._on_clear)
        search_row.pack_end(clear_btn, False, False, 0)
        self._clear_btn = clear_btn

        # Divider
        self._divider = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self._divider.get_style_context().add_class('divider')
        self._divider.set_no_show_all(True)
        main_box.pack_start(self._divider, False, False, 0)

        # Scrolled results area
        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroll.set_max_content_height(400)
        self._scroll.set_propagate_natural_height(True)
        self._scroll.set_no_show_all(True)
        main_box.pack_start(self._scroll, False, False, 0)

        self._results_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._results_box.set_margin_top(6)
        self._results_box.set_margin_bottom(6)
        self._scroll.add(self._results_box)

        # ── Signals ───────────────────────────────────────────────────────────
        win.connect('key-press-event', self._on_key)
        # focus-out hiding disabled — close with Escape or by clicking a result
        win.connect('delete-event', lambda w, e: w.hide() or True)
        self.entry.connect('changed', self._on_text_changed)
        self.entry.connect('activate', self._on_enter)

        self.win = win

    def _apply_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ── Positioning ───────────────────────────────────────────────────────────

    def _position(self):
        """Centre the window. Falls back gracefully on Wayland where move() is ignored."""
        self.win.set_position(Gtk.WindowPosition.CENTER)
        # X11 only: fine-tune vertical position to upper quarter of screen
        display = Gdk.Display.get_default()
        if display.get_name() != 'wayland':
            try:
                seat = display.get_default_seat()
                _screen, cx, cy = seat.get_pointer().get_position()
                monitor = display.get_monitor_at_point(cx, cy)
                geom = monitor.get_geometry()
                x = geom.x + (geom.width - WINDOW_WIDTH) // 2
                y = geom.y + int(geom.height * 0.22)
                self.win.move(x, y)
            except Exception:
                pass

    # ── Show / hide ───────────────────────────────────────────────────────────

    def _show(self):
        self.entry.set_text('')
        self._clear_results()
        self._position()
        self._focus_guard = True
        self.win.show_all()
        self._divider.hide()
        self._scroll.hide()
        self._clear_btn.hide()
        self.win.present()
        self.entry.grab_focus()
        GLib.timeout_add(3000, self._release_focus_guard)

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_key(self, _win, event):
        k = event.keyval
        if k == Gdk.KEY_Escape:
            self.win.hide()
            return True
        if k == Gdk.KEY_Down:
            self._move_sel(1)
            return True
        if k == Gdk.KEY_Up:
            self._move_sel(-1)
            return True
        if k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if 0 <= self.selected < len(self.results):
                self._activate(self.results[self.selected])
            else:
                self._on_enter(None)
            return True
        return False

    def _release_focus_guard(self):
        self._focus_guard = False
        return False

    def _on_focus_out(self, _win, _event):
        if self._focus_guard:
            return False
        GLib.timeout_add(180, lambda: self.win.hide() or False)
        return False

    def _on_clear(self, _btn):
        self.entry.set_text('')
        self.entry.grab_focus()

    def _on_text_changed(self, entry):
        text = entry.get_text()
        if text:
            self._clear_btn.show()
        else:
            self._clear_btn.hide()
            self._clear_results()
            return
        self._cancel = True
        GLib.timeout_add(130, self._debounced_search, text)

    def _debounced_search(self, query):
        if self.entry.get_text() != query:
            return False
        self._cancel = False
        threading.Thread(
            target=self._worker, args=(query,), daemon=True).start()
        return False

    def _selected_engine(self):
        idx = self._engine_combo.get_active()
        if idx < 0:
            idx = 0
        return SEARCH_ENGINES[idx]

    def _on_enter(self, _entry):
        q = self.entry.get_text().strip()
        if q:
            self.win.hide()
            name, url_tmpl = self._selected_engine()
            webbrowser.open(url_tmpl.format(urllib.parse.quote(q)))

    # ── Selection ─────────────────────────────────────────────────────────────

    def _move_sel(self, delta):
        if not self.results:
            return
        self.selected = max(0, min(
            self.selected + delta, len(self.results) - 1))
        self._refresh_sel()

    def _refresh_sel(self):
        for i, row in enumerate(self._results_box.get_children()):
            ctx = row.get_style_context()
            if i == self.selected:
                ctx.add_class('selected')
            else:
                ctx.remove_class('selected')

    # ── Search worker (background thread) ────────────────────────────────────

    def _worker(self, query):
        if self._cancel:
            return
        eng_name, url_tmpl = self._selected_engine()
        results = [{
            'type': 'web',
            'title': f'Search {eng_name} for "{query}"',
            'subtitle': url_tmpl.format('…'),
            'icon': 'web-browser-symbolic',
            'icon_cls': 'web',
            'badge': 'WEB',
            'badge_cls': 'web',
            'action': lambda q=query, t=url_tmpl: webbrowser.open(
                t.format(urllib.parse.quote(q))),
        }]

        if not self._cancel:
            results.extend(self._search_files(query))

        if not self._cancel:
            GLib.idle_add(self._display, results, query)

    def _search_files(self, query: str, limit: int = 15) -> list:
        results = []
        home = os.path.expanduser('~')

        # Fast path: plocate / locate
        for cmd in ('plocate', 'locate'):
            try:
                proc = subprocess.run(
                    [cmd, '-i', '-l', str(limit + 10), '--', query],
                    capture_output=True, text=True, timeout=2.0,
                )
                if proc.returncode == 0:
                    paths = [p for p in proc.stdout.splitlines() if p]
                    # Prioritise home directory hits
                    home_hits = [p for p in paths if p.startswith(home) and os.path.exists(p)]
                    other_hits = [p for p in paths if not p.startswith(home) and os.path.exists(p)]
                    for path in (home_hits + other_hits)[:limit]:
                        if self._cancel:
                            return results
                        results.append(self._make_file_result(path))
                    return results
            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                break

        # Slow fallback: find in common dirs
        common_dirs = [
            home,
            os.path.join(home, 'Documents'),
            os.path.join(home, 'Downloads'),
            os.path.join(home, 'Desktop'),
            os.path.join(home, 'Pictures'),
            os.path.join(home, 'Videos'),
        ]
        seen: set = set()
        for d in common_dirs:
            if not os.path.isdir(d) or self._cancel:
                continue
            try:
                proc = subprocess.run(
                    ['find', d, '-maxdepth', '5',
                     '-not', '-path', '*/.*',
                     '-iname', f'*{query}*'],
                    capture_output=True, text=True, timeout=2.5,
                )
                for path in proc.stdout.splitlines():
                    if path and path not in seen:
                        seen.add(path)
                        results.append(self._make_file_result(path))
                        if len(results) >= limit:
                            return results
            except subprocess.TimeoutExpired:
                break
        return results

    def _make_file_result(self, path: str) -> dict:
        name = os.path.basename(path)
        home = os.path.expanduser('~')
        display_dir = os.path.dirname(path).replace(home, '~', 1)
        icon_name, icon_cls = file_icon(path)
        is_dir = os.path.isdir(path)
        return {
            'type': 'dir' if is_dir else 'file',
            'title': name,
            'subtitle': display_dir,
            'icon': icon_name,
            'icon_cls': icon_cls or ('dir' if is_dir else None),
            'badge': 'DIR' if is_dir else 'FILE',
            'badge_cls': 'dir' if is_dir else 'file',
            'action': lambda p=path: subprocess.Popen(['xdg-open', p]),
        }

    # ── Results display ───────────────────────────────────────────────────────

    def _display(self, results: list, query: str):
        if self.entry.get_text() != query:
            return False
        self._clear_results(keep_ui=True)
        self.results = results
        self.selected = -1

        if not results:
            self._divider.hide()
            self._scroll.hide()
            return False

        self._divider.show()
        self._scroll.show()

        for i, r in enumerate(results):
            self._results_box.pack_start(self._build_row(r, i), False, False, 0)
        self._results_box.show_all()
        return False

    def _build_row(self, result: dict, index: int) -> Gtk.Widget:
        ev = Gtk.EventBox()
        ev.get_style_context().add_class('result-row')
        ev.connect('button-press-event',
                   lambda w, e, r=result: self._activate(r))
        ev.connect('enter-notify-event',
                   lambda w, e, i=index: self._hover(i))

        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        inner.get_style_context().add_class('result-inner')
        ev.add(inner)

        # Icon
        icon_w = Gtk.Image.new_from_icon_name(
            result['icon'], Gtk.IconSize.LARGE_TOOLBAR)
        ctx = icon_w.get_style_context()
        ctx.add_class('result-icon')
        if result.get('icon_cls'):
            ctx.add_class(result['icon_cls'])
        inner.pack_start(icon_w, False, False, 0)

        # Title + subtitle
        text_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        inner.pack_start(text_col, True, True, 0)

        title_lbl = Gtk.Label(label=result['title'])
        title_lbl.get_style_context().add_class('result-title')
        title_lbl.set_halign(Gtk.Align.START)
        title_lbl.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        text_col.pack_start(title_lbl, False, False, 0)

        sub = result.get('subtitle', '')
        if sub:
            sub_lbl = Gtk.Label(label=sub)
            sub_lbl.get_style_context().add_class('result-path')
            sub_lbl.set_halign(Gtk.Align.START)
            sub_lbl.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            text_col.pack_start(sub_lbl, False, False, 0)

        # Badge
        badge = Gtk.Label(label=result.get('badge', ''))
        ctx2 = badge.get_style_context()
        ctx2.add_class('badge')
        if result.get('badge_cls'):
            ctx2.add_class(result['badge_cls'])
        badge.set_valign(Gtk.Align.CENTER)
        inner.pack_end(badge, False, False, 0)

        return ev

    def _hover(self, index: int):
        self.selected = index
        self._refresh_sel()

    def _activate(self, result: dict):
        self.win.hide()
        GLib.timeout_add(50, result['action'])

    def _clear_results(self, keep_ui: bool = False):
        for child in self._results_box.get_children():
            self._results_box.remove(child)
        self.results = []
        self.selected = -1
        if not keep_ui:
            self._divider.hide()
            self._scroll.hide()

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self):
        signal.signal(signal.SIGINT,  lambda *_: Gtk.main_quit())
        signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
        self._show()
        Gtk.main()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if '--toggle' in args:
        # Signal existing instance to toggle, or fall through to start fresh
        if send_command(b'toggle'):
            sys.exit(0)
    elif '--show' in args:
        if send_command(b'show'):
            sys.exit(0)
    elif args and '--no-fork' not in args:
        print(f"Usage: {sys.argv[0]} [--toggle | --show]")
        sys.exit(1)
    elif '--no-fork' not in args:
        # No args: if already running, just show it
        if send_command(b'show'):
            sys.exit(0)

    # Re-launch with --no-fork so the background process has no threads yet
    if '--no-fork' not in args:
        subprocess.Popen(
            [sys.executable] + sys.argv + ['--no-fork'],
            start_new_session=True,
            close_fds=True,
        )
        sys.exit(0)

    app = SearchApp()
    app.run()


if __name__ == '__main__':
    main()
