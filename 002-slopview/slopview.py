#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SlopView - a vibe-coded image viewer.
Part of slopware: https://github.com/Techrul/slopware

One file. Needs PySide6:
  CachyOS / Arch:  sudo pacman -S pyside6
  Everything else: pip install PySide6

Run it:   python slopview.py [image or folder]

Settings live in:
  Windows: %APPDATA%\\SlopView\\settings.json
  macOS:   ~/Library/Application Support/SlopView/settings.json
  Linux:   ~/.config/slopview/settings.json
  (override with the SLOPVIEW_CONFIG_DIR environment variable)
"""

import collections
import copy
import json
import math
import os
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zlib

APP_NAME = "SlopView"
APP_ID = "slopware.slopview"
VERSION = "0.4.0"
REPO_URL = "https://github.com/Techrul/slopware"

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = not IS_WIN and not IS_MAC


def _missing_qt():
    sys.stderr.write(
        "SlopView needs PySide6 (Qt for Python), which isn't installed for this Python.\n"
        "  CachyOS / Arch:  sudo pacman -S pyside6\n"
        "  Windows / macOS: pip install PySide6\n"
        "  Other Linux:     pip install --user PySide6  (or your distro's pyside6 package)\n")
    sys.exit(1)

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

def _config_dir():
    override = os.environ.get("SLOPVIEW_CONFIG_DIR")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if IS_WIN:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_NAME)
    if IS_MAC:
        return os.path.expanduser("~/Library/Application Support/" + APP_NAME)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "slopview")


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
    ("syn_keyword", "Code: keywords"),
    ("syn_string", "Code: strings"),
    ("syn_comment", "Code: comments"),
    ("syn_number", "Code: numbers"),
    ("syn_function", "Code: functions / keys"),
    ("syn_type", "Code: types / variables"),
    ("syn_constant", "Code: constants"),
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
    "syn_keyword": "#b39dff", "syn_string": "#9ece6a", "syn_comment": "#5f6670", "syn_number": "#ff9e64",
    "syn_function": "#7aa2f7", "syn_type": "#2ac3de", "syn_constant": "#ff757f",
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
        ui_dim="#5c8c88", current_match_bg="#0f8a80", match_bg="#08302d",
        syn_keyword="#4fd6e8", syn_string="#9ff0c4", syn_comment="#3f6b68", syn_number="#ffb86c",
        syn_function="#7fdbff", syn_type="#a5f3e8", syn_constant="#ff8fa3"),
    "OLED Mocha": _variant(
        fg="#cdd6f4", cursor="#f5e0dc", selection_bg="#313244",
        selection_fg="#cdd6f4", gutter_fg="#45475a", gutter_active="#b4befe",
        accent="#cba6f7", ui_fg="#bac2de", ui_dim="#6c7086",
        match_bg="#3b2f3f", current_match_bg="#f9e2af", tab_active_fg="#cdd6f4",
        syn_keyword="#cba6f7", syn_string="#a6e3a1", syn_comment="#6c7086", syn_number="#fab387",
        syn_function="#89b4fa", syn_type="#f9e2af", syn_constant="#f38ba8"),
    "OLED Matrix": _variant(
        fg="#33ff66", cursor="#00ff41", selection_bg="#003b12",
        selection_fg="#b6ffc8", gutter_fg="#0f4d1f", gutter_active="#33ff66",
        accent="#00ff41", ui_fg="#7dff9b", ui_dim="#2f7a44",
        match_bg="#0d3a00", current_match_bg="#2a8a00", tab_active_fg="#00ff41",
        syn_keyword="#b6ff3d", syn_string="#9effc1", syn_comment="#1f6b35", syn_number="#e6ff6b",
        syn_function="#00ffaa", syn_type="#5dfc8d", syn_constant="#ffffff"),
    "OLED Crimson": _variant(
        cursor="#ff5470", selection_bg="#4a0b16", gutter_active="#ff8095",
        accent="#ff3355", current_match_bg="#a3122b", match_bg="#33060e",
        syn_keyword="#ff5470", syn_string="#ffb3c1", syn_comment="#5f5f5f", syn_number="#ff9e64",
        syn_function="#ff8fab", syn_type="#e6a8ff", syn_constant="#ffd166"),
    "OLED Amber": _variant(
        fg="#ffb000", cursor="#ffcc33", selection_bg="#4d3500",
        selection_fg="#ffe08a", gutter_fg="#5c4000", gutter_active="#ffb000",
        accent="#ffb000", ui_fg="#ffc23d", ui_dim="#8a6000",
        match_bg="#3d2c00", current_match_bg="#7a5500", tab_active_fg="#ffcc33",
        syn_keyword="#ffd966", syn_string="#ffe9a8", syn_comment="#6b4c00", syn_number="#ff8c00",
        syn_function="#ffc94d", syn_type="#ffcf7a", syn_constant="#ff6a00"),
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
        "syn_keyword": "#7c3aed", "syn_string": "#15803d", "syn_comment": "#9a9a90", "syn_number": "#c2410c",
        "syn_function": "#1d4ed8", "syn_type": "#0e7490", "syn_constant": "#b91c1c",
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


# Catppuccin (https://catppuccin.com) - official palette, mapped the way their style guide suggests
_CATPPUCCIN = {
    "Mocha": "1e1e2e 181825 11111b 313244 45475a 585b70 6c7086 7f849c 9399b2 cdd6f4 bac2de "
             "f5e0dc b4befe cba6f7 f38ba8 fab387 f9e2af a6e3a1 94e2d5 89b4fa",
    "Macchiato": "24273a 1e2030 181926 363a4f 494d64 5b6078 6e738d 8087a2 939ab7 cad3f5 b8c0e0 "
                 "f4dbd6 b7bdf8 c6a0f6 ed8796 f5a97f eed49f a6da95 8bd5ca 8aadf4",
    "Frappé": "303446 292c3c 232634 414559 51576d 626880 737994 838ba7 949cbb c6d0f5 b5bfe2 "
              "f2d5cf babbf1 ca9ee6 e78284 ef9f76 e5c890 a6d189 81c8be 8caaee",
    "Latte": "eff1f5 e6e9ef dce0e8 ccd0da bcc0cc acb0be 9ca0b0 8c8fa1 7c7f93 4c4f69 5c5f77 "
             "dc8a78 7287fd 8839ef d20f39 fe640b df8e1d 40a02b 179299 1e66f5",
}
_CTP_NAMES = ("base mantle crust surface0 surface1 surface2 overlay0 overlay1 overlay2 text subtext1 "
              "rosewater lavender mauve red peach yellow green teal blue").split()


def _catppuccin_theme(flavor):
    c = dict(zip(_CTP_NAMES, ("#" + h for h in _CATPPUCCIN[flavor].split())))
    light = flavor == "Latte"
    return {
        "bg": c["base"], "fg": c["text"], "cursor": c["rosewater"],
        "selection_bg": blend(c["base"], c["overlay2"], 0.30), "selection_fg": c["text"],
        "current_line": blend(c["base"], c["surface0"], 0.55),
        "gutter_bg": c["base"], "gutter_fg": c["overlay0"], "gutter_active": c["lavender"],
        "match_bg": blend(c["base"], c["yellow"], 0.28), "current_match_bg": c["peach"],
        "ui_bg": c["mantle"], "ui_fg": c["subtext1"], "ui_dim": c["overlay1"], "ui_hover": c["surface0"],
        "input_bg": c["base"] if light else c["crust"], "accent": c["mauve"], "border": c["crust"],
        "tab_active_bg": c["base"], "tab_active_fg": c["text"],
        "scrollbar": c["surface1"], "scrollbar_hover": c["surface2"],
        "syn_keyword": c["mauve"], "syn_string": c["green"], "syn_comment": c["overlay2"],
        "syn_number": c["peach"], "syn_function": c["blue"], "syn_type": c["yellow"], "syn_constant": c["red"],
    }


for _flavor in ("Mocha", "Macchiato", "Frappé", "Latte"):
    BUILTIN_THEMES["Catppuccin " + _flavor] = _catppuccin_theme(_flavor)


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "theme": DEFAULT_THEME,
    "custom_themes": {},
    "canvas_opacity": 100,
    "native_titlebar": False,
    "topmost": False,
    "checkerboard": True,
    "fit_mode": "fit",
    "wheel_action": "zoom",
    "zoom_speed": "normal",
    "smooth_scaling": True,
    "pixelated_zoom": True,
    "animate": True,
    "sort_by": "name",
    "sort_desc": False,
    "loop_folder": True,
    "show_filmstrip": True,
    "thumb_size": 72,
    "show_info": False,
    "status_bar": True,
    "slideshow_seconds": 4,
    "slideshow_shuffle": False,
    "confirm_delete": True,
    "draw_tool": "ellipse",
    "draw_color": "#ff3b30",
    "draw_size": 4,
    "reopen_last": True,
    "last_path": "",
    "ui_font_size": 10,
    "recent": [],
    "window_state": "",
    "check_updates": False,
    "last_update_check": 0.0,
}

NUMERIC_LIMITS = {
    "canvas_opacity": (0, 100), "thumb_size": (40, 200), "slideshow_seconds": (1, 120), "ui_font_size": (7, 24), "draw_size": (1, 40),
}


def _compatible(default, value):
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, type(default))


FIT_VALUES = ("fit", "fit_all", "original")
WHEEL_VALUES = ("zoom", "navigate")
ZOOM_VALUES = ("slow", "normal", "fast")
DRAW_TOOL_VALUES = ("pen", "highlighter", "line", "arrow", "rect", "ellipse", "text", "counter", "pixelate")
SORT_VALUES = ("name", "date", "size", "type")


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
        for key, allowed in (("fit_mode", FIT_VALUES), ("wheel_action", WHEEL_VALUES), ("sort_by", SORT_VALUES),
                             ("zoom_speed", ZOOM_VALUES), ("draw_tool", DRAW_TOOL_VALUES)):
            if d[key] not in allowed:
                d[key] = DEFAULT_SETTINGS[key]
        d["draw_color"] = norm_hex(d["draw_color"]) or DEFAULT_SETTINGS["draw_color"]
        if not isinstance(d["custom_themes"], dict):
            d["custom_themes"] = {}
        d["recent"] = [p for p in d["recent"] if isinstance(p, str)][:15]

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

def atomic_write(path, data):
    path = os.path.realpath(path)
    folder = os.path.dirname(path) or "."
    mode = None
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        pass
    try:
        fd, tmp = tempfile.mkstemp(prefix=".slopview-", suffix=".tmp", dir=folder)
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

# --------------------------------------------------------------------------
# Install / uninstall / updates (all of this works without Qt installed)
# --------------------------------------------------------------------------

SCRIPT_PATH = os.path.realpath(__file__)
UPDATE_URL = (os.environ.get("SLOPVIEW_UPDATE_URL")
              or "https://raw.githubusercontent.com/Techrul/slopware/main/002-slopview/slopview.py")
# raw.githubusercontent.com caches files for up to 5 minutes, so right after a push it can still hand
# out the old version. GitHub's API is always fresh, so ask it first and fall back to a cache-busted
# raw link (the API allows 60 requests an hour per IP, which is plenty for this).
UPDATE_API_URL = "https://api.github.com/repos/Techrul/slopware/contents/002-slopview/slopview.py?ref=main"
WIN_PROGID = "SlopView.Image"
OPEN_WITH_EXTS = (".jpg", ".jpeg", ".jfif", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff",
                  ".svg", ".ico", ".tga")
CONFIG_FILES = ("settings.json", "settings.json.tmp", "settings.json.broken", "errors.log", "slopview.ico",
                "update-backup.py", "update-backup.json")
BACKUP_PATH = os.path.join(CONFIG_DIR, "update-backup.py")
SESSION_DIR = os.path.join(CONFIG_DIR, "session")
SESSION_FILE = os.path.join(SESSION_DIR, "session.json")
BACKUP_INFO = os.path.join(CONFIG_DIR, "update-backup.json")

ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect x="2" y="2" width="60" height="60" rx="12" fill="#000" stroke="#8b6cff" stroke-width="4"/>
<circle cx="44" cy="21" r="6" fill="#8b6cff"/>
<polygon points="10,50 26,27 41,50" fill="#c9bcff"/>
<polygon points="29,50 43,33 56,50" fill="#a796f0"/>
</svg>
"""


# ---- icon as .ico (drawn pixel by pixel, no image libraries needed)

def _in_rrect(px, py, x, y, w, h, r):
    if px < x or py < y or px > x + w or py > y + h:
        return False
    cx = min(max(px, x + r), x + w - r)
    cy = min(max(py, y + r), y + h - r)
    return (px - cx) ** 2 + (py - cy) ** 2 <= r * r


_ICON_ACC, _ICON_LIGHT, _ICON_BLACK = (0x8b, 0x6c, 0xff), (0xc9, 0xbc, 0xff), (0, 0, 0)


def _in_tri(px, py, a, b, c):
    def s(p, q, r):
        return (p[0] - r[0]) * (q[1] - r[1]) - (q[0] - r[0]) * (p[1] - r[1])
    d1, d2, d3 = s((px, py), a, b), s((px, py), b, c), s((px, py), c, a)
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (neg and pos)


_ICON_LIGHT2 = (0xa7, 0x96, 0xf0)


def _icon_color(u, v):
    if (u - 44) ** 2 + (v - 21) ** 2 <= 36:
        return _ICON_ACC
    if _in_tri(u, v, (29, 50), (43, 33), (56, 50)):
        return _ICON_LIGHT2
    if _in_tri(u, v, (10, 50), (26, 27), (41, 50)):
        return _ICON_LIGHT
    if _in_rrect(u, v, 4, 4, 56, 56, 10):
        return _ICON_BLACK
    if _in_rrect(u, v, 0, 0, 64, 64, 14):
        return _ICON_ACC
    return None


def render_icon_png(size):
    scale = 64.0 / size
    samples = ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75))
    raw = bytearray()
    for py in range(size):
        raw.append(0)  # PNG filter: none
        for px in range(size):
            r = g = b = n = 0
            for ox, oy in samples:
                c = _icon_color((px + ox) * scale, (py + oy) * scale)
                if c:
                    r, g, b, n = r + c[0], g + c[1], b + c[2], n + 1
            if n:
                raw += bytes((r // n, g // n, b // n, 255 * n // 4))
            else:
                raw += b"\0\0\0\0"

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def make_ico_bytes(sizes=(16, 24, 32, 48, 64, 256)):
    pngs = [(s, render_icon_png(s)) for s in sizes]
    out = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    data = b""
    for s, png in pngs:
        dim = 0 if s >= 256 else s
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    return out + data


# ---- shared helpers

def _git_checkout_dir():
    d = os.path.dirname(SCRIPT_PATH)
    for _ in range(5):
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def _run_quiet(cmd, **kw):
    try:
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, **kw)
    except (OSError, subprocess.SubprocessError):
        return None


def _remove(path, out):
    try:
        os.remove(path)
        out.append("Removed " + path)
        return True
    except FileNotFoundError:
        return False
    except OSError as e:
        out.append("Couldn't remove %s (%s)" % (path, e))
        return False


# ---- Linux

def _linux_paths():
    data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return (os.path.join(data, "applications", "slopview.desktop"),
            os.path.join(data, "icons", "hicolor", "scalable", "apps", "slopview.svg"),
            os.path.join(data, "applications"))


LINUX_ICON_SIZES = (32, 48, 64, 128, 256)


def _linux_pngs():
    data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return [os.path.join(data, "icons", "hicolor", "%dx%d" % (n, n), "apps", "slopview.png") for n in LINUX_ICON_SIZES]


def _linux_refresh(apps_dir):
    data = os.path.dirname(apps_dir)
    hicolor = os.path.join(data, "icons", "hicolor")
    try:
        os.utime(hicolor)  # icon caches notice changes by the folder's timestamp
    except OSError:
        pass
    cmds = [["update-desktop-database", apps_dir], ["kbuildsycoca6"], ["kbuildsycoca5"]]
    if os.path.isfile(os.path.join(hicolor, "icon-theme.cache")):  # a stale cache would hide our icon
        cmds.insert(0, ["gtk-update-icon-cache", "-f", "-t", hicolor])
    for cmd in cmds:
        _run_quiet(cmd)


def _linux_install(out):
    desktop, icon, apps_dir = _linux_paths()
    os.makedirs(os.path.dirname(desktop), exist_ok=True)
    os.makedirs(os.path.dirname(icon), exist_ok=True)
    with open(icon, "w", encoding="utf-8") as f:
        f.write(ICON_SVG)
    pngs = _linux_pngs()
    for n, png in zip(LINUX_ICON_SIZES, pngs):
        os.makedirs(os.path.dirname(png), exist_ok=True)
        with open(png, "wb") as f:
            f.write(render_icon_png(n))
    with open(desktop, "w", encoding="utf-8") as f:
        f.write(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=SlopView\n"
            "GenericName=Image Viewer\n"
            "Comment=A vibe-coded image viewer (slopware)\n"
            'Exec="%s" "%s" %%F\n'
            "Icon=%s\n"
            "Terminal=false\n"
            "Categories=Graphics;Viewer;\n"
            "MimeType=image/jpeg;image/png;image/gif;image/webp;image/bmp;image/tiff;image/svg+xml;image/x-icon;image/x-tga;\n"
            "StartupWMClass=slopview\n" % (sys.executable, SCRIPT_PATH, pngs[-1]))
    try:
        os.chmod(SCRIPT_PATH, os.stat(SCRIPT_PATH).st_mode | 0o111)
    except OSError:
        pass
    _linux_refresh(apps_dir)
    out.append("SlopView is now in your app launcher (it may take a moment to show up).")
    out.append("Right-click any image -> Open With -> SlopView.")
    out.append("Launcher: " + desktop)
    return True


def _linux_clean_mimeapps(out):
    cfg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    for path in (os.path.join(cfg, "mimeapps.list"), os.path.join(data, "applications", "mimeapps.list")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            continue
        new, changed = [], False
        for line in lines:
            if "=" in line and not line.lstrip().startswith(("[", "#")):
                key, val = line.split("=", 1)
                items = [i for i in val.strip().split(";") if i]
                kept = [i for i in items if i != "slopview.desktop"]
                if len(kept) != len(items):
                    changed = True
                    if kept:
                        new.append("%s=%s;\n" % (key, ";".join(kept)))
                    continue
            new.append(line)
        if changed:
            atomic_write(path, "".join(new).encode("utf-8"))
            out.append("Removed SlopView from default apps in " + path)


def _linux_uninstall(out):
    desktop, icon, apps_dir = _linux_paths()
    _remove(desktop, out)
    _remove(icon, out)
    for png in _linux_pngs():
        _remove(png, out)
    _linux_clean_mimeapps(out)
    _linux_refresh(apps_dir)


# ---- Windows

def _win_paths():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    lnk = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "SlopView.lnk")
    return lnk, os.path.join(CONFIG_DIR, "slopview.ico")


def _pythonw():
    cand = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return cand if os.path.isfile(cand) else sys.executable


def _win_notify():
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED
    except Exception:
        pass


def _win_install(out):
    import winreg
    lnk, ico = _win_paths()
    os.makedirs(os.path.dirname(ico), exist_ok=True)
    with open(ico, "wb") as f:
        f.write(make_ico_bytes())
    pyw = _pythonw()
    ok = True

    # Start Menu shortcut (paths go through env vars so no quoting can break the command)
    os.makedirs(os.path.dirname(lnk), exist_ok=True)
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:SP_LNK);"
          "$s.TargetPath=$env:SP_TARGET;$s.Arguments=$env:SP_ARGS;$s.IconLocation=$env:SP_ICON;"
          "$s.WorkingDirectory=$env:SP_DIR;$s.Description='SlopView text editor';$s.Save()")
    env = dict(os.environ, SP_LNK=lnk, SP_TARGET=pyw, SP_ARGS='"%s"' % SCRIPT_PATH,
               SP_ICON=ico + ",0", SP_DIR=os.path.dirname(SCRIPT_PATH))
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-Command", ps], env=env, capture_output=True, text=True, timeout=60,
                           creationflags=0x08000000)  # CREATE_NO_WINDOW
        err = (r.stderr or "").strip()
    except (OSError, subprocess.SubprocessError) as e:
        err = str(e)
    if os.path.exists(lnk):
        out.append("Added SlopView to the Start Menu.")
    else:
        ok = False
        out.append("Couldn't create the Start Menu shortcut: " + (err or "unknown error"))

    # "Open with" entries (current user only, no admin needed)
    cmd = '"%s" "%s" "%%1"' % (pyw, SCRIPT_PATH)
    base = "Software\\Classes\\" + WIN_PROGID
    HK = winreg.HKEY_CURRENT_USER

    def setv(path, name, value):
        with winreg.CreateKey(HK, path) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)

    setv(base, "", "SlopView image")
    setv(base, "FriendlyTypeName", "SlopView image")
    setv(base + "\\DefaultIcon", "", ico + ",0")
    setv(base + "\\Application", "ApplicationName", "SlopView")
    setv(base + "\\Application", "ApplicationIcon", ico + ",0")
    setv(base + "\\shell\\open", "FriendlyAppName", "SlopView")
    setv(base + "\\shell\\open", "Icon", ico + ",0")
    setv(base + "\\shell\\open\\command", "", cmd)
    for ext in OPEN_WITH_EXTS:
        with winreg.CreateKey(HK, "Software\\Classes\\%s\\OpenWithProgids" % ext) as k:
            winreg.SetValueEx(k, WIN_PROGID, 0, winreg.REG_NONE, b"")
    _win_notify()
    out.append("SlopView now shows up in \"Open with\" for %d image types (.jpg, .png, .gif, ...)."
               % len(OPEN_WITH_EXTS))
    return ok


