# Desktop Search Bar

A fast, floating search bar for Linux — type to search **the web** (Google, YouTube,
GitHub, DuckDuckGo, and more) or your **local files**, all from one keyboard shortcut.
Built with GTK 3 and pure Python; runs as a lightweight background daemon and toggles
instantly.

> Targeted at Pop!_OS / GNOME-based desktops. See the [desktop notes](#desktop-notes) for COSMIC/Wayland.

## Features
- 🔎 **Unified search** — web search engines *and* local files in one bar.
- ⚡ **Instant toggle** — runs as a daemon; a global shortcut shows/hides it with no startup lag.
- 📁 **Fast file search** — uses `plocate` when available, falls back to `find` across your common folders.
- ⌨️ **Keyboard-driven** — `↑`/`↓` to navigate, `Enter` to open, `Esc` to dismiss.
- 🎨 **Themed UI** — rounded, translucent, file-type icons and badges.

<!-- Add a screenshot or GIF here — it makes a big difference for a UI project:
![Search bar](docs/screenshot.png) -->

## Requirements
- Python 3.9+
- GTK 3 + PyGObject (`python3-gi`, `python3-gi-cairo`, `gir1.2-gtk-3.0`)
- `plocate` (recommended) and `xdg-utils`

## Install
```bash
git clone https://github.com/Jacmd/search-bar.git
cd search-bar
./install.sh
```
The installer sets up dependencies, a `.desktop` entry, a login autostart (daemon
starts hidden), and — on GNOME — a global keyboard shortcut (default `Super+Space`).

Pick a different shortcut:
```bash
SHORTCUT_KEY="<Ctrl><Alt>space" ./install.sh
```

## Usage
```bash
python3 search_bar.py            # start + show the bar
python3 search_bar.py --toggle   # show/hide (bind this to your shortcut)
python3 search_bar.py --daemon   # start hidden (used by autostart)
```
Then: choose an engine, type a query, `Enter` to search the web — or pick a file
result to open it. `Esc` closes the bar.

## Desktop notes
- **GNOME (Pop!_OS 22.04, Ubuntu):** fully supported, including automatic shortcut setup.
- **COSMIC (Pop!_OS 24.04) / Wayland:** COSMIC doesn't use GNOME `gsettings` shortcuts,
  so the installer prints manual instructions instead. Under Wayland, window centering
  is left to the compositor (a client can't position its own windows); a future version
  may add `gtk-layer-shell` support.

## How it works
- A single background process owns a private Unix socket in `$XDG_RUNTIME_DIR`; `--toggle`/`--show`
  send it commands over that socket, so there's only ever one instance.
- Searches run on a worker thread (debounced) and post results back to the GTK main loop,
  keeping the UI responsive.

## License
[MIT](LICENSE)
