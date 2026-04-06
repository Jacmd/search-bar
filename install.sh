#!/usr/bin/env bash
# install.sh — Desktop Search Bar installer for Pop OS 24.04
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_PY="$SCRIPT_DIR/search_bar.py"
SHORTCUT_KEY="${SHORTCUT_KEY:-<Super>space}"   # override: SHORTCUT_KEY="<Ctrl><Alt>space" ./install.sh

GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${CYAN}▶ $*${NC}"; }
ok()    { echo -e "${GREEN}✓ $*${NC}"; }
err()   { echo -e "${RED}✗ $*${NC}" >&2; }

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   Desktop Search Bar — Installer     ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. System packages ────────────────────────────────────────────────────────
info "Installing system packages…"
sudo apt-get install -y \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0 \
    plocate \
    xdg-utils \
    >/dev/null 2>&1
ok "Packages installed"

# Update locate database (background, non-fatal)
info "Updating file database (runs in background)…"
sudo updatedb &>/dev/null &
ok "updatedb started"

# ── 2. Make script executable ─────────────────────────────────────────────────
chmod +x "$APP_PY"
ok "search_bar.py marked executable"

# ── 3. .desktop entry ─────────────────────────────────────────────────────────
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"

cat > "$APPS_DIR/search-bar.desktop" << EOF
[Desktop Entry]
Name=Search Bar
GenericName=Desktop Search
Comment=Quick search for local files and the web
Exec=python3 $APP_PY
Icon=system-search
Type=Application
Categories=Utility;
Keywords=search;files;web;google;
StartupNotify=false
NoDisplay=false
EOF

update-desktop-database "$APPS_DIR" 2>/dev/null || true
ok ".desktop entry created"

# ── 4. Keyboard shortcut via gsettings ───────────────────────────────────────
info "Registering keyboard shortcut ($SHORTCUT_KEY)…"

BINDING_CMD="python3 $APP_PY --toggle"
BINDING_NAME="Search Bar"

# Find a free custom slot
SLOT=0
while gsettings get \
    "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:\
/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom${SLOT}/" \
    name &>/dev/null 2>&1; do
    SLOT=$((SLOT + 1))
done

BPATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom${SLOT}/"

gsettings set \
    "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${BPATH}" \
    name    "$BINDING_NAME"
gsettings set \
    "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${BPATH}" \
    command "$BINDING_CMD"
gsettings set \
    "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${BPATH}" \
    binding "$SHORTCUT_KEY"

# Append to the custom-keybindings list
CURRENT=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)
if [[ "$CURRENT" == "@as []" || "$CURRENT" == "[]" ]]; then
    NEW_LIST="['${BPATH}']"
else
    # Insert before the closing ]
    NEW_LIST="${CURRENT%]}, '${BPATH}']"
fi
gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$NEW_LIST"

ok "Keyboard shortcut registered: $SHORTCUT_KEY"

# ── 5. Autostart (optional) ───────────────────────────────────────────────────
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/search-bar.desktop" << EOF
[Desktop Entry]
Name=Search Bar Daemon
Comment=Start the search bar daemon at login
Exec=python3 $APP_PY
Type=Application
Hidden=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF
ok "Autostart entry created (daemon starts at login)"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Installation complete!                              ║"
echo "╠══════════════════════════════════════════════════════╣"
printf "║  Shortcut : %-41s║\n" "$SHORTCUT_KEY  →  toggle search bar"
echo "║                                                      ║"
echo "║  Usage:                                              ║"
echo "║    • Press shortcut to open/close the search bar     ║"
echo "║    • Type to search files OR the web                 ║"
echo "║    • ↑ ↓ keys to navigate results                   ║"
echo "║    • Enter  → activate selected result               ║"
echo "║    • Escape → close                                  ║"
echo "║                                                      ║"
echo "║  Change shortcut:                                    ║"
echo "║    Settings → Keyboard → Custom Shortcuts            ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
info "Launch now with:  python3 $APP_PY"
echo ""