def _win_delete_tree(winreg, root, path):
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _win_delete_tree(winreg, root, path + "\\" + sub)
        winreg.DeleteKey(root, path)
        return True
    except FileNotFoundError:
        return False


def _win_key_empty(winreg, root, path):
    try:
        with winreg.OpenKey(root, path) as k:
            n_sub, n_val, _ = winreg.QueryInfoKey(k)
            return n_sub == 0 and n_val == 0
    except FileNotFoundError:
        return False


def _win_uninstall(out):
    import winreg
    HK = winreg.HKEY_CURRENT_USER
    lnk, ico = _win_paths()
    _remove(lnk, out)
    _remove(ico, out)
    if _win_delete_tree(winreg, HK, "Software\\Classes\\" + WIN_PROGID):
        out.append("Removed SlopView's file type from the registry.")
    removed = 0
    for ext in OPEN_WITH_EXTS:
        sub = "Software\\Classes\\%s\\OpenWithProgids" % ext
        try:
            with winreg.OpenKey(HK, sub, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, WIN_PROGID)
                removed += 1
        except FileNotFoundError:
            continue
        for path in (sub, "Software\\Classes\\" + ext):  # tidy up keys only if we left them empty
            if _win_key_empty(winreg, HK, path):
                try:
                    winreg.DeleteKey(HK, path)
                except OSError:
                    pass
    for ext in OPEN_WITH_EXTS:  # Explorer's own per-user copy of the list
        sub = "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\FileExts\\%s\\OpenWithProgids" % ext
        try:
            with winreg.OpenKey(HK, sub, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, WIN_PROGID)
        except OSError:
            pass
    if removed:
        out.append("Removed SlopView from \"Open with\" for %d file types." % removed)
    _win_notify()


# ---- public install / uninstall

def is_installed():
    if IS_LINUX:
        return os.path.exists(_linux_paths()[0])
    if IS_WIN:
        return os.path.exists(_win_paths()[0])
    return False


def install_supported():
    return IS_LINUX or IS_WIN


def install(out):
    """Add SlopView to the app menu / Start Menu and to "Open with". Returns True on success."""
    try:
        if IS_LINUX:
            return _linux_install(out)
        if IS_WIN:
            return _win_install(out)
    except Exception as e:
        out.append("Install failed: %s" % e)
        return False
    out.append("Nothing to install on macOS - just run slopview.py.")
    return False


def uninstall(out, remove_settings=False, remove_program=False):
    """Undo install(). Optionally also delete settings/themes/logs and the program file itself."""
    try:
        if IS_LINUX:
            _linux_uninstall(out)
        elif IS_WIN:
            _win_uninstall(out)
    except Exception as e:
        out.append("Couldn't fully remove the launcher: %s" % e)
    if remove_settings:
        if os.path.isdir(SESSION_DIR):
            shutil.rmtree(SESSION_DIR, ignore_errors=True)
            out.append("Removed remembered tabs in " + SESSION_DIR)
        for name in CONFIG_FILES:
            _remove(os.path.join(CONFIG_DIR, name), out)
        try:
            os.rmdir(CONFIG_DIR)
            out.append("Removed " + CONFIG_DIR)
        except OSError:
            pass
    if remove_program:
        git = _git_checkout_dir()
        if git:
            out.append("Kept slopview.py because it's inside a git repo (%s). Delete it with git if you want." % git)
        else:
            _remove(SCRIPT_PATH + ".bak", out)
            _remove(SCRIPT_PATH, out)
    if not out:
        out.append("Nothing to remove - SlopView wasn't installed.")


# ---- updates

def _parse_version(text):
    m = re.search(r'^VERSION = "(\d+(?:\.\d+)*)"', text, re.M)
    return m.group(1) if m else None


def _vtuple(v):
    return tuple(int(x) for x in v.split("."))


def check_update(timeout=10):
    """Returns {"status": "newer" | "current" | "error", "latest": str, "text": str, "error": str}."""
    import urllib.error
    import urllib.request
    if os.environ.get("SLOPVIEW_UPDATE_URL"):
        sources = [(UPDATE_URL, {})]
    else:
        sources = [(UPDATE_API_URL, {"Accept": "application/vnd.github.raw"}),
                   (UPDATE_URL + "?nocache=%d" % int(time.time()), {})]
    try:
        text, last_error = None, None
        for url, extra in sources:
            headers = {"User-Agent": "SlopView/" + VERSION, "Cache-Control": "no-cache"}
            headers.update(extra)
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
                    text = r.read(5 * 1024 * 1024).decode("utf-8")
                if _parse_version(text):
                    break
            except (urllib.error.URLError, UnicodeDecodeError) as e:
                last_error = e
            text = None
        if text is None:
            raise last_error or ValueError("No update source answered.")
        latest = _parse_version(text)
        if not latest:
            return {"status": "error", "error": "The file on GitHub has no version number in it."}
        status = "newer" if _vtuple(latest) > _vtuple(VERSION) else "current"
        return {"status": status, "latest": latest, "text": text}
    except urllib.error.HTTPError as e:
        return {"status": "error", "error": "GitHub answered with error %d." % e.code}
    except urllib.error.URLError as e:
        return {"status": "error", "error": "Couldn't reach GitHub (%s). Are you online?" % e.reason}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def apply_update(text, force=False):
    """Replace this file with the downloaded one. Keeps a backup as slopview.py.bak."""
    if not re.search(r'^APP_NAME = "SlopView"', text, re.M):
        raise ValueError("The downloaded file doesn't look like SlopView, so nothing was changed.")
    if getattr(sys, "frozen", False):
        raise ValueError("This SlopView is a bundled app, so it can't update itself. Download the new "
                         "slopview.py from GitHub instead.")
    compile(text, "slopview.py", "exec")  # refuse to install something that won't even parse
    git = _git_checkout_dir()
    if git and not force:
        raise RuntimeError("This copy of SlopView is inside a git repo (%s). Use \"git pull\" instead, "
                           "so git doesn't get confused." % git)
    # The backup lives in the settings folder (not next to slopview.py) and is deleted automatically
    # once the new version has started up fine. See cleanup_after_update().
    backup = BACKUP_PATH
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        shutil.copy2(SCRIPT_PATH, backup)
        with open(BACKUP_INFO, "w", encoding="utf-8") as f:
            json.dump({"from": VERSION, "to": _parse_version(text), "script": SCRIPT_PATH,
                       "time": time.time()}, f)
        atomic_write(SCRIPT_PATH, text.encode("utf-8"))
    except PermissionError:
        raise ValueError("SlopView isn't allowed to change files in %s. Move %s to a folder you own "
                         "(like Documents) and try again." % (os.path.dirname(SCRIPT_PATH),
                                                             os.path.basename(SCRIPT_PATH)))
    return backup


def cleanup_after_update():
    """Run once SlopView has started fine. Deletes the update backup (and old-style .bak files).
    Returns the version we updated from, if this was the first start after an update."""
    updated_from = None
    try:
        with open(BACKUP_INFO, "r", encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError):
        info = None
    if isinstance(info, dict) and info.get("to") == VERSION:
        updated_from = info.get("from")
        for p in (BACKUP_PATH, BACKUP_INFO):
            try:
                os.remove(p)
            except OSError:
                pass
    legacy = SCRIPT_PATH + ".bak"  # v0.3.0/0.3.1 kept the backup next to the script
    try:
        with open(legacy, "r", encoding="utf-8", errors="replace") as f:
            head = f.read(4096)
        if 'APP_NAME = "SlopView"' in head:
            os.remove(legacy)
    except OSError:
        pass
    return updated_from


# ---- command line

def _ask_yes(question):
    if not sys.stdin or not sys.stdin.isatty():
        return False
    try:
        return input(question + " [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def run_cli(argv):
    """Commands that don't need Qt. Returns an exit code, or None to start the editor."""
    if not argv:
        return None
    a = argv[0]
    if a in ("-h", "--help"):
        print("usage: slopview.py [image or folder]\n\n"
              "  --install         add SlopView to your app menu / Start Menu and to \"Open with\"\n"
              "  --uninstall       remove that again (asks about settings and the program file)\n"
              "  --uninstall --all remove everything: launcher, settings, custom themes, and slopview.py\n"
              "  --check-update    see if there's a newer version on GitHub\n"
              "  --update          download and install the newer version\n"
              "  --version         print the version\n\n"
              "A vibe-coded image viewer. Part of slopware: " + REPO_URL)
        return 0
    if a in ("-V", "--version"):
        print("%s %s" % (APP_NAME, VERSION))
        return 0
    if a == "--install":
        out = []
        ok = install(out)
        print("\n".join(out))
        if ok:
            print("If you move slopview.py later, run --install again.")
        return 0 if ok else 1
    if a == "--uninstall":
        everything = "--all" in argv[1:]
        rs = everything or _ask_yes("Also delete your settings, custom themes and error log?")
        rp = everything or _ask_yes("Also delete the program file itself (%s)?" % SCRIPT_PATH)
        out = []
        uninstall(out, remove_settings=rs, remove_program=rp)
        print("\n".join(out))
        return 0
    if a in ("--check-update", "--update"):
        print("Checking GitHub for updates...")
        res = check_update()
        if res["status"] == "error":
            print("Update check failed: " + res["error"])
            return 1
        if res["status"] == "current":
            print("You're up to date (%s %s)." % (APP_NAME, VERSION))
            return 0
        print("Version %s is available (you have %s)." % (res["latest"], VERSION))
        if a == "--check-update":
            print("Run with --update to install it.")
            return 0
        try:
            backup = apply_update(res["text"], force="--force" in argv[1:])
        except Exception as e:
            print("Update failed: %s" % e)
            if "git" in str(e):
                print("(Add --force to update anyway.)")
            return 1
        print("Updated to %s! Your old version is backed up at %s\n"
              "That backup is deleted automatically once the new version starts up fine." % (res["latest"], backup))
        return 0
    return None

if __name__ == "__main__":
    _code = run_cli(sys.argv[1:])
    if _code is not None:
        sys.exit(_code)

try:
    from PySide6.QtCore import (QEvent, QFileSystemWatcher, QObject, QPoint, QPointF, QRectF, QSize, Qt,
                                QTimer, QUrl, Signal)
    from PySide6.QtGui import (QAction, QActionGroup, QBrush, QColor, QConicalGradient, QDesktopServices, QFont, QFontDatabase, QFontMetricsF,
                               QIcon,
                               QImage, QImageReader, QImageWriter, QIntValidator, QKeySequence, QMovie, QPainter, QPainterPath,
                               QPen, QPixmap, QShortcut, QTransform)
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QApplication, QColorDialog, QDialog, QFileDialog, QFrame,
                                   QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
                                   QMenuBar, QPlainTextEdit, QPushButton, QSizePolicy, QSlider, QStyle,
                                   QStyledItemDelegate, QToolButton, QTreeWidget, QTreeWidgetItem,
                                   QVBoxLayout, QWidget)
    from PySide6.QtCore import QFile
except ImportError:
    if __name__ == "__main__":
        _missing_qt()
    raise


# --------------------------------------------------------------------------
# Qt helpers
# --------------------------------------------------------------------------


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
    p.setPen(QPen(acc, 4))
    p.setBrush(QColor("#000000"))
    p.drawRoundedRect(QRectF(2, 2, 60, 60), 12, 12)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(acc)
    p.drawEllipse(QPointF(44, 21), 6, 6)
    p.setBrush(QColor(blend(theme["accent"], "#ffffff", 0.55)))
    p.drawPolygon([QPointF(10, 50), QPointF(26, 27), QPointF(41, 50)])
    p.setBrush(QColor(blend(theme["accent"], "#ffffff", 0.35)))
    p.drawPolygon([QPointF(29, 50), QPointF(43, 33), QPointF(56, 50)])
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


class IconButton(QAbstractButton):
    """Small button whose icon is drawn with lines, so it looks identical on every OS and font."""

    def __init__(self, app, kind, slot=None, tip=None, width=46, height=None):
        super().__init__()
        self.app, self.kind, self.hover = app, kind, False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if width:
            self.setFixedWidth(width)
        if height:
            self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding if not height
                           else QSizePolicy.Policy.Fixed)
        if tip:
            self.setToolTip(tip)
        if slot:
            self.clicked.connect(lambda *_: slot())

    def sizeHint(self):
        return QSize(self.width() or 46, 32)

    def set_kind(self, kind, tip=None):
        self.kind = kind
        if tip:
            self.setToolTip(tip)
        self.update()

    def enterEvent(self, e):
        self.hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.hover = False
        self.update()
        super().leaveEvent(e)

    def icon_color(self):
        return QColor(self.app.theme["ui_fg"])

    def paint_background(self, p):
        if self.hover or self.isDown():
            danger = self.kind == "close"
            p.fillRect(self.rect(), QColor("#e81123" if danger else self.app.theme["ui_hover"]))

    def paintEvent(self, _e):
        p = QPainter(self)
        self.paint_background(p)
        color = self.icon_color()
        if self.kind == "close" and (self.hover or self.isDown()):
            color = QColor("#ffffff")
        cx = int(self.width() / 2)
        cy = int(self.height() / 2)
        s = 5
        pen = QPen(color, 1)
        pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        k = self.kind
        if k == "min":
            p.drawLine(cx - s, cy, cx + s, cy)
        elif k == "max":
            p.drawRect(cx - s, cy - s, 2 * s, 2 * s)
        elif k == "restore":
            p.drawRect(cx - s, cy - s + 2, 2 * s - 2, 2 * s - 2)
            p.drawLine(cx - s + 2, cy - s, cx + s, cy - s)
            p.drawLine(cx + s, cy - s, cx + s, cy + s - 2)
        elif k == "plus":
            p.drawLine(cx - s, cy, cx + s, cy)
            p.drawLine(cx, cy - s, cx, cy + s)
        else:  # close / x
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(color, 1.15))
            s2 = 4.0 if k == "x" else 5.0
            p.drawLine(QPointF(cx - s2, cy - s2), QPointF(cx + s2 + 0.5, cy + s2 + 0.5))
            p.drawLine(QPointF(cx - s2, cy + s2 + 0.5), QPointF(cx + s2 + 0.5, cy - s2))
        p.end()


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
        # The title floats on top, centred on the whole window (not just the gap between menus and buttons)
        self.title = label("", "title")
        self.title.setParent(self)
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_text = ""
        self.btn_min = IconButton(app, "min", lambda: app.win.showMinimized(), "Minimize")
        self.btn_max = IconButton(app, "max", app.toggle_maximize, "Maximize")
        self.btn_close = IconButton(app, "close", app.win.close, "Close")
        for b in (self.btn_min, self.btn_max, self.btn_close):
            lay.addWidget(b)

    def set_title(self, text):
        self._title_text = text
        self.place_title()

    def place_title(self):
        fm = self.title.fontMetrics()
        left = self.menubar.geometry().right() + 16
        right = (self.btn_min.geometry().left() if self.btn_min.isVisible() else self.width()) - 16
        avail = max(0, right - left)
        text = fm.elidedText(self._title_text, Qt.TextElideMode.ElideMiddle, avail)
        w = min(avail, fm.horizontalAdvance(text) + 6)
        x = (self.width() - w) // 2
        x = max(left, min(x, right - w))
        self.title.setText(text)
        self.title.setGeometry(x, 0, w, self.height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.place_title()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self.place_title)

    def set_frameless(self, frameless):
        for w in (self.btn_min, self.btn_max, self.btn_close, self.title):
            w.setVisible(frameless)
        QTimer.singleShot(0, self.place_title)

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
        if self.app._quitting or self.app.confirm_quit():
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
        half = (len(VIEW_THEME_KEYS) + 1) // 2
        for i, (key, text) in enumerate(VIEW_THEME_KEYS):
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
        c = QColorDialog.getColor(QColor(self.work[key]), self, dict(VIEW_THEME_KEYS)[key])
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
        raise ValueError("No SlopView colors found in that file.")
    name = data.get("name") if isinstance(data.get("name"), str) else None
    name = (name or os.path.splitext(os.path.basename(path))[0]).strip() or "Imported theme"
    return name, complete_theme(colors)


# --------------------------------------------------------------------------
# Image helpers
# --------------------------------------------------------------------------

VIEW_THEME_KEYS = [
    ("bg", "Canvas background"),
    ("ui_bg", "Interface background"),
    ("ui_fg", "Interface text"),
    ("ui_dim", "Interface dim text"),
    ("ui_hover", "Hover"),
    ("input_bg", "Inputs and buttons"),
    ("fg", "Input text"),
    ("accent", "Accent"),
    ("border", "Borders"),
    ("selection_bg", "Menu highlight"),
    ("selection_fg", "Menu highlight text"),
    ("scrollbar", "Scrollbar"),
    ("scrollbar_hover", "Scrollbar (hover)"),
    ("tab_active_bg", "Selected thumbnail"),
]

FIT_MODES = [("fit", "Shrink big images to fit"), ("fit_all", "Fit everything (also enlarge small)"),
             ("original", "Always show at 100%")]
WHEEL_MODES = [("zoom", "Zoom"), ("navigate", "Next / previous image")]
ZOOM_SPEEDS = [("slow", "Slow"), ("normal", "Normal"), ("fast", "Fast")]
ZOOM_FACTORS = {"slow": 1.12, "normal": 1.25, "fast": 1.45}  # zoom per mouse wheel notch
SORT_MODES = [("name", "Name"), ("date", "Date modified"), ("size", "File size"), ("type", "File type")]


def natural_key(name):
    return [(0, int(x)) if x.isdigit() else (1, x.lower()) for x in re.split(r"(\d+)", name)]


def human_size(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "bytes" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return "%d" % n


_EXIF_TAGS = {0x010F: "Make", 0x0110: "Model", 0x0131: "Software", 0x0132: "DateTime",
              0x9003: "DateTimeOriginal", 0x829A: "ExposureTime", 0x829D: "FNumber", 0x8827: "ISO",
              0x920A: "FocalLength", 0xA434: "LensModel"}


def read_exif(path, limit=512 * 1024):
    """Tiny JPEG EXIF reader for the info panel (camera, lens, exposure). Never reads GPS."""
    try:
        with open(path, "rb") as f:
            data = f.read(limit)
    except OSError:
        return {}
    if not data.startswith(b"\xff\xd8"):
        return {}
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        ln = struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\0\0":
            try:
                return _parse_tiff(data[i + 10:i + 2 + ln])
            except (struct.error, IndexError, ValueError):
                return {}
        if marker == 0xDA:
            break
        i += 2 + ln
    return {}


def _parse_tiff(t):
    if len(t) < 8 or t[:2] not in (b"II", b"MM"):
        return {}
    end = "<" if t[:2] == b"II" else ">"
    out = {}
    sizes = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}

    def ifd(off, depth=0):
        if off + 2 > len(t) or depth > 2:
            return
        n = struct.unpack(end + "H", t[off:off + 2])[0]
        for k in range(min(n, 512)):
            e = off + 2 + 12 * k
            if e + 12 > len(t):
                return
            tag, typ, cnt = struct.unpack(end + "HHI", t[e:e + 8])
            valoff = t[e + 8:e + 12]
            if tag == 0x8769:  # Exif sub-IFD
                ifd(struct.unpack(end + "I", valoff)[0], depth + 1)
                continue
            if tag not in _EXIF_TAGS:
                continue
            size = sizes.get(typ, 1) * cnt
            raw = valoff[:size] if size <= 4 else t[struct.unpack(end + "I", valoff)[0]:][:size]
            try:
                if typ == 2:
                    v = raw.split(b"\0")[0].decode("utf-8", "replace").strip()
                elif typ == 3:
                    v = struct.unpack(end + "H", raw[:2])[0]
                elif typ == 4:
                    v = struct.unpack(end + "I", raw[:4])[0]
                elif typ in (5, 10):
                    v = struct.unpack(end + ("II" if typ == 5 else "ii"), raw[:8])
                else:
                    continue
            except struct.error:
                continue
            if v != "":
                out[_EXIF_TAGS[tag]] = v

    ifd(struct.unpack(end + "I", t[4:8])[0])
    return out


def format_exif(ex):
    rows = []

    def frac(v):
        return v[0] / float(v[1]) if isinstance(v, tuple) and v[1] else None

    cam = " ".join(x for x in (ex.get("Make", ""), ex.get("Model", "")) if x)
    if ex.get("Make") and ex.get("Model", "").lower().startswith(ex["Make"].lower()):
        cam = ex["Model"]
    if cam:
        rows.append(("Camera", cam))
    if ex.get("LensModel"):
        rows.append(("Lens", ex["LensModel"]))
    if ex.get("DateTimeOriginal") or ex.get("DateTime"):
        d = ex.get("DateTimeOriginal") or ex.get("DateTime")
        rows.append(("Taken", d.replace(":", "-", 2)))
    bits = []
    et = ex.get("ExposureTime")
    if isinstance(et, tuple) and et[1]:
        bits.append(("1/%d s" % round(et[1] / float(et[0]))) if et[0] and et[0] < et[1] else "%g s" % frac(et))
    fn = frac(ex.get("FNumber"))
    if fn:
        bits.append("f/%.1f" % fn)
    if isinstance(ex.get("ISO"), int):
        bits.append("ISO %d" % ex["ISO"])
    fl = frac(ex.get("FocalLength"))
    if fl:
        bits.append("%g mm" % round(fl, 1))
    if bits:
        rows.append(("Exposure", "  ".join(bits)))
    if ex.get("Software"):
        rows.append(("Software", ex["Software"]))
    return rows


def supported_exts():
    exts = {"." + bytes(f).decode("ascii", "ignore").lower() for f in QImageReader.supportedImageFormats()}
    exts.discard(".pdf")  # Qt lists it on some systems but can't render pages as images
    return exts


