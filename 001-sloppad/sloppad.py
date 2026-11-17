#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SlopPad - a vibe-coded text editor (Qt edition).
Part of slopware: https://github.com/Techrul/slopware

One file. Needs PySide6:
  CachyOS / Arch:  sudo pacman -S pyside6
  Everything else: pip install PySide6

Run it:   python sloppad.py [file ...]

Settings live in:
  Windows: %APPDATA%\\SlopPad\\settings.json
  macOS:   ~/Library/Application Support/SlopPad/settings.json
  Linux:   ~/.config/sloppad/settings.json
  (override with the SLOPPAD_CONFIG_DIR environment variable)
"""

import bisect
import codecs
import copy
import json
import os
import platform
import re
import stat
import subprocess
import sys
import tempfile
import time
import traceback

APP_NAME = "SlopPad"
APP_ID = "slopware.sloppad"
VERSION = "0.2.0"
REPO_URL = "https://github.com/Techrul/slopware"

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = not IS_WIN and not IS_MAC


def _missing_qt():
    sys.stderr.write(
        "SlopPad needs PySide6 (Qt for Python), which isn't installed for this Python.\n"
        "  CachyOS / Arch:  sudo pacman -S pyside6\n"
        "  Windows / macOS: pip install PySide6\n"
        "  Other Linux:     pip install --user PySide6  (or your distro's pyside6 package)\n")
    sys.exit(1)



# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

def _config_dir():
    override = os.environ.get("SLOPPAD_CONFIG_DIR")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if IS_WIN:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_NAME)
    if IS_MAC:
        return os.path.expanduser("~/Library/Application Support/" + APP_NAME)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "sloppad")


CONFIG_DIR = _config_dir()
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
LOG_PATH = os.path.join(CONFIG_DIR, "errors.log")


# --------------------------------------------------------------------------
# Themes
# --------------------------------------------------------------------------

THEME_KEYS = [
    ("bg", "Editor background"),
    ("fg", "Editor text"),
    ("cursor", "Cursor"),
    ("selection_bg", "Selection"),
    ("selection_fg", "Selected text"),
    ("current_line", "Current line"),
    ("gutter_bg", "Line numbers background"),
    ("gutter_fg", "Line numbers"),
    ("gutter_active", "Current line number"),
    ("match_bg", "Search match"),
    ("current_match_bg", "Current search match"),
    ("ui_bg", "Interface background"),
    ("ui_fg", "Interface text"),
    ("ui_dim", "Interface dim text"),
    ("ui_hover", "Hover"),
    ("input_bg", "Inputs and buttons"),
    ("accent", "Accent"),
    ("border", "Borders"),
    ("tab_active_bg", "Active tab"),
    ("tab_active_fg", "Active tab text"),
    ("scrollbar", "Scrollbar"),
    ("scrollbar_hover", "Scrollbar (hover)"),
]

OLED_BASE = {
    "bg": "#000000", "fg": "#e8e8e8", "cursor": "#ffffff",
    "selection_bg": "#2d1f66", "selection_fg": "#ffffff",
    "current_line": "#0a0a0a",
    "gutter_bg": "#000000", "gutter_fg": "#3c3c3c", "gutter_active": "#b8b8b8",
    "match_bg": "#3a2f00", "current_match_bg": "#9a7400",
    "ui_bg": "#000000", "ui_fg": "#d0d0d0", "ui_dim": "#707070",
    "ui_hover": "#161616", "input_bg": "#0b0b0b",
    "accent": "#8b6cff", "border": "#1f1f1f",
    "tab_active_bg": "#0e0e0e", "tab_active_fg": "#ffffff",
    "scrollbar": "#262626", "scrollbar_hover": "#4a4a4a",
}


def _variant(**over):
    d = dict(OLED_BASE)
    d.update(over)
    return d


BUILTIN_THEMES = {
    "OLED Black": dict(OLED_BASE),
    "OLED Sea Breeze": _variant(
        fg="#dcf5f2", cursor="#5ff5e8", selection_bg="#0b3d3a",
        gutter_active="#5ff5e8", accent="#2ee6d6", ui_fg="#c9ecea",
        ui_dim="#5c8c88", current_match_bg="#0f8a80", match_bg="#08302d"),
    "OLED Mocha": _variant(
        fg="#cdd6f4", cursor="#f5e0dc", selection_bg="#313244",
        selection_fg="#cdd6f4", gutter_fg="#45475a", gutter_active="#b4befe",
        accent="#cba6f7", ui_fg="#bac2de", ui_dim="#6c7086",
        match_bg="#3b2f3f", current_match_bg="#f9e2af", tab_active_fg="#cdd6f4"),
    "OLED Matrix": _variant(
        fg="#33ff66", cursor="#00ff41", selection_bg="#003b12",
        selection_fg="#b6ffc8", gutter_fg="#0f4d1f", gutter_active="#33ff66",
        accent="#00ff41", ui_fg="#7dff9b", ui_dim="#2f7a44",
        match_bg="#0d3a00", current_match_bg="#2a8a00", tab_active_fg="#00ff41"),
    "OLED Crimson": _variant(
        cursor="#ff5470", selection_bg="#4a0b16", gutter_active="#ff8095",
        accent="#ff3355", current_match_bg="#a3122b", match_bg="#33060e"),
    "OLED Amber": _variant(
        fg="#ffb000", cursor="#ffcc33", selection_bg="#4d3500",
        selection_fg="#ffe08a", gutter_fg="#5c4000", gutter_active="#ffb000",
        accent="#ffb000", ui_fg="#ffc23d", ui_dim="#8a6000",
        match_bg="#3d2c00", current_match_bg="#7a5500", tab_active_fg="#ffcc33"),
    "Paper (light)": {
        "bg": "#fbfbf8", "fg": "#1f1f1f", "cursor": "#000000",
        "selection_bg": "#cfe0ff", "selection_fg": "#000000",
        "current_line": "#f1f1ea",
        "gutter_bg": "#fbfbf8", "gutter_fg": "#b4b4ac", "gutter_active": "#404040",
        "match_bg": "#fff0a8", "current_match_bg": "#ffc93d",
        "ui_bg": "#f3f3ef", "ui_fg": "#2a2a2a", "ui_dim": "#7d7d78",
        "ui_hover": "#e4e4de", "input_bg": "#ffffff",
        "accent": "#5b5bd6", "border": "#d8d8d0",
        "tab_active_bg": "#fbfbf8", "tab_active_fg": "#000000",
        "scrollbar": "#cfcfc8", "scrollbar_hover": "#a6a69e",
    },
}
DEFAULT_THEME = "OLED Black"

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def norm_hex(value):
    if not isinstance(value, str):
        return None
    m = _HEX_RE.match(value.strip())
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h.lower()


def _rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def luminance(h):
    r, g, b = _rgb(h)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def contrast_text(h):
    return "#000000" if luminance(h) > 0.55 else "#ffffff"


def blend(a, b, amount):
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    mix = lambda x, y: int(round(x + (y - x) * amount))
    return "#%02x%02x%02x" % (mix(ra, rb), mix(ga, gb), mix(ba, bb))


def complete_theme(colors):
    """Fill missing / invalid keys from OLED Black so a theme can never be broken."""
    out = dict(OLED_BASE)
    if isinstance(colors, dict):
        for key in out:
            v = norm_hex(colors.get(key))
            if v:
                out[key] = v
    return out


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "theme": DEFAULT_THEME,
    "custom_themes": {},
    "editor_opacity": 100,
    "native_titlebar": False,
    "topmost": False,
    "font_family": "",
    "font_size": 12,
    "font_bold": False,
    "ui_font_size": 10,
    "ui_use_editor_font": False,
    "tab_width": 4,
    "insert_spaces": True,
    "auto_indent": True,
    "wrap": False,
    "line_numbers": True,
    "highlight_line": True,
    "cursor_width": 2,
    "cursor_blink": True,
    "block_cursor": False,
    "padding": 10,
    "status_bar": True,
    "default_newline": "CRLF" if IS_WIN else "LF",
    "restore_session": True,
    "session": [],
    "recent": [],
    "window_state": "",
    "monospace_only": True,
}

NUMERIC_LIMITS = {
    "font_size": (6, 96), "ui_font_size": (7, 24), "editor_opacity": (20, 100),
    "tab_width": (1, 16), "cursor_width": (1, 10), "padding": (0, 80),
}


def _compatible(default, value):
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, type(default))


class Settings:
    def __init__(self):
        self.data = copy.deepcopy(DEFAULT_SETTINGS)
        self.load_error = None
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                for k, v in loaded.items():
                    if k in DEFAULT_SETTINGS and _compatible(DEFAULT_SETTINGS[k], v):
                        self.data[k] = v
        except FileNotFoundError:
            pass
        except Exception as e:  # corrupted file: keep a copy and start fresh
            self.load_error = str(e)
            try:
                os.replace(SETTINGS_PATH, SETTINGS_PATH + ".broken")
            except OSError:
                pass
        self.clamp()

    def clamp(self):
        d = self.data
        for k, (lo, hi) in NUMERIC_LIMITS.items():
            d[k] = max(lo, min(hi, int(d[k])))
        if d["default_newline"] not in ("LF", "CRLF"):
            d["default_newline"] = DEFAULT_SETTINGS["default_newline"]
        if not isinstance(d["custom_themes"], dict):
            d["custom_themes"] = {}
        d["recent"] = [p for p in d["recent"] if isinstance(p, str)][:15]
        d["session"] = [p for p in d["session"] if isinstance(p, str)]

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, SETTINGS_PATH)


# --------------------------------------------------------------------------
# File helpers
# --------------------------------------------------------------------------

class BinaryFileError(Exception):
    pass


ENCODINGS = ["UTF-8", "UTF-8 with BOM", "UTF-16", "Windows-1252", "Latin-1"]


def read_text_file(path, force=False):
    """Returns (text, encoding_name, bom, newline or None)."""
    with open(path, "rb") as f:
        raw = f.read()
    bom = False
    if raw.startswith(codecs.BOM_UTF8):
        text, enc, bom = raw[3:].decode("utf-8", errors="replace"), "UTF-8", True
    elif raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        text, enc, bom = raw.decode("utf-16", errors="replace"), "UTF-16", True
    else:
        if not force and b"\x00" in raw[:65536]:
            raise BinaryFileError(path)
        try:
            text, enc = raw.decode("utf-8"), "UTF-8"
        except UnicodeDecodeError:
            try:
                text, enc = raw.decode("cp1252"), "Windows-1252"
            except UnicodeDecodeError:
                text, enc = raw.decode("latin-1"), "Latin-1"
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    newline = None
    if crlf or lf or cr:
        if crlf >= lf and crlf >= cr:
            newline = "CRLF"
        elif cr > lf:
            newline = "CR"
        else:
            newline = "LF"
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text, enc, bom, newline


_SURROGATE_RE = re.compile("[\ud800-\udfff]")


def fix_surrogates(s):
    if _SURROGATE_RE.search(s):
        s = s.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    return s


def encode_text(text, encoding, bom):
    text = fix_surrogates(text)
    if encoding == "UTF-8":
        data = text.encode("utf-8")
        return (codecs.BOM_UTF8 + data) if bom else data
    if encoding == "UTF-16":
        return text.encode("utf-16")
    if encoding == "Windows-1252":
        return text.encode("cp1252")
    if encoding == "Latin-1":
        return text.encode("latin-1")
    return text.encode("utf-8")


def atomic_write(path, data):
    path = os.path.realpath(path)
    folder = os.path.dirname(path) or "."
    mode = None
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        pass
    try:
        fd, tmp = tempfile.mkstemp(prefix=".sloppad-", suffix=".tmp", dir=folder)
    except OSError:
        with open(path, "wb") as f:
            f.write(data)
        return
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            try:
                os.chmod(tmp, mode)
            except OSError:
                pass
        try:
            os.replace(tmp, path)
        except PermissionError:  # e.g. file locked/attributes on Windows
            with open(path, "wb") as f:
                f.write(data)
            os.unlink(tmp)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def open_in_file_manager(path):
    try:
        if IS_WIN:
            os.startfile(path)  # type: ignore[attr-defined]
        elif IS_MAC:
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False



def set_titlebar_hwnd(hwnd, theme):
    """Windows 10/11: dark title bar for dialogs; Windows 11: title bar matches the theme."""
    if not IS_WIN or not hwnd:
        return
    try:
        import ctypes
        dwm = ctypes.windll.dwmapi
        h = ctypes.c_void_p(int(hwnd))
        dark = ctypes.c_int(1 if luminance(theme["ui_bg"]) < 0.5 else 0)
        if dwm.DwmSetWindowAttribute(h, 20, ctypes.byref(dark), ctypes.sizeof(dark)) != 0:
            dwm.DwmSetWindowAttribute(h, 19, ctypes.byref(dark), ctypes.sizeof(dark))

        def colorref(hexc):
            r, g, b = _rgb(hexc)
            return (b << 16) | (g << 8) | r

        for attr, key in ((35, "ui_bg"), (36, "ui_fg"), (34, "border")):
            c = ctypes.c_int(colorref(theme[key]))
            dwm.DwmSetWindowAttribute(h, attr, ctypes.byref(c), ctypes.sizeof(c))
    except Exception:
        pass


def utf16_len(s):
    return len(s.encode("utf-16-le")) // 2


_ASTRAL_RE = re.compile("[\U00010000-\U0010FFFF]")


class PosConverter:
    """Python string offsets -> Qt document positions (Qt counts UTF-16 units)."""

    def __init__(self, content):
        self.astral = [m.start() for m in _ASTRAL_RE.finditer(content)]

    def __call__(self, off):
        if not self.astral:
            return off
        return off + bisect.bisect_left(self.astral, off)


# --------------------------------------------------------------------------
# Linux launcher (works without Qt installed)
# --------------------------------------------------------------------------

ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect x="2" y="2" width="60" height="60" rx="12" fill="#000" stroke="#8b6cff" stroke-width="4"/>
<rect x="14" y="16" width="36" height="6" rx="3" fill="#8b6cff"/>
<rect x="14" y="28" width="28" height="4" rx="2" fill="#c9bcff"/>
<rect x="14" y="37" width="32" height="4" rx="2" fill="#c9bcff"/>
<rect x="14" y="46" width="18" height="4" rx="2" fill="#c9bcff"/>
</svg>
"""


def _linux_paths():
    data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return (os.path.join(data, "applications", "sloppad.desktop"),
            os.path.join(data, "icons", "hicolor", "scalable", "apps", "sloppad.svg"),
            os.path.join(data, "applications"))