class Loader(QObject):
    """Decodes full images and thumbnails on background threads so browsing stays smooth."""
    loaded = Signal(str, object, str)   # path, QImage or None, error
    thumb = Signal(str, int, object)    # path, size, QImage or None

    def __init__(self):
        super().__init__()
        import concurrent.futures
        self.full = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.thumbs = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    closed = False

    def load(self, path):
        if not self.closed:
            self.full.submit(self._load, path)

    def _load(self, path):
        try:
            r = QImageReader(path)
            r.setAutoTransform(True)
            img = r.read()
            if img.isNull():
                self.loaded.emit(path, None, r.errorString() or "Unknown error")
            else:
                self.loaded.emit(path, img, "")
        except Exception as e:  # never let a worker thread die silently
            self.loaded.emit(path, None, str(e))

    def load_thumb(self, path, size):
        if not self.closed:
            self.thumbs.submit(self._thumb, path, size)

    def _thumb(self, path, size):
        try:
            r = QImageReader(path)
            r.setAutoTransform(True)
            s = r.size()
            if s.isValid() and s.width() > 0 and s.height() > 0:
                k = min(size / float(s.width()), size / float(s.height()), 1.0)
                r.setScaledSize(QSize(max(1, int(s.width() * k)), max(1, int(s.height() * k))))
            img = r.read()
            if not img.isNull() and (img.width() > size or img.height() > size):
                img = img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            if not img.isNull() and max(img.width(), img.height()) * 2 <= size:
                # tiny images (icons, pixel art): blow them up with crisp pixels so they're visible
                k = max(1, size // max(img.width(), img.height()))
                img = img.scaled(img.width() * k, img.height() * k, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.FastTransformation)
            self.thumb.emit(path, size, None if img.isNull() else img)
        except Exception:
            self.thumb.emit(path, size, None)

    def shutdown(self):
        self.closed = True
        for ex in (self.full, self.thumbs):
            try:
                ex.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                ex.shutdown(wait=False)


# --------------------------------------------------------------------------
# The canvas
# --------------------------------------------------------------------------

class Canvas(QWidget):
    MIN_ZOOM, MAX_ZOOM = 0.01, 50.0

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("canvas")
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.grabGesture(Qt.GestureType.PinchGesture)  # touchscreens
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(200, 150)
        self.img = None
        self.pix = None
        self.message = ""
        self.rotation = 0
        self.flip_h = self.flip_v = False
        self.fit = True
        self.zoom = 1.0
        self.offset = QPointF(0, 0)
        self._drag = None
        self.drawing = None
        self._draw_start = None
        self._cache = None
        self._cache_key = None
        self._checker = None
        self._checker_key = None
        self.cache_timer = QTimer(self)
        self.cache_timer.setSingleShot(True)
        self.cache_timer.timeout.connect(self._build_cache)
        self.hide_cursor_timer = QTimer(self)
        self.hide_cursor_timer.setSingleShot(True)
        self.hide_cursor_timer.timeout.connect(self._hide_cursor)

    # ---- state
    def set_image(self, img, reset_view=True):
        self.img = img
        self.pix = QPixmap.fromImage(img) if img is not None else None
        self.message = ""
        self._cache = None
        if reset_view:
            self.rotation = 0
            self.flip_h = self.flip_v = False
            self.fit = True
            self.offset = QPointF(0, 0)
        self.update()

    def set_frame(self, img):
        self.img = img
        self.pix = QPixmap.fromImage(img)
        self._cache = None
        self.update()

    def clear(self, message=""):
        self.img = self.pix = None
        self._cache = None
        self.message = message
        self.update()

    def oriented_size(self):
        if self.pix is None:
            return 0, 0
        w, h = self.pix.width(), self.pix.height()
        return (h, w) if self.rotation % 2 else (w, h)

    def fit_zoom(self):
        w, h = self.oriented_size()
        if not w or not h:
            return 1.0
        mode = self.app.settings["fit_mode"]
        if mode == "original":
            return 1.0
        z = min(self.width() / float(w), self.height() / float(h))
        return z if mode == "fit_all" else min(z, 1.0)

    def eff_zoom(self):
        return self.fit_zoom() if self.fit else self.zoom

    def zoom_to(self, z, anchor=None):
        if self.pix is None:
            return
        z = max(self.MIN_ZOOM, min(self.MAX_ZOOM, z))
        old = self.eff_zoom()
        if anchor is None:
            anchor = QPointF(self.width() / 2.0, self.height() / 2.0)
        c = QPointF(self.width() / 2.0, self.height() / 2.0)
        rel = anchor - c - self.offset
        self.offset = anchor - c - rel * (z / old if old else 1.0)
        self.fit = False
        self.zoom = z
        self._clamp()
        self.update()
        self.app.on_view_changed()

    def zoom_by(self, steps, anchor=None):
        factor = ZOOM_FACTORS.get(self.app.settings["zoom_speed"], 1.25)
        self.zoom_to(self.eff_zoom() * (factor ** steps), anchor)

    def set_fit(self):
        self.fit = True
        self.offset = QPointF(0, 0)
        self.update()
        self.app.on_view_changed()

    def rotate(self, d):
        self.rotation = (self.rotation + d) % 4
        self._cache = None
        self._clamp()
        self.update()
        self.app.on_view_changed()

    def flip(self, horizontal):
        if horizontal:
            self.flip_h = not self.flip_h
        else:
            self.flip_v = not self.flip_v
        self._cache = None
        self.update()
        self.app.on_view_changed()

    def transformed_image(self):
        """The image as currently shown (rotation + flips), for copying / saving."""
        if self.img is None:
            return None
        img = self.img if self.app.markup.empty() else self.app.markup.render(self.img)
        if not (self.rotation or self.flip_h or self.flip_v):
            return img
        return img.transformed(self._orient_transform(), Qt.TransformationMode.SmoothTransformation)

    def _orient_transform(self):
        t = QTransform()
        t.scale(-1 if self.flip_h else 1, -1 if self.flip_v else 1)
        t.rotate(90 * self.rotation)
        return t

    def image_transform(self):
        """Maps image pixels -> widget coordinates (zoom, pan, rotation, flips)."""
        z = self.eff_zoom()
        w, h = self.pix.width(), self.pix.height()
        t = QTransform()
        t.translate(self.width() / 2.0 + self.offset.x(), self.height() / 2.0 + self.offset.y())
        t.scale(-1 if self.flip_h else 1, -1 if self.flip_v else 1)
        t.rotate(90 * self.rotation)
        t.translate(-w * z / 2.0, -h * z / 2.0)
        t.scale(z, z)
        return t

    def to_image(self, pos):
        inv, _ok = self.image_transform().inverted()
        return inv.map(QPointF(pos))

    def _clamp(self):
        w, h = self.oriented_size()
        z = self.eff_zoom()
        sw, sh = w * z, h * z
        ox, oy = self.offset.x(), self.offset.y()
        lx = max(0.0, (sw - self.width()) / 2.0)
        ly = max(0.0, (sh - self.height()) / 2.0)
        self.offset = QPointF(max(-lx, min(lx, ox)), max(-ly, min(ly, oy)))

    def can_pan(self):
        w, h = self.oriented_size()
        z = self.eff_zoom()
        return w * z > self.width() + 1 or h * z > self.height() + 1

    # ---- painting
    def _checker_brush(self):
        t = self.app.theme
        key = (t["bg"], t["ui_fg"])
        if self._checker_key != key:
            tile = QPixmap(24, 24)
            a = QColor(blend(t["bg"], t["ui_fg"], 0.10))
            b = QColor(blend(t["bg"], t["ui_fg"], 0.18))
            tile.fill(a)
            p = QPainter(tile)
            p.fillRect(0, 0, 12, 12, b)
            p.fillRect(12, 12, 12, 12, b)
            p.end()
            self._checker = tile
            self._checker_key = key
        return self._checker

    def _cache_wanted(self):
        return self.app.settings["smooth_scaling"] and self.eff_zoom() < 0.999

    def _build_cache(self):
        if self.img is None or not self._cache_wanted():
            return
        z = self.eff_zoom()
        key = (round(z, 5), self.rotation, self.flip_h, self.flip_v, self.img.cacheKey())
        if key == self._cache_key and self._cache is not None:
            return
        w, h = self.img.width(), self.img.height()
        scaled = self.img.scaled(max(1, round(w * z)), max(1, round(h * z)),
                                 Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if self.rotation or self.flip_h or self.flip_v:
            scaled = scaled.transformed(self._orient_transform())
        self._cache = QPixmap.fromImage(scaled)
        self._cache_key = key
        self.update()

    def paintEvent(self, _e):
        t, s = self.app.theme, self.app.settings
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), qcolor(t["bg"], self.app.canvas_alpha()))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if self.pix is None:
            p.setPen(QColor(t["ui_dim"]))
            f = QFont(self.font())
            f.setPointSizeF(f.pointSizeF() + 2)
            p.setFont(f)
            msg = self.message or "Drop an image here, or press Ctrl+O"
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), msg)
            p.end()
            return
        z = self.eff_zoom()
        w, h = self.oriented_size()
        sw, sh = w * z, h * z
        cx = self.width() / 2.0 + self.offset.x()
        cy = self.height() / 2.0 + self.offset.y()
        target = QRectF(cx - sw / 2.0, cy - sh / 2.0, sw, sh)
        if s["checkerboard"] and self.img is not None and self.img.hasAlphaChannel():
            p.fillRect(target, QBrush(self._checker_brush()))
        key = (round(z, 5), self.rotation, self.flip_h, self.flip_v, self.img.cacheKey() if self.img else 0)
        if self._cache is not None and self._cache_key == key and self._cache_wanted():
            p.drawPixmap(QPointF(round(target.x()), round(target.y())), self._cache)
        else:
            smooth = s["smooth_scaling"] and not (s["pixelated_zoom"] and z >= 2.0)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, smooth)
            p.translate(cx, cy)
            p.scale(-1 if self.flip_h else 1, -1 if self.flip_v else 1)
            p.rotate(90 * self.rotation)
            pw, ph = self.pix.width() * z, self.pix.height() * z
            p.drawPixmap(QRectF(-pw / 2.0, -ph / 2.0, pw, ph), self.pix, QRectF(self.pix.rect()))
            if self._cache_wanted():
                self.cache_timer.start(70)
        shapes = self.app.markup.shapes
        if shapes or self.drawing:
            p.setTransform(self.image_transform())
            paint_shapes(p, shapes + ([self.drawing] if self.drawing else []), self.img)
        p.end()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._cache = None
        self._clamp()
        self.app.on_view_changed()

    # ---- mouse
    def mousePressEvent(self, e):
        b = e.button()
        if b == Qt.MouseButton.BackButton:
            self.app.go(-1)
            return
        if b == Qt.MouseButton.ForwardButton:
            self.app.go(1)
            return
        if self.app.draw_mode and self.pix is not None:
            if b == Qt.MouseButton.LeftButton:
                self.start_shape(e.position(), e.modifiers())
            elif b == Qt.MouseButton.MiddleButton:  # pan while drawing
                self._drag = (e.position(), QPointF(self.offset))
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if b == Qt.MouseButton.LeftButton and self.can_pan():
            self._drag = (e.position(), QPointF(self.offset))
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        if b == Qt.MouseButton.MiddleButton:
            self.app.toggle_fullscreen()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        self._show_cursor()
        if self.drawing is not None:
            self.move_shape(e.position(), e.modifiers())
            return
        if self._drag is not None:
            start, off = self._drag
            self.offset = off + (e.position() - start)
            self._clamp()
            self.update()
        else:
            self.setCursor(self.idle_cursor())

    def idle_cursor(self):
        if self.app.draw_mode and self.pix is not None:
            return Qt.CursorShape.CrossCursor
        return Qt.CursorShape.OpenHandCursor if self.can_pan() else Qt.CursorShape.ArrowCursor

    def mouseReleaseEvent(self, e):
        if self.drawing is not None and e.button() == Qt.MouseButton.LeftButton:
            self.move_shape(e.position(), e.modifiers())
            self.finish_shape(e.position())
            return
        if self._drag is not None:
            self._drag = None
            self.setCursor(self.idle_cursor())
        super().mouseReleaseEvent(e)

    # ---- drawing
    def start_shape(self, pos, mods):
        s = self.app.settings
        z = self.eff_zoom() or 1.0
        ip = self.to_image(pos)
        tool, color, size = s["draw_tool"], s["draw_color"], s["draw_size"]
        if tool == "text":
            text = TextPrompt.ask_text(self.app)
            if text:
                self.app.markup_add({"kind": "text", "color": color, "width": size / z, "pts": [ip],
                                     "text": text, "size": (11 + size * 2.2) / z})
            return
        if tool == "counter":
            n = 1 + sum(1 for x in self.app.markup.shapes if x["kind"] == "counter")
            self.app.markup_add({"kind": "counter", "color": color, "width": size / z, "pts": [ip], "n": n,
                                 "size": (9 + size * 1.3) / z})
            return
        self.drawing = {"kind": tool, "color": color, "width": size / z,
                        "pts": [ip] if tool in ("pen", "highlighter") else [ip, ip]}
        self._draw_start = QPointF(pos)
        self.update()

    def move_shape(self, pos, mods):
        d = self.drawing
        if d is None:
            return
        ip = self.to_image(pos)
        if d["kind"] in ("pen", "highlighter"):
            last = d["pts"][-1]
            if (ip - last).manhattanLength() * self.eff_zoom() >= 1.5:
                d["pts"].append(ip)
        else:
            if mods & Qt.KeyboardModifier.ShiftModifier:
                ip = snap_45(d["pts"][0], ip) if d["kind"] in ("line", "arrow") else square_from(d["pts"][0], ip)
            d["pts"][1] = ip
        self.update()

    def finish_shape(self, pos):
        d, self.drawing = self.drawing, None
        start, self._draw_start = self._draw_start, None
        if d["kind"] not in ("pen", "highlighter") and start is not None and (pos - start).manhattanLength() < 4:
            self.update()  # just a click - nothing to draw
            return
        self.app.markup_add(d)

    def mouseDoubleClickEvent(self, e):
        if self.app.draw_mode:
            return
        if e.button() != Qt.MouseButton.LeftButton or self.pix is None:
            return
        if self.fit and abs(self.fit_zoom() - 1.0) > 0.001:
            self.zoom_to(1.0, e.position())
        elif not self.fit:
            self.set_fit()
        else:
            self.app.toggle_fullscreen()

    def event(self, e):
        t = e.type()
        if t == QEvent.Type.NativeGesture:  # trackpad pinch (KDE/GNOME Wayland, X11, macOS)
            g = e.gestureType()
            if g == Qt.NativeGestureType.ZoomNativeGesture and self.pix is not None:
                self.zoom_to(self.eff_zoom() * (1.0 + e.value()), e.position())
                return True
            if g == Qt.NativeGestureType.SmartZoomNativeGesture and self.pix is not None:
                if self.fit:
                    self.zoom_to(1.0, e.position())
                else:
                    self.set_fit()
                return True
            if g in (Qt.NativeGestureType.BeginNativeGesture, Qt.NativeGestureType.EndNativeGesture):
                return True
        elif t == QEvent.Type.Gesture:  # touchscreen pinch
            pinch = e.gesture(Qt.GestureType.PinchGesture)
            if pinch is not None and self.pix is not None:
                anchor = self.mapFromGlobal(pinch.centerPoint().toPoint())
                self.zoom_to(self.eff_zoom() * pinch.scaleFactor(), QPointF(anchor))
                e.accept()
                return True
        return super().event(e)

    def wheelEvent(self, e):
        # mouse wheels report 120 per notch; some touchpads only report pixels, so convert those
        dy = e.angleDelta().y() or e.angleDelta().x()
        if not dy:
            px = e.pixelDelta().y() or e.pixelDelta().x()
            dy = px * 2
        if not dy:
            e.accept()
            return
        ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if ctrl or self.app.settings["wheel_action"] == "zoom":
            self.zoom_by(dy / 120.0, e.position())
        else:
            # add up small touchpad / smooth-wheel movements so one swipe = one image
            self._wheel_acc = getattr(self, "_wheel_acc", 0) + dy
            while abs(self._wheel_acc) >= 120:
                step = 1 if self._wheel_acc > 0 else -1
                self._wheel_acc -= 120 * step
                self.app.go(-step)
        e.accept()

    def contextMenuEvent(self, e):
        self.app.show_context_menu(e.globalPos())

    # ---- cursor auto-hide (full screen)
    def _show_cursor(self):
        if self.app.win.isFullScreen():
            if self.cursor().shape() == Qt.CursorShape.BlankCursor:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            self.hide_cursor_timer.start(2000)

    def _hide_cursor(self):
        if self.app.win.isFullScreen() and self._drag is None and not self.app.draw_mode:
            self.setCursor(Qt.CursorShape.BlankCursor)


# --------------------------------------------------------------------------
# Filmstrip + info panel
# --------------------------------------------------------------------------

class ThumbDelegate(QStyledItemDelegate):
    """Draws filmstrip thumbnails ourselves so Qt never tints the selected one."""

    def __init__(self, strip):
        super().__init__(strip)
        self.strip = strip

    def sizeHint(self, option, index):
        n = self.strip.thumb_px
        return QSize(n + 12, n + 12)

    def paint(self, p, option, index):
        t = self.strip.app.theme
        r = QRectF(option.rect).adjusted(2, 2, -2, -2)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hover:
            p.setPen(QPen(QColor(t["accent"]), 2) if selected else Qt.PenStyle.NoPen)
            p.setBrush(QColor(t["tab_active_bg"] if selected else t["ui_hover"]))
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 5, 5)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QIcon) and not icon.isNull():
            n = self.strip.thumb_px
            pm = icon.pixmap(QSize(n, n))
            target = QRectF(0, 0, pm.width() / pm.devicePixelRatio(), pm.height() / pm.devicePixelRatio())
            target.moveCenter(r.center())
            p.drawPixmap(target.toRect(), pm)
        p.restore()


class Filmstrip(QListWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("filmstrip")
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setMovement(QListWidget.Movement.Static)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setHorizontalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setUniformItemSizes(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setItemDelegate(ThumbDelegate(self))
        self.paths = []
        self.index_of = {}
        self.requested = set()
        self.thumb_px = 0
        self.itemClicked.connect(lambda it: self.app.show_index(self.row(it)))
        self.horizontalScrollBar().valueChanged.connect(lambda *_: self.load_visible())
        self.set_size(app.settings["thumb_size"])

    def set_size(self, n):
        self.thumb_px = n
        self.setIconSize(QSize(n, n))
        self.setGridSize(QSize(n + 12, n + 12))
        self.setFixedHeight(n + 30)
        self.requested.clear()
        for i in range(self.count()):
            self.item(i).setIcon(self._blank())
        self.load_visible()

    def _blank(self):
        pm = QPixmap(self.thumb_px, self.thumb_px)
        pm.fill(QColor(blend(self.app.theme["ui_bg"], self.app.theme["ui_fg"], 0.06)))
        return QIcon(pm)

    def set_files(self, paths):
        self.blockSignals(True)
        self.clear()
        self.paths = list(paths)
        self.index_of = {p: i for i, p in enumerate(self.paths)}
        self.requested.clear()
        blank = self._blank()
        for p in self.paths:
            it = QListWidgetItem(blank, "")
            it.setToolTip(os.path.basename(p))
            it.setSizeHint(QSize(self.thumb_px + 12, self.thumb_px + 12))
            self.addItem(it)
        self.blockSignals(False)
        QTimer.singleShot(0, self.load_visible)

    def select(self, i):
        if 0 <= i < self.count():
            self.blockSignals(True)
            self.setCurrentRow(i)
            self.blockSignals(False)
            self.scrollToItem(self.item(i), QListWidget.ScrollHint.PositionAtCenter)
            QTimer.singleShot(0, self.load_visible)

    def load_visible(self):
        if not self.paths or not self.isVisible():
            return
        mid = self.viewport().height() // 2
        a = self.indexAt(QPoint(4, mid)).row()
        b = self.indexAt(QPoint(self.viewport().width() - 4, mid)).row()
        if a < 0:
            a = max(0, self.currentRow())
        if b < 0:
            b = min(len(self.paths) - 1, a + self.viewport().width() // max(1, self.thumb_px + 12) + 1)
        for i in range(max(0, a - 8), min(len(self.paths), b + 9)):
            p = self.paths[i]
            key = (p, self.thumb_px)
            if key in self.requested:
                continue
            self.requested.add(key)
            cached = self.app.thumb_cache.get(key)
            if cached is not None:
                self.item(i).setIcon(QIcon(QPixmap.fromImage(cached)))
            else:
                self.app.loader.load_thumb(p, self.thumb_px)

    def set_thumb(self, path, size, img):
        i = self.index_of.get(path)
        if i is None or size != self.thumb_px:
            return
        pm = QPixmap.fromImage(img) if img is not None else self._broken()
        icon = QIcon()
        for mode in (QIcon.Mode.Normal, QIcon.Mode.Selected, QIcon.Mode.Active):
            icon.addPixmap(pm, mode)  # stop Qt from tinting the selected thumbnail
        self.item(i).setIcon(icon)

    def _broken(self):
        t = self.app.theme
        n = self.thumb_px
        pm = QPixmap(n, n)
        pm.fill(QColor(blend(t["ui_bg"], t["ui_fg"], 0.06)))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(t["ui_dim"]), max(2, n // 24)))
        m = n * 0.36
        p.drawLine(QPointF(m, m), QPointF(n - m, n - m))
        p.drawLine(QPointF(n - m, m), QPointF(m, n - m))
        p.end()
        return pm

    def wheelEvent(self, e):
        d = e.angleDelta().y() or e.angleDelta().x()
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d)
        e.accept()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self.load_visible)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self.load_visible)


class InfoPanel(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("infopanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(270)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        lay.addWidget(label("INFO", "header"))
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self.body, 1)

    def show_rows(self, rows):
        t = self.app.theme
        import html as _html
        cells = "".join(
            '<tr><td style="color:%s; padding:3px 12px 3px 0; white-space:nowrap;">%s</td>'
            '<td style="color:%s; padding:3px 0;">%s</td></tr>'
            % (t["ui_dim"], _html.escape(k), t["ui_fg"], _html.escape(str(v))) for k, v in rows)
        self.body.setText("<table>%s</table>" % cells if rows else
                          '<span style="color:%s">No image open</span>' % t["ui_dim"])


# --------------------------------------------------------------------------
# Preferences
# --------------------------------------------------------------------------

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
        self.op_slider.setRange(*NUMERIC_LIMITS["canvas_opacity"])
        self.op_slider.setValue(s["canvas_opacity"])
        self.op_slider.setFixedWidth(170)
        self.op_label = label("%d%%" % s["canvas_opacity"], "dim")
        self.op_label.setFixedWidth(40)
        self.op_slider.valueChanged.connect(self._opacity)
        h.addWidget(self.op_slider)
        h.addWidget(self.op_label)
        self.row(left, "Background opacity", w)
        self.op_note = label("", "dim", wrap=True)
        self.wide(left, self.op_note)
        self.toggle(left, "Checkerboard behind see-through images", "checkerboard")
        self.toggle(left, "Always on top", "topmost")
        self.toggle(left, "Use system title bar", "native_titlebar")

        self.section(left, "VIEWING")
        self.choice(left, "Opening an image", "fit_mode", FIT_MODES, 230)
        self.choice(left, "Mouse wheel", "wheel_action", WHEEL_MODES, 230)
        self.choice(left, "Zoom speed", "zoom_speed", ZOOM_SPEEDS, 230)
        self.toggle(left, "Smooth scaling", "smooth_scaling")
        self.toggle(left, "Crisp pixels when zoomed in", "pixelated_zoom")
        self.toggle(left, "Play animated GIF / WebP", "animate")

        self.section(right, "BROWSING")
        self.choice(right, "Sort by", "sort_by", SORT_MODES, 150)
        self.toggle(right, "Reverse order", "sort_desc")
        self.toggle(right, "Wrap around at the end", "loop_folder")
        self.toggle(right, "Filmstrip", "show_filmstrip")
        self.number(right, "Thumbnail size", "thumb_size")
        self.toggle(right, "Info panel", "show_info")
        self.toggle(right, "Status bar", "status_bar")
        self.section(right, "SLIDESHOW")
        self.number(right, "Seconds per image", "slideshow_seconds")
        self.toggle(right, "Shuffle", "slideshow_shuffle")
        self.section(right, "OTHER")
        self.toggle(right, "Ask before moving to trash", "confirm_delete")
        self.toggle(right, "Reopen last image on startup", "reopen_last")
        self.toggle(right, "Check for updates on startup", "check_updates")
        self.number(right, "UI font size", "ui_font_size")
        for g in (left, right):
            g.setRowStretch(self._rows[id(g)], 1)

        bar = QHBoxLayout()
        bar.addWidget(button("Open settings folder", app.open_config_folder))
        bar.addWidget(button("Reset everything...", app.reset_settings))
        bar.addStretch(1)
        bar.addWidget(button("Done", self.close, accent=True))
        self.body.addSpacing(8)
        self.body.addLayout(bar)
        self._update_op_note()

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

    def choice(self, g, text, key, options, width):
        labels = dict(options)
        values = {v: k for k, v in options}
        dd = DropButton([v for _, v in options], labels.get(self.app.settings[key], options[0][1]),
                        lambda v, k=key: self.app.set_setting(k, values[v]), width)
        dd.labels = labels
        self.controls[key] = dd
        self.row(g, text, dd)

    def _opacity(self, v):
        self.op_label.setText("%d%%" % v)
        self.app.set_setting("canvas_opacity", int(v))

    def _update_op_note(self):
        if not self.app.transparency_possible():
            self.op_note.setText("Windows can only see through the background with SlopView's own title bar. "
                                 "Turn off \"Use system title bar\" to use this.")
            self.op_note.show()
            self.op_slider.setEnabled(False)
        else:
            self.op_note.hide()
            self.op_slider.setEnabled(True)

    def sync(self, key, value):
        if key == "canvas_opacity":
            self.op_slider.blockSignals(True)
            self.op_slider.setValue(int(value))
            self.op_slider.blockSignals(False)
            self.op_label.setText("%d%%" % value)
            return
        c = self.controls.get(key)
        if c is None:
            return
        if isinstance(c, DropButton) and hasattr(c, "labels"):
            c.set_value(c.labels.get(value, value))
        else:
            c.set_value(value)
        if key == "native_titlebar":
            self._update_op_note()

    def on_theme(self):
        super().on_theme()
        for c in self.controls.values():
            c.update()

    def done(self, r):
        self.app.prefs = None
        super().done(r)


VIEWER_STYLESHEET = """
    #drawbar { background: %(ui_bg)s; }
    QTreeWidget#metatree { background: %(input_bg)s; color: %(fg)s; border: 1px solid %(border)s;
        border-radius: 6px; padding: 4px; outline: none; }
    QTreeWidget#metatree::item { padding: 3px 2px; }
    QTreeWidget#metatree::item:selected { background: %(selection_bg)s; color: %(selection_fg)s; }
    QTreeWidget#metatree::item:hover:!selected { background: %(ui_hover)s; }
    QHeaderView::section { background: %(ui_bg)s; color: %(ui_dim)s; border: none;
        border-bottom: 1px solid %(border)s; padding: 4px 6px; }
    QWidget#infopanel { background: %(ui_bg)s; border-left: 1px solid %(border)s; }
    QListWidget#filmstrip { background: %(ui_bg)s; border: none; border-top: 1px solid %(border)s;
        padding: 4px 6px; outline: none; }
"""


# --------------------------------------------------------------------------
# Full metadata (for the Metadata window)
# --------------------------------------------------------------------------

EXIF_NAMES = {
    # IFD0 / IFD1
    0x0100: "Image width", 0x0101: "Image height", 0x0102: "Bits per sample", 0x0103: "Compression",
    0x0106: "Photometric interpretation", 0x010E: "Image description", 0x010F: "Camera make",
    0x0110: "Camera model", 0x0112: "Orientation", 0x0115: "Samples per pixel", 0x011A: "X resolution",
    0x011B: "Y resolution", 0x011C: "Planar configuration", 0x0128: "Resolution unit", 0x0131: "Software",
    0x0132: "Date modified", 0x013B: "Artist", 0x013E: "White point", 0x013F: "Primary chromaticities",
    0x0211: "YCbCr coefficients", 0x0213: "YCbCr positioning", 0x0214: "Reference black/white",
    0x8298: "Copyright", 0x4746: "Rating", 0x4749: "Rating percent", 0x9C9B: "Title (Windows)",
    0x9C9C: "Comment (Windows)", 0x9C9D: "Author (Windows)", 0x9C9E: "Keywords (Windows)",
    0x9C9F: "Subject (Windows)", 0xA401: "Custom rendered",
    # Exif IFD
    0x829A: "Exposure time", 0x829D: "F-number", 0x8822: "Exposure program", 0x8824: "Spectral sensitivity",
    0x8827: "ISO", 0x8830: "Sensitivity type", 0x8832: "Recommended exposure index", 0x9000: "Exif version",
    0x9003: "Date taken", 0x9004: "Date digitized", 0x9010: "Time zone", 0x9011: "Time zone (taken)",
    0x9012: "Time zone (digitized)", 0x9101: "Components configuration", 0x9102: "Compressed bits per pixel",
    0x9201: "Shutter speed (APEX)", 0x9202: "Aperture (APEX)", 0x9203: "Brightness (APEX)",
    0x9204: "Exposure compensation", 0x9205: "Max aperture (APEX)", 0x9206: "Subject distance",
    0x9207: "Metering mode", 0x9208: "Light source", 0x9209: "Flash", 0x920A: "Focal length",
    0x9214: "Subject area", 0x927C: "Maker note", 0x9286: "User comment", 0x9290: "Subsec time",
    0x9291: "Subsec time (taken)", 0x9292: "Subsec time (digitized)", 0xA000: "FlashPix version",
    0xA001: "Color space", 0xA002: "Pixel width", 0xA003: "Pixel height", 0xA004: "Related sound file",
    0xA20E: "Focal plane X resolution", 0xA20F: "Focal plane Y resolution", 0xA210: "Focal plane resolution unit",
    0xA215: "Exposure index", 0xA217: "Sensing method", 0xA300: "File source", 0xA301: "Scene type",
    0xA302: "CFA pattern", 0xA402: "Exposure mode", 0xA403: "White balance", 0xA404: "Digital zoom ratio",
    0xA405: "Focal length (35 mm)", 0xA406: "Scene capture type", 0xA407: "Gain control", 0xA408: "Contrast",
    0xA409: "Saturation", 0xA40A: "Sharpness", 0xA40C: "Subject distance range", 0xA420: "Unique image ID",
    0xA430: "Camera owner", 0xA431: "Body serial number", 0xA432: "Lens specification", 0xA433: "Lens make",
    0xA434: "Lens model", 0xA435: "Lens serial number", 0xA460: "Composite image",
    # GPS IFD
}
GPS_NAMES = {
    0x0000: "GPS version", 0x0001: "Latitude ref", 0x0002: "Latitude", 0x0003: "Longitude ref",
    0x0004: "Longitude", 0x0005: "Altitude ref", 0x0006: "Altitude", 0x0007: "GPS time (UTC)",
    0x0008: "Satellites", 0x0009: "GPS status", 0x000A: "Measure mode", 0x000B: "Precision (DOP)",
    0x000C: "Speed unit", 0x000D: "Speed", 0x000E: "Direction of movement ref", 0x000F: "Direction of movement",
    0x0010: "Image direction ref", 0x0011: "Image direction", 0x0012: "Map datum", 0x0017: "Destination bearing ref",
    0x0018: "Destination bearing", 0x001B: "Processing method", 0x001C: "Area information",
    0x001D: "GPS date", 0x001E: "Differential", 0x001F: "Horizontal error",
}
_EXIF_ENUMS = {
    "Orientation": {1: "Normal", 2: "Mirrored", 3: "Upside down", 4: "Upside down, mirrored",
                    5: "Rotated 90°, mirrored", 6: "Rotated 90° clockwise", 7: "Rotated 90°, mirrored",
                    8: "Rotated 90° counter-clockwise"},
    "Resolution unit": {1: "None", 2: "Inches", 3: "Centimeters"},
    "Exposure program": {0: "Not defined", 1: "Manual", 2: "Program", 3: "Aperture priority",
                         4: "Shutter priority", 5: "Creative", 6: "Action", 7: "Portrait", 8: "Landscape"},
    "Metering mode": {0: "Unknown", 1: "Average", 2: "Center-weighted", 3: "Spot", 4: "Multi-spot",
                      5: "Pattern", 6: "Partial", 255: "Other"},
    "Light source": {0: "Unknown", 1: "Daylight", 2: "Fluorescent", 3: "Tungsten", 4: "Flash", 9: "Fine weather",
                     10: "Cloudy", 11: "Shade", 17: "Standard light A", 21: "D65", 255: "Other"},
    "Color space": {1: "sRGB", 2: "Adobe RGB", 0xFFFF: "Uncalibrated"},
    "Exposure mode": {0: "Auto", 1: "Manual", 2: "Auto bracket"},
    "White balance": {0: "Auto", 1: "Manual"},
    "Scene capture type": {0: "Standard", 1: "Landscape", 2: "Portrait", 3: "Night"},
    "Contrast": {0: "Normal", 1: "Soft", 2: "Hard"}, "Saturation": {0: "Normal", 1: "Low", 2: "High"},
    "Sharpness": {0: "Normal", 1: "Soft", 2: "Hard"},
    "Sensing method": {1: "Not defined", 2: "One-chip color", 3: "Two-chip color", 4: "Three-chip color",
                       5: "Color sequential", 7: "Trilinear", 8: "Color sequential linear"},
    "Compression": {1: "None", 6: "JPEG (old)", 7: "JPEG", 5: "LZW", 8: "Deflate", 32773: "PackBits"},
    "Altitude ref": {0: "Above sea level", 1: "Below sea level"},
}
_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}


def _num(v):
    if isinstance(v, tuple) and len(v) == 2:
        return v[0] / float(v[1]) if v[1] else 0.0
    return float(v)


def _fmt_num(x):
    return ("%.4f" % x).rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


def parse_tiff_all(t):
    """Every readable tag in a TIFF/EXIF block -> {"Image": [...], "Exif": [...], "GPS": [...], "Thumbnail": [...]}.
    Values come back as (name, python value)."""
    groups = {"Image": [], "Exif": [], "GPS": [], "Thumbnail": []}
    if len(t) < 8 or t[:2] not in (b"II", b"MM"):
        return groups
    end = "<" if t[:2] == b"II" else ">"
    seen = set()

    def read_ifd(off, group, names):
        if off in seen or off <= 0 or off + 2 > len(t):
            return 0
        seen.add(off)
        n = struct.unpack(end + "H", t[off:off + 2])[0]
        for k in range(min(n, 1024)):
            e = off + 2 + 12 * k
            if e + 12 > len(t):
                return 0
            tag, typ, cnt = struct.unpack(end + "HHI", t[e:e + 8])
            valoff = t[e + 8:e + 12]
            if tag == 0x8769 and group != "GPS":
                read_ifd(struct.unpack(end + "I", valoff)[0], "Exif", EXIF_NAMES)
                continue
            if tag == 0x8825:
                read_ifd(struct.unpack(end + "I", valoff)[0], "GPS", GPS_NAMES)
                continue
            if tag in (0xA005, 0x0201, 0x0202, 0x0111, 0x0117, 0x014A):  # pointers / strip offsets
                continue
            size = _TYPE_SIZES.get(typ, 1) * cnt
            if size <= 4:
                raw = valoff[:size]
            else:
                p = struct.unpack(end + "I", valoff)[0]
                if p + size > len(t):
                    continue
                raw = t[p:p + size]
            name = names.get(tag, "Tag 0x%04X" % tag)
            try:
                val = _decode(raw, typ, cnt, end, tag)
            except (struct.error, ValueError, IndexError):
                continue
            if val is None or val == "":
                continue
            groups[group].append((name, val))
        nxt = off + 2 + 12 * min(n, 1024)
        if nxt + 4 <= len(t):
            return struct.unpack(end + "I", t[nxt:nxt + 4])[0]
        return 0

    nxt = read_ifd(struct.unpack(end + "I", t[4:8])[0], "Image", EXIF_NAMES)
    if nxt:
        read_ifd(nxt, "Thumbnail", EXIF_NAMES)
    return groups


def _decode(raw, typ, cnt, end, tag):
    if tag in (0x9C9B, 0x9C9C, 0x9C9D, 0x9C9E, 0x9C9F):  # Windows XP tags are UTF-16 in BYTE arrays
        return raw.decode("utf-16-le", "replace").rstrip("\0").strip()
    if tag == 0x927C:
        return "(%s of camera-specific data)" % human_size(len(raw))
    if tag == 0x9286:  # user comment: 8-byte charset header
        head, body = raw[:8], raw[8:]
        enc = "utf-16-be" if head.startswith(b"UNICODE") and end == ">" else \
            "utf-16-le" if head.startswith(b"UNICODE") else "latin-1"
        return body.decode(enc, "replace").rstrip("\0 ").strip()
    if typ == 2:
        return raw.split(b"\0")[0].decode("utf-8", "replace").strip()
    if typ in (1, 7, 6):
        if tag in (0x9000, 0xA000):  # versions like "0232"
            return raw.decode("ascii", "replace")
        if cnt > 16:
            if typ == 7 and all(32 <= b < 127 or b in (9, 10, 13) for b in raw.rstrip(b"\0")) and raw.strip(b"\0"):
                return raw.rstrip(b"\0").decode("ascii")
            return "(%s of data)" % human_size(len(raw))
        vals = list(raw)
        return vals[0] if len(vals) == 1 else tuple(vals)
    fmt = {3: "H", 4: "I", 8: "h", 9: "i", 11: "f", 12: "d"}.get(typ)
    if fmt:
        vals = struct.unpack(end + fmt * cnt, raw[:struct.calcsize(fmt) * cnt])
        if cnt > 16:
            return "(%d values)" % cnt
        return vals[0] if cnt == 1 else tuple(vals)
    if typ in (5, 10):
        f = "II" if typ == 5 else "ii"
        vals = [struct.unpack(end + f, raw[8 * k:8 * k + 8]) for k in range(min(cnt, 16))]
        return vals[0] if cnt == 1 else tuple(vals)
    return None


def _pretty_exif(name, v):
    """Human-friendly value for one tag."""
    if name in _EXIF_ENUMS and isinstance(v, int):
        return _EXIF_ENUMS[name].get(v, str(v))
    if name == "Exposure time" and isinstance(v, tuple) and v[1]:
        return ("1/%d s" % round(v[1] / float(v[0]))) if v[0] and v[0] < v[1] else "%s s" % _fmt_num(_num(v))
    if name == "F-number" and isinstance(v, tuple):
        return "f/%.1f" % _num(v)
    if name in ("Focal length", "Focal length (35 mm)"):
        return "%s mm" % _fmt_num(_num(v)) if isinstance(v, tuple) else "%s mm" % v
    if name == "Exposure compensation" and isinstance(v, tuple):
        return "%+.1f EV" % _num(v)
    if name == "Flash" and isinstance(v, int):
        return "Fired" if v & 1 else "Did not fire"
    if name in ("Date taken", "Date digitized", "Date modified") and isinstance(v, str):
        return v.replace(":", "-", 2)
    if name == "Lens specification" and isinstance(v, tuple) and len(v) == 4:
        a, b, c, d = (_num(x) for x in v)
        mm = _fmt_num(a) if a == b else "%s-%s" % (_fmt_num(a), _fmt_num(b))
        return "%s mm f/%s" % (mm, _fmt_num(c) if c == d else "%s-%s" % (_fmt_num(c), _fmt_num(d)))
    if isinstance(v, tuple) and len(v) == 2 and all(isinstance(x, int) for x in v) and name not in (
            "GPS version",) and v[1] != 0 and not name.startswith("Tag 0x"):
        return _fmt_num(_num(v))
    if isinstance(v, tuple):
        return ", ".join(_fmt_num(_num(x)) if isinstance(x, tuple) else str(x) for x in v)
    return str(v)


def _gps_rows(gps):
    d = dict(gps)
    rows = []

    def deg(v):
        if isinstance(v, tuple) and len(v) == 3 and all(isinstance(x, tuple) for x in v):
            return _num(v[0]) + _num(v[1]) / 60.0 + _num(v[2]) / 3600.0
        return None

    lat, lon = deg(d.get("Latitude")), deg(d.get("Longitude"))
    if lat is not None and lon is not None:
        if d.get("Latitude ref") == "S":
            lat = -lat
        if d.get("Longitude ref") == "W":
            lon = -lon
        rows.append(("Coordinates", "%.6f, %.6f" % (lat, lon)))
        rows.append(("Map", "https://www.openstreetmap.org/?mlat=%.6f&mlon=%.6f#map=16/%.6f/%.6f"
                     % (lat, lon, lat, lon)))
    if isinstance(d.get("Altitude"), tuple):
        alt = _num(d["Altitude"]) * (-1 if d.get("Altitude ref") == 1 else 1)
        rows.append(("Altitude", "%s m" % _fmt_num(round(alt, 1))))
    if isinstance(d.get("GPS time (UTC)"), tuple) and len(d["GPS time (UTC)"]) == 3:
        h, m, sec = (_num(x) for x in d["GPS time (UTC)"])
        rows.append(("GPS time (UTC)", "%s %02d:%02d:%02d" % (d.get("GPS date", "").replace(":", "-"),
                                                              h, m, sec)))
    skip = {"Latitude", "Longitude", "Latitude ref", "Longitude ref", "Altitude", "Altitude ref",
            "GPS time (UTC)", "GPS date"}
    for name, v in gps:
        if name not in skip:
            rows.append((name, _pretty_exif(name, v)))
    return rows


def _xmp_rows(xml):
    rows = []
    for m in re.finditer(r'\s([A-Za-z][\w.-]*):([A-Za-z][\w.-]*)="([^"]*)"', xml):
        if m.group(1) in ("xmlns", "x", "rdf") or not m.group(3).strip():
            continue
        rows.append(("%s:%s" % (m.group(1), m.group(2)), m.group(3)))
    for m in re.finditer(r"<([A-Za-z][\w.-]*):([A-Za-z][\w.-]*)>([^<]+)</\1:\2>", xml):
        if m.group(1) != "rdf" and m.group(3).strip():
            rows.append(("%s:%s" % (m.group(1), m.group(2)), m.group(3).strip()))
    for m in re.finditer(r"<([A-Za-z][\w.-]*):([A-Za-z][\w.-]*)>\s*<rdf:(Alt|Seq|Bag)>(.*?)</rdf:\3>", xml, re.S):
        items = [x.strip() for x in re.findall(r"<rdf:li[^>]*>([^<]*)</rdf:li>", m.group(4)) if x.strip()]
        if items:
            rows.append(("%s:%s" % (m.group(1), m.group(2)), ", ".join(items)))
    out, seen = [], set()
    for k, v in rows:
        if (k, v) not in seen:
            seen.add((k, v))
            out.append((k, v.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")))
    return out


def _find_blocks(path, limit=32 * 1024 * 1024):
    """Pull raw EXIF / XMP / ICC blocks out of JPEG, PNG, WebP, TIFF and HEIF-less containers."""
    out = {"exif": None, "xmp": None, "icc": None, "png_text": [], "notes": []}
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            data = f.read(min(size, limit))
    except OSError:
        return out
    if data[:2] in (b"II", b"MM") and data[2:4] in (b"*\0", b"\0*"):
        out["exif"] = data
    elif data.startswith(b"\xff\xd8"):
        i, icc = 2, []
        while i + 4 <= len(data):
            if data[i] != 0xFF:
                break
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            ln = struct.unpack(">H", data[i + 2:i + 4])[0]
            seg = data[i + 4:i + 2 + ln]
            if marker == 0xE1 and seg.startswith(b"Exif\0\0") and out["exif"] is None:
                out["exif"] = seg[6:]
            elif marker == 0xE1 and seg.startswith(b"http://ns.adobe.com/xap/1.0/\0"):
                out["xmp"] = seg[29:].decode("utf-8", "replace")
            elif marker == 0xE2 and seg.startswith(b"ICC_PROFILE\0"):
                icc.append(seg[14:])
            elif marker == 0xFE:
                out["png_text"].append(("JPEG comment", seg.decode("utf-8", "replace").strip("\0 ")))
            elif marker in (0xC0, 0xC1, 0xC2):
                out["notes"].append(("JPEG type", "Progressive" if marker == 0xC2 else "Baseline"))
            if marker == 0xDA:
                break
            i += 2 + ln
        if icc:
            out["icc"] = b"".join(icc)
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        i = 8
        while i + 8 <= len(data):
            ln, typ = struct.unpack(">I4s", data[i:i + 8])
            body = data[i + 8:i + 8 + ln]
            if typ == b"eXIf":
                out["exif"] = body
            elif typ == b"iCCP":
                name, _, rest = body.partition(b"\0")
                try:
                    out["icc"] = zlib.decompress(rest[1:])
                except zlib.error:
                    pass
            elif typ in (b"tEXt", b"zTXt", b"iTXt"):
                k, _, rest = body.partition(b"\0")
                key = k.decode("latin-1")
                try:
                    if typ == b"tEXt":
                        val = rest.decode("latin-1")
                    elif typ == b"zTXt":
                        val = zlib.decompress(rest[1:]).decode("latin-1")
                    else:
                        comp = rest[0]
                        rest = rest[2:]
                        _lang, _, rest = rest.partition(b"\0")
                        _tkey, _, rest = rest.partition(b"\0")
                        val = (zlib.decompress(rest) if comp else rest).decode("utf-8", "replace")
                except (zlib.error, IndexError):
                    continue
                if key == "XML:com.adobe.xmp":
                    out["xmp"] = val
                else:
                    out["png_text"].append((key, val))
            elif typ == b"pHYs" and ln == 9:
                x, y, unit = struct.unpack(">IIB", body)
                if unit == 1:
                    out["notes"].append(("Resolution", "%d × %d DPI" % (round(x * 0.0254), round(y * 0.0254))))
            elif typ == b"acTL" and ln == 8:
                out["notes"].append(("Animated PNG", "%d frames" % struct.unpack(">I", body[:4])[0]))
            elif typ == b"IEND":
                break
            i += 12 + ln
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        i = 12
        while i + 8 <= len(data):
            typ, ln = struct.unpack("<4sI", data[i:i + 8])
            body = data[i + 8:i + 8 + ln]
            if typ == b"EXIF":
                out["exif"] = body[6:] if body.startswith(b"Exif\0\0") else body
            elif typ == b"XMP ":
                out["xmp"] = body.decode("utf-8", "replace")
            elif typ == b"ICCP":
                out["icc"] = body
            elif typ == b"VP8L":
                out["notes"].append(("WebP type", "Lossless"))
            elif typ == b"VP8 ":
                out["notes"].append(("WebP type", "Lossy"))
            elif typ == b"ANIM":
                out["notes"].append(("WebP type", "Animated"))
            i += 8 + ln + (ln & 1)
    elif data[:6] in (b"GIF87a", b"GIF89a"):
        out["notes"].append(("GIF version", data[3:6].decode()))
    return out


def _icc_description(icc):
    """Profile name from an ICC blob ('desc' tag, v2 'desc' or v4 'mluc')."""
    try:
        n = struct.unpack(">I", icc[128:132])[0]
        for k in range(min(n, 100)):
            sig, off, ln = struct.unpack(">4sII", icc[132 + 12 * k:144 + 12 * k])
            if sig != b"desc":
                continue
            tag = icc[off:off + ln]
            if tag[:4] == b"desc":
                cnt = struct.unpack(">I", tag[8:12])[0]
                return tag[12:12 + cnt].split(b"\0")[0].decode("latin-1")
            if tag[:4] == b"mluc":
                rec_ln, rec_off = struct.unpack(">II", tag[20:28])
                return tag[rec_off:rec_off + rec_ln].decode("utf-16-be", "replace").strip("\0")
    except (struct.error, IndexError):
        pass
    return None


def read_metadata(path, img=None):
    """Everything we can find about an image, as [(section, [(key, value), ...]), ...]."""
    sections = []
    file_rows = [("Name", os.path.basename(path)), ("Folder", os.path.dirname(path))]
    try:
        st = os.stat(path)
        file_rows.append(("File size", human_size(st.st_size) if st.st_size < 1024 else
                          "%s (%s bytes)" % (human_size(st.st_size), format(st.st_size, ","))))
        file_rows.append(("Modified", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))))
        created = getattr(st, "st_birthtime", None) or (st.st_ctime if IS_WIN else None)
        if created:
            file_rows.append(("Created", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created))))
    except OSError:
        pass
    sections.append(("File", file_rows))

    r = QImageReader(path)
    img_rows = []
    if not r.canRead():
        img_rows.append(("Problem", "This file can't be opened as an image (damaged or not really an image)"))
    fmt = bytes(r.format()).decode("ascii", "ignore").upper()
    if fmt:
        img_rows.append(("Format", fmt))
    sz = r.size()
    if sz.isValid():
        mp = sz.width() * sz.height() / 1e6
        img_rows.append(("Dimensions", "%d × %d px" % (sz.width(), sz.height())
                         + ("  (%.1f MP)" % mp if mp >= 1 else "")))
    if img is not None:
        img_rows.append(("Transparency", "Yes" if img.hasAlphaChannel() else "No"))
        img_rows.append(("Bit depth", "%d bits per pixel" % img.depth()))
        cs = img.colorSpace()
        if cs.isValid() and cs.description():
            img_rows.append(("Color space", cs.description()))
    if r.supportsAnimation() and r.imageCount() > 1:
        img_rows.append(("Frames", str(r.imageCount())))
        if r.loopCount() != 0:
            img_rows.append(("Loops", "Forever" if r.loopCount() < 0 else str(r.loopCount())))
    blocks = _find_blocks(path)
    img_rows.extend(blocks["notes"])
    if blocks["icc"]:
        name = _icc_description(blocks["icc"])
        img_rows.append(("ICC profile", "%s  (%s)" % (name, human_size(len(blocks["icc"]))) if name
                         else human_size(len(blocks["icc"]))))
    sections.append(("Image", img_rows))

    if blocks["exif"]:
        g = parse_tiff_all(blocks["exif"])
        cam = [(n, _pretty_exif(n, v)) for n, v in g["Image"] if not n.startswith("Tag 0x")]
        exif = [(n, _pretty_exif(n, v)) for n, v in g["Exif"] if not n.startswith("Tag 0x")]
        unknown = [(n, _pretty_exif(n, v)) for n, v in g["Image"] + g["Exif"] if n.startswith("Tag 0x")]
        if cam:
            sections.append(("Camera / image tags (EXIF)", cam))
        if exif:
            sections.append(("Photo settings (EXIF)", exif))
        if g["GPS"]:
            sections.append(("Location (GPS)", _gps_rows(g["GPS"])))
        if unknown:
            sections.append(("Other EXIF tags", unknown))
        if g["Thumbnail"]:
            sections.append(("Embedded thumbnail", [(n, _pretty_exif(n, v)) for n, v in g["Thumbnail"]]))

    text = list(blocks["png_text"])
    if not text:  # other formats Qt knows text for (e.g. GIF comments)
        for k in r.textKeys():
            v = r.text(k)
            if v and k.lower() not in ("xml:com.adobe.xmp",):
                text.append((k, v))
    if text:
        sections.append(("Text", text))
    if blocks["xmp"]:
        rows = _xmp_rows(blocks["xmp"])
        rows.append(("Raw XMP", blocks["xmp"].strip()))
        sections.append(("XMP", rows))
    return sections