def install_launcher():
    """Linux: add SlopPad to the app menu and to 'Open With' for text files."""
    if not IS_LINUX:
        print("--install is for Linux. On Windows, rename the file to sloppad.pyw and "
              "double-click it (or make a shortcut to it).")
        return 1
    script = os.path.realpath(__file__)
    desktop, icon, apps_dir = _linux_paths()
    os.makedirs(os.path.dirname(desktop), exist_ok=True)
    os.makedirs(os.path.dirname(icon), exist_ok=True)
    with open(icon, "w", encoding="utf-8") as f:
        f.write(ICON_SVG)
    with open(desktop, "w", encoding="utf-8") as f:
        f.write(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=SlopPad\n"
            "GenericName=Text Editor\n"
            "Comment=A vibe-coded text editor (slopware)\n"
            'Exec="%s" "%s" %%F\n'
            "Icon=sloppad\n"
            "Terminal=false\n"
            "Categories=Utility;TextEditor;\n"
            "MimeType=text/plain;text/x-python;text/markdown;application/json;application/x-shellscript;\n"
            "StartupWMClass=sloppad\n" % (sys.executable, script))
    try:
        os.chmod(script, os.stat(script).st_mode | 0o111)
    except OSError:
        pass
    for cmd in (["update-desktop-database", apps_dir], ["kbuildsycoca6"], ["kbuildsycoca5"]):
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass
    print("Installed! SlopPad is now in your app launcher.\n"
          "  Launcher: %s\n  Icon:     %s\n"
          "Right-click any text file -> Open With -> SlopPad.\n"
          "If you move sloppad.py later, run --install again.\n"
          "Remove it with: python3 sloppad.py --uninstall" % (desktop, icon))
    return 0


def uninstall_launcher():
    if not IS_LINUX:
        print("Nothing to uninstall on this OS.")
        return 0
    desktop, icon, apps_dir = _linux_paths()
    for p in (desktop, icon):
        try:
            os.remove(p)
            print("Removed " + p)
        except FileNotFoundError:
            pass
    try:
        subprocess.run(["update-desktop-database", apps_dir], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass
    return 0


def run_cli(argv):
    """Commands that don't need Qt. Returns an exit code, or None to start the editor."""
    if not argv:
        return None
    a = argv[0]
    if a in ("-h", "--help"):
        print("usage: sloppad.py [file ...]\n"
              "       sloppad.py --install     add SlopPad to your Linux app menu / Open With\n"
              "       sloppad.py --uninstall   remove that again\n\n"
              "A vibe-coded text editor. Part of slopware: " + REPO_URL)
        return 0
    if a in ("-V", "--version"):
        print("%s %s" % (APP_NAME, VERSION))
        return 0
    if a == "--install":
        return install_launcher()
    if a == "--uninstall":
        return uninstall_launcher()
    return None


if __name__ == "__main__":
    _code = run_cli(sys.argv[1:])
    if _code is not None:
        sys.exit(_code)

try:
    from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
    from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont, QFontDatabase, QFontMetricsF,
                               QIcon, QIntValidator, QKeySequence, QPainter, QPen, QPixmap,
                               QTextCursor, QTextFormat)
    from PySide6.QtWidgets import (QAbstractButton, QApplication, QColorDialog, QDialog,
                                   QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                                   QListWidget, QMenu, QMenuBar, QPlainTextEdit, QPushButton, QSizePolicy,
                                   QSlider, QStackedWidget, QTabBar, QTextEdit, QToolButton,
                                   QVBoxLayout, QWidget)
except ImportError:
    if __name__ == "__main__":
        _missing_qt()
    raise


# --------------------------------------------------------------------------
# Qt helpers
# --------------------------------------------------------------------------

KEEP = QTextCursor.MoveMode.KeepAnchor
MOVE = QTextCursor.MoveMode.MoveAnchor
OP = QTextCursor.MoveOperation


def qcolor(h, alpha=255):
    c = QColor(h)
    c.setAlpha(int(alpha))
    return c


def rgba(h, a):
    r, g, b = _rgb(h)
    return "rgba(%d, %d, %d, %d)" % (r, g, b, int(a))


def build_stylesheet(t, ed_alpha):
    """One stylesheet for the whole app, generated from the theme."""
    on_acc = contrast_text(t["accent"])
    track = blend(t["input_bg"], t["ui_fg"], 0.18)
    ed_bg = rgba(t["bg"], ed_alpha)
    return """
    QWidget#titlebar, QWidget#tabrow, QWidget#findbar, QWidget#status, QDialog, QWidget#page {
        background: %(ui_bg)s; color: %(ui_fg)s; }
    QFrame#sep { background: %(border)s; border: none; }
    QLabel { color: %(ui_fg)s; background: transparent; }
    QLabel#dim { color: %(ui_dim)s; }
    QLabel#header { color: %(accent)s; font-weight: bold; }
    QLabel#title { color: %(ui_dim)s; }
    QLabel#error { color: #ff6b6b; }
    QToolTip { background: %(input_bg)s; color: %(ui_fg)s; border: 1px solid %(border)s; padding: 4px; }

    QMenuBar { background: transparent; color: %(ui_fg)s; border: none; }
    QMenuBar::item { background: transparent; padding: 6px 10px; }
    QMenuBar::item:selected, QMenuBar::item:pressed { background: %(ui_hover)s; }
    QMenu { background: %(input_bg)s; color: %(ui_fg)s; border: 1px solid %(border)s; padding: 4px; }
    QMenu::item { padding: 5px 28px 5px 24px; background: transparent; }
    QMenu::item:selected { background: %(selection_bg)s; color: %(selection_fg)s; }
    QMenu::item:disabled { color: %(ui_dim)s; }
    QMenu::separator { height: 1px; background: %(border)s; margin: 4px 8px; }
    QMenu::indicator { width: 12px; height: 12px; left: 6px; }
    QMenu::indicator:checked { background: %(accent)s; border-radius: 6px; }

    QToolButton#winbtn { background: transparent; color: %(ui_fg)s; border: none; padding: 4px 16px; }
    QToolButton#winbtn:hover { background: %(ui_hover)s; }
    QToolButton#closebtn { background: transparent; color: %(ui_fg)s; border: none; padding: 4px 16px; }
    QToolButton#closebtn:hover { background: #e81123; color: #ffffff; }
    QToolButton#flat { background: transparent; color: %(ui_fg)s; border: none; padding: 3px 8px;
        border-radius: 4px; }
    QToolButton#flat:hover { background: %(ui_hover)s; }
    QToolButton#statusbtn { background: transparent; color: %(ui_dim)s; border: none; padding: 2px 8px; }
    QToolButton#statusbtn:hover { background: %(ui_hover)s; color: %(ui_fg)s; }
    QToolButton#statusbtn::menu-indicator { image: none; width: 0; }
    QToolButton#chip { background: %(input_bg)s; color: %(ui_dim)s; border: 1px solid %(border)s;
        border-radius: 4px; padding: 2px 7px; font-weight: bold; }
    QToolButton#chip:checked { background: %(accent)s; color: %(on_acc)s; border-color: %(accent)s; }
    QToolButton#tabclose { background: transparent; color: %(ui_dim)s; border: none; padding: 0px 3px;
        border-radius: 3px; }
    QToolButton#tabclose:hover { background: %(ui_hover)s; color: %(accent)s; }
    QToolButton#tabclose[modified="true"] { color: %(accent)s; }

    QTabBar { background: %(ui_bg)s; border: none; }
    QTabBar::tab { background: %(ui_bg)s; color: %(ui_dim)s; padding: 7px 6px 7px 14px; border: none;
        border-right: 1px solid %(border)s; border-top: 2px solid %(ui_bg)s; }
    QTabBar::tab:selected { background: %(tab_active_bg)s; color: %(tab_active_fg)s;
        border-top: 2px solid %(accent)s; }
    QTabBar::tab:hover:!selected { background: %(ui_hover)s; color: %(ui_fg)s; }
    QTabBar QToolButton { background: %(ui_bg)s; color: %(ui_fg)s; border: none; }

    QPushButton { background: %(input_bg)s; color: %(ui_fg)s; border: 1px solid %(border)s;
        border-radius: 4px; padding: 5px 14px; }
    QPushButton:hover { background: %(ui_hover)s; }
    QPushButton#accent { background: %(accent)s; color: %(on_acc)s; border-color: %(accent)s; }
    QPushButton#accent:hover { background: %(accent_hover)s; }
    QPushButton::menu-indicator { image: none; width: 0; }

    QLineEdit, QSpinBox { background: %(input_bg)s; color: %(fg)s; border: 1px solid %(border)s;
        border-radius: 4px; padding: 4px 6px; selection-background-color: %(selection_bg)s;
        selection-color: %(selection_fg)s; }
    QLineEdit:focus, QSpinBox:focus { border-color: %(accent)s; }
    QPushButton#pm { padding: 0px; min-width: 28px; max-width: 28px; }
    QListWidget { background: %(input_bg)s; color: %(ui_fg)s; border: 1px solid %(border)s;
        border-radius: 4px; outline: none; }
    QListWidget::item { padding: 3px 6px; }
    QListWidget::item:selected { background: %(accent)s; color: %(on_acc)s; }
    QPlainTextEdit#errorbox { background: %(input_bg)s; color: %(fg)s; border: 1px solid %(border)s; }

    QSlider::groove:horizontal { height: 4px; background: %(track)s; border-radius: 2px; }
    QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 2px; }
    QSlider::handle:horizontal { background: %(fg)s; border: 2px solid %(accent)s; width: 12px;
        height: 12px; margin: -6px 0; border-radius: 8px; }

    QPlainTextEdit#editor { background: transparent; border: none; }
    QPlainTextEdit#editor QScrollBar:vertical { background: %(ed_bg)s; width: 12px; margin: 0; border: none; }
    QPlainTextEdit#editor QScrollBar:horizontal { background: %(ed_bg)s; height: 12px; margin: 0; border: none; }
    QPlainTextEdit#editor QAbstractScrollArea::corner { background: %(ed_bg)s; border: none; }
    QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
    QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
    QScrollBar::handle:vertical { background: %(scrollbar)s; min-height: 28px; border-radius: 3px;
        margin: 2px 3px; }
    QScrollBar::handle:horizontal { background: %(scrollbar)s; min-width: 28px; border-radius: 3px;
        margin: 3px 2px; }
    QScrollBar::handle:hover { background: %(scrollbar_hover)s; }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; }
    QScrollBar::add-page, QScrollBar::sub-page { background: none; }
    """ % dict(t, on_acc=on_acc, track=track, ed_bg=ed_bg,
               accent_hover=blend(t["accent"], "#ffffff", 0.18))


def make_icon(theme):
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    acc = QColor(theme["accent"])
    light = QColor(blend(theme["accent"], "#ffffff", 0.55))
    p.setPen(QPen(acc, 4))
    p.setBrush(QColor("#000000"))
    p.drawRoundedRect(QRectF(2, 2, 60, 60), 12, 12)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(acc)
    p.drawRoundedRect(QRectF(14, 16, 36, 6), 3, 3)
    p.setBrush(light)
    for y, w in ((28, 28), (37, 32), (46, 18)):
        p.drawRoundedRect(QRectF(14, y, w, 4), 2, 2)
    p.end()
    return QIcon(pm)


def sep(horizontal=True):
    f = QFrame()
    f.setObjectName("sep")
    if horizontal:
        f.setFixedHeight(1)
    else:
        f.setFixedWidth(1)
    return f


def label(text, name=None, wrap=False):
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def button(text, slot, accent=False, tip=None):
    b = QPushButton(text)
    if accent:
        b.setObjectName("accent")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(lambda *_: slot())
    if tip:
        b.setToolTip(tip)
    return b


def tool(text, slot, name="flat", tip=None, checkable=False):
    b = QToolButton()
    b.setText(text)
    b.setObjectName(name)
    b.setCheckable(checkable)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoRaise(True)
    if slot:
        b.clicked.connect(lambda *_: slot())
    if tip:
        b.setToolTip(tip)
    return b


class Toggle(QAbstractButton):
    """iOS-style switch, painted by hand so it looks the same everywhere."""

    def __init__(self, app, checked=False, slot=None):
        super().__init__()
        self.app = app
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(40, 22)
        if slot:
            self.toggled.connect(slot)

    def set_value(self, v):
        self.blockSignals(True)
        self.setChecked(bool(v))
        self.blockSignals(False)
        self.update()

    def paintEvent(self, _e):
        t = self.app.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t["accent"] if on else blend(t["input_bg"], t["ui_fg"], 0.18)))
        p.drawRoundedRect(QRectF(1, 2, 38, 18), 9, 9)
        p.setBrush(QColor(contrast_text(t["accent"]) if on else t["ui_fg"]))
        x = 21 if on else 4
        p.drawEllipse(QRectF(x, 5, 12, 12))
        p.end()


class NumberField(QWidget):
    """[-] [ 12 ] [+]  - a number box that looks the same everywhere."""

    def __init__(self, value, lo, hi, slot):
        super().__init__()
        self.value, self.lo, self.hi, self.slot = int(value), lo, hi, slot
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.edit = QLineEdit(str(self.value))
        self.edit.setValidator(QIntValidator(lo, hi, self.edit))
        self.edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit.setFixedWidth(56)
        self.edit.editingFinished.connect(self.commit)
        self.edit.installEventFilter(self)
        for text, d in (("-", -1), ("+", 1)):
            b = QPushButton(text)
            b.setObjectName("pm")
            b.setFixedSize(28, 28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda *_, d=d: self.commit(self.value + d))
            if d < 0:
                lay.addWidget(b)
                lay.addWidget(self.edit)
            else:
                lay.addWidget(b)

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Type.Wheel:
            dy = e.angleDelta().y()
            if dy:
                self.commit(self.value + (1 if dy > 0 else -1))
            return True
        return False

    def commit(self, v=None):
        if v is None:
            try:
                v = int(self.edit.text().strip())
            except ValueError:
                v = self.value
        v = max(self.lo, min(self.hi, int(v)))
        self.edit.setText(str(v))
        if v != self.value:
            self.value = v
            self.slot(v)

    def set_value(self, v):
        self.value = int(v)
        self.edit.setText(str(self.value))


class DropButton(QPushButton):
    """A button that pops up a list of choices (prettier than QComboBox when themed)."""

    def __init__(self, options, value, slot, min_width=150):
        super().__init__()
        self.options, self.slot = options, slot
        self.setMinimumWidth(min_width)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("text-align: left;")
        self.set_value(value)
        self.clicked.connect(self._open)

    def set_value(self, v):
        self.value = v
        self.setText("%s   ▾" % v)

    def _open(self):
        m = QMenu(self)
        group = QActionGroup(m)
        opts = self.options() if callable(self.options) else self.options
        for o in opts:
            a = m.addAction(o)
            a.setCheckable(True)
            a.setChecked(o == self.value)
            group.addAction(a)
            a.triggered.connect(lambda *_, o=o: self._choose(o))
        m.exec(self.mapToGlobal(QPoint(0, self.height())))

    def _choose(self, o):
        self.set_value(o)
        self.slot(o)