def metadata_has_location(sections):
    return any(name == "Location (GPS)" and rows for name, rows in sections)


class MetadataDialog(Dialog):
    """Every bit of metadata for the current image, searchable and copyable."""

    def __init__(self, app):
        super().__init__(app, "Metadata")
        self.resize(640, 640)
        self.sections = []
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tags and values...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.fill)
        top.addWidget(self.search, 1)
        self.body.addLayout(top)
        self.warn = label("", "error", wrap=True)
        self.warn.hide()
        self.body.addWidget(self.warn)
        self.tree = QTreeWidget()
        self.tree.setObjectName("metatree")
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Tag", "Value"])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(False)
        self.tree.setWordWrap(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.header().setStretchLastSection(True)
        self.tree.setColumnWidth(0, 210)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemDoubleClicked.connect(self._double)
        self.tree.setMinimumHeight(380)
        self.body.addWidget(self.tree, 1)
        QShortcut(QKeySequence.StandardKey.Copy, self.tree, self.copy_selected)
        row = QHBoxLayout()
        self.count = label("", "dim")
        row.addWidget(self.count)
        row.addStretch(1)
        row.addWidget(button("Copy all", self.copy_all))
        row.addWidget(button("Close", self.close, accent=True))
        self.body.addLayout(row)
        self.refresh()

    def refresh(self):
        p = self.app.current_path
        if not p:
            self.sections = []
        else:
            self.sections = read_metadata(p, self.app.canvas.img)
            err = self.app.errors.get(p)
            if err:
                for name, rows in self.sections:
                    if name == "Image" and not any(k == "Problem" for k, _ in rows):
                        rows.insert(0, ("Problem", "Couldn't be opened: %s" % err))
        self.setWindowTitle("Metadata - %s" % os.path.basename(p) if p else "Metadata")
        if metadata_has_location(self.sections):
            self.warn.setText("⚠ This image has its GPS location saved in it. Anyone you send the "
                              "original file to can see where it was taken.")
            self.warn.show()
        else:
            self.warn.hide()
        self.fill()

    def fill(self, *_):
        q = self.search.text().strip().lower()
        self.tree.clear()
        total = shown = 0
        acc = QColor(self.app.theme["accent"])
        for name, rows in self.sections:
            if not rows:
                continue
            top = QTreeWidgetItem([name, ""])
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            top.setForeground(0, acc)
            top.setFirstColumnSpanned(False)
            for k, v in rows:
                total += 1
                v = str(v)
                if q and q not in k.lower() and q not in v.lower() and q not in name.lower():
                    continue
                shown += 1
                display = v if len(v) <= 600 and v.count("\n") < 12 else v[:600].split("\n")[0] + "  ... (double-click to see all)"
                it = QTreeWidgetItem([k, display])
                it.setData(1, Qt.ItemDataRole.UserRole, v)
                it.setToolTip(1, v[:2000])
                top.addChild(it)
            if top.childCount():
                self.tree.addTopLevelItem(top)
                top.setExpanded(True)
        if not self.sections:
            self.count.setText("No image open")
        elif q:
            self.count.setText("%d of %d tags" % (shown, total))
        else:
            self.count.setText("%d tags" % total)

    def _value(self, it):
        v = it.data(1, Qt.ItemDataRole.UserRole)
        return v if v is not None else it.text(1)

    def _double(self, it, col):
        v = self._value(it)
        if it.parent() is None:
            return
        if v.startswith("https://www.openstreetmap.org/"):
            QDesktopServices.openUrl(QUrl(v))
            return
        d = Dialog(self.app, it.text(0))
        box = QPlainTextEdit(v)
        box.setObjectName("errorbox")
        box.setReadOnly(True)
        box.setMinimumSize(560, 360)
        d.body.addWidget(box)
        r = QHBoxLayout()
        r.addStretch(1)
        r.addWidget(button("Copy", lambda: self.app.copy_text(v)))
        r.addWidget(button("Close", d.accept, accent=True))
        d.body.addLayout(r)
        d.show()

    def copy_selected(self):
        items = [it for it in self.tree.selectedItems() if it.parent() is not None]
        if not items:
            return
        if len(items) == 1:
            self.app.copy_text(self._value(items[0]))
        else:
            self.app.copy_text("\n".join("%s: %s" % (it.text(0), self._value(it)) for it in items))

    def copy_all(self):
        lines = []
        for name, rows in self.sections:
            lines.append("[%s]" % name)
            lines.extend("%s: %s" % (k, v) for k, v in rows)
            lines.append("")
        self.app.copy_text("\n".join(lines).strip())

    def _menu(self, pos):
        it = self.tree.itemAt(pos)
        m = QMenu(self)
        if it is not None and it.parent() is not None:
            m.addAction("Copy value", lambda: self.app.copy_text(self._value(it)))
            m.addAction("Copy tag + value", lambda: self.app.copy_text("%s: %s" % (it.text(0), self._value(it))))
            m.addAction("Show full value", lambda: self._double(it, 1))
            m.addSeparator()
        m.addAction("Copy all", self.copy_all)
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def on_theme(self):
        super().on_theme()
        self.fill()

    def done(self, r):
        self.app.meta_dialog = None
        super().done(r)

    def closeEvent(self, e):
        self.app.meta_dialog = None
        super().closeEvent(e)


# --------------------------------------------------------------------------
# Drawing on images (markup)
# --------------------------------------------------------------------------

DRAW_TOOLS = [
    ("pen", "Pen"), ("highlighter", "Highlighter"), ("line", "Line"), ("arrow", "Arrow"),
    ("rect", "Box (hold Shift for a square)"), ("ellipse", "Circle (hold Shift for a perfect circle)"),
    ("text", "Text"), ("counter", "Numbered marker"), ("pixelate", "Blur out (hide private stuff)"),
]
DRAW_TOOL_VALUES = tuple(k for k, _ in DRAW_TOOLS)
DRAW_COLORS = ["#ff3b30", "#ff9f0a", "#ffd60a", "#30d158", "#0a84ff", "#bf5af2", "#ffffff", "#000000"]
DRAW_SIZES = [2, 4, 7, 12]  # screen pixels


class Markup:
    """The drawings on the current image, in image pixel coordinates, with undo / redo."""

    def __init__(self):
        self.history = [[]]
        self.pos = 0
        self.dirty = False

    @property
    def shapes(self):
        return self.history[self.pos]

    def empty(self):
        return not self.shapes

    def _push(self, shapes):
        self.history = self.history[:self.pos + 1] + [shapes]
        if len(self.history) > 300:
            self.history = self.history[-300:]
        self.pos = len(self.history) - 1
        self.dirty = True

    def add(self, shape):
        self._push(self.shapes + [shape])

    def clear(self):
        if self.shapes:
            self._push([])

    def can_undo(self):
        return self.pos > 0

    def can_redo(self):
        return self.pos < len(self.history) - 1

    def undo(self):
        if self.can_undo():
            self.pos -= 1
            self.dirty = True
            return True
        return False

    def redo(self):
        if self.can_redo():
            self.pos += 1
            self.dirty = True
            return True
        return False

    def reset(self):
        self.__init__()

    def render(self, img):
        """A copy of img with the drawings burned in."""
        fmt = QImage.Format.Format_ARGB32_Premultiplied if img.hasAlphaChannel() else QImage.Format.Format_RGB32
        out = img.convertToFormat(fmt)
        p = QPainter(out)
        paint_shapes(p, self.shapes, img)
        p.end()
        return out


def _smooth_path(pts):
    path = QPainterPath(pts[0])
    if len(pts) == 1:
        path.lineTo(pts[0] + QPointF(0.01, 0.01))
        return path
    if len(pts) == 2:
        path.lineTo(pts[1])
        return path
    for i in range(1, len(pts) - 1):
        mid = (pts[i] + pts[i + 1]) / 2.0
        path.quadTo(pts[i], mid)
    path.lineTo(pts[-1])
    return path


def _pixelated(img, rect):
    r = rect.toAlignedRect().intersected(img.rect())
    if r.width() < 2 or r.height() < 2:
        return None, r
    block = max(6, round(max(img.width(), img.height()) / 90.0))
    small = img.copy(r).scaled(max(1, r.width() // block), max(1, r.height() // block),
                               Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return small.scaled(r.width(), r.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.FastTransformation), r


def _text_font(size):
    f = QFont(QApplication.font())
    f.setBold(True)
    f.setPixelSize(max(4, int(round(size))))
    return f


def paint_shapes(p, shapes, img):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    for sh in shapes:
        paint_shape(p, sh, img)
    p.restore()


def paint_shape(p, sh, img):
    kind = sh["kind"]
    color = QColor(sh["color"])
    w = sh["width"]
    pts = sh["pts"]
    if not pts:
        return
    a, b = pts[0], pts[-1]
    pen = QPen(color, w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind in ("pen", "highlighter"):
        if kind == "highlighter":
            color.setAlpha(95)
            pen = QPen(color, w * 3.5)
            pen.setCapStyle(Qt.PenCapStyle.SquareCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPath(_smooth_path(pts))
    elif kind == "line":
        p.setPen(pen)
        p.drawLine(a, b)
    elif kind == "arrow":
        d = b - a
        length = math.hypot(d.x(), d.y())
        if length < 0.5:
            return
        ux, uy = d.x() / length, d.y() / length
        head = min(max(w * 4.5, w + 6), length * 0.6)
        base = b - QPointF(ux, uy) * head
        p.setPen(pen)
        p.drawLine(a, base + QPointF(ux, uy) * (w * 0.5))
        px, py = -uy, ux
        half = head * 0.55
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPolygon([b, base + QPointF(px, py) * half, base - QPointF(px, py) * half])
    elif kind in ("rect", "ellipse"):
        r = QRectF(a, b).normalized()
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin if kind == "rect" else Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        if kind == "rect":
            p.drawRect(r)
        else:
            p.drawEllipse(r)
    elif kind == "pixelate":
        r = QRectF(a, b).normalized()
        if img is None:
            return
        key = (img.cacheKey(), r.x(), r.y(), r.width(), r.height())
        cached = sh.get("_cache")
        if not cached or cached[0] != key:
            pix, ir = _pixelated(img, r)
            sh["_cache"] = cached = (key, pix, ir)
        if cached[1] is not None:
            p.drawImage(cached[2].topLeft(), cached[1])
    elif kind == "text":
        text = sh.get("text", "")
        if not text:
            return
        f = _text_font(sh["size"])
        fm = QFontMetricsF(f)
        path = QPainterPath()
        y = a.y() + fm.ascent()
        for line in text.split("\n"):
            path.addText(QPointF(a.x(), y), f, line)
            y += fm.lineSpacing()
        outline = QColor(contrast_text(sh["color"]))
        outline.setAlpha(200)
        op = QPen(outline, max(1.0, sh["size"] / 7.0))
        op.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(op)
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPath(path)
    elif kind == "counter":
        r = sh["size"]
        p.setPen(QPen(QColor(contrast_text(sh["color"])), max(1.0, r / 9.0)))
        p.setBrush(color)
        p.drawEllipse(a, r, r)
        f = _text_font(r * 1.15)
        p.setFont(f)
        p.setPen(QColor(contrast_text(sh["color"])))
        p.drawText(QRectF(a.x() - r, a.y() - r, 2 * r, 2 * r), int(Qt.AlignmentFlag.AlignCenter), str(sh["n"]))


def snap_45(a, b):
    d = b - a
    ang = math.atan2(d.y(), d.x())
    step = math.pi / 4
    ang = round(ang / step) * step
    length = math.hypot(d.x(), d.y())
    return a + QPointF(math.cos(ang) * length, math.sin(ang) * length)


def square_from(a, b):
    d = b - a
    s = max(abs(d.x()), abs(d.y()))
    return a + QPointF(s if d.x() >= 0 else -s, s if d.y() >= 0 else -s)


class DrawIcon(QAbstractButton):
    """Little toolbar button with a hand-drawn icon (looks the same on every OS)."""

    def __init__(self, bar, kind, tip, slot, checkable=False, size=32):
        super().__init__()
        self.bar, self.kind, self.hover = bar, kind, False
        self.setCheckable(checkable)
        self.setToolTip(tip)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clicked.connect(lambda *_: slot())

    def enterEvent(self, e):
        self.hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        t = self.bar.app.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        if self.isChecked():
            p.setPen(QPen(QColor(t["accent"]), 1.5))
            p.setBrush(QColor(t["tab_active_bg"]))
            p.drawRoundedRect(r, 6, 6)
        elif self.hover or self.isDown():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t["ui_hover"]))
            p.drawRoundedRect(r, 6, 6)
        fg = QColor(t["accent"] if self.isChecked() else t["ui_fg"])
        if not self.isEnabled():
            fg = QColor(t["ui_dim"])
            fg.setAlpha(110)
        self.draw_glyph(p, fg, self.width() / 2.0, self.height() / 2.0)

    def draw_glyph(self, p, fg, cx, cy):
        k = self.kind
        pen = QPen(fg, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        P = QPointF
        if k == "pen":
            path = QPainterPath(P(cx - 8, cy + 5))
            path.cubicTo(P(cx - 4, cy - 9), P(cx + 1, cy + 9), P(cx + 4, cy - 2))
            path.quadTo(P(cx + 6, cy - 7), P(cx + 8, cy - 5))
            p.drawPath(path)
        elif k == "highlighter":
            c = QColor(fg)
            c.setAlpha(120)
            hp = QPen(c, 6)
            hp.setCapStyle(Qt.PenCapStyle.SquareCap)
            p.setPen(hp)
            p.drawLine(P(cx - 6, cy + 2), P(cx + 6, cy + 2))
            p.setPen(pen)
            p.drawLine(P(cx - 8, cy + 7), P(cx + 8, cy + 7))
            p.drawLine(P(cx - 3, cy - 7), P(cx + 3, cy - 7))
        elif k == "line":
            p.drawLine(P(cx - 7, cy + 7), P(cx + 7, cy - 7))
        elif k == "arrow":
            p.drawLine(P(cx - 7, cy + 7), P(cx + 6, cy - 6))
            p.setBrush(fg)
            p.drawPolygon([P(cx + 8, cy - 8), P(cx + 1, cy - 6), P(cx + 6, cy - 1)])
        elif k == "rect":
            p.drawRect(QRectF(cx - 8, cy - 6, 16, 12))
        elif k == "ellipse":
            p.drawEllipse(QRectF(cx - 8, cy - 6.5, 16, 13))
        elif k == "text":
            p.drawLine(P(cx - 6, cy - 7), P(cx + 6, cy - 7))
            p.drawLine(P(cx, cy - 7), P(cx, cy + 7))
            p.drawLine(P(cx - 2.5, cy + 7), P(cx + 2.5, cy + 7))
        elif k == "counter":
            p.drawEllipse(P(cx, cy), 8, 8)
            p.drawLine(P(cx - 2, cy - 3), P(cx + 0.5, cy - 5))
            p.drawLine(P(cx + 0.5, cy - 5), P(cx + 0.5, cy + 4.5))
        elif k == "pixelate":
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(3):
                for j in range(3):
                    c = QColor(fg)
                    c.setAlpha(230 if (i + j) % 2 == 0 else 90)
                    p.setBrush(c)
                    p.drawRect(QRectF(cx - 7.5 + 5 * i, cy - 7.5 + 5 * j, 5, 5))
        elif k in ("undo", "redo"):
            s = -1 if k == "redo" else 1
            path = QPainterPath(P(cx + 6 * s, cy + 6))
            path.cubicTo(P(cx + 8 * s, cy - 4), P(cx - 2 * s, cy - 6), P(cx - 7 * s, cy - 2))
            p.drawPath(path)
            p.drawLine(P(cx - 7 * s, cy - 2), P(cx - 7 * s, cy - 8))
            p.drawLine(P(cx - 7 * s, cy - 2), P(cx - 1 * s, cy - 2))
        elif k == "clear":
            p.drawLine(P(cx - 7, cy - 5), P(cx + 7, cy - 5))
            p.drawLine(P(cx - 2.5, cy - 8), P(cx + 2.5, cy - 8))
            p.drawLine(P(cx - 2.5, cy - 8), P(cx - 2.5, cy - 5))
            p.drawLine(P(cx + 2.5, cy - 8), P(cx + 2.5, cy - 5))
            path = QPainterPath(P(cx - 5.5, cy - 5))
            path.lineTo(P(cx - 4.5, cy + 8))
            path.lineTo(P(cx + 4.5, cy + 8))
            path.lineTo(P(cx + 5.5, cy - 5))
            p.drawPath(path)
            p.drawLine(P(cx - 1.5, cy - 1), P(cx - 1.2, cy + 5))
            p.drawLine(P(cx + 1.5, cy - 1), P(cx + 1.2, cy + 5))
        elif k == "copy":
            p.drawRoundedRect(QRectF(cx - 7, cy - 4, 10, 12), 2, 2)
            path = QPainterPath(P(cx - 3, cy - 6))
            path.lineTo(P(cx - 3, cy - 8))
            path.lineTo(P(cx + 7, cy - 8))
            path.lineTo(P(cx + 7, cy + 4))
            path.lineTo(P(cx + 5, cy + 4))
            p.drawPath(path)
        elif k == "save":
            p.drawLine(P(cx, cy - 8), P(cx, cy + 3))
            p.drawLine(P(cx - 4.5, cy - 1.5), P(cx, cy + 3))
            p.drawLine(P(cx + 4.5, cy - 1.5), P(cx, cy + 3))
            path = QPainterPath(P(cx - 8, cy + 2))
            path.lineTo(P(cx - 8, cy + 8))
            path.lineTo(P(cx + 8, cy + 8))
            path.lineTo(P(cx + 8, cy + 2))
            p.drawPath(path)
        elif k == "done":
            p.setPen(QPen(fg, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPolyline([P(cx - 7, cy), P(cx - 2, cy + 5), P(cx + 7, cy - 5)])


class Swatch(QAbstractButton):
    def __init__(self, bar, color, slot, tip=None, size=24):
        super().__init__()
        self.bar, self.color = bar, color  # color None = "pick a custom color"
        self.setFixedSize(size, size)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip(tip or color)
        self.clicked.connect(lambda *_: slot(self))

    def paintEvent(self, _e):
        t = self.bar.app.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2.0, self.height() / 2.0)
        rad = self.width() / 2.0 - 4
        if self.isChecked():
            p.setPen(QPen(QColor(t["accent"]), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, rad + 2.5, rad + 2.5)
        if self.color is None:
            g = QConicalGradient(c, 90)
            for i, col in enumerate(("#ff3b30", "#ffd60a", "#30d158", "#0a84ff", "#bf5af2", "#ff3b30")):
                g.setColorAt(i / 5.0, QColor(col))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(c, rad, rad)
            p.setBrush(QColor(t["ui_bg"]))
            p.drawEllipse(c, rad * 0.55, rad * 0.55)
            p.setPen(QPen(QColor(t["ui_fg"]), 1.4))
            p.drawLine(QPointF(c.x() - 2.5, c.y()), QPointF(c.x() + 2.5, c.y()))
            p.drawLine(QPointF(c.x(), c.y() - 2.5), QPointF(c.x(), c.y() + 2.5))
        else:
            p.setPen(QPen(QColor(blend(t["ui_bg"], t["ui_fg"], 0.35)), 1))
            p.setBrush(QColor(self.color))
            p.drawEllipse(c, rad, rad)


class SizeDot(QAbstractButton):
    def __init__(self, bar, size_px, slot):
        super().__init__()
        self.bar, self.size_px = bar, size_px
        self.setFixedSize(26, 30)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("Thickness %d" % (DRAW_SIZES.index(size_px) + 1))
        self.clicked.connect(lambda *_: slot(self))

    def paintEvent(self, _e):
        t = self.bar.app.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 3, -1, -3)
        if self.isChecked():
            p.setPen(QPen(QColor(t["accent"]), 1.5))
            p.setBrush(QColor(t["tab_active_bg"]))
            p.drawRoundedRect(r, 6, 6)
        d = {2: 3, 4: 5.5, 7: 8.5, 12: 12}.get(self.size_px, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.bar.app.settings["draw_color"]))
        p.drawEllipse(QPointF(self.width() / 2.0, self.height() / 2.0), d / 2.0, d / 2.0)


class DrawBar(QWidget):
    """The drawing toolbar shown above the image in drawing mode."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("drawbar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        h = QHBoxLayout()
        h.setContentsMargins(8, 3, 8, 3)
        h.setSpacing(1)
        outer.addLayout(h)
        outer.addWidget(sep())
        self.tools = {}
        for key, tip in DRAW_TOOLS:
            b = DrawIcon(self, key, tip, lambda k=key: self.pick_tool(k), checkable=True)
            self.tools[key] = b
            h.addWidget(b)
        h.addSpacing(10)
        self.swatches = []
        for c in DRAW_COLORS:
            s = Swatch(self, c, self.pick_swatch)
            self.swatches.append(s)
            h.addWidget(s)
        self.custom = Swatch(self, None, self.pick_custom, tip="Pick any color...")
        h.addWidget(self.custom)
        h.addSpacing(10)
        self.sizes = []
        for n in DRAW_SIZES:
            d = SizeDot(self, n, self.pick_size)
            self.sizes.append(d)
            h.addWidget(d)
        h.addSpacing(10)
        A = self.app
        self.undo_b = DrawIcon(self, "undo", "Undo (Ctrl+Z)", A.markup_undo)
        self.redo_b = DrawIcon(self, "redo", "Redo (Ctrl+Shift+Z)", A.markup_redo)
        self.clear_b = DrawIcon(self, "clear", "Erase all drawings", A.markup_clear)
        for b in (self.undo_b, self.redo_b, self.clear_b):
            h.addWidget(b)
        h.addStretch(1)
        self.copy_b = DrawIcon(self, "copy", "Copy image with drawings (Ctrl+C)", A.copy_image)
        self.save_b = DrawIcon(self, "save", "Save...", self.save_menu)
        self.done_b = DrawIcon(self, "done", "Done drawing (D or Esc)", A.toggle_draw)
        for b in (self.copy_b, self.save_b, self.done_b):
            h.addWidget(b)
        self.sync()

    def pick_tool(self, key):
        self.app.set_setting("draw_tool", key)
        self.sync()

    def pick_swatch(self, sw):
        self.app.set_setting("draw_color", sw.color)
        self.sync()

    def pick_custom(self, _sw):
        start = QColor(self.app.settings["draw_color"])
        c = QColorDialog.getColor(start, self.app.win, "Drawing color")
        if c.isValid():
            self.app.set_setting("draw_color", c.name())
        self.sync()

    def pick_size(self, dot):
        self.app.set_setting("draw_size", dot.size_px)
        self.sync()

    def save_menu(self):
        m = QMenu(self)
        m.addAction("Save a copy...", self.app.save_as)
        a = m.addAction("Save over the original", self.app.save_over_original)
        a.setEnabled(self.app.can_overwrite())
        m.exec(self.save_b.mapToGlobal(QPoint(0, self.save_b.height())))

    def sync(self):
        s = self.app.settings
        for key, b in self.tools.items():
            b.setChecked(key == s["draw_tool"])
        col = s["draw_color"].lower()
        known = False
        for sw in self.swatches:
            sw.setChecked(sw.color == col)
            known = known or sw.color == col
        self.custom.setChecked(not known)
        for d in self.sizes:
            d.setChecked(d.size_px == min(DRAW_SIZES, key=lambda n: abs(n - s["draw_size"])))
            d.update()
        self.sync_history()

    def sync_history(self):
        m = self.app.markup
        self.undo_b.setEnabled(m.can_undo())
        self.redo_b.setEnabled(m.can_redo())
        self.clear_b.setEnabled(not m.empty())
        for b in (self.undo_b, self.redo_b, self.clear_b):
            b.update()


class TextPrompt(Dialog):
    def __init__(self, app):
        super().__init__(app, "Add text")
        self.setModal(True)
        self.body.addWidget(label("Text to put on the image:", "dim"))
        self.edit = QLineEdit()
        self.edit.setMinimumWidth(360)
        self.edit.returnPressed.connect(self.accept)
        self.body.addWidget(self.edit)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Cancel", self.reject))
        row.addWidget(button("Add", self.accept, accent=True))
        self.body.addLayout(row)
        self.edit.setFocus()

    @staticmethod
    def ask_text(app):
        d = TextPrompt(app)
        ok = d.exec() == QDialog.DialogCode.Accepted
        return d.edit.text().strip() if ok else ""


# --------------------------------------------------------------------------
# The app
# --------------------------------------------------------------------------

class App:
    RESIZE_MARGIN = 6
    CACHE_SIZE = 6

    def __init__(self, files, qapp=None):
        self.settings = Settings()
        if IS_WIN:
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
            except Exception:
                pass
        self.qapp = qapp or QApplication.instance() or QApplication(sys.argv[:1])
        self.qapp.setApplicationName("slopview")
        self.qapp.setApplicationDisplayName(APP_NAME)
        self.qapp.setDesktopFileName("slopview")
        self.qapp.setQuitOnLastWindowClosed(True)
        QImageReader.setAllocationLimit(2048)  # MB - allow really big photos and panoramas
        sys.excepthook = self.on_exception
        self.dialogs = []
        self.prefs = None
        self.theme_editor = None
        self.meta_dialog = None
        self.markup = Markup()
        self.draw_mode = False
        self._showing_error = False
        self._resize_cursor = False
        self._quitting = False
        self._no_save = False
        self._update_result = None
        self._update_busy = False
        self.server = None
        self.files, self.index, self.folder = [], -1, None
        self.current_path = None
        self.cache = collections.OrderedDict()
        self.thumb_cache = collections.OrderedDict()
        self.errors = {}
        self.movie = None
        self.exts = supported_exts()
        self.theme = self.resolve_theme(self.settings["theme"])
        self.loader = Loader()
        self.loader.loaded.connect(self.on_loaded)
        self.loader.thumb.connect(self.on_thumb)
        self.watcher = QFileSystemWatcher()
        self.watcher.directoryChanged.connect(lambda *_: self.rescan_timer.start(400))

        self.base_ui_family = QApplication.font().family()
        self.update_ui_font()
        self.win = MainWindow(self)
        self.frameless = self._want_frameless()
        self._apply_window_flags(first=True)
        self.build_ui()
        self.apply_theme()

        self.save_timer = QTimer()
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save_settings)
        self.flash_timer = QTimer()
        self.flash_timer.setSingleShot(True)
        self.flash_timer.timeout.connect(lambda: self.st_msg.setText(""))
        self.rescan_timer = QTimer()
        self.rescan_timer.setSingleShot(True)
        self.rescan_timer.timeout.connect(self.rescan)
        self.slideshow = QTimer()
        self.slideshow.timeout.connect(self._slideshow_tick)
        self._was_max_before_full = False

        opened = False
        for p in files:
            if self.open_path(p):
                opened = True
        last = self.settings["last_path"]
        if not opened and self.settings["reopen_last"] and last and os.path.isfile(last):
            self.open_path(last, quiet=True)
        self.refresh_all()
        self.restore_window()
        self.qapp.installEventFilter(self._filter_obj())
        self.canvas.setFocus()
        QTimer.singleShot(8000, self._post_start_cleanup)
        if self.settings["check_updates"] and time.time() - self.settings["last_update_check"] > 20 * 3600:
            QTimer.singleShot(2500, lambda: self.check_for_updates(silent=True))
        if self.settings.load_error:
            QTimer.singleShot(300, lambda: self.error(
                "Settings were reset", "Your settings file couldn't be read, so SlopView started fresh.",
                detail="A copy was saved as settings.json.broken\n\n" + self.settings.load_error))

    # ---- transparency
    def canvas_alpha(self):
        if not self.transparency_possible():
            return 255
        return int(round(self.settings["canvas_opacity"] / 100.0 * 255))

    def toggle_fullscreen(self):
        w = self.win
        if w.isFullScreen():
            w.showNormal()
            if self._was_max_before_full:
                w.showMaximized()
        else:
            self._was_max_before_full = w.isMaximized()
            w.showFullScreen()
        self.update_chrome()

    def update_chrome(self):
        full = self.win.isFullScreen()
        s = self.settings
        for wdg in self.chrome_widgets:
            wdg.setVisible(not full)
        self.filmstrip.setVisible(s["show_filmstrip"] and not full)
        self.info_panel.setVisible(s["show_info"] and not full)
        self.status.setVisible(s["status_bar"] and not full)
        self.drawbar.setVisible(self.draw_mode)
        if not full:
            self.canvas.setCursor(self.canvas.idle_cursor())
            self.canvas.hide_cursor_timer.stop()
        else:
            self.canvas.hide_cursor_timer.start(2000)

    def update_ui_font(self):
        f = QFont(self.base_ui_family)
        f.setPointSizeF(self.settings["ui_font_size"])
        self.qapp.setFont(f)
        if hasattr(self, "titlebar"):
            QTimer.singleShot(0, self.titlebar.place_title)

    # ---- UI
    def build_ui(self):
        w = self.win
        w.setWindowTitle(APP_NAME)
        w.setMinimumSize(480, 320)
        self.shell = Shell(self)
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)
        lay = self.shell.lay
        self.titlebar = TitleBar(self)
        top_sep = sep()
        lay.addWidget(self.titlebar)
        lay.addWidget(top_sep)
        self.chrome_widgets = [self.titlebar, top_sep]
        self.drawbar = DrawBar(self)
        lay.addWidget(self.drawbar)
        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        self.canvas = Canvas(self)
        bl.addWidget(self.canvas, 1)
        self.info_panel = InfoPanel(self)
        bl.addWidget(self.info_panel)
        lay.addWidget(body, 1)
        self.filmstrip = Filmstrip(self)
        lay.addWidget(self.filmstrip)
        self.build_status()
        lay.addWidget(self.status)
        self.build_menus()
        self.titlebar.set_frameless(self.frameless)
        self.update_chrome()

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
        self.st_pos = label("", "dim")
        self.st_name = label("", "dim")
        self.st_msg = label("", "header")
        h.addWidget(self.st_pos)
        h.addSpacing(10)
        h.addWidget(self.st_name)
        h.addSpacing(14)
        h.addWidget(self.st_msg)
        h.addStretch(1)
        self.st_dims = label("", "dim")
        h.addWidget(self.st_dims)
        h.addSpacing(6)
        self.st_zoom = tool("100%", self._zoom_menu, name="statusbtn", tip="Zoom")
        h.addWidget(self.st_zoom)

    def _zoom_menu(self):
        m = QMenu(self.win)
        m.addAction("Fit to window", self.canvas.set_fit)
        m.addSeparator()
        for pct in (25, 50, 100, 200, 400, 800):
            m.addAction("%d%%" % pct, lambda p=pct: self.canvas.zoom_to(p / 100.0))
        m.exec(self.st_zoom.mapToGlobal(QPoint(0, -m.sizeHint().height())))

    def _act(self, menu, text, slot, shortcut=None, checkable=False, checked=False):
        a = QAction(text, self.win)
        if shortcut:
            seqs = shortcut if isinstance(shortcut, (list, tuple)) else [shortcut]
            a.setShortcuts([QKeySequence(x) for x in seqs])
            a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        a.setCheckable(checkable)
        if checkable:
            a.setChecked(checked)
            a.toggled.connect(slot)
        else:
            a.triggered.connect(lambda *_: slot())
        if menu is not None:
            menu.addAction(a)
        self.win.addAction(a)
        return a

    def build_menus(self):
        mb = self.titlebar.menubar
        s = self.settings
        A = self._act
        c = self.canvas
        self.checks = {}

        fm = mb.addMenu("File")
        A(fm, "Open...", self.open_dialog, "Ctrl+O")
        A(fm, "Open folder...", self.open_folder_dialog, "Ctrl+Shift+O")
        self.recent_menu = fm.addMenu("Open recent")
        self.recent_menu.aboutToShow.connect(self.fill_recent)
        fm.addSeparator()
        A(fm, "Save a copy as...", self.save_as, "Ctrl+S")
        A(fm, "Paste image", self.paste_image, "Ctrl+V")
        A(fm, "Copy image", self.copy_image, "Ctrl+C")
        A(fm, "Copy file path", self.copy_path, "Ctrl+Shift+C")
        fm.addSeparator()
        A(fm, "Rename...", self.rename_current, "F2")
        A(fm, "Move to trash", self.trash_current, "Del")
        A(fm, "Open containing folder", self.open_containing)
        A(fm, "Metadata...", self.open_metadata, ["M", "Ctrl+M"])
        fm.addSeparator()
        A(fm, "Quit", self.win.close, "Ctrl+Q")

        vm = mb.addMenu("View")
        A(vm, "Fit to window", c.set_fit, ["0", "Ctrl+0"])
        A(vm, "Actual size (100%)", lambda: c.zoom_to(1.0), ["1", "Ctrl+1"])
        A(vm, "Zoom in", lambda: c.zoom_by(1), ["+", "=", "Ctrl+=", "Ctrl++"])
        A(vm, "Zoom out", lambda: c.zoom_by(-1), ["-", "Ctrl+-"])
        vm.addSeparator()
        A(vm, "Rotate right", lambda: c.rotate(1), "R")
        A(vm, "Rotate left", lambda: c.rotate(-1), ["L", "Shift+R"])
        A(vm, "Flip horizontally", lambda: c.flip(True), "H")
        A(vm, "Flip vertically", lambda: c.flip(False), "V")
        vm.addSeparator()
        for key, text, sc in (("show_filmstrip", "Filmstrip", "T"), ("show_info", "Info panel", "I"),
                              ("status_bar", "Status bar", None), ("checkerboard", "Checkerboard", None)):
            self.checks[key] = A(vm, text, lambda v, k=key: self.set_setting(k, bool(v)), sc,
                                 checkable=True, checked=s[key])
        om = vm.addMenu("Background opacity")
        self.opacity_group = QActionGroup(om)
        self.opacity_actions = {}
        for pct in range(100, 0, -10):
            if pct < NUMERIC_LIMITS["canvas_opacity"][0]:
                break
            a = om.addAction("%d%%" % pct)
            a.setCheckable(True)
            a.setChecked(s["canvas_opacity"] == pct)
            self.opacity_group.addAction(a)
            a.triggered.connect(lambda *_, p=pct: self.set_setting("canvas_opacity", p))
            self.opacity_actions[pct] = a
        self.checks["topmost"] = A(vm, "Always on top", lambda v: self.set_setting("topmost", bool(v)),
                                   checkable=True, checked=s["topmost"])
        A(vm, "Full screen", self.toggle_fullscreen, ["F11", "F", "Return"])
        A(None, "Leave full screen / stop slideshow", self.escape, "Esc")

        gm = mb.addMenu("Go")
        A(gm, "Next image", lambda: self.go(1), ["Right", "PgDown", "Space", "N"])
        A(gm, "Previous image", lambda: self.go(-1), ["Left", "PgUp", "Backspace", "P"])
        A(gm, "First image", lambda: self.show_index(0), "Home")
        A(gm, "Last image", lambda: self.show_index(len(self.files) - 1), "End")
        A(gm, "Random image", self.go_random, "X")
        gm.addSeparator()
        self.slide_action = A(gm, "Slideshow", self.toggle_slideshow, "S")
        A(gm, "Pause / play animation", self.toggle_animation, "Ctrl+Space")
        gm.addSeparator()
        sm = gm.addMenu("Sort by")
        self.sort_group = QActionGroup(sm)
        for val, text in SORT_MODES:
            a = sm.addAction(text)
            a.setCheckable(True)
            a.setChecked(s["sort_by"] == val)
            self.sort_group.addAction(a)
            a.triggered.connect(lambda *_, v=val: self.set_setting("sort_by", v))
        sm.addSeparator()
        self.checks["sort_desc"] = A(sm, "Reverse order", lambda v: self.set_setting("sort_desc", bool(v)),
                                     checkable=True, checked=s["sort_desc"])

        dm = mb.addMenu("Draw")
        self.draw_action = A(dm, "Drawing mode", self.toggle_draw, "D")
        dm.addSeparator()
        A(dm, "Undo", self.markup_undo, "Ctrl+Z")
        A(dm, "Redo", self.markup_redo, ["Ctrl+Shift+Z", "Ctrl+Y"])
        A(dm, "Erase all drawings", self.markup_clear)
        dm.addSeparator()
        tm = dm.addMenu("Tool")
        for key, text in DRAW_TOOLS:
            tm.addAction(text.split(" (")[0], lambda k=key: self.drawbar.pick_tool(k))
        dm.addSeparator()
        A(dm, "Save over the original", self.save_over_original)

        self.theme_menu = mb.addMenu("Theme")
        self.theme_menu.aboutToShow.connect(self.fill_theme_menu)
        self.fill_theme_menu()

        stm = mb.addMenu("Settings")
        A(stm, "Preferences...", self.open_prefs, "Ctrl+,")
        A(stm, "Theme editor...", self.open_theme_editor)
        A(stm, "Check for updates...", lambda: self.check_for_updates(silent=False))
        stm.addSeparator()
        A(stm, "Open settings folder", self.open_config_folder)
        A(stm, "Reset everything...", self.reset_settings)
        if install_supported():
            stm.addSeparator()
            self.install_action = A(stm, "Add to app menu / Open with...", self.gui_install)
            A(stm, "Uninstall SlopView...", self.gui_uninstall)
            stm.aboutToShow.connect(self._refresh_install_label)

        hm = mb.addMenu("Help")
        A(hm, "Keyboard shortcuts", self.show_shortcuts, "F1")
        A(hm, "About SlopView", self.show_about)

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

    def show_context_menu(self, gpos):
        m = QMenu(self.win)
        has = self.current_path is not None
        for text, fn, ok in (("Open...", self.open_dialog, True), ("Paste image", self.paste_image, True),
                             (None, None, None),
                             ("Leave drawing mode" if self.draw_mode else "Draw on it", self.toggle_draw, has),
                             (None, None, None),
                             ("Fit to window", self.canvas.set_fit, has),
                             ("Actual size (100%)", lambda: self.canvas.zoom_to(1.0), has),
                             ("Rotate right", lambda: self.canvas.rotate(1), has),
                             ("Rotate left", lambda: self.canvas.rotate(-1), has), (None, None, None),
                             ("Copy image", self.copy_image, has), ("Copy file path", self.copy_path, has),
                             ("Save a copy as...", self.save_as, has), (None, None, None),
                             ("Rename...", self.rename_current, has),
                             ("Move to trash", self.trash_current, has),
                             ("Open containing folder", self.open_containing, has),
                             ("Metadata...", self.open_metadata, has), (None, None, None),
                             ("Slideshow", self.toggle_slideshow, len(self.files) > 1),
                             ("Full screen", self.toggle_fullscreen, True)):
            if text is None:
                m.addSeparator()
                continue
            a = m.addAction(text)
            a.setEnabled(bool(ok))
            a.triggered.connect(lambda *_, fn=fn: fn())
        m.exec(gpos)

    # ---- theming
    def apply_theme(self):
        t = self.theme
        self.qapp.setStyleSheet(build_stylesheet(t, self.canvas_alpha()) + VIEWER_STYLESHEET % t)
        icon = make_icon(t)
        self.win.setWindowIcon(icon)
        self.qapp.setWindowIcon(icon)
        self.titlebar.icon.setPixmap(icon.pixmap(18, 18))
        set_titlebar_hwnd(int(self.win.winId()), t)
        for d in list(self.dialogs):
            d.on_theme()
        self.shell.update()
        self.canvas.update()
        if hasattr(self, "filmstrip"):
            self.filmstrip.set_size(self.settings["thumb_size"])
        self.refresh_info()

    # ---- settings
    def set_setting(self, key, value):
        self.settings[key] = value
        a = getattr(self, "checks", {}).get(key)
        if a is not None and a.isChecked() != bool(value):
            a.blockSignals(True)
            a.setChecked(bool(value))
            a.blockSignals(False)
        if key == "canvas_opacity" and value in getattr(self, "opacity_actions", {}):
            self.opacity_actions[value].setChecked(True)
        self.apply_setting(key)
        self._sync_dialogs(key, value)
        self.save_settings_soon()

    def apply_setting(self, key):
        s = self.settings
        if key == "canvas_opacity":
            self.qapp.setStyleSheet(build_stylesheet(self.theme, self.canvas_alpha()) + VIEWER_STYLESHEET % self.theme)
            self.canvas.update()
        elif key in ("topmost", "native_titlebar"):
            self._apply_window_flags()
            self.apply_setting("canvas_opacity")
        elif key in ("show_filmstrip", "show_info", "status_bar"):
            self.update_chrome()
            if key == "show_filmstrip" and s["show_filmstrip"]:
                self.filmstrip.select(self.index)
        elif key == "thumb_size":
            self.filmstrip.set_size(s["thumb_size"])
        elif key in ("sort_by", "sort_desc"):
            for a in self.sort_group.actions():
                a.setChecked(a.text() == dict(SORT_MODES)[s["sort_by"]])
            self.resort()
        elif key == "ui_font_size":
            self.update_ui_font()
        elif key == "animate":
            if self.current_path:
                self.show_index(self.index, keep_view=True)
        elif key == "slideshow_seconds":
            if self.slideshow.isActive():
                self.slideshow.start(s["slideshow_seconds"] * 1000)
        elif key in ("draw_tool", "draw_color", "draw_size"):
            if hasattr(self, "drawbar"):
                self.drawbar.sync()
        elif key in ("fit_mode", "smooth_scaling", "pixelated_zoom", "checkerboard"):
            self.canvas._cache = None
            self.canvas.update()
            self.on_view_changed()

    def reset_settings(self):
        if not self.ask("Reset everything?", "Put every setting back to default?",
                        [("Reset", True, True), ("Cancel", None, False)],
                        detail="Your custom themes and recent files are kept.", parent=self.prefs):
            return
        keep = {k: self.settings[k] for k in ("custom_themes", "recent", "window_state", "last_path")}
        old = (self.settings["native_titlebar"], self.settings["topmost"])
        self.settings.data = copy.deepcopy(DEFAULT_SETTINGS)
        self.settings.data.update(keep)
        for key, a in self.checks.items():
            a.blockSignals(True)
            a.setChecked(bool(self.settings[key]))
            a.blockSignals(False)
        if old != (self.settings["native_titlebar"], self.settings["topmost"]):
            self._apply_window_flags()
        self.update_ui_font()
        self.set_theme(DEFAULT_THEME)
        for key in DEFAULT_SETTINGS:
            self._sync_dialogs(key, self.settings[key])
        self.update_chrome()
        self.resort()
        self.flash("Settings reset")

    # ---- folder + navigation
    def is_image(self, path):
        return os.path.splitext(path)[1].lower() in self.exts

    def sort_key(self):
        mode = self.settings["sort_by"]

        def key(p):
            name = os.path.basename(p)
            try:
                st = os.stat(p)
            except OSError:
                st = None
            if mode == "date":
                return (st.st_mtime if st else 0, natural_key(name))
            if mode == "size":
                return (st.st_size if st else 0, natural_key(name))
            if mode == "type":
                return (os.path.splitext(name)[1].lower(), natural_key(name))
            return natural_key(name)

        return key

    def scan_folder(self, folder, keep=None):
        try:
            names = os.listdir(folder)
        except OSError as e:
            self.flash("Couldn't read folder: %s" % (e.strerror or e))
            names = []
        paths = [os.path.join(folder, n) for n in names if self.is_image(n)]
        paths = [p for p in paths if os.path.isfile(p)]
        if keep and keep not in paths and os.path.isfile(keep):
            paths.append(keep)  # an image Qt can read even though its extension is unusual
        paths.sort(key=self.sort_key(), reverse=self.settings["sort_desc"])
        if self.folder != folder:
            if self.folder and self.folder in self.watcher.directories():
                self.watcher.removePath(self.folder)
            self.watcher.addPath(folder)
            self.folder = folder
        self.files = paths
        self.filmstrip.set_files(paths)

    def resort(self):
        if not self.files:
            return
        cur = self.current_path
        self.files.sort(key=self.sort_key(), reverse=self.settings["sort_desc"])
        self.filmstrip.set_files(self.files)
        if cur in self.files:
            self.index = self.files.index(cur)
            self.filmstrip.select(self.index)
        self.refresh_all()

    def rescan(self):
        if not self.folder:
            return
        cur = self.current_path
        old_index = self.index
        self.scan_folder(self.folder, keep=cur if cur and os.path.isfile(cur) else None)
        if cur in self.files:
            self.index = self.files.index(cur)
            self.filmstrip.select(self.index)
            self.refresh_all()
        elif self.files:
            self.show_index(min(max(0, old_index), len(self.files) - 1), force=True)
            self.flash("The image was moved or deleted by another program")
        else:
            self.close_image("This folder has no images left")

    def open_path(self, path, quiet=False):
        path = os.path.abspath(os.path.expanduser(path))
        if path != self.current_path and not self.markup_ok():
            return False
        if os.path.isdir(path):
            self.scan_folder(path)
            if not self.files:
                if not quiet:
                    self.flash("No images in that folder")
                self.close_image("No images in %s" % path)
                return False
            self.add_recent(path)
            self.show_index(0, force=True)
            return True
        if not os.path.isfile(path):
            if not quiet:
                self.error("Couldn't open", "That file doesn't exist (anymore?)", detail=path)
                self.settings["recent"] = [p for p in self.settings["recent"] if p != path]
            return False
        folder = os.path.dirname(path)
        if folder != self.folder or path not in self.files:
            self.scan_folder(folder, keep=path)
        self.add_recent(path)
        self.show_index(self.files.index(path) if path in self.files else 0, force=True)
        return True

    def show_index(self, i, keep_view=False, force=False):
        if not self.files:
            return
        i = max(0, min(len(self.files) - 1, i))
        path = self.files[i]
        if path != self.current_path:
            if not force and not self.markup_ok():
                self.filmstrip.select(self.index)
                return
            self.reset_markup()
        self.index = i
        self.current_path = path
        self._stop_movie()
        if path in self.cache:
            self.cache.move_to_end(path)
            self._display(path, self.cache[path], keep_view)
        elif path in self.errors:
            self.canvas.clear("Couldn't open %s\n%s" % (os.path.basename(path), self.errors[path]))
        else:
            self.st_msg.setText("Loading...")
            self.loader.load(path)
            QTimer.singleShot(150, lambda p=path: self.canvas.clear("Loading %s..." % os.path.basename(p))
                              if self.current_path == p and p not in self.cache and p not in self.errors else None)
        self.filmstrip.select(i)
        self.refresh_all()
        self.settings["last_path"] = path
        self.save_settings_soon()
        for d in (1, -1, 2):  # preload the neighbours so flipping through is instant
            j = i + d
            if self.settings["loop_folder"] and self.files:
                j %= len(self.files)
            if 0 <= j < len(self.files):
                q = self.files[j]
                if q not in self.cache and q not in self.errors:
                    self.loader.load(q)

    def _display(self, path, img, keep_view=False):
        self.st_msg.setText("")
        animated = False
        if self.settings["animate"]:
            r = QImageReader(path)
            if r.supportsAnimation() and r.imageCount() != 1:
                mv = QMovie(path)
                if mv.isValid():
                    self.movie = mv
                    mv.frameChanged.connect(lambda *_: self.canvas.set_frame(mv.currentImage())
                                            if self.movie is mv else None)
                    mv.start()
                    animated = True
        self.canvas.set_image(img, reset_view=not keep_view)
        if animated and not self.movie.currentImage().isNull():
            self.canvas.set_frame(self.movie.currentImage())
        if animated and self.draw_mode:
            self.movie.setPaused(True)
        self.canvas.setCursor(self.canvas.idle_cursor())
        self.refresh_all()

    def on_loaded(self, path, img, err):
        if img is None:
            self.errors[path] = err
            if path == self.current_path:
                self.st_msg.setText("")
                self.canvas.clear("Couldn't open %s\n%s" % (os.path.basename(path), err))
                self.refresh_all()
            return
        self.cache[path] = img
        self.cache.move_to_end(path)
        while len(self.cache) > self.CACHE_SIZE:
            old, _ = self.cache.popitem(last=False)
            if old == self.current_path:  # never drop what's on screen
                self.cache[old] = _
        if path == self.current_path:
            self._display(path, img)

    def on_thumb(self, path, size, img):
        if img is not None:
            self.thumb_cache[(path, size)] = img
            while len(self.thumb_cache) > 3000:
                self.thumb_cache.popitem(last=False)
        self.filmstrip.set_thumb(path, size, img)

    def _stop_movie(self):
        if self.movie is not None:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None

    def toggle_animation(self):
        if self.movie is not None:
            paused = self.movie.state() == QMovie.MovieState.Paused
            self.movie.setPaused(not paused)
            self.flash("Playing" if paused else "Paused")

    def go(self, d):
        if not self.files:
            return
        i = self.index + d
        if self.settings["loop_folder"]:
            i %= len(self.files)
        elif i < 0 or i >= len(self.files):
            QApplication.beep()
            self.flash("That's the %s image" % ("first" if i < 0 else "last"))
            return
        self.show_index(i)

    def go_random(self):
        if len(self.files) > 1:
            import random
            choices = [k for k in range(len(self.files)) if k != self.index]
            self.show_index(random.choice(choices))

    def close_image(self, message=""):
        self.reset_markup()
        self._stop_movie()
        self.current_path = None
        self.index = -1
        self.canvas.clear(message)
        self.refresh_all()

    # ---- display info
    def on_view_changed(self):
        if hasattr(self, "st_zoom"):
            self.st_zoom.setText("%d%%" % round(self.canvas.eff_zoom() * 100) if self.canvas.pix else "")
            if self.settings["show_info"]:
                self.refresh_info()

    def refresh_all(self):
        self.update_title()
        self.update_status()
        self.refresh_info()
        if self.meta_dialog is not None and self.meta_dialog.isVisible():
            self.meta_dialog.refresh()

    def open_metadata(self):
        if self.meta_dialog is None:
            self.meta_dialog = MetadataDialog(self)
        else:
            self.meta_dialog.refresh()
        self.meta_dialog.show()
        self.meta_dialog.raise_()
        self.meta_dialog.activateWindow()

    def update_title(self):
        p = self.current_path
        text = "%s - %s" % (os.path.basename(p), APP_NAME) if p else APP_NAME
        self.win.setWindowTitle(text)
        self.titlebar.set_title(text)

    def update_status(self):
        p = self.current_path
        if not p:
            self.st_pos.setText("")
            self.st_name.setText("")
            self.st_dims.setText("")
            self.st_zoom.setText("")
            return
        self.st_pos.setText("%d / %d" % (self.index + 1, len(self.files)))
        self.st_name.setText(os.path.basename(p))
        parts = []
        if self.canvas.img is not None:
            parts.append("%d × %d" % (self.canvas.img.width(), self.canvas.img.height()))
        try:
            parts.append(human_size(os.path.getsize(p)))
        except OSError:
            pass
        if self.slideshow.isActive():
            parts.append("Slideshow ▶")
        self.st_dims.setText("   ·   ".join(parts))
        self.on_view_changed()

    def refresh_info(self):
        if not hasattr(self, "info_panel") or not self.settings["show_info"]:
            return
        p = self.current_path
        if not p:
            self.info_panel.show_rows([])
            return
        rows = [("Name", os.path.basename(p)), ("Folder", os.path.dirname(p))]
        img = self.canvas.img
        if img is not None:
            w, h = img.width(), img.height()
            rows.append(("Size", "%d × %d  (%.1f MP)" % (w, h, w * h / 1e6)))
            rows.append(("Has transparency", "Yes" if img.hasAlphaChannel() else "No"))
        try:
            st = os.stat(p)
            rows.append(("File size", human_size(st.st_size)))
            rows.append(("Modified", time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))))
        except OSError:
            pass
        fmt = bytes(QImageReader.imageFormat(p)).decode("ascii", "ignore").upper()
        if fmt:
            rows.append(("Format", fmt))
        if self.movie is not None:
            rows.append(("Animation", "%d frames" % self.movie.frameCount() if self.movie.frameCount() > 0
                         else "Yes"))
        rows.append(("Zoom", "%d%%" % round(self.canvas.eff_zoom() * 100)))
        if self.canvas.rotation or self.canvas.flip_h or self.canvas.flip_v:
            bits = []
            if self.canvas.rotation:
                bits.append("rotated %d°" % (90 * self.canvas.rotation))
            if self.canvas.flip_h:
                bits.append("flipped H")
            if self.canvas.flip_v:
                bits.append("flipped V")
            rows.append(("View", ", ".join(bits)))
        rows.extend(format_exif(read_exif(p)))
        self.info_panel.show_rows(rows)

    def flash(self, msg):
        self.st_msg.setText(msg)
        self.flash_timer.start(2600)

    # ---- file actions
    def add_recent(self, path):
        rec = [p for p in self.settings["recent"] if os.path.normcase(p) != os.path.normcase(path)]
        self.settings["recent"] = [path] + rec[:14]
        self.save_settings_soon()

    def _start_dir(self):
        if self.folder:
            return self.folder
        if self.settings["recent"]:
            return os.path.dirname(self.settings["recent"][0])
        pics = os.path.join(os.path.expanduser("~"), "Pictures")
        return pics if os.path.isdir(pics) else os.path.expanduser("~")

    def open_dialog(self):
        pattern = " ".join("*" + e for e in sorted(self.exts))
        path, _ = QFileDialog.getOpenFileName(self.win, "Open image", self._start_dir(),
                                              "Images (%s);;All files (*)" % pattern)
        if path:
            self.open_path(path)

    def open_folder_dialog(self):
        path = QFileDialog.getExistingDirectory(self.win, "Open folder", self._start_dir())
        if path:
            self.open_path(path)

    def copy_image(self):
        img = self.canvas.transformed_image()
        if img is not None:
            QApplication.clipboard().setImage(img)
            if not self.markup.empty():
                self.markup.dirty = False
                self.flash("Image copied with your drawings")
            else:
                self.flash("Image copied")

    def copy_path(self):
        if self.current_path:
            self.copy_text(self.current_path)

    def open_containing(self):
        if self.current_path:
            open_in_file_manager(os.path.dirname(self.current_path))

    def save_as(self):
        img = self.canvas.transformed_image()
        if img is None:
            return False
        base, ext = os.path.splitext(os.path.basename(self.current_path))
        writable = {bytes(f).decode("ascii", "ignore").lower() for f in QImageWriter.supportedImageFormats()}
        ext = ext.lower() if ext.lower().lstrip(".") in writable else ".png"
        folder = os.path.dirname(self.current_path)
        if self.is_pasted(self.current_path):
            pics = os.path.join(os.path.expanduser("~"), "Pictures")
            folder = pics if os.path.isdir(pics) else os.path.expanduser("~")
            base = base.replace("Pasted", "Screenshot")
            start = os.path.join(folder, base + ext)
        else:
            start = os.path.join(folder, base + (" marked" if not self.markup.empty() else " copy") + ext)
        path, _ = QFileDialog.getSaveFileName(self.win, "Save a copy as", start,
                                              "PNG (*.png);;JPEG (*.jpg *.jpeg);;WebP (*.webp);;"
                                              "BMP (*.bmp);;All files (*)")
        if not path:
            return False
        if not os.path.splitext(path)[1]:
            path += ext
        fmt = os.path.splitext(path)[1].lstrip(".").lower()
        if fmt in ("jpg", "jpeg") and img.hasAlphaChannel():
            img = img.convertToFormat(QImage.Format.Format_RGB32)  # JPEG has no transparency
        if not img.save(path, None, 95 if fmt in ("jpg", "jpeg", "webp") else -1):
            self.error("Couldn't save", "Saving to %s didn't work." % os.path.basename(path),
                       detail="Check the file type and that the folder is writable.")
            return False
        self.markup.dirty = False
        self.flash("Saved %s" % os.path.basename(path))
        if self.movie is not None:
            self.flash("Saved the current frame as %s" % os.path.basename(path))
        return True

    def trash_current(self):
        if self.draw_mode:  # Delete while drawing removes the last drawing, not the file
            self.markup_undo()
            return
        p = self.current_path
        if not p:
            return
        if not self.markup_ok():
            return
        if self.settings["confirm_delete"]:
            if not self.ask("Move to trash?", 'Move "%s" to the trash?' % os.path.basename(p),
                            [("Move to trash", True, True), ("Cancel", None, False)],
                            detail="You can turn this question off in Preferences."):
                return
        self._stop_movie()
        try:
            res = QFile.moveToTrash(p)
            ok = res[0] if isinstance(res, tuple) else bool(res)
        except Exception:
            ok = False
        if not ok:
            if not self.ask("No trash here", "This drive doesn't have a trash. Delete the file for good?",
                            [("Delete", True, False), ("Cancel", None, True)], default=1):
                self.show_index(self.index, keep_view=True)
                return
            try:
                os.remove(p)
            except OSError as e:
                self.error("Couldn't delete", str(e))
                return
        self._forget(p)
        self.flash("Moved %s to the trash" % os.path.basename(p))

    def _forget(self, p):
        i = self.files.index(p) if p in self.files else self.index
        if p in self.files:
            self.files.remove(p)
        self.cache.pop(p, None)
        self.filmstrip.set_files(self.files)
        if self.files:
            self.show_index(min(i, len(self.files) - 1), force=True)
        else:
            self.close_image("No images left in this folder")

    def rename_current(self):
        p = self.current_path
        if not p:
            return
        d = Dialog(self, "Rename")
        d.setModal(True)
        d.body.addWidget(label("New name for this image:", "dim"))
        e = QLineEdit(os.path.basename(p))
        e.setMinimumWidth(340)
        d.body.addWidget(e)
        err = label("", "error", wrap=True)
        err.hide()
        d.body.addWidget(err)
        e.setSelection(0, len(os.path.splitext(os.path.basename(p))[0]))

        def go():
            msg = self.do_rename(p, e.text().strip())
            if msg:
                err.setText(msg)
                err.show()
                return
            d.accept()

        e.returnPressed.connect(go)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Cancel", d.reject))
        row.addWidget(button("Rename", go, accent=True))
        d.body.addLayout(row)
        e.setFocus()
        d.exec()

    def do_rename(self, p, new):
        bad = r'[\\/:*?"<>|]' if IS_WIN else r"/"
        if not new or new in (".", ".."):
            return "Type a name."
        if re.search(bad, new) or "\0" in new:
            return "Names can't contain %s" % (' \\ / : * ? " < > |' if IS_WIN else "/")
        if new == os.path.basename(p):
            return None
        dst = os.path.join(os.path.dirname(p), new)
        if os.path.exists(dst) and os.path.normcase(dst) != os.path.normcase(p):
            return '"%s" already exists in that folder.' % new
        try:
            os.rename(p, dst)
        except OSError as ex:
            return "Couldn't rename: %s" % (ex.strerror or ex)
        i = self.files.index(p) if p in self.files else -1
        if i >= 0:
            self.files[i] = dst
        if p in self.cache:
            self.cache[dst] = self.cache.pop(p)
        self.current_path = dst
        self.settings["recent"] = [dst if q == p else q for q in self.settings["recent"]]
        self.filmstrip.set_files(self.files)
        self.filmstrip.select(self.index)
        self.refresh_all()
        self.flash("Renamed to %s" % new)
        return None

    # ---- drawing
    def toggle_draw(self):
        if not self.draw_mode and self.canvas.img is None:
            self.flash("Open an image first")
            return
        self.draw_mode = not self.draw_mode
        self.canvas.drawing = None
        if self.movie is not None:
            self.movie.setPaused(self.draw_mode)
        if self.draw_mode and self.slideshow.isActive():
            self.toggle_slideshow()
        self.drawbar.sync()
        self.update_chrome()
        self.canvas.setCursor(self.canvas.idle_cursor())
        self.canvas.update()
        if self.draw_mode:
            self.flash("Drawing - drag on the image. Ctrl+C copies it, Esc when you're done")
        elif not self.markup.empty():
            self.flash("Your drawings stay until you go to another image")

    def markup_add(self, shape):
        self.markup.add(shape)
        self.drawbar.sync_history()
        self.canvas.update()

    def markup_undo(self):
        if self.markup.undo():
            self.drawbar.sync_history()
            self.canvas.update()

    def markup_redo(self):
        if self.markup.redo():
            self.drawbar.sync_history()
            self.canvas.update()

    def markup_clear(self):
        self.markup.clear()
        self.drawbar.sync_history()
        self.canvas.update()

    def reset_markup(self):
        self.markup.reset()
        self.canvas.drawing = None
        if hasattr(self, "drawbar"):
            self.drawbar.sync_history()

    def markup_ok(self, quitting=False):
        """True if it's fine to throw away the current drawings (asks if they haven't been saved/copied)."""
        if self.markup.empty() or not self.markup.dirty:
            return True
        what = "quitting" if quitting else "moving on"
        choice = self.ask("Keep your drawing?", "You drew on this image but haven't saved or copied it.",
                          [("Save a copy...", "save", True), ("Copy", "copy", False), ("Throw away", "discard", False),
                           ("Cancel", None, False)],
                          detail="Pick what to do with it before %s." % what)
        if choice == "save":
            return bool(self.save_as())
        if choice == "copy":
            self.copy_image()
            return True
        return choice == "discard"

    def can_overwrite(self):
        p = self.current_path
        if not p or self.canvas.img is None or self.movie is not None:
            return False
        ext = os.path.splitext(p)[1].lower().lstrip(".")
        writable = {bytes(f).decode("ascii", "ignore").lower() for f in QImageWriter.supportedImageFormats()}
        return ext in writable and ext not in ("svg", "svgz", "gif", "ico", "cur", "icns")

    def save_over_original(self):
        p = self.current_path
        if not self.can_overwrite():
            self.flash("Can't save over this kind of file - use Save a copy")
            return False
        if self.markup.empty() and not (self.canvas.rotation or self.canvas.flip_h or self.canvas.flip_v):
            self.flash("Nothing changed")
            return False
        if not self.ask("Save over the original?", 'Replace "%s" with this version?' % os.path.basename(p),
                        [("Replace", True, True), ("Cancel", None, False)],
                        detail="The drawings (and any rotation) get burned into the file. This can't be undone."):
            return False
        img = self.canvas.transformed_image()
        fmt = os.path.splitext(p)[1].lstrip(".").lower()
        if fmt in ("jpg", "jpeg") and img.hasAlphaChannel():
            img = img.convertToFormat(QImage.Format.Format_RGB32)
        tmp = p + ".slopview-tmp"
        if not img.save(tmp, fmt.upper() if fmt != "jpg" else "JPG", 95 if fmt in ("jpg", "jpeg", "webp") else -1):
            try:
                os.remove(tmp)
            except OSError:
                pass
            self.error("Couldn't save", "Saving over %s didn't work." % os.path.basename(p))
            return False
        try:
            shutil.copymode(p, tmp)
        except OSError:
            pass
        try:
            os.replace(tmp, p)
        except OSError as e:
            self.error("Couldn't save", str(e))
            return False
        self.cache.pop(p, None)
        self.thumb_cache = collections.OrderedDict((k, v) for k, v in self.thumb_cache.items() if k[0] != p)
        self.reset_markup()
        self.canvas.set_image(img, reset_view=False)
        self.canvas.rotation = 0
        self.canvas.flip_h = self.canvas.flip_v = False
        self.cache[p] = img
        self.filmstrip.load_visible() if hasattr(self.filmstrip, "load_visible") else None
        self.refresh_all()
        self.flash("Saved over %s" % os.path.basename(p))
        return True

    PASTE_DIR = os.path.join(tempfile.gettempdir(), "slopview-pastes")

    def is_pasted(self, path):
        return bool(path) and os.path.dirname(os.path.abspath(path)) == os.path.abspath(self.PASTE_DIR)

    def paste_image(self):
        cb = QApplication.clipboard()
        md = cb.mimeData()
        if md is not None and md.hasUrls():
            for u in md.urls():
                if u.isLocalFile() and (os.path.isdir(u.toLocalFile()) or self.is_image(u.toLocalFile())):
                    self.open_path(u.toLocalFile())
                    return
        img = cb.image()
        if img.isNull():
            self.flash("There's no image on the clipboard")
            return
        if not self.markup_ok():
            return
        os.makedirs(self.PASTE_DIR, exist_ok=True)
        now = time.time()
        for n in os.listdir(self.PASTE_DIR):  # tidy pastes older than two days
            f = os.path.join(self.PASTE_DIR, n)
            try:
                if now - os.path.getmtime(f) > 2 * 86400 and f != self.current_path:
                    os.remove(f)
            except OSError:
                pass
        path = os.path.join(self.PASTE_DIR, time.strftime("Pasted %Y-%m-%d %H-%M-%S.png"))
        k = 2
        while os.path.exists(path):
            path = os.path.join(self.PASTE_DIR, time.strftime("Pasted %Y-%m-%d %H-%M-%S") + " (%d).png" % k)
            k += 1
        if not img.save(path, "PNG"):
            self.error("Couldn't paste", "Saving the pasted image to a temporary file didn't work.")
            return
        self.open_path(path)
        self.flash("Pasted - press D to draw on it, Ctrl+S to save it")

    # ---- slideshow / escape
    def toggle_slideshow(self):
        if self.slideshow.isActive():
            self.slideshow.stop()
            self.flash("Slideshow stopped")
        elif len(self.files) > 1:
            self.slideshow.start(self.settings["slideshow_seconds"] * 1000)
            self.flash("Slideshow started - Esc to stop")
        self.update_status()

    def _slideshow_tick(self):
        if self.settings["slideshow_shuffle"]:
            self.go_random()
        elif not self.settings["loop_folder"] and self.index >= len(self.files) - 1:
            self.toggle_slideshow()
        else:
            self.go(1)

    def escape(self):
        if self.draw_mode:
            if self.canvas.drawing is not None:
                self.canvas.drawing = None
                self.canvas.update()
            else:
                self.toggle_draw()
        elif self.slideshow.isActive():
            self.toggle_slideshow()
        elif self.win.isFullScreen():
            self.toggle_fullscreen()

    # ---- help
    def show_shortcuts(self):
        d = Dialog(self, "Keyboard shortcuts")
        M = "Cmd+" if IS_MAC else "Ctrl+"
        rows = [
            ("Next / previous image", "Right / Left  (or Space / Backspace, mouse back/forward)"),
            ("First / last / random", "Home / End / X"), ("Zoom in / out", "+ / -  (or " + M + "scroll)"),
            ("Fit / actual size", "0 / 1  (or double-click)"), ("Pan", "Drag with the mouse"),
            ("Rotate right / left", "R / L"), ("Flip horizontal / vertical", "H / V"),
            ("Full screen", "F, F11, Enter or middle-click"), ("Slideshow", "S  (Esc stops)"),
            ("Filmstrip / info panel", "T / I"), ("All metadata", "M"),
            ("Draw on the image", "D  (Ctrl+Z undo, Shift for straight lines / perfect circles)"),
            ("Paste a screenshot", M + "V"), ("Copy image / copy path", M + "C / " + M + "Shift+C"),
            ("Save a copy (with rotation)", M + "S"), ("Rename / move to trash", "F2 / Delete"),
            ("Open file / folder", M + "O / " + M + "Shift+O"), ("Preferences", M + ","),
            ("Open images", "Drag them onto the window"),
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
        d = Dialog(self, "About SlopView")
        t = label(APP_NAME, "header")
        f = t.font()
        f.setPointSizeF(f.pointSizeF() + 6)
        t.setFont(f)
        d.body.addWidget(t)
        d.body.addWidget(label("Version %s" % VERSION, "dim"))
        d.body.addWidget(label("An image viewer vibe-coded by Claude for slopware.\n"
                               "The human who ships it has never read the code. Use accordingly."))
        link = QLabel('<a href="%s" style="color:%s">%s</a>' % (REPO_URL, self.theme["accent"], REPO_URL))
        link.setOpenExternalLinks(True)
        d.body.addWidget(link)
        from PySide6 import __version__ as pyside_version
        d.body.addWidget(label("Python %s  |  PySide6 %s  |  %s\nOpens: %s\nSettings: %s" % (
            platform.python_version(), pyside_version, platform.platform(),
            ", ".join(sorted(e.lstrip(".") for e in self.exts)), SETTINGS_PATH), "dim", wrap=True))
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Close", d.accept, accent=True))
        d.body.addLayout(row)
        d.show()

    # ---- single window, restart, quit
    def _on_client(self, srv):
        sock = srv.nextPendingConnection()
        if sock is None:
            return
        buf = bytearray()

        def done():
            try:
                files = json.loads(bytes(buf).decode("utf-8")).get("files", [])
            except ValueError:
                files = []
            sock.deleteLater()
            self.bring_to_front()
            for f in files[:1] or []:
                self.open_path(f)

        def read():
            buf.extend(bytes(sock.readAll()))
            if buf.endswith(b"\n"):
                done()

        sock.readyRead.connect(read)

    def restart(self):
        if not self.confirm_quit():
            return
        args = [sys.executable, SCRIPT_PATH] + ([self.current_path] if self.current_path else [])
        try:
            subprocess.Popen(args, close_fds=True)
        except OSError as e:
            self.error("Couldn't restart", str(e), detail="Start SlopView again yourself.")
        self._quitting = True
        self.qapp.quit()

    def confirm_quit(self):
        if not self.markup_ok(quitting=True):
            return False
        self.slideshow.stop()
        self._stop_movie()
        if self.win.isFullScreen():
            self.win.showNormal()
        self.store_window()
        self.save_settings()
        if self.server is not None:
            self.server.close()
        for d in list(self.dialogs):
            d.close()
        self.loader.shutdown()
        return True

    # ---- shared with SlopView
    def _want_frameless(self):
        if IS_MAC:
            return not self.settings["native_titlebar"]
        return not self.settings["native_titlebar"]

    def transparency_possible(self):
        return not (IS_WIN and self.settings["native_titlebar"])

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

    def on_window_state(self):
        if not hasattr(self, "shell"):
            return
        edge = 1 if (self.frameless and not self.win.isMaximized() and not self.win.isFullScreen()) else 0
        self.shell.lay.setContentsMargins(edge, edge, edge, edge)
        if self.win.isMaximized():
            self.titlebar.btn_max.set_kind("restore", "Restore")
        else:
            self.titlebar.btn_max.set_kind("max", "Maximize")
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

    def _sync_dialogs(self, key, value):
        for d in list(self.dialogs):
            try:
                d.sync(key, value)
            except RuntimeError:
                pass

    def save_settings_soon(self):
        if hasattr(self, "save_timer"):
            self.save_timer.start(700)

    def save_settings(self):
        if self._no_save:
            return
        try:
            self.settings.save()
        except Exception as e:
            self._log("Could not save settings: %s" % e)

    def open_config_folder(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        if not open_in_file_manager(CONFIG_DIR):
            self.info("Settings folder", CONFIG_DIR)

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

    @staticmethod
    def server_name():
        import hashlib
        return "slopview-" + hashlib.sha1(CONFIG_DIR.encode("utf-8")).hexdigest()[:12]

    def start_server(self):
        srv = QLocalServer(self.win)
        name = self.server_name()
        if not srv.listen(name):
            QLocalServer.removeServer(name)  # leftover from a crash
            if not srv.listen(name):
                return
        srv.newConnection.connect(lambda: self._on_client(srv))
        self.server = srv

    def bring_to_front(self):
        w = self.win
        if w.isMinimized():
            w.showNormal()
        w.show()
        w.raise_()
        w.activateWindow()

    def _refresh_install_label(self):
        a = getattr(self, "install_action", None)
        if a is not None:
            a.setText("Repair app menu / Open with..." if is_installed() else "Add to app menu / Open with...")

    def gui_install(self):
        where = "Start Menu" if IS_WIN else "app launcher"
        if not self.ask("Add SlopView to your system?",
                        "This adds SlopView to your %s and to \"Open with\" for images." % where,
                        [("Add it", True, True), ("Cancel", None, False)],
                        detail="Only your user account is changed (no admin needed). You can undo it any time "
                               "with Settings -> Uninstall SlopView. If you move slopview.py later, do this again."):
            return
        out = []
        ok = install(out)
        (self.info if ok else self.error)("Done!" if ok else "Something went wrong", "\n".join(out))

    def gui_uninstall(self):
        d = Dialog(self, "Uninstall SlopView")
        d.setModal(True)
        head = label("Uninstall SlopView?")
        head.setStyleSheet("font-weight: bold;")
        d.body.addWidget(head)
        d.body.addWidget(label("This removes SlopView from your %s and from \"Open with\"."
                               % ("Start Menu" if IS_WIN else "app launcher"), "dim", wrap=True))
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        t_set = Toggle(self, False)
        t_prog = Toggle(self, False)
        grid.addWidget(label("Also delete settings, custom themes and the error log"), 0, 0)
        grid.addWidget(t_set, 0, 1)
        grid.addWidget(label("Also delete the program file (slopview.py)"), 1, 0)
        grid.addWidget(t_prog, 1, 1)
        d.body.addLayout(grid)
        git = _git_checkout_dir()
        if git:
            t_prog.setEnabled(False)
            d.body.addWidget(label("slopview.py is inside a git repo, so it won't be deleted from here.",
                                   "dim", wrap=True))
        d.body.addWidget(label("Custom themes you didn't export will be gone for good if you delete settings.",
                               "dim", wrap=True))
        choice = {"go": False}

        def go():
            choice["go"] = True
            d.accept()

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Cancel", d.reject))
        row.addWidget(button("Uninstall", go, accent=True))
        d.body.addSpacing(8)
        d.body.addLayout(row)
        d.exec()
        if not choice["go"]:
            return
        rs, rp = t_set.isChecked(), t_prog.isChecked() and not git
        out = []
        uninstall(out, remove_settings=rs, remove_program=rp)
        if rs or rp:
            self._no_save = rs
            self.info("SlopView uninstalled", "\n".join(out),
                      detail="SlopView will close now." + ("" if rp else " Delete slopview.py whenever you like."))
            if self.confirm_quit():
                self._quitting = True
                self.qapp.quit()
        else:
            self.info("Removed from your system", "\n".join(out),
                      detail="SlopView itself still works - run it again any time.")

    def check_for_updates(self, silent=False):
        if self._update_busy:
            return
        self._update_busy = True
        self._update_result = None
        if not silent:
            self.flash("Checking for updates...")

        def work():
            self._update_result = check_update()

        threading.Thread(target=work, daemon=True).start()
        poll = QTimer(self.win)

        def tick():
            if self._update_result is None:
                return
            poll.stop()
            poll.deleteLater()
            self._update_busy = False
            self._on_update_result(self._update_result, silent)

        poll.timeout.connect(tick)
        poll.start(150)

    def _on_update_result(self, res, silent):
        self.settings["last_update_check"] = time.time()
        self.save_settings_soon()
        if res["status"] == "error":
            if not silent:
                self.error("Couldn't check for updates", res["error"])
            return
        if res["status"] == "current":
            if not silent:
                self.info("You're up to date", "SlopView %s is the newest version." % VERSION)
            return
        latest = res["latest"]
        if silent:
            self.st_msg.setText("Update available: v%s  (Settings -> Check for updates)" % latest)
            return
        if not self.ask("Update available", "SlopView %s is out (you have %s). Update now?" % (latest, VERSION),
                        [("Update", True, True), ("Later", None, False)],
                        detail="A backup of your current version is kept until the new one starts up fine."):
            return
        try:
            backup = apply_update(res["text"])
        except RuntimeError as e:  # git checkout (ValueError = permissions / bad download)
            if not self.ask("Use git instead?", str(e), [("Update anyway", True, False), ("Cancel", None, True)],
                            default=1):
                return
            try:
                backup = apply_update(res["text"], force=True)
            except Exception as e2:
                self.error("Update failed", str(e2))
                return
        except Exception as e:
            self.error("Update failed", str(e), detail="Nothing was changed.")
            return
        if self.ask("Updated to %s!" % latest, "Restart SlopView now to use the new version?",
                    [("Restart", True, True), ("Later", None, False)],
                    detail="Your old version is backed up at " + backup):
            self.restart()

    def _post_start_cleanup(self):
        try:
            old = cleanup_after_update()
        except Exception:
            old = None
        if old:
            self.flash("Updated from v%s to v%s \u2713" % (old, VERSION))
            self.flash_timer.start(8000)

    def _log(self, text):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write("\n[%s] SlopView %s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), VERSION, text))
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
            msg = label("SlopView hit an error. Screenshot this for the bug report:")
            msg.setStyleSheet("font-weight: bold;")
            d.body.addWidget(msg)
            box = QPlainTextEdit()
            box.setObjectName("errorbox")
            box.setReadOnly(True)
            box.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
            box.setMinimumSize(760, 260)
            box.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            box.setPlainText("SlopView %s | Python %s | PySide6 %s | %s\n\n%s" % (
                VERSION, platform.python_version(), pyside_version, platform.platform(), text))
            d.body.addWidget(box)
            if os.path.exists(BACKUP_PATH):
                d.body.addWidget(label("Broke right after an update? Your previous version is at %s - copy it over "
                                       "%s to roll back." % (BACKUP_PATH, SCRIPT_PATH), "dim", wrap=True))
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

    def store_window(self):
        try:
            self.settings["window_state"] = bytes(self.win.saveGeometry().toBase64()).decode("ascii")
        except Exception:
            pass

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

    def copy_text(self, s):
        QApplication.clipboard().setText(s)
        self.flash("Copied")

    def run(self):
        return self.qapp.exec()

    error = info


def hand_off_to_running(files):
    """If SlopView is already open, send it our image and return True."""
    sock = QLocalSocket()
    sock.connectToServer(App.server_name())
    if not sock.waitForConnected(400):
        return False
    payload = json.dumps({"files": [os.path.abspath(os.path.expanduser(f)) for f in files]}) + "\n"
    sock.write(payload.encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    code = run_cli(argv)
    if code is not None:
        return code
    qapp = QApplication(sys.argv[:1])
    if os.environ.get("SLOPVIEW_NEW_WINDOW") != "1" and hand_off_to_running(argv):
        return 0
    app = App(argv, qapp)
    app.start_server()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