# --------------------------------------------------------------------------
# The editor widget
# --------------------------------------------------------------------------

class Gutter(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.ed = editor
        self._anchor = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def sizeHint(self):
        return QSize(self.ed.gutter_width(), 0)

    def paintEvent(self, e):
        self.ed.paint_gutter(e)

    def wheelEvent(self, e):
        self.ed.wheelEvent(e)

    def _block_at(self, y):
        ed = self.ed
        block = ed.firstVisibleBlock()
        top = ed.blockBoundingGeometry(block).translated(ed.contentOffset()).top()
        while block.isValid():
            bottom = top + ed.blockBoundingRect(block).height()
            if y < bottom:
                return block.blockNumber()
            nxt = block.next()
            if not nxt.isValid():
                return block.blockNumber()
            block, top = nxt, bottom
        return 0

    def mousePressEvent(self, e):
        n = self._block_at(e.position().y())
        self._anchor = n
        self.ed.select_lines(n, n, with_newline=True)

    def mouseMoveEvent(self, e):
        if self._anchor is not None:
            n = self._block_at(e.position().y())
            self.ed.select_lines(min(n, self._anchor), max(n, self._anchor), with_newline=True)

    def mouseReleaseEvent(self, _e):
        self._anchor = None


class Editor(QPlainTextEdit):
    def __init__(self, app, tab):
        super().__init__()
        self.app, self.tab = app, tab
        self.setObjectName("editor")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.viewport().setAutoFillBackground(False)
        self.setCursorWidth(0)  # we draw our own cursor (line or block, blinking or not)
        self.gutter = Gutter(self)
        self.match_selections = []
        self._blink_on = True
        self._last_cursor_rect = QRect()
        self.blink = QTimer(self)
        self.blink.timeout.connect(self._blink)
        self.blockCountChanged.connect(lambda *_: self.update_gutter_width())
        self.updateRequest.connect(self._on_update_request)
        self.cursorPositionChanged.connect(self._on_cursor)
        self.selectionChanged.connect(self.refresh_extra)
        self.apply_settings()

    # ---- settings & theme
    def apply_settings(self):
        s = self.app.settings
        doc = self.document()
        was_modified = doc.isModified()  # Qt marks the doc "modified" when you change its margin
        doc.blockSignals(True)
        font = QFont(self.app.editor_font)
        self.setFont(font)
        self.document().setDefaultFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if s["wrap"]
                             else QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(QFontMetricsF(font).horizontalAdvance(" ") * s["tab_width"])
        if doc.documentMargin() != s["padding"]:
            doc.setDocumentMargin(s["padding"])
        doc.setModified(was_modified)
        doc.blockSignals(False)
        self.gutter.setVisible(s["line_numbers"])
        self.update_gutter_width()
        self.apply_theme()
        self._restart_blink()

    def apply_theme(self):
        t = self.app.theme
        pal = self.palette()
        pal.setColor(pal.ColorRole.Text, QColor(t["fg"]))
        pal.setColor(pal.ColorRole.Highlight, QColor(t["selection_bg"]))
        pal.setColor(pal.ColorRole.HighlightedText, QColor(t["selection_fg"]))
        self.setPalette(pal)
        self.refresh_extra()
        self.viewport().update()
        self.gutter.update()

    # ---- painting
    def paintEvent(self, e):
        p = QPainter(self.viewport())
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(e.rect(), qcolor(self.app.theme["bg"], self.app.editor_alpha()))
        p.end()
        super().paintEvent(e)
        self._paint_cursor()

    def _cursor_paint_rect(self):
        r = self.cursorRect()
        if self.app.settings["block_cursor"]:
            w = int(QFontMetricsF(self.font()).horizontalAdvance(self._char_under_cursor() or " ")) + 1
        else:
            w = self.app.settings["cursor_width"]
        return QRect(r.x(), r.y(), max(1, w), r.height())

    def _char_under_cursor(self):
        c = QTextCursor(self.textCursor())
        c.clearSelection()
        c.movePosition(OP.NextCharacter, KEEP)
        ch = c.selectedText()
        if ch in ("", " ", "\t"):
            return " "
        return ch

    def _paint_cursor(self):
        if self.isReadOnly():
            return
        t, s = self.app.theme, self.app.settings
        focused = self.hasFocus()
        rect = self._cursor_paint_rect()
        p = QPainter(self.viewport())
        color = QColor(t["cursor"])
        if focused and self._blink_on:
            if s["block_cursor"]:
                p.fillRect(rect, color)
                ch = self._char_under_cursor()
                if ch.strip():
                    p.setFont(self.font())
                    p.setPen(QColor(t["bg"]))
                    fm = QFontMetricsF(self.font())
                    p.drawText(QPointF(rect.x(), rect.y() + (rect.height() - fm.height()) / 2 + fm.ascent()), ch)
            else:
                p.fillRect(rect, color)
        elif not focused:
            p.setPen(QPen(color, 1))
            p.drawRect(rect.adjusted(0, 0, -1, -1) if s["block_cursor"] else QRect(rect.x(), rect.y(), 1, rect.height()))
        p.end()

    def _update_cursor_area(self):
        new = self._cursor_paint_rect().adjusted(-2, -2, 2, 2)
        self.viewport().update(self._last_cursor_rect.united(new))
        self._last_cursor_rect = new

    def _blink(self):
        self._blink_on = not self._blink_on
        self._update_cursor_area()

    def _restart_blink(self):
        self._blink_on = True
        if self.app.settings["cursor_blink"] and self.hasFocus():
            self.blink.start(530)
        else:
            self.blink.stop()
        self._update_cursor_area()

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self._restart_blink()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.blink.stop()
        self._update_cursor_area()

    # ---- gutter
    def gutter_width(self):
        if not self.app.settings["line_numbers"]:
            return 0
        digits = max(3, len(str(self.blockCount())))
        return int(QFontMetricsF(self.font()).horizontalAdvance("9") * digits) + 26

    def update_gutter_width(self):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)
        cr = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.update_gutter_width()

    def _on_update_request(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def paint_gutter(self, e):
        t = self.app.theme
        p = QPainter(self.gutter)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(e.rect(), qcolor(t["gutter_bg"], self.app.editor_alpha()))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setFont(self.font())
        fm = QFontMetricsF(self.font())
        block = self.firstVisibleBlock()
        num = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()
        cur = self.textCursor().blockNumber()
        w = self.gutter.width() - 12
        while block.isValid() and top <= e.rect().bottom():
            if block.isVisible() and bottom >= e.rect().top():
                p.setPen(QColor(t["gutter_active"] if num == cur else t["gutter_fg"]))
                p.drawText(QRectF(0, top, w, fm.height()),
                           int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop), str(num + 1))
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            num += 1
        p.end()

    # ---- highlights
    def _on_cursor(self):
        self.refresh_extra()
        self.gutter.update()
        self._restart_blink()

    def refresh_extra(self):
        sels = []
        t = self.app.theme
        if self.app.settings["highlight_line"] and not self.textCursor().hasSelection():
            s = QTextEdit.ExtraSelection()
            s.format.setBackground(qcolor(t["current_line"], self.app.editor_alpha()))
            s.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            c = QTextCursor(self.textCursor())
            c.clearSelection()
            s.cursor = c
            sels.append(s)
        sels.extend(self.match_selections)
        self.setExtraSelections(sels)

    # ---- input
    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            dy = e.angleDelta().y()
            if dy:
                self.app.zoom(1 if dy > 0 else -1)
            e.accept()
            return
        super().wheelEvent(e)

    def insertFromMimeData(self, md):
        if md.hasText():
            text = md.text().replace("\r\n", "\n").replace("\r", "\n")
            self.textCursor().insertText(text)
            self.ensureCursorVisible()

    def canInsertFromMimeData(self, md):
        return md.hasText() or md.hasUrls()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and any(u.isLocalFile() for u in e.mimeData().urls()):
            e.acceptProposedAction()
            return
        super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls() and any(u.isLocalFile() for u in e.mimeData().urls()):
            e.acceptProposedAction()
            return
        super().dragMoveEvent(e)

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()] if e.mimeData().hasUrls() else []
        if files:
            e.acceptProposedAction()
            for f in files:
                self.app.open_path(f)
            return
        super().dropEvent(e)

    def keyPressEvent(self, e):
        key, mods = e.key(), e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        K = Qt.Key
        if key == K.Key_Escape and self.app.findbar.isVisible():
            self.app.findbar.close_bar()
            return
        if not ctrl and not alt:
            if key == K.Key_Tab:
                self.on_tab()
                return
            if key == K.Key_Backtab:
                self.on_shift_tab()
                return
            if key in (K.Key_Return, K.Key_Enter) and self.app.settings["auto_indent"] and not shift:
                self.on_return()
                return
            if key == K.Key_Backspace and self.on_backspace():
                return
            if key == K.Key_Home and self.on_home(shift):
                return
        if alt and not ctrl and key in (K.Key_Up, K.Key_Down):
            self.move_lines(-1 if key == K.Key_Up else 1)
            return
        super().keyPressEvent(e)

    # ---- editing helpers
    def _unit(self):
        s = self.app.settings
        return " " * s["tab_width"] if s["insert_spaces"] else "\t"

    def _left_text(self, c):
        c2 = QTextCursor(c)
        c2.clearSelection()
        c2.movePosition(OP.StartOfBlock, KEEP)
        return c2.selectedText()

    def sel_lines(self):
        c = self.textCursor()
        doc = self.document()
        if c.hasSelection():
            a = doc.findBlock(c.selectionStart()).blockNumber()
            end = c.selectionEnd()
            eb = doc.findBlock(end)
            b = eb.blockNumber()
            if b > a and end == eb.position():
                b -= 1
            return a, b, True
        n = c.blockNumber()
        return n, n, False

    def select_lines(self, a, b, with_newline=False):
        doc = self.document()
        c = QTextCursor(doc)
        c.setPosition(doc.findBlockByNumber(a).position())
        last = doc.findBlockByNumber(b)
        nxt = last.next()
        if with_newline and nxt.isValid():
            c.setPosition(nxt.position(), KEEP)
        else:
            c.setPosition(last.position() + last.length() - 1, KEEP)
        self.setTextCursor(c)

    def indent(self, a, b):
        doc, unit = self.document(), self._unit()
        c = QTextCursor(doc)
        c.beginEditBlock()
        for n in range(a, b + 1):
            blk = doc.findBlockByNumber(n)
            if blk.text().strip():
                c.setPosition(blk.position())
                c.insertText(unit)
        c.endEditBlock()
        self.select_lines(a, b)

    def dedent(self, a, b, reselect):
        doc, tw = self.document(), self.app.settings["tab_width"]
        c = QTextCursor(doc)
        c.beginEditBlock()
        for n in range(a, b + 1):
            blk = doc.findBlockByNumber(n)
            line = blk.text()
            k = 1 if line.startswith("\t") else min(len(line) - len(line.lstrip(" ")), tw)
            if k:
                c.setPosition(blk.position())
                c.setPosition(blk.position() + k, KEEP)
                c.removeSelectedText()
        c.endEditBlock()
        if reselect:
            self.select_lines(a, b)

    def on_tab(self):
        c = self.textCursor()
        s = self.app.settings
        if c.hasSelection():
            a, b, _ = self.sel_lines()
            if a != b or c.selectedText().endswith(" "):
                self.indent(a, b)
                return
        if s["insert_spaces"]:
            col = len(self._left_text(c).replace("\t", " " * s["tab_width"])) if not c.hasSelection() else 0
            c.insertText(" " * (s["tab_width"] - col % s["tab_width"]))
        else:
            c.insertText("\t")
        self.setTextCursor(c)

    def on_shift_tab(self):
        a, b, had = self.sel_lines()
        self.dedent(a, b, had)

    def on_return(self):
        c = self.textCursor()
        left = self._left_text(c)
        indent = re.match(r"[ \t]*", left).group(0)
        if left.rstrip().endswith((":", "{", "[", "(")):
            indent += self._unit()
        c.beginEditBlock()
        c.removeSelectedText()
        c.insertText("\n" + indent)
        c.endEditBlock()
        self.setTextCursor(c)
        self.ensureCursorVisible()

    def on_backspace(self):
        c = self.textCursor()
        s = self.app.settings
        if c.hasSelection() or not s["insert_spaces"]:
            return False
        left = self._left_text(c)
        if len(left) >= 2 and left.strip(" ") == "":
            n = len(left) % s["tab_width"] or s["tab_width"]
            c.movePosition(OP.PreviousCharacter, KEEP, n)
            c.removeSelectedText()
            return True
        return False

    def on_home(self, shift):
        c = self.textCursor()
        line = c.block().text()
        first = len(line) - len(line.lstrip(" \t"))
        col = c.positionInBlock()
        target = 0 if col == first else first
        c.setPosition(c.block().position() + target, KEEP if shift else MOVE)
        self.setTextCursor(c)
        return True

    def duplicate(self):
        c = self.textCursor()
        doc = self.document()
        if c.hasSelection():
            text = c.selectedText().replace(" ", "\n")
            c2 = QTextCursor(doc)
            c2.setPosition(c.selectionEnd())
            c2.insertText(text)
            return
        col = c.positionInBlock()
        blk = c.block()
        c2 = QTextCursor(doc)
        c2.setPosition(blk.position() + blk.length() - 1)
        c2.insertText("\n" + blk.text())
        nb = blk.next()
        c.setPosition(nb.position() + min(col, nb.length() - 1))
        self.setTextCursor(c)

    def delete_line(self):
        a, b, _ = self.sel_lines()
        doc = self.document()
        last = doc.blockCount() - 1
        c = QTextCursor(doc)
        ba, bb = doc.findBlockByNumber(a), doc.findBlockByNumber(b)
        if b < last:
            c.setPosition(ba.position())
            c.setPosition(bb.next().position(), KEEP)
        elif a > 0:
            prev = ba.previous()
            c.setPosition(prev.position() + prev.length() - 1)
            c.setPosition(bb.position() + bb.length() - 1, KEEP)
        else:
            c.select(QTextCursor.SelectionType.Document)
        c.removeSelectedText()
        self.setTextCursor(c)

    def move_lines(self, d):
        a, b, had = self.sel_lines()
        doc = self.document()
        last = doc.blockCount() - 1
        if (d < 0 and a <= 0) or (d > 0 and b >= last):
            return
        cur = self.textCursor()
        ins_line, ins_col = cur.blockNumber(), cur.positionInBlock()
        lines = [doc.findBlockByNumber(n).text() for n in range(a, b + 1)]
        block = "\n".join(lines)
        c = QTextCursor(doc)
        if d < 0:
            other = doc.findBlockByNumber(a - 1)
            end = doc.findBlockByNumber(b)
            c.setPosition(other.position())
            c.setPosition(end.position() + end.length() - 1, KEEP)
            c.insertText(block + "\n" + other.text())
        else:
            other = doc.findBlockByNumber(b + 1)
            start = doc.findBlockByNumber(a)
            c.setPosition(start.position())
            c.setPosition(other.position() + other.length() - 1, KEEP)
            c.insertText(other.text() + "\n" + block)
        if had:
            self.select_lines(a + d, b + d)
        else:
            blk = doc.findBlockByNumber(ins_line + d)
            c = QTextCursor(doc)
            c.setPosition(blk.position() + min(ins_col, blk.length() - 1))
            self.setTextCursor(c)
        self.ensureCursorVisible()

    def select_line(self):
        a, b, _ = self.sel_lines()
        self.select_lines(a, b, with_newline=True)

    def change_case(self, upper):
        c = self.textCursor()
        if not c.hasSelection():
            return
        start, end = c.selectionStart(), c.selectionEnd()
        s = c.selectedText()
        new = s.upper() if upper else s.lower()
        if new != s:
            c.insertText(new.replace(" ", "\n"))
            c.setPosition(start)
            c.setPosition(start + utf16_len(new), KEEP)
            self.setTextCursor(c)
        del end

    def trim_trailing(self):
        doc = self.document()
        c = QTextCursor(doc)
        count = 0
        c.beginEditBlock()
        blk = doc.lastBlock()
        while blk.isValid():
            t = blk.text()
            s = t.rstrip(" \t")
            if len(s) != len(t):
                c.setPosition(blk.position() + utf16_len(s))
                c.setPosition(blk.position() + utf16_len(t), KEEP)
                c.removeSelectedText()
                count += 1
            blk = blk.previous()
        c.endEditBlock()
        self.app.flash("Trimmed %d line%s" % (count, "" if count == 1 else "s"))

    def contextMenuEvent(self, e):
        m = self.createStandardContextMenu()
        m.addSeparator()
        m.addAction("Find...", lambda: self.app.findbar.open_bar(False))
        m.exec(e.globalPos())


# --------------------------------------------------------------------------
# Tabs
# --------------------------------------------------------------------------

class TabCloseButton(QToolButton):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.setObjectName("tabclose")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(True)
        self.hover = False
        self.clicked.connect(lambda *_: tab.app.close_tab(tab))
        self.refresh()

    def enterEvent(self, e):
        self.hover = True
        self.refresh()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.hover = False
        self.refresh()
        super().leaveEvent(e)

    def refresh(self):
        mod = self.tab.is_modified()
        self.setText("×" if (self.hover or not mod) else "●")
        self.setProperty("modified", "true" if (mod and not self.hover) else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class Tab:
    def __init__(self, app, path=None):
        self.app = app
        self.path = path
        self.encoding, self.bom = "UTF-8", False
        self.newline = app.settings["default_newline"]
        self.version = 0
        app.untitled_counter += 1
        self.untitled_no = app.untitled_counter
        self.editor = Editor(app, self)
        doc = self.editor.document()
        doc.contentsChanged.connect(self._changed)
        doc.modificationChanged.connect(lambda *_: app.refresh_modified(self))
        self.close_btn = TabCloseButton(self)

    def _changed(self):
        self.version += 1
        self.app.on_text_change(self)

    def title(self):
        return os.path.basename(self.path) if self.path else "Untitled-%d" % self.untitled_no

    def is_modified(self):
        try:
            return self.editor.document().isModified()
        except RuntimeError:
            return False

    def set_modified(self, v):
        self.editor.document().setModified(bool(v))
        self.app.refresh_modified(self)

    def is_pristine(self):
        return not self.path and not self.is_modified() and self.editor.document().characterCount() <= 1

    def content(self):
        return self.editor.document().toRawText().replace(" ", "\n")

    def set_content(self, text):
        ed = self.editor
        ed.setPlainText(text)
        doc = ed.document()
        doc.clearUndoRedoStacks()
        doc.setModified(False)
        c = ed.textCursor()
        c.movePosition(OP.Start)
        ed.setTextCursor(c)


# --------------------------------------------------------------------------
# Find bar
# --------------------------------------------------------------------------

class FindBar(QWidget):
    MAX_HIGHLIGHT = 4000

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("findbar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.matches, self.cur = [], -1
        self.scan_tab, self.scan_version = None, -1
        self.anchor = 0
        self.truncated = False
        self.replace_mode = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(sep())
        r1 = QHBoxLayout()
        r1.setContentsMargins(10, 6, 10, 6)
        r1.setSpacing(6)
        outer.addLayout(r1)
        self.row2 = QWidget()
        r2 = QHBoxLayout(self.row2)
        r2.setContentsMargins(10, 0, 10, 6)
        r2.setSpacing(6)
        outer.addWidget(self.row2)

        lb = label("Find", "dim")
        lb.setFixedWidth(60)
        r1.addWidget(lb)
        self.find_edit = QLineEdit()
        self.find_edit.setFixedWidth(300)
        self.find_edit.setPlaceholderText("Search")
        r1.addWidget(self.find_edit)
        self.chips = {}
        for key, txt, tip in (("case", "Aa", "Match case"), ("word", "W", "Whole word"),
                              ("regex", ".*", "Regular expression")):
            b = tool(txt, None, name="chip", tip=tip, checkable=True)
            b.toggled.connect(lambda *_: self.rescan(True))
            r1.addWidget(b)
            self.chips[key] = b
        self.count = label("", "dim")
        self.count.setMinimumWidth(130)
        r1.addWidget(self.count)
        r1.addWidget(button("↑", lambda: self.step(-1), tip="Previous match (Shift+Enter)"))
        r1.addWidget(button("↓", lambda: self.step(1), tip="Next match (Enter)"))
        r1.addStretch(1)
        self.toggle_btn = tool("Replace", lambda: self.open_bar(not self.replace_mode),
                               tip="Show / hide replace")
        r1.addWidget(self.toggle_btn)
        r1.addWidget(tool("×", self.close_bar, tip="Close (Esc)"))

        lb = label("Replace", "dim")
        lb.setFixedWidth(60)
        r2.addWidget(lb)
        self.repl_edit = QLineEdit()
        self.repl_edit.setFixedWidth(300)
        self.repl_edit.setPlaceholderText("Replace with")
        r2.addWidget(self.repl_edit)
        r2.addWidget(button("Replace", self.replace_one))
        r2.addWidget(button("Replace all", self.replace_all))
        r2.addStretch(1)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.rescan(True))
        self.find_edit.textChanged.connect(lambda *_: self.timer.start(120))
        self.find_edit.installEventFilter(self)
        self.repl_edit.installEventFilter(self)
        self.hide()

    def flag(self, key):
        return self.chips[key].isChecked()

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Type.KeyPress:
            k = e.key()
            if k == Qt.Key.Key_Escape:
                self.close_bar()
                return True
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if obj is self.repl_edit:
                    self.replace_one()
                else:
                    self.step(-1 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1)
                return True
        return super().eventFilter(obj, e)

    # ---- open / close
    def open_bar(self, replace=False):
        tab = self.app.current
        if tab is None:
            return
        self.replace_mode = replace
        self.row2.setVisible(replace)
        self.toggle_btn.setText("Hide replace" if replace else "Replace")
        self.show()
        c = tab.editor.textCursor()
        if c.hasSelection():
            sel = c.selectedText()
            if " " not in sel and len(sel) < 300:
                self.find_edit.blockSignals(True)
                self.find_edit.setText(re.escape(sel) if self.flag("regex") else sel)
                self.find_edit.blockSignals(False)
            self.anchor = c.selectionStart()
        else:
            self.anchor = c.position()
        self.find_edit.setFocus()
        self.find_edit.selectAll()
        self.rescan(True)

    def close_bar(self):
        if not self.isVisible():
            return
        self.hide()
        for t in self.app.tabs:
            t.editor.match_selections = []
            t.editor.refresh_extra()
        self.matches, self.cur = [], -1
        if self.app.current is not None:
            self.app.current.editor.setFocus()

    # ---- search
    def compile(self):
        pat = self.find_edit.text()
        if not pat:
            return None
        p = pat if self.flag("regex") else re.escape(pat)
        if self.flag("word"):
            p = r"(?<!\w)(?:" + p + r")(?!\w)"
        flags = re.MULTILINE | (0 if self.flag("case") else re.IGNORECASE)
        try:
            return re.compile(p, flags)
        except re.error:
            return False

    def set_count(self, text, error=False):
        self.count.setText(text)
        self.count.setObjectName("error" if error else "dim")
        self.count.style().unpolish(self.count)
        self.count.style().polish(self.count)

    def rescan(self, navigate=False):
        tab = self.app.current
        if not self.isVisible() or tab is None:
            return
        if self.scan_tab is not None and self.scan_tab is not tab:
            try:
                self.scan_tab.editor.match_selections = []
                self.scan_tab.editor.refresh_extra()
            except RuntimeError:
                pass
        self.scan_tab, self.scan_version = tab, tab.version
        self.matches, self.cur, self.truncated = [], -1, False
        rx = self.compile()
        ed = tab.editor
        if not rx:
            ed.match_selections = []
            ed.refresh_extra()
            if rx is None:
                self.set_count("")
            else:
                self.set_count("Invalid regex", error=True)
            return
        content = tab.content()
        conv = PosConverter(content)
        for m in rx.finditer(content):
            if m.end() == m.start():
                continue
            self.matches.append((conv(m.start()), conv(m.end()), m))
            if len(self.matches) >= 50000:
                self.truncated = True
                break
        if not self.matches:
            ed.match_selections = []
            ed.refresh_extra()
            self.set_count("No results", error=True)
            return
        starts = [s for s, _, _ in self.matches]
        self.cur = bisect.bisect_left(starts, self.anchor)
        if self.cur >= len(self.matches):
            self.cur = 0
        self._highlight(navigate)

    def _highlight(self, navigate):
        t = self.app.theme
        ed = self.scan_tab.editor
        doc = ed.document()
        sels = []
        lo = max(0, self.cur - self.MAX_HIGHLIGHT // 2)
        for i, (s, e, _) in enumerate(self.matches[lo:lo + self.MAX_HIGHLIGHT], start=lo):
            sel = QTextEdit.ExtraSelection()
            c = QTextCursor(doc)
            c.setPosition(s)
            c.setPosition(e, KEEP)
            sel.cursor = c
            if i == self.cur:
                sel.format.setBackground(QColor(t["current_match_bg"]))
                sel.format.setForeground(QColor(contrast_text(t["current_match_bg"])))
            else:
                sel.format.setBackground(QColor(t["match_bg"]))
            sels.append(sel)
        ed.match_selections = sels
        if navigate:
            s, e, _ = self.matches[self.cur]
            c = QTextCursor(doc)
            c.setPosition(s)
            c.setPosition(e, KEEP)
            ed.setTextCursor(c)
            ed.centerCursor() if not ed.viewport().rect().contains(ed.cursorRect()) else ed.ensureCursorVisible()
        ed.refresh_extra()
        self.set_count("%d of %d%s" % (self.cur + 1, len(self.matches), "+" if self.truncated else ""))

    def _stale(self):
        tab = self.app.current
        return tab is None or tab is not self.scan_tab or tab.version != self.scan_version

    def step(self, d):
        if not self.isVisible():
            self.open_bar(False)
            return
        if self._stale() or not self.matches:
            self.rescan(False)
        if not self.matches:
            QApplication.beep()
            return
        self.cur = (self.cur + d) % len(self.matches)
        self.anchor = self.matches[self.cur][0]
        self._highlight(True)

    def _replacement(self, m):
        repl = self.repl_edit.text()
        return m.expand(repl) if self.flag("regex") else repl

    def replace_one(self):
        if not self.replace_mode:
            self.open_bar(True)
            return
        if self._stale() or not self.matches:
            self.rescan(False)
        if not self.matches:
            QApplication.beep()
            return
        s, e, m = self.matches[self.cur]
        try:
            rep = self._replacement(m)
        except (re.error, IndexError) as ex:
            self.set_count("Bad replace: %s" % ex, error=True)
            return
        ed = self.scan_tab.editor
        c = QTextCursor(ed.document())
        c.setPosition(s)
        c.setPosition(e, KEEP)
        c.insertText(rep.replace("\r\n", "\n"))
        self.anchor = s + utf16_len(rep)
        self.rescan(True)

    def replace_all(self):
        tab = self.app.current
        rx = self.compile()
        if tab is None or not rx:
            return
        content = tab.content()
        try:
            new, n = rx.subn(self._replacement, content)
        except (re.error, IndexError) as ex:
            self.set_count("Bad replace: %s" % ex, error=True)
            return
        if not n:
            self.set_count("No results", error=True)
            return
        ed = tab.editor
        pos = ed.textCursor().position()
        scroll = ed.verticalScrollBar().value()
        c = QTextCursor(ed.document())
        c.beginEditBlock()
        c.select(QTextCursor.SelectionType.Document)
        c.insertText(new)
        c.endEditBlock()
        c.setPosition(min(pos, ed.document().characterCount() - 1))
        ed.setTextCursor(c)
        ed.verticalScrollBar().setValue(scroll)
        self.rescan(False)
        self.set_count("Replaced %d" % n)
        self.app.flash("Replaced %d match%s" % (n, "" if n == 1 else "es"))


# --------------------------------------------------------------------------
# Window chrome
# --------------------------------------------------------------------------

class TitleBar(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("titlebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 0, 0)
        lay.setSpacing(0)
        self.icon = QLabel()
        self.icon.setFixedWidth(26)
        lay.addWidget(self.icon)
        self.menubar = QMenuBar()
        self.menubar.setNativeMenuBar(False)
        self.menubar.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        lay.addWidget(self.menubar)
        lay.addStretch(1)
        self.title = label("", "title")
        lay.addWidget(self.title)
        lay.addStretch(1)
        self.btn_min = tool("–", lambda: app.win.showMinimized(), name="winbtn", tip="Minimize")
        self.btn_max = tool("□", app.toggle_maximize, name="winbtn", tip="Maximize")
        self.btn_close = tool("✕", app.win.close, name="closebtn", tip="Close")
        for b in (self.btn_min, self.btn_max, self.btn_close):
            b.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            lay.addWidget(b)

    def set_frameless(self, frameless):
        for w in (self.btn_min, self.btn_max, self.btn_close, self.title):
            w.setVisible(frameless)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.app.frameless:
            h = self.app.win.windowHandle()
            if h is not None:
                h.startSystemMove()
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self.app.frameless and e.button() == Qt.MouseButton.LeftButton:
            self.app.toggle_maximize()
            return
        super().mouseDoubleClickEvent(e)


class Shell(QWidget):
    """Central widget. Paints nothing except a 1px border, so the editor can be see-through."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.lay = QVBoxLayout(self)
        self.lay.setSpacing(0)

    def paintEvent(self, _e):
        if self.app.frameless and not self.app.win.isMaximized() and not self.app.win.isFullScreen():
            p = QPainter(self)
            p.setPen(QColor(self.app.theme["border"]))
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))
            p.end()


class MainWindow(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setAcceptDrops(True)

    def closeEvent(self, e):
        if self.app.confirm_quit():
            e.accept()
        else:
            e.ignore()

    def changeEvent(self, e):
        if e.type() == QEvent.Type.WindowStateChange:
            self.app.on_window_state()
        super().changeEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.isLocalFile():
                self.app.open_path(u.toLocalFile())


class Dialog(QDialog):
    def __init__(self, app, title, parent=None):
        super().__init__(parent or app.win)
        self.app = app
        self.setWindowTitle(title)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(20, 18, 20, 16)
        self.body.setSpacing(10)
        app.dialogs.append(self)
        self.finished.connect(lambda *_: app.dialogs.remove(self) if self in app.dialogs else None)

    def showEvent(self, e):
        super().showEvent(e)
        set_titlebar_hwnd(int(self.winId()), self.app.theme)

    def on_theme(self):
        set_titlebar_hwnd(int(self.winId()), self.app.theme)

    def sync(self, key, value):
        pass


class PrefsDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, "Preferences")
        self.setModal(False)
        self.controls = {}
        s = app.settings
        cols = QHBoxLayout()
        cols.setSpacing(36)
        self.body.addLayout(cols)
        left, right = QGridLayout(), QGridLayout()
        for g in (left, right):
            g.setHorizontalSpacing(16)
            g.setVerticalSpacing(8)
            g.setColumnStretch(1, 1)
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        self._rows = {id(left): 0, id(right): 0}

        # look
        self.section(left, "LOOK")
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        dd = DropButton(app.theme_names, s["theme"], app.set_theme, 170)
        h.addWidget(dd)
        h.addWidget(button("Edit...", app.open_theme_editor))
        self.controls["theme"] = dd
        self.row(left, "Theme", w)

        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        self.op_slider = QSlider(Qt.Orientation.Horizontal)
        self.op_slider.setRange(*NUMERIC_LIMITS["editor_opacity"])
        self.op_slider.setValue(s["editor_opacity"])
        self.op_slider.setFixedWidth(170)
        self.op_label = label("%d%%" % s["editor_opacity"], "dim")
        self.op_label.setFixedWidth(40)
        self.op_slider.valueChanged.connect(self._opacity)
        h.addWidget(self.op_slider)
        h.addWidget(self.op_label)
        self.row(left, "Editor opacity", w)
        self.op_note = label("", "dim", wrap=True)
        self.wide(left, self.op_note)
        self.toggle(left, "Always on top", "topmost")
        self.toggle(left, "Use system title bar", "native_titlebar")

        # font
        self.section(left, "EDITOR FONT")
        fw = QWidget()
        fv = QVBoxLayout(fw)
        fv.setContentsMargins(0, 0, 0, 0)
        fv.setSpacing(6)
        top = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter fonts")
        self.filter.textChanged.connect(lambda *_: self.fill_fonts())
        top.addWidget(self.filter, 1)
        top.addWidget(label("Monospace only", "dim"))
        self.mono = Toggle(app, s["monospace_only"], self._mono)
        top.addWidget(self.mono)
        fv.addLayout(top)
        self.fonts = QListWidget()
        self.fonts.setMinimumHeight(170)
        self.fonts.currentTextChanged.connect(self._font_picked)
        fv.addWidget(self.fonts)
        self.preview = QLabel("SlopPad 0O 1lI {}[]() => != ~")
        self.preview.setFont(app.editor_font)
        fv.addWidget(self.preview)
        self.wide(left, fw)
        self.number(left, "Size", "font_size")
        self.toggle(left, "Bold", "font_bold")

        # editing
        self.section(right, "EDITING")
        self.number(right, "Tab width", "tab_width")
        self.toggle(right, "Indent with spaces", "insert_spaces")
        self.toggle(right, "Auto-indent", "auto_indent")
        self.toggle(right, "Word wrap", "wrap")
        self.section(right, "DISPLAY")
        self.toggle(right, "Line numbers", "line_numbers")
        self.toggle(right, "Highlight current line", "highlight_line")
        self.toggle(right, "Block cursor", "block_cursor")
        self.toggle(right, "Blinking cursor", "cursor_blink")
        self.number(right, "Cursor width", "cursor_width")
        self.number(right, "Padding", "padding")
        self.toggle(right, "Status bar", "status_bar")
        self.section(right, "INTERFACE")
        self.number(right, "UI font size", "ui_font_size")
        self.toggle(right, "Use editor font for UI", "ui_use_editor_font")
        dd = DropButton(["LF", "CRLF"], s["default_newline"], lambda v: app.set_setting("default_newline", v), 90)
        self.controls["default_newline"] = dd
        self.row(right, "New file line endings", dd)
        self.toggle(right, "Reopen files on startup", "restore_session")
        for g in (left, right):
            g.setRowStretch(self._rows[id(g)], 1)

        bar = QHBoxLayout()
        bar.addWidget(button("Open settings folder", app.open_config_folder))
        bar.addWidget(button("Reset everything...", app.reset_settings))
        bar.addStretch(1)
        bar.addWidget(button("Done", self.close, accent=True))
        self.body.addSpacing(8)
        self.body.addLayout(bar)
        self.fill_fonts()
        self._update_op_note()

    # layout helpers
    def _next(self, g):
        r = self._rows[id(g)]
        self._rows[id(g)] = r + 1
        return r

    def section(self, g, title):
        r = self._next(g)
        lb = label(title, "header")
        if r:
            lb.setContentsMargins(0, 10, 0, 0)
        g.addWidget(lb, r, 0, 1, 2)

    def row(self, g, text, widget):
        r = self._next(g)
        g.addWidget(label(text), r, 0)
        g.addWidget(widget, r, 1, Qt.AlignmentFlag.AlignRight)

    def wide(self, g, widget):
        g.addWidget(widget, self._next(g), 0, 1, 2)

    def toggle(self, g, text, key):
        t = Toggle(self.app, self.app.settings[key], lambda v, k=key: self.app.set_setting(k, bool(v)))
        self.controls[key] = t
        self.row(g, text, t)

    def number(self, g, text, key):
        lo, hi = NUMERIC_LIMITS[key]
        n = NumberField(self.app.settings[key], lo, hi, lambda v, k=key: self.app.set_setting(k, int(v)))
        self.controls[key] = n
        self.row(g, text, n)

    # behaviour
    def _opacity(self, v):
        self.op_label.setText("%d%%" % v)
        self.app.set_setting("editor_opacity", int(v))

    def _update_op_note(self):
        if not self.app.transparency_possible():
            self.op_note.setText("Windows can only see through the editor with SlopPad's own title bar. "
                                 "Turn off \"Use system title bar\" to use this.")
            self.op_note.show()
            self.op_slider.setEnabled(False)
        else:
            self.op_note.hide()
            self.op_slider.setEnabled(True)

    def _mono(self, v):
        self.app.set_setting("monospace_only", bool(v))
        self.fill_fonts()

    def fill_fonts(self):
        q = self.filter.text().strip().lower()
        fams = self.app.mono_fonts() if self.mono.isChecked() else self.app.font_families()
        self.fonts.blockSignals(True)
        self.fonts.clear()
        items = [f for f in fams if q in f.lower()]
        self.fonts.addItems(items)
        cur = self.app.editor_font.family()
        if cur in items:
            self.fonts.setCurrentRow(items.index(cur))
            self.fonts.scrollToItem(self.fonts.currentItem())
        self.fonts.blockSignals(False)

    def _font_picked(self, fam):
        if fam:
            self.app.set_setting("font_family", fam)

    def sync(self, key, value):
        if key == "editor_opacity":
            self.op_slider.blockSignals(True)
            self.op_slider.setValue(int(value))
            self.op_slider.blockSignals(False)
            self.op_label.setText("%d%%" % value)
        elif key == "native_titlebar":
            self.controls[key].set_value(value)
            self._update_op_note()
        elif key in ("font_family", "font_size", "font_bold"):
            self.preview.setFont(self.app.editor_font)
            if key in self.controls:
                self.controls[key].set_value(value)
        elif key in self.controls:
            self.controls[key].set_value(value)

    def on_theme(self):
        super().on_theme()
        for c in self.controls.values():
            c.update()
        self.mono.update()

    def done(self, r):
        self.app.prefs = None
        super().done(r)


class ThemeEditor(Dialog):
    def __init__(self, app):
        super().__init__(app, "Theme editor")
        self.orig = app.settings["theme"]
        self.work = dict(app.theme)
        self.saved = False
        custom = app.settings["custom_themes"]
        top = QHBoxLayout()
        top.addWidget(label("Theme name"))
        self.name = QLineEdit(self.orig if self.orig in custom else self.orig + " (custom)")
        self.name.setFixedWidth(260)
        top.addWidget(self.name)
        top.addStretch(1)
        self.body.addLayout(top)
        self.body.addWidget(label("Click a swatch to pick a color, or type a hex code and press Enter. "
                                  "Everything previews live.", "dim", wrap=True))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.body.addLayout(grid)
        self.swatches, self.hexes = {}, {}
        half = (len(THEME_KEYS) + 1) // 2
        for i, (key, text) in enumerate(THEME_KEYS):
            col, r = (0, i) if i < half else (1, i - half)
            base = col * 4
            sw = QPushButton()
            sw.setFixedSize(34, 24)
            sw.setCursor(Qt.CursorShape.PointingHandCursor)
            sw.clicked.connect(lambda *_, k=key: self.pick(k))
            grid.addWidget(sw, r, base)
            grid.addWidget(label(text), r, base + 1)
            ed = QLineEdit(self.work[key])
            ed.setFixedWidth(90)
            ed.editingFinished.connect(lambda k=key: self.commit_hex(k))
            grid.addWidget(ed, r, base + 2)
            if col == 0:
                grid.setColumnMinimumWidth(3, 30)
            self.swatches[key], self.hexes[key] = sw, ed
        bar = QHBoxLayout()
        bar.addWidget(button("Import...", self.import_theme))
        bar.addWidget(button("Export...", lambda: app.export_theme(self.name.text().strip() or "My theme",
                                                                   self.work, self)))
        bar.addWidget(button("Reset", self.reset))
        if self.orig in custom:
            bar.addWidget(button("Delete", self.delete))
        bar.addStretch(1)
        bar.addWidget(button("Cancel", self.reject))
        bar.addWidget(button("Save theme", self.save, accent=True))
        self.body.addSpacing(6)
        self.body.addLayout(bar)
        self.refresh()

    def refresh(self):
        for k, sw in self.swatches.items():
            sw.setStyleSheet("QPushButton { background: %s; border: 1px solid %s; border-radius: 4px; }"
                             % (self.work[k], self.app.theme["border"]))
            if self.hexes[k].text() != self.work[k]:
                self.hexes[k].setText(self.work[k])

    def on_theme(self):
        super().on_theme()
        self.refresh()

    def pick(self, key):
        c = QColorDialog.getColor(QColor(self.work[key]), self, dict(THEME_KEYS)[key])
        if c.isValid():
            self.set_color(key, c.name())

    def commit_hex(self, key):
        v = norm_hex(self.hexes[key].text())
        if v and v != self.work[key]:
            self.set_color(key, v)
        elif not v:
            self.hexes[key].setText(self.work[key])

    def set_color(self, key, value):
        v = norm_hex(value)
        if v:
            self.work[key] = v
            self.app.preview_theme(self.work)

    def reset(self):
        self.work = dict(self.app.resolve_theme(self.orig))
        self.app.preview_theme(self.work)

    def import_theme(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import theme", "", "Theme files (*.json);;All files (*)")
        if not path:
            return
        try:
            name, colors = load_theme_file(path)
        except Exception as e:
            self.app.error("Couldn't import theme", str(e), parent=self)
            return
        self.work = colors
        self.name.setText(name)
        self.app.preview_theme(self.work)

    def delete(self):
        if self.app.ask("Delete theme", 'Delete the theme "%s"?' % self.orig,
                        [("Delete", True, True), ("Cancel", None, False)], parent=self):
            self.app.settings["custom_themes"].pop(self.orig, None)
            self.saved = True
            self.app.set_theme(DEFAULT_THEME)
            self.accept()

    def save(self):
        name = self.name.text().strip() or "My theme"
        if name in BUILTIN_THEMES:
            name += " (custom)"
        self.app.settings["custom_themes"][name] = dict(self.work)
        self.saved = True
        self.app.set_theme(name)
        self.app.flash('Saved theme "%s"' % name)
        self.accept()

    def done(self, r):
        self.app.theme_editor = None
        if self in self.app.dialogs:
            self.app.dialogs.remove(self)
        if not self.saved:
            self.app.set_theme(self.app.settings["theme"])  # undo the live preview
        super().done(r)


def load_theme_file(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    colors = data.get("colors", data) if isinstance(data, dict) else None
    if not isinstance(colors, dict) or not any(norm_hex(colors.get(k)) for k, _ in THEME_KEYS):
        raise ValueError("No SlopPad colors found in that file.")
    name = data.get("name") if isinstance(data.get("name"), str) else None
    name = (name or os.path.splitext(os.path.basename(path))[0]).strip() or "Imported theme"
    return name, complete_theme(colors)


# --------------------------------------------------------------------------
# The app
# --------------------------------------------------------------------------

class App:
    RESIZE_MARGIN = 6

    def __init__(self, files, qapp=None):
        self.settings = Settings()
        if IS_WIN:
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
            except Exception:
                pass
        self.qapp = qapp or QApplication.instance() or QApplication(sys.argv[:1])
        self.qapp.setApplicationName("sloppad")
        self.qapp.setApplicationDisplayName(APP_NAME)
        self.qapp.setDesktopFileName("sloppad")
        self.qapp.setQuitOnLastWindowClosed(True)
        sys.excepthook = self.on_exception
        self.tabs, self.current, self.dialogs = [], None, []
        self.untitled_counter = 0
        self.zoom_delta = 0
        self.prefs = None
        self.theme_editor = None
        self._families = None
        self._mono = None
        self._showing_error = False
        self._resize_cursor = False
        self.theme = self.resolve_theme(self.settings["theme"])

        self.setup_fonts()
        self.win = MainWindow(self)
        self.frameless = self._want_frameless()
        self._apply_window_flags(first=True)
        self.build_ui()
        self.apply_theme()

        self.save_timer = QTimer()
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save_settings)
        self.status_timer = QTimer()
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(self.update_status)
        self.words_timer = QTimer()
        self.words_timer.setSingleShot(True)
        self.words_timer.timeout.connect(self.update_words)
        self.find_timer = QTimer()
        self.find_timer.setSingleShot(True)
        self.find_timer.timeout.connect(lambda: self.findbar.rescan(False))
        self.flash_timer = QTimer()
        self.flash_timer.setSingleShot(True)
        self.flash_timer.timeout.connect(lambda: self.st_msg.setText(""))

        for p in files:
            self.open_path(p)
        if not files and self.settings["restore_session"]:
            for p in self.settings["session"]:
                if os.path.isfile(p):
                    self.open_path(p, quiet=True)
        if not self.tabs:
            self.new_tab()
        self.select_tab(self.tabs[-1] if files else self.tabs[0])

        self.restore_window()
        self.qapp.installEventFilter(self._filter_obj())
        if self.settings.load_error:
            QTimer.singleShot(300, lambda: self.error(
                "Settings were reset", "Your settings file couldn't be read, so SlopPad started fresh.",
                detail="A copy was saved as settings.json.broken\n\n" + self.settings.load_error))

    # ---- window frame / transparency
    def _want_frameless(self):
        if IS_MAC:
            return not self.settings["native_titlebar"]
        return not self.settings["native_titlebar"]

    def transparency_possible(self):
        return not (IS_WIN and self.settings["native_titlebar"])

    def editor_alpha(self):
        if not self.transparency_possible():
            return 255
        return int(round(self.settings["editor_opacity"] / 100.0 * 255))

    def _apply_window_flags(self, first=False):
        w = self.win
        geo = w.saveGeometry() if not first else None
        was_max = w.isMaximized()
        self.frameless = self._want_frameless()
        translucent = self.transparency_possible()
        w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, translucent)
        w.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, translucent)
        flags = Qt.WindowType.Window
        if self.frameless:
            flags |= (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowMinMaxButtonsHint
                      | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowSystemMenuHint)
        if self.settings["topmost"]:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        w.setWindowFlags(flags)
        if not first:
            if geo is not None:
                w.restoreGeometry(geo)
            if was_max:
                w.showMaximized()
            else:
                w.show()
            self.titlebar.set_frameless(self.frameless)
            self.on_window_state()
            set_titlebar_hwnd(int(w.winId()), self.theme)

    def toggle_maximize(self):
        if self.win.isMaximized():
            self.win.showNormal()
        else:
            self.win.showMaximized()

    def toggle_fullscreen(self):
        if self.win.isFullScreen():
            self.win.showNormal()
        else:
            self.win.showFullScreen()

    def on_window_state(self):
        if not hasattr(self, "shell"):
            return
        edge = 1 if (self.frameless and not self.win.isMaximized() and not self.win.isFullScreen()) else 0
        self.shell.lay.setContentsMargins(edge, edge, edge, edge)
        self.titlebar.btn_max.setText("❐" if self.win.isMaximized() else "□")
        self.shell.update()

    def _filter_obj(self):
        app = self

        class F(QWidget):
            def eventFilter(self, obj, e):
                return app._resize_filter(obj, e)

        self._filter = F()
        return self._filter

    def _edges_at(self, gpos):
        w = self.win
        if not self.frameless or w.isMaximized() or w.isFullScreen():
            return None
        g = w.frameGeometry()
        m = self.RESIZE_MARGIN
        x, y = gpos.x(), gpos.y()
        if not g.adjusted(-1, -1, 1, 1).contains(gpos):
            return None
        edges = Qt.Edge(0)
        if x <= g.left() + m:
            edges |= Qt.Edge.LeftEdge
        elif x >= g.right() - m:
            edges |= Qt.Edge.RightEdge
        if y <= g.top() + m:
            edges |= Qt.Edge.TopEdge
        elif y >= g.bottom() - m:
            edges |= Qt.Edge.BottomEdge
        return edges if edges != Qt.Edge(0) else None

    def _resize_filter(self, obj, e):
        t = e.type()
        if t not in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.HoverMove):
            return False
        if not isinstance(obj, QWidget) or obj.window() is not self.win:
            return False
        gp = e.globalPosition().toPoint() if hasattr(e, "globalPosition") else None
        if gp is None:
            return False
        edges = self._edges_at(gp)
        if t == QEvent.Type.MouseButtonPress and edges and e.button() == Qt.MouseButton.LeftButton:
            h = self.win.windowHandle()
            if h is not None and h.startSystemResize(edges):
                return True
            return False
        if edges:
            L, R, T, B = Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge
            if edges in (L | T, R | B):
                shape = Qt.CursorShape.SizeFDiagCursor
            elif edges in (R | T, L | B):
                shape = Qt.CursorShape.SizeBDiagCursor
            elif edges in (L, R):
                shape = Qt.CursorShape.SizeHorCursor
            else:
                shape = Qt.CursorShape.SizeVerCursor
            if self._resize_cursor:
                QApplication.changeOverrideCursor(shape)
            else:
                QApplication.setOverrideCursor(shape)
                self._resize_cursor = True
        elif self._resize_cursor:
            QApplication.restoreOverrideCursor()
            self._resize_cursor = False
        return False

    # ---- fonts
    def font_families(self):
        if self._families is None:
            self._families = sorted({f for f in QFontDatabase.families()
                                     if not f.startswith("@") and "emoji" not in f.lower()}, key=str.lower)
        return self._families

    def mono_fonts(self):
        if self._mono is None:
            self._mono = [f for f in self.font_families() if QFontDatabase.isFixedPitch(f)] or self.font_families()
        return self._mono

    def _default_font_family(self):
        fams = {f.lower(): f for f in self.font_families()}
        for cand in ("JetBrains Mono", "Cascadia Code", "Cascadia Mono", "Fira Code", "SF Mono", "Menlo",
                     "Consolas", "Hack", "Source Code Pro", "DejaVu Sans Mono", "Noto Sans Mono",
                     "Ubuntu Mono", "Liberation Mono", "Courier New"):
            if cand.lower() in fams:
                return fams[cand.lower()]
        return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()

    def setup_fonts(self):
        s = self.settings
        fam = s["font_family"] if s["font_family"] in self.font_families() else self._default_font_family()
        self.editor_font = QFont(fam)
        self.editor_font.setPointSizeF(s["font_size"])
        self.editor_font.setBold(s["font_bold"])
        self.editor_font.setStyleHint(QFont.StyleHint.Monospace)
        self.base_ui_family = QApplication.font().family()
        self.update_ui_font()

    def update_editor_font(self):
        s = self.settings
        if s["font_family"]:
            self.editor_font.setFamily(s["font_family"])
        self.editor_font.setPointSizeF(max(6, min(96, s["font_size"] + self.zoom_delta)))
        self.editor_font.setBold(s["font_bold"])
        for t in self.tabs:
            t.editor.apply_settings()
        if s["ui_use_editor_font"]:
            self.update_ui_font()
        self.update_status()

    def update_ui_font(self):
        s = self.settings
        f = QFont(self.editor_font.family() if s["ui_use_editor_font"] else self.base_ui_family)
        f.setPointSizeF(s["ui_font_size"])
        self.qapp.setFont(f)
        for t in self.tabs:
            t.editor.setFont(self.editor_font)

    # ---- UI
    def build_ui(self):
        w = self.win
        w.setWindowTitle(APP_NAME)
        w.setMinimumSize(480, 300)
        self.shell = Shell(self)
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)
        lay = self.shell.lay

        self.titlebar = TitleBar(self)
        lay.addWidget(self.titlebar)
        lay.addWidget(sep())

        tabrow = QWidget()
        tabrow.setObjectName("tabrow")
        tabrow.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        th = QHBoxLayout(tabrow)
        th.setContentsMargins(0, 0, 4, 0)
        th.setSpacing(0)
        self.tabbar = QTabBar()
        self.tabbar.setDocumentMode(True)
        self.tabbar.setExpanding(False)
        self.tabbar.setMovable(True)
        self.tabbar.setUsesScrollButtons(True)
        self.tabbar.setElideMode(Qt.TextElideMode.ElideNone)
        self.tabbar.setDrawBase(False)
        self.tabbar.currentChanged.connect(self._tab_changed)
        self.tabbar.tabMoved.connect(self._tab_moved)
        self.tabbar.tabBarDoubleClicked.connect(lambda i: self.new_tab() if i < 0 else None)
        self.tabbar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabbar.customContextMenuRequested.connect(self._tab_menu)
        th.addWidget(self.tabbar)
        th.addStretch(1)
        th.addWidget(tool("+", self.new_tab, tip="New tab (Ctrl+N)"))
        lay.addWidget(tabrow)
        lay.addWidget(sep())

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.findbar = FindBar(self)
        lay.addWidget(self.findbar)
        self.build_status()
        lay.addWidget(self.status)
        self.status.setVisible(self.settings["status_bar"])
        self.build_menus()
        self.titlebar.set_frameless(self.frameless)

    def build_status(self):
        st = self.status = QWidget()
        st.setObjectName("status")
        st.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        v = QVBoxLayout(st)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(sep())
        h = QHBoxLayout()
        h.setContentsMargins(10, 2, 6, 2)
        h.setSpacing(4)
        v.addLayout(h)
        self.st_pos = label("Ln 1, Col 1", "dim")
        self.st_sel = label("", "dim")
        self.st_msg = label("", "header")
        h.addWidget(self.st_pos)
        h.addSpacing(10)
        h.addWidget(self.st_sel)
        h.addSpacing(14)
        h.addWidget(self.st_msg)
        h.addStretch(1)
        self.st_words = label("", "dim")
        h.addWidget(self.st_words)
        h.addSpacing(8)
        self.st_zoom = tool("", lambda: self.zoom(0), name="statusbtn", tip="Zoom (click to reset)")
        self.st_indent = tool("Spaces: 4", self._indent_menu, name="statusbtn", tip="Indentation")
        self.st_eol = tool("LF", self._eol_menu, name="statusbtn", tip="Line endings")
        self.st_enc = tool("UTF-8", self._enc_menu, name="statusbtn", tip="File encoding")
        for b in (self.st_zoom, self.st_indent, self.st_eol, self.st_enc):
            h.addWidget(b)

    def _popup(self, widget, fill):
        m = QMenu(self.win)
        fill(m)
        m.exec(widget.mapToGlobal(QPoint(0, -m.sizeHint().height())))

    def _eol_menu(self):
        tab = self.current
        if not tab:
            return

        def fill(m):
            g = QActionGroup(m)
            for nl, desc in (("LF", "LF  (Linux / macOS)"), ("CRLF", "CRLF  (Windows)"), ("CR", "CR  (old Mac)")):
                a = m.addAction(desc)
                a.setCheckable(True)
                a.setChecked(tab.newline == nl)
                g.addAction(a)
                a.triggered.connect(lambda *_, nl=nl: self.set_newline(nl))

        self._popup(self.st_eol, fill)

    def set_newline(self, nl):
        tab = self.current
        if tab and tab.newline != nl:
            tab.newline = nl
            tab.set_modified(True)
            self.update_status()

    def _enc_menu(self):
        tab = self.current
        if not tab:
            return
        cur = "UTF-8 with BOM" if (tab.encoding == "UTF-8" and tab.bom) else tab.encoding

        def fill(m):
            a = m.addAction("Save with encoding:")
            a.setEnabled(False)
            g = QActionGroup(m)
            for enc in ENCODINGS:
                a = m.addAction(enc)
                a.setCheckable(True)
                a.setChecked(enc == cur)
                g.addAction(a)
                a.triggered.connect(lambda *_, e=enc: self.set_encoding(e))

        self._popup(self.st_enc, fill)

    def set_encoding(self, enc):
        tab = self.current
        if not tab:
            return
        if enc == "UTF-8 with BOM":
            tab.encoding, tab.bom = "UTF-8", True
        else:
            tab.encoding, tab.bom = enc, enc == "UTF-16"
        tab.set_modified(True)
        self.update_status()

    def _indent_menu(self):
        s = self.settings

        def fill(m):
            g = QActionGroup(m)
            for label_, val in (("Indent with spaces", True), ("Indent with tabs", False)):
                a = m.addAction(label_)
                a.setCheckable(True)
                a.setChecked(s["insert_spaces"] == val)
                g.addAction(a)
                a.triggered.connect(lambda *_, v=val: self.set_setting("insert_spaces", v))
            m.addSeparator()
            g2 = QActionGroup(m)
            for w in (2, 4, 8):
                a = m.addAction("Width: %d" % w)
                a.setCheckable(True)
                a.setChecked(s["tab_width"] == w)
                g2.addAction(a)
                a.triggered.connect(lambda *_, w=w: self.set_setting("tab_width", w))

        self._popup(self.st_indent, fill)

    def _act(self, menu, text, slot, shortcut=None, checkable=False, checked=False):
        a = QAction(text, self.win)
        if shortcut:
            a.setShortcuts([QKeySequence(s) for s in (shortcut if isinstance(shortcut, (list, tuple)) else [shortcut])])
            a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        a.setCheckable(checkable)
        if checkable:
            a.setChecked(checked)
            a.toggled.connect(slot)
        else:
            a.triggered.connect(lambda *_: slot())
        menu.addAction(a)
        self.win.addAction(a)
        return a

    def _ed(self, name, *args):
        return lambda: getattr(self.current.editor, name)(*args) if self.current else None

    def build_menus(self):
        mb = self.titlebar.menubar
        s = self.settings
        A = self._act
        self.checks = {}

        fm = mb.addMenu("File")
        A(fm, "New tab", self.new_tab, "Ctrl+N")
        A(fm, "Open...", self.open_dialog, "Ctrl+O")
        self.recent_menu = fm.addMenu("Open recent")
        self.recent_menu.aboutToShow.connect(self.fill_recent)
        A(fm, "Reload from disk", self.reload_current)
        fm.addSeparator()
        A(fm, "Save", lambda: self.save_tab(self.current), "Ctrl+S")
        A(fm, "Save as...", lambda: self.save_tab(self.current, save_as=True), "Ctrl+Shift+S")
        A(fm, "Save all", self.save_all)
        fm.addSeparator()
        A(fm, "Close tab", lambda: self.close_tab(self.current), "Ctrl+W")
        A(fm, "Quit", self.win.close, "Ctrl+Q")

        em = mb.addMenu("Edit")
        A(em, "Undo", self._ed("undo"), QKeySequence.StandardKey.Undo)
        A(em, "Redo", self._ed("redo"), ["Ctrl+Y", "Ctrl+Shift+Z"])
        em.addSeparator()
        A(em, "Cut", self._ed("cut"), QKeySequence.StandardKey.Cut)
        A(em, "Copy", self._ed("copy"), QKeySequence.StandardKey.Copy)
        A(em, "Paste", self._ed("paste"), QKeySequence.StandardKey.Paste)
        A(em, "Select all", self._ed("selectAll"), QKeySequence.StandardKey.SelectAll)
        A(em, "Select line", self._ed("select_line"), "Ctrl+L")
        em.addSeparator()
        A(em, "Find...", lambda: self.findbar.open_bar(False), "Ctrl+F")
        A(em, "Replace...", lambda: self.findbar.open_bar(True), "Ctrl+H")
        A(em, "Find next", lambda: self.findbar.step(1), "F3")
        A(em, "Find previous", lambda: self.findbar.step(-1), "Shift+F3")
        A(em, "Go to line...", self.goto_line, "Ctrl+G")
        em.addSeparator()
        A(em, "Duplicate line", self._ed("duplicate"), "Ctrl+D")
        A(em, "Delete line", self._ed("delete_line"), "Ctrl+Shift+K")
        A(em, "Move line up", self._ed("move_lines", -1))
        A(em, "Move line down", self._ed("move_lines", 1))
        em.addSeparator()
        A(em, "UPPERCASE selection", self._ed("change_case", True))
        A(em, "lowercase selection", self._ed("change_case", False))
        A(em, "Trim trailing whitespace", self._ed("trim_trailing"))

        vm = mb.addMenu("View")
        for key, text, sc in (("wrap", "Word wrap", "Alt+Z"), ("line_numbers", "Line numbers", None),
                              ("highlight_line", "Highlight current line", None),
                              ("status_bar", "Status bar", None)):
            self.checks[key] = A(vm, text, lambda v, k=key: self.set_setting(k, bool(v)), sc,
                                 checkable=True, checked=s[key])
        vm.addSeparator()
        A(vm, "Zoom in", lambda: self.zoom(1), ["Ctrl+=", "Ctrl++"])
        A(vm, "Zoom out", lambda: self.zoom(-1), "Ctrl+-")
        A(vm, "Reset zoom", lambda: self.zoom(0), "Ctrl+0")
        vm.addSeparator()
        om = vm.addMenu("Editor opacity")
        self.opacity_group = QActionGroup(om)
        self.opacity_actions = {}
        for pct in range(100, 10, -10):
            if pct < NUMERIC_LIMITS["editor_opacity"][0]:
                break
            a = om.addAction("%d%%" % pct)
            a.setCheckable(True)
            a.setChecked(s["editor_opacity"] == pct)
            self.opacity_group.addAction(a)
            a.triggered.connect(lambda *_, p=pct: self.set_setting("editor_opacity", p))
            self.opacity_actions[pct] = a
        self.checks["topmost"] = A(vm, "Always on top", lambda v: self.set_setting("topmost", bool(v)),
                                   checkable=True, checked=s["topmost"])
        A(vm, "Full screen", self.toggle_fullscreen, "F11")
        A(vm, "Next tab", lambda: self.cycle_tab(1), "Ctrl+Tab")
        A(vm, "Previous tab", lambda: self.cycle_tab(-1), ["Ctrl+Shift+Tab", "Ctrl+Shift+Backtab"])

        self.theme_menu = mb.addMenu("Theme")
        self.theme_menu.aboutToShow.connect(self.fill_theme_menu)
        self.fill_theme_menu()

        sm = mb.addMenu("Settings")
        A(sm, "Preferences...", self.open_prefs, "Ctrl+,")
        A(sm, "Theme editor...", self.open_theme_editor)
        sm.addSeparator()
        A(sm, "Open settings folder", self.open_config_folder)
        A(sm, "Reset everything...", self.reset_settings)

        hm = mb.addMenu("Help")
        A(hm, "Keyboard shortcuts", self.show_shortcuts, "F1")
        A(hm, "About SlopPad", self.show_about)

    def fill_recent(self):
        m = self.recent_menu
        m.clear()
        rec = self.settings["recent"]
        if not rec:
            a = m.addAction("(nothing yet)")
            a.setEnabled(False)
            return
        for p in rec:
            m.addAction(p if len(p) <= 70 else "..." + p[-67:], lambda p=p: self.open_path(p))
        m.addSeparator()
        m.addAction("Clear list", self.clear_recent)

    def clear_recent(self):
        self.settings["recent"] = []
        self.save_settings_soon()

    def fill_theme_menu(self):
        m = self.theme_menu
        m.clear()
        g = QActionGroup(m)

        def add(name):
            a = m.addAction(name)
            a.setCheckable(True)
            a.setChecked(name == self.settings["theme"])
            g.addAction(a)
            a.triggered.connect(lambda *_, n=name: self.set_theme(n))

        for name in BUILTIN_THEMES:
            add(name)
        custom = sorted(self.settings["custom_themes"], key=str.lower)
        if custom:
            m.addSeparator()
            for name in custom:
                add(name)
        m.addSeparator()
        m.addAction("Theme editor...", self.open_theme_editor)
        m.addAction("Import theme...", self.import_theme_file)
        m.addAction("Export current theme...", lambda: self.export_theme(self.settings["theme"], self.theme))

    # ---- theming
    def theme_names(self):
        return list(BUILTIN_THEMES) + sorted(self.settings["custom_themes"], key=str.lower)

    def resolve_theme(self, name):
        custom = self.settings["custom_themes"]
        if name in custom:
            return complete_theme(custom[name])
        return complete_theme(BUILTIN_THEMES.get(name, BUILTIN_THEMES[DEFAULT_THEME]))

    def set_theme(self, name):
        if name not in BUILTIN_THEMES and name not in self.settings["custom_themes"]:
            name = DEFAULT_THEME
        self.settings["theme"] = name
        self.theme = self.resolve_theme(name)
        self.apply_theme()
        self._sync_dialogs("theme", name)
        self.save_settings_soon()

    def preview_theme(self, colors):
        self.theme = complete_theme(colors)
        self.apply_theme()

    def apply_theme(self):
        t = self.theme
        self.qapp.setStyleSheet(build_stylesheet(t, self.editor_alpha()))
        icon = make_icon(t)
        self.win.setWindowIcon(icon)
        self.qapp.setWindowIcon(icon)
        self.titlebar.icon.setPixmap(icon.pixmap(18, 18))
        for tab in self.tabs:
            tab.editor.apply_theme()
            tab.close_btn.refresh()
        set_titlebar_hwnd(int(self.win.winId()), t)
        for d in list(self.dialogs):
            d.on_theme()
        self.shell.update()
        if self.findbar.isVisible() and self.findbar.matches and not self.findbar._stale():
            self.findbar._highlight(False)

    # ---- settings
    def set_setting(self, key, value):
        self.settings[key] = value
        a = getattr(self, "checks", {}).get(key)
        if a is not None and a.isChecked() != bool(value):
            a.blockSignals(True)
            a.setChecked(bool(value))
            a.blockSignals(False)
        if key == "editor_opacity" and value in getattr(self, "opacity_actions", {}):
            self.opacity_actions[value].setChecked(True)
        self.apply_setting(key)
        self._sync_dialogs(key, value)
        self.save_settings_soon()

    def _sync_dialogs(self, key, value):
        for d in list(self.dialogs):
            try:
                d.sync(key, value)
            except RuntimeError:
                pass

    def apply_setting(self, key):
        if key in ("font_family", "font_size", "font_bold"):
            self.update_editor_font()
        elif key in ("ui_font_size", "ui_use_editor_font"):
            self.update_ui_font()
        elif key == "editor_opacity":
            self.qapp.setStyleSheet(build_stylesheet(self.theme, self.editor_alpha()))
            for t in self.tabs:
                t.editor.apply_theme()
        elif key in ("topmost", "native_titlebar"):
            self._apply_window_flags()
            self.apply_setting("editor_opacity")
        elif key == "status_bar":
            self.status.setVisible(self.settings["status_bar"])
        elif key in ("default_newline", "restore_session", "monospace_only", "theme"):
            pass
        else:
            for t in self.tabs:
                t.editor.apply_settings()
            self.update_status()

    def save_settings_soon(self):
        if hasattr(self, "save_timer"):
            self.save_timer.start(700)

    def save_settings(self):
        try:
            self.settings.save()
        except Exception as e:
            self._log("Could not save settings: %s" % e)

    def reset_settings(self):
        if not self.ask("Reset everything?", "Put every setting back to default?",
                        [("Reset", True, True), ("Cancel", None, False)],
                        detail="Your custom themes and recent files are kept.", parent=self.prefs):
            return
        keep = {k: self.settings[k] for k in ("custom_themes", "recent", "session", "window_state")}
        old_native, old_top = self.settings["native_titlebar"], self.settings["topmost"]
        self.settings.data = copy.deepcopy(DEFAULT_SETTINGS)
        self.settings.data.update(keep)
        self.zoom_delta = 0
        self.editor_font.setFamily(self._default_font_family())
        for key, a in self.checks.items():
            a.blockSignals(True)
            a.setChecked(bool(self.settings[key]))
            a.blockSignals(False)
        self.update_editor_font()
        self.update_ui_font()
        self.status.setVisible(self.settings["status_bar"])
        if (old_native, old_top) != (self.settings["native_titlebar"], self.settings["topmost"]):
            self._apply_window_flags()
        self.set_theme(DEFAULT_THEME)
        self.apply_setting("editor_opacity")
        for key in DEFAULT_SETTINGS:
            self._sync_dialogs(key, self.settings[key])
        if self.prefs:
            self.prefs.fill_fonts()
        self.flash("Settings reset")

    def open_config_folder(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        if not open_in_file_manager(CONFIG_DIR):
            self.info("Settings folder", CONFIG_DIR)

    def zoom(self, d):
        if d == 0:
            self.zoom_delta = 0
        elif 6 <= self.settings["font_size"] + self.zoom_delta + d <= 96:
            self.zoom_delta += d
        self.update_editor_font()

    # ---- dialogs
    def open_prefs(self):
        if self.prefs is not None:
            self.prefs.raise_()
            self.prefs.activateWindow()
            return
        self.prefs = PrefsDialog(self)
        self.prefs.show()

    def open_theme_editor(self):
        if self.theme_editor is not None:
            self.theme_editor.raise_()
            return
        self.theme_editor = ThemeEditor(self)
        self.theme_editor.show()

    def ask(self, title, message, buttons, detail=None, parent=None, default=0):
        """buttons: list of (label, value, is_accent). Returns the value, or None if closed."""
        d = Dialog(self, title, parent=parent)
        d.setModal(True)
        msg = label(message, wrap=True)
        msg.setStyleSheet("font-weight: bold;")
        msg.setMinimumWidth(380)
        d.body.addWidget(msg)
        if detail:
            d.body.addWidget(label(detail, "dim", wrap=True))
        row = QHBoxLayout()
        row.addStretch(1)
        result = {"v": None}

        def choose(v):
            result["v"] = v
            d.accept()

        made = []
        for text, value, accent in reversed(buttons):
            b = button(text, lambda v=value: choose(v), accent=accent)
            row.addWidget(b)
            made.append(b)
        made[len(made) - 1 - default].setDefault(True)
        d.body.addSpacing(8)
        d.body.addLayout(row)
        d.exec()
        return result["v"]

    def info(self, title, message, detail=None, parent=None):
        self.ask(title, message, [("OK", True, True)], detail=detail, parent=parent)

    error = info

    def ask_save(self, tab):
        self.select_tab(tab)
        return self.ask("Unsaved changes", 'Save changes to "%s"?' % tab.title(),
                        [("Save", "save", True), ("Don't save", "discard", False), ("Cancel", None, False)],
                        detail="If you don't save, your changes will be lost.")

    def goto_line(self):
        tab = self.current
        if not tab:
            return
        ed = tab.editor
        last = ed.blockCount()
        d = Dialog(self, "Go to line")
        d.body.addWidget(label("Line number (1 - %d), or line:column" % last, "dim"))
        e = QLineEdit(str(ed.textCursor().blockNumber() + 1))
        e.setMinimumWidth(260)
        d.body.addWidget(e)

        def go():
            m = re.match(r"^\s*(\d+)\s*(?:[:,.]\s*(\d+))?\s*$", e.text())
            if not m:
                QApplication.beep()
                return
            ln = max(1, min(last, int(m.group(1))))
            blk = ed.document().findBlockByNumber(ln - 1)
            col = max(0, int(m.group(2) or 1) - 1)
            c = QTextCursor(blk)
            c.setPosition(blk.position() + min(col, blk.length() - 1))
            ed.setTextCursor(c)
            ed.centerCursor()
            d.accept()
            ed.setFocus()

        e.returnPressed.connect(go)
        e.selectAll()
        d.show()
        e.setFocus()

    def show_shortcuts(self):
        d = Dialog(self, "Keyboard shortcuts")
        M = "Cmd+" if IS_MAC else "Ctrl+"
        A = "Option+" if IS_MAC else "Alt+"
        rows = [
            ("New tab / Open / Save", M + "N  /  " + M + "O  /  " + M + "S"), ("Save as", M + "Shift+S"),
            ("Close tab / Quit", M + "W  /  " + M + "Q"), ("Next / previous tab", M + "Tab  /  " + M + "Shift+Tab"),
            ("Find / Replace", M + "F  /  " + M + "H"), ("Next / previous match", "Enter / Shift+Enter  (or F3)"),
            ("Go to line", M + "G"), ("Undo / Redo", M + "Z  /  " + M + "Y"), ("Select line", M + "L"),
            ("Duplicate line", M + "D"), ("Delete line", M + "Shift+K"),
            ("Move line up / down", A + "Up  /  " + A + "Down"), ("Indent / unindent", "Tab  /  Shift+Tab"),
            ("Delete word", M + "Backspace  /  " + M + "Delete"),
            ("Zoom", M + "+  /  " + M + "-  /  " + M + "0  (or " + M + "scroll)"),
            ("Word wrap", "Alt+Z"), ("Full screen", "F11"), ("Preferences", M + ","),
            ("Open files", "Drag them onto the window"),
        ]
        g = QGridLayout()
        g.setHorizontalSpacing(28)
        for i, (desc, keys) in enumerate(rows):
            g.addWidget(label(desc), i, 0)
            g.addWidget(label(keys, "header"), i, 1)
        d.body.addLayout(g)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Close", d.accept, accent=True))
        d.body.addLayout(row)
        d.show()

    def show_about(self):
        d = Dialog(self, "About SlopPad")
        t = label(APP_NAME, "header")
        f = t.font()
        f.setPointSizeF(f.pointSizeF() + 6)
        t.setFont(f)
        d.body.addWidget(t)
        d.body.addWidget(label("Version %s (Qt edition)" % VERSION, "dim"))
        d.body.addWidget(label("A text editor vibe-coded by Claude for slopware.\n"
                               "The human who ships it has never read the code. Use accordingly."))
        link = QLabel('<a href="%s" style="color:%s">%s</a>' % (REPO_URL, self.theme["accent"], REPO_URL))
        link.setOpenExternalLinks(True)
        d.body.addWidget(link)
        from PySide6 import __version__ as pyside_version
        d.body.addWidget(label("Python %s  |  PySide6 %s  |  %s\nSettings: %s" % (
            platform.python_version(), pyside_version, platform.platform(), SETTINGS_PATH), "dim", wrap=True))
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Close", d.accept, accent=True))
        d.body.addLayout(row)
        d.show()

    def import_theme_file(self):
        path, _ = QFileDialog.getOpenFileName(self.win, "Import theme", "", "Theme files (*.json);;All files (*)")
        if not path:
            return
        try:
            name, colors = load_theme_file(path)
        except Exception as e:
            self.error("Couldn't import theme", str(e))
            return
        if name in BUILTIN_THEMES:
            name += " (imported)"
        self.settings["custom_themes"][name] = colors
        self.set_theme(name)
        self.flash('Imported "%s"' % name)

    def export_theme(self, name, colors, parent=None):
        safe = re.sub(r'[\\/:*?"<>|]+', "_", name) or "theme"
        path, _ = QFileDialog.getSaveFileName(parent or self.win, "Export theme", safe + ".json",
                                              "Theme files (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"name": name, "app": APP_NAME, "colors": complete_theme(colors)}, f, indent=2)
            self.flash("Exported theme")
        except OSError as e:
            self.error("Couldn't export theme", str(e), parent=parent)

    # ---- tabs
    def new_tab(self, path=None, select=True):
        tab = Tab(self, path)
        self.tabs.append(tab)
        self.stack.addWidget(tab.editor)
        i = self.tabbar.addTab(tab.title())
        self.tabbar.setTabButton(i, QTabBar.ButtonPosition.RightSide, tab.close_btn)
        self.tabbar.setTabToolTip(i, tab.path or "Not saved yet")
        if select:
            self.select_tab(tab)
        return tab

    def _tab_index(self, tab):
        try:
            return self.tabs.index(tab)
        except ValueError:
            return -1

    def select_tab(self, tab):
        if tab not in self.tabs:
            return
        i = self._tab_index(tab)
        if self.tabbar.currentIndex() != i:
            self.tabbar.setCurrentIndex(i)  # -> _tab_changed
        else:
            self._tab_changed(i)

    def _tab_changed(self, i):
        if i < 0 or i >= len(self.tabs):
            return
        tab = self.tabs[i]
        changed = tab is not self.current
        self.current = tab
        self.stack.setCurrentWidget(tab.editor)
        tab.editor.setFocus()
        if changed and self.findbar.isVisible():
            self.findbar.anchor = tab.editor.textCursor().position()
            self.findbar.rescan(False)
        self.update_title()
        self.update_status()
        self.words_timer.start(50) if hasattr(self, "words_timer") else None

    def _tab_moved(self, frm, to):
        tab = self.tabs.pop(frm)
        self.tabs.insert(to, tab)

    def _tab_menu(self, pos):
        i = self.tabbar.tabAt(pos)
        if i < 0:
            return
        tab = self.tabs[i]
        m = QMenu(self.win)
        m.addAction("Close", lambda: self.close_tab(tab))
        m.addAction("Close others", lambda: self.close_others(tab))
        m.addSeparator()
        a = m.addAction("Copy path", lambda: self.copy_text(tab.path or ""))
        a.setEnabled(bool(tab.path))
        a = m.addAction("Open containing folder", lambda: open_in_file_manager(os.path.dirname(tab.path)))
        a.setEnabled(bool(tab.path))
        m.exec(self.tabbar.mapToGlobal(pos))

    def cycle_tab(self, d):
        if len(self.tabs) > 1 and self.current in self.tabs:
            i = self._tab_index(self.current)
            self.select_tab(self.tabs[(i + d) % len(self.tabs)])

    def close_tab(self, tab, ask=True):
        if tab is None or tab not in self.tabs:
            return False
        if ask and tab.is_modified():
            ans = self.ask_save(tab)
            if ans is None:
                return False
            if ans == "save" and not self.save_tab(tab):
                return False
        i = self._tab_index(tab)
        if self.findbar.scan_tab is tab:
            self.findbar.scan_tab = None
        was_current = tab is self.current
        self.tabs.pop(i)
        if was_current:
            self.current = None
        self.tabbar.blockSignals(True)
        self.tabbar.removeTab(i)
        self.tabbar.blockSignals(False)
        self.stack.removeWidget(tab.editor)
        tab.editor.deleteLater()
        if not self.tabs:
            self.new_tab()
        elif was_current:
            self.select_tab(self.tabs[min(i, len(self.tabs) - 1)])
        else:
            self._tab_changed(self.tabbar.currentIndex())
        self.update_session()
        return True

    def close_others(self, keep):
        for tab in [t for t in self.tabs if t is not keep]:
            if not self.close_tab(tab):
                break
        self.select_tab(keep)

    def refresh_tab(self, tab):
        i = self._tab_index(tab)
        if i >= 0:
            self.tabbar.setTabText(i, tab.title())
            self.tabbar.setTabToolTip(i, tab.path or "Not saved yet")
        tab.close_btn.refresh()

    def refresh_modified(self, tab):
        self.refresh_tab(tab)
        if tab is self.current:
            self.update_title()

    def update_title(self):
        tab = self.current
        if not tab:
            text = APP_NAME
        else:
            mark = "● " if tab.is_modified() else ""
            where = "  (%s)" % os.path.dirname(tab.path) if tab.path else ""
            text = "%s%s%s - %s" % (mark, tab.title(), where, APP_NAME)
        self.win.setWindowTitle(text)
        self.titlebar.title.setText(text)

    # ---- editor events
    def on_text_change(self, tab):
        if tab is self.current:
            self.status_timer.start(15)
            self.words_timer.start(400)
            if self.findbar.isVisible():
                self.find_timer.start(250)

    def update_status(self):
        tab = self.current
        if not tab:
            return
        ed = tab.editor
        c = ed.textCursor()
        self.st_pos.setText("Ln %d, Col %d" % (c.blockNumber() + 1, c.positionInBlock() + 1))
        if c.hasSelection():
            n = len(c.selectedText())
            doc = ed.document()
            a = doc.findBlock(c.selectionStart()).blockNumber()
            b = doc.findBlock(c.selectionEnd()).blockNumber()
            lines = b - a + 1
            self.st_sel.setText("(%d selected%s)" % (n, ", %d lines" % lines if lines > 1 else ""))
        else:
            self.st_sel.setText("")
        s = self.settings
        self.st_enc.setText("UTF-8 BOM" if (tab.encoding == "UTF-8" and tab.bom) else tab.encoding)
        self.st_eol.setText(tab.newline)
        self.st_indent.setText(("Spaces: %d" if s["insert_spaces"] else "Tab size: %d") % s["tab_width"])
        self.st_zoom.setText("Zoom %+d" % self.zoom_delta)
        self.st_zoom.setVisible(bool(self.zoom_delta))

    def update_words(self):
        tab = self.current
        if not tab:
            return
        content = tab.content()
        if len(content) > 3000000:
            self.st_words.setText("%d chars" % len(content))
            return
        words = len(content.split())
        self.st_words.setText("%d word%s, %d chars" % (words, "" if words == 1 else "s", len(content)))

    def flash(self, msg):
        self.st_msg.setText(msg)
        self.flash_timer.start(2600)

    # ---- files
    def _last_dir(self):
        if self.current and self.current.path:
            return os.path.dirname(self.current.path)
        if self.settings["recent"]:
            return os.path.dirname(self.settings["recent"][0])
        return os.path.expanduser("~")

    def add_recent(self, path):
        rec = [p for p in self.settings["recent"] if os.path.normcase(p) != os.path.normcase(path)]
        self.settings["recent"] = [path] + rec[:14]
        self.save_settings_soon()

    def update_session(self):
        self.settings["session"] = [t.path for t in self.tabs if t.path]
        self.save_settings_soon()

    def open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self.win, "Open", self._last_dir())
        for p in paths:
            self.open_path(p)

    def open_path(self, path, quiet=False, select=True):
        path = os.path.abspath(os.path.expanduser(path))
        for t in self.tabs:
            if t.path and os.path.normcase(t.path) == os.path.normcase(path):
                if select:
                    self.select_tab(t)
                return t
        if not os.path.exists(path):
            if quiet:
                return None
            tab = self._target_tab(path)
            if select:
                self.select_tab(tab)
            self.flash("New file (not saved yet)")
            return tab
        if os.path.isdir(path):
            if not quiet:
                self.error("That's a folder", path)
            return None
        try:
            size = os.path.getsize(path)
            if size > 50 * 1024 * 1024 and not quiet:
                if not self.ask("Big file", "%s is %.0f MB." % (os.path.basename(path), size / 1048576.0),
                                [("Open anyway", True, True), ("Cancel", None, False)]):
                    return None
            try:
                content, enc, bom, nl = read_text_file(path)
            except BinaryFileError:
                if quiet or not self.ask("Binary file?", "%s doesn't look like a text file." % os.path.basename(path),
                                         [("Open anyway", True, True), ("Cancel", None, False)],
                                         detail="Saving it from a text editor will probably break it."):
                    return None
                content, enc, bom, nl = read_text_file(path, force=True)
        except OSError as e:
            if not quiet:
                self.error("Couldn't open file", str(e))
                self.settings["recent"] = [p for p in self.settings["recent"] if p != path]
            return None
        tab = self._target_tab(path)
        tab.encoding, tab.bom = enc, bom
        tab.newline = nl or self.settings["default_newline"]
        tab.set_content(content)
        self.refresh_tab(tab)
        self.add_recent(path)
        if select:
            self.select_tab(tab)
        self.update_session()
        return tab

    def _target_tab(self, path):
        cur = self.current
        if cur is not None and cur.is_pristine():
            cur.path = path
            self.refresh_tab(cur)
            return cur
        return self.new_tab(path, select=False)

    def reload_current(self):
        tab = self.current
        if not tab or not tab.path or not os.path.exists(tab.path):
            QApplication.beep()
            return
        if tab.is_modified() and not self.ask("Reload?", "Throw away your changes and reload from disk?",
                                              [("Reload", True, True), ("Cancel", None, False)]):
            return
        try:
            content, enc, bom, nl = read_text_file(tab.path, force=True)
        except OSError as e:
            self.error("Couldn't reload", str(e))
            return
        pos = tab.editor.textCursor().position()
        tab.encoding, tab.bom, tab.newline = enc, bom, nl or tab.newline
        tab.set_content(content)
        c = tab.editor.textCursor()
        c.setPosition(min(pos, tab.editor.document().characterCount() - 1))
        tab.editor.setTextCursor(c)
        self.refresh_modified(tab)
        self.flash("Reloaded")

    def save_tab(self, tab, save_as=False):
        if tab is None:
            return False
        path = tab.path
        if save_as or not path:
            start = path or os.path.join(self._last_dir(), "untitled.txt")
            path, _ = QFileDialog.getSaveFileName(self.win, "Save as", start)
            if not path:
                return False
        content = tab.content()
        nl = {"LF": "\n", "CRLF": "\r\n", "CR": "\r"}.get(tab.newline, "\n")
        if nl != "\n":
            content = content.replace("\n", nl)
        try:
            data = encode_text(content, tab.encoding, tab.bom)
        except UnicodeEncodeError:
            if not self.ask("Encoding problem", "This text has characters that %s can't store." % tab.encoding,
                            [("Save as UTF-8", True, True), ("Cancel", None, False)]):
                return False
            tab.encoding, tab.bom = "UTF-8", False
            data = encode_text(content, "UTF-8", False)
        try:
            atomic_write(path, data)
        except OSError as e:
            self.error("Couldn't save", str(e))
            return False
        tab.path = os.path.abspath(path)
        tab.set_modified(False)
        self.refresh_tab(tab)
        self.add_recent(tab.path)
        self.update_session()
        self.update_title()
        self.update_status()
        self.flash("Saved ✓")
        return True

    def save_all(self):
        for tab in list(self.tabs):
            if (tab.is_modified() or not tab.path) and not tab.is_pristine():
                self.select_tab(tab)
                if not self.save_tab(tab):
                    return

    def copy_text(self, s):
        QApplication.clipboard().setText(s)
        self.flash("Copied")

    # ---- window state
    def restore_window(self):
        st = self.settings["window_state"]
        ok = False
        if st:
            try:
                from PySide6.QtCore import QByteArray
                ok = self.win.restoreGeometry(QByteArray.fromBase64(st.encode("ascii")))
            except Exception:
                ok = False
        if not ok:
            self.win.resize(1100, 720)
            scr = self.qapp.primaryScreen()
            if scr is not None:
                g = scr.availableGeometry()
                self.win.move(g.center() - self.win.rect().center())
        self.win.show()
        self.on_window_state()
        set_titlebar_hwnd(int(self.win.winId()), self.theme)

    def store_window(self):
        try:
            self.settings["window_state"] = bytes(self.win.saveGeometry().toBase64()).decode("ascii")
        except Exception:
            pass

    # ---- errors
    def _log(self, text):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write("\n[%s] SlopPad %s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), VERSION, text))
        except Exception:
            pass

    def on_exception(self, exc, val, tb):
        text = "".join(traceback.format_exception(exc, val, tb))
        sys.stderr.write(text)
        self._log(text)
        if self._showing_error:
            return
        self._showing_error = True
        try:
            from PySide6 import __version__ as pyside_version
            d = Dialog(self, "Something broke")
            d.setModal(True)
            msg = label("SlopPad hit an error. Screenshot this for the bug report:")
            msg.setStyleSheet("font-weight: bold;")
            d.body.addWidget(msg)
            box = QPlainTextEdit()
            box.setObjectName("errorbox")
            box.setReadOnly(True)
            box.setFont(self.editor_font)
            box.setMinimumSize(760, 260)
            box.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            box.setPlainText("SlopPad %s | Python %s | PySide6 %s | %s\n\n%s" % (
                VERSION, platform.python_version(), pyside_version, platform.platform(), text))
            d.body.addWidget(box)
            row = QHBoxLayout()
            row.addWidget(label("Also saved to " + LOG_PATH, "dim"))
            row.addStretch(1)
            row.addWidget(button("Copy error", lambda: self.copy_text(box.toPlainText())))
            row.addWidget(button("Close", d.accept, accent=True))
            d.body.addLayout(row)
            d.exec()
        except Exception:
            pass
        finally:
            self._showing_error = False

    # ---- quit
    def confirm_quit(self):
        for tab in list(self.tabs):
            if tab.is_modified():
                ans = self.ask_save(tab)
                if ans is None:
                    return False
                if ans == "save" and not self.save_tab(tab):
                    return False
        self.store_window()
        self.settings["session"] = [t.path for t in self.tabs if t.path]
        self.save_settings()
        for d in list(self.dialogs):
            d.close()
        return True

    def run(self):
        return self.qapp.exec()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    code = run_cli(argv)
    if code is not None:
        return code
    qapp = QApplication(sys.argv[:1])
    app = App(argv, qapp)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
