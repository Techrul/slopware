#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SlopPad - a vibe-coded text editor.
Part of slopware: https://github.com/Techrul/slopware

One file, Python standard library only (tkinter).
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
import webbrowser

try:
    import tkinter as tk
    from tkinter import colorchooser, filedialog
    from tkinter import font as tkfont
except ImportError:  # pragma: no cover - depends on the machine
    sys.stderr.write(
        "SlopPad needs tkinter, which isn't installed for this Python.\n"
        "  Debian/Ubuntu: sudo apt install python3-tk\n"
        "  Fedora:        sudo dnf install python3-tkinter\n"
        "  Arch/CachyOS:  sudo pacman -S tk\n"
        "  Windows/macOS: reinstall Python from python.org with 'tcl/tk' ticked\n"
    )
    sys.exit(1)

APP_NAME = "SlopPad"
APP_ID = "slopware.sloppad"
VERSION = "0.1.1"
REPO_URL = "https://github.com/Techrul/slopware"

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_X11 = not IS_WIN and not IS_MAC
MOD = "Command" if IS_MAC else "Control"
MOD_TXT = "Cmd+" if IS_MAC else "Ctrl+"
ALT_TXT = "Option+" if IS_MAC else "Alt+"
RIGHT_CLICK = "<Button-2>" if IS_MAC else "<Button-3>"
MIDDLE_CLICK = "<Button-3>" if IS_MAC else "<Button-2>"


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
    "alpha": 1.0,
    "topmost": False,
    "font_family": "",
    "font_size": 12,
    "font_bold": False,
    "line_spacing": 2,
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
    "geometry": "1100x720",
    "maximized": False,
    "monospace_only": True,
}

NUMERIC_LIMITS = {
    "font_size": (6, 96), "line_spacing": (0, 30), "ui_font_size": (7, 24),
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
        d["alpha"] = max(0.3, min(1.0, float(d["alpha"])))
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


# --------------------------------------------------------------------------
# Small utilities
# --------------------------------------------------------------------------

def wheel_steps(e):
    num = getattr(e, "num", None)
    if num == 4:
        return -1
    if num == 5:
        return 1
    d = getattr(e, "delta", 0) or 0
    if not d:
        return 0
    if IS_MAC:
        return -1 if d > 0 else 1
    steps = -int(d / 120)
    if steps == 0:
        steps = -1 if d > 0 else 1
    return steps


def bind_wheel(widget, fn):
    widget.bind("<MouseWheel>", fn, add="+")
    if IS_X11:
        widget.bind("<Button-4>", fn, add="+")
        widget.bind("<Button-5>", fn, add="+")


def set_titlebar(win, theme):
    """Windows 10/11: dark title bar; Windows 11: title bar matches the theme."""
    if not IS_WIN:
        return
    try:
        import ctypes
        win.update_idletasks()
        user32 = ctypes.windll.user32
        user32.GetParent.restype = ctypes.c_void_p
        hwnd = user32.GetParent(ctypes.c_void_p(win.winfo_id()))
        if not hwnd:
            return
        hwnd = ctypes.c_void_p(hwnd)
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(1 if luminance(theme["ui_bg"]) < 0.5 else 0)
        if dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark)) != 0:
            dwm.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dark), ctypes.sizeof(dark))

        def colorref(h):
            r, g, b = _rgb(h)
            return (b << 16) | (g << 8) | r

        for attr, key in ((35, "ui_bg"), (36, "ui_fg"), (34, "border")):
            c = ctypes.c_int(colorref(theme[key]))
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(c), ctypes.sizeof(c))
        # SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED -> repaint the frame
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
    except Exception:
        pass


class undo_block:
    """Group several edits into one undo step."""

    def __init__(self, text):
        self.t = text

    def __enter__(self):
        self.t.edit_separator()
        self.t.configure(autoseparators=False)
        return self

    def __exit__(self, *exc):
        self.t.configure(autoseparators=True)
        self.t.edit_separator()
        return False


class IndexConverter:
    """Turns Python string offsets into Tk text indices ("line.col")."""

    def __init__(self, content, utf16):
        self.content = content
        self.starts = [0]
        pos = content.find("\n")
        while pos != -1:
            self.starts.append(pos + 1)
            pos = content.find("\n", pos + 1)
        self.astral = utf16 and bool(re.search("[\U00010000-\U0010FFFF]", content))

    def __call__(self, off):
        line = bisect.bisect_right(self.starts, off) - 1
        start = self.starts[line]
        col = off - start
        if self.astral and col:
            seg = self.content[start:off]
            col = len(seg.encode("utf-16-le")) // 2
        return "%d.%d" % (line + 1, col)


_PROXY_TCL = r"""
namespace eval ::sloppad {}
proc ::sloppad::proxy {orig w args} {
    set result [uplevel 1 [linsert $args 0 $orig]]
    switch -exact -- [lindex $args 0] {
        insert - delete - replace {
            event generate $w <<SlopChange>> -when tail
        }
        mark {
            if {[lindex $args 1] eq "set" && [lindex $args 2] eq "insert"} {
                event generate $w <<SlopCursor>> -when tail
            }
        }
    }
    return $result
}
"""


def install_proxy(text_widget):
    """Wrap the Tk text command so we hear about every edit and cursor move."""
    w = str(text_widget)
    t = text_widget.tk
    t.eval(_PROXY_TCL)
    t.call("rename", w, w + "_sp_orig")
    t.call("interp", "alias", "", w, "", "::sloppad::proxy", w + "_sp_orig", w)


# --------------------------------------------------------------------------
# Custom widgets (all drawn by us so they look the same on every OS)
# --------------------------------------------------------------------------

def hoverable(app, w, kind):
    w._sp_role = kind

    def enter(_e):
        t = app.theme
        try:
            if kind == "accent_button":
                w.configure(bg=blend(t["accent"], "#ffffff", 0.18))
            elif kind == "dim_button":
                w.configure(bg=t["ui_hover"], fg=t["ui_fg"])
            else:
                w.configure(bg=t["ui_hover"])
        except tk.TclError:
            pass

    def leave(_e):
        app.paint_widget(w, recurse=False)

    w.bind("<Enter>", enter, add="+")
    w.bind("<Leave>", leave, add="+")
    return w


def make_button(app, parent, text, command, kind="button", padx=12, pady=4, font=None, tip=None):
    b = tk.Label(parent, text=text, font=font or app.ui_font, padx=padx, pady=pady,
                 cursor="hand2", highlightthickness=1 if kind in ("button", "accent_button") else 0)
    hoverable(app, b, kind)

    def release(e):
        if 0 <= e.x < b.winfo_width() and 0 <= e.y < b.winfo_height():
            command()

    b.bind("<ButtonRelease-1>", release)
    if tip:
        Tooltip(app, b, tip)
    return b


def make_entry(app, parent, var=None, width=20):
    e = tk.Entry(parent, textvariable=var, width=width, relief="flat", bd=4,
                 highlightthickness=1, font=app.ui_font)
    e._sp_role = "entry"
    return e


def make_label(app, parent, text, role="label", font=None, **kw):
    lbl = tk.Label(parent, text=text, font=font or app.ui_font, **kw)
    lbl._sp_role = role
    return lbl


def make_frame(parent, role="bg", **kw):
    f = tk.Frame(parent, bd=0, highlightthickness=0, **kw)
    f._sp_role = role
    return f


class Tooltip:
    def __init__(self, app, widget, text):
        self.app, self.w, self.text = app, widget, text
        self.job = None
        self.tip = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._leave, add="+")

    def _enter(self, _e):
        self._cancel()
        self.job = self.w.after(600, self._show)

    def _leave(self, _e=None):
        self._cancel()
        if self.tip is not None:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None

    def _cancel(self):
        if self.job:
            try:
                self.w.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None

    def _show(self):
        self.job = None
        if self.tip is not None or not self.w.winfo_exists():
            return
        t = self.app.theme
        tip = self.tip = tk.Toplevel(self.w)
        tip.wm_overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(tip, text=self.text, font=self.app.ui_font, bg=t["input_bg"], fg=t["ui_fg"],
                 padx=8, pady=4, highlightthickness=1, highlightbackground=t["border"]).pack()
        x = self.w.winfo_rootx() + 4
        y = self.w.winfo_rooty() + self.w.winfo_height() + 6
        tip.geometry("+%d+%d" % (x, y))


class FlatScrollbar(tk.Canvas):
    THICK = 12

    def __init__(self, master, app, orient, command, bg_key="bg"):
        self.vertical = orient == "vertical"
        kw = {"width": self.THICK} if self.vertical else {"height": self.THICK}
        super().__init__(master, highlightthickness=0, bd=0, **kw)
        self.app, self.command, self.bg_key = app, command, bg_key
        self._sp_role = "custom"
        self.first, self.last = 0.0, 1.0
        self.hover = False
        self.drag = None
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Enter>", lambda e: self._hov(True))
        self.bind("<Leave>", lambda e: self._hov(False))
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)
        bind_wheel(self, self._wheel)

    def apply_theme(self, t):
        self.configure(bg=t[self.bg_key])
        self.redraw()

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self.redraw()

    def _hov(self, v):
        self.hover = v
        self.redraw()

    def _len(self):
        return self.winfo_height() if self.vertical else self.winfo_width()

    def _thumb(self):
        length = max(1, self._len())
        span = max(0.0, min(1.0, self.last - self.first))
        size = min(float(length), max(28.0, span * length))
        free = length - size
        start = (self.first / (1.0 - span)) * free if span < 1.0 else 0.0
        start = max(0.0, min(free, start))
        return start, start + size, free, span

    def redraw(self):
        self.delete("all")
        if self.last - self.first >= 0.9999:
            return
        a, b, _, _ = self._thumb()
        t = self.app.theme
        active = self.hover or self.drag is not None
        color = t["scrollbar_hover"] if active else t["scrollbar"]
        w = 8 if active else 5
        c = self.THICK / 2.0
        r = w / 2.0 + 2
        if self.vertical:
            self.create_line(c, a + r, c, max(a + r, b - r), width=w, capstyle="round", fill=color)
        else:
            self.create_line(a + r, c, max(a + r, b - r), c, width=w, capstyle="round", fill=color)

    def _pos(self, e):
        return e.y if self.vertical else e.x

    def _press(self, e):
        if self.last - self.first >= 0.9999:
            return
        a, b, _, _ = self._thumb()
        p = self._pos(e)
        if a <= p <= b:
            self.drag = (p, self.first)
        else:
            self.command("scroll", 1 if p > b else -1, "pages")
        self.redraw()

    def _motion(self, e):
        if self.drag is None:
            return
        _, _, free, span = self._thumb()
        if free <= 0:
            return
        p0, f0 = self.drag
        self.command("moveto", f0 + (self._pos(e) - p0) / free * (1.0 - span))

    def _release(self, _e):
        self.drag = None
        self.redraw()

    def _wheel(self, e):
        s = wheel_steps(e)
        if s:
            self.command("scroll", s * 3, "units")
        return "break"


class Toggle(tk.Canvas):
    def __init__(self, master, app, value=False, command=None):
        super().__init__(master, width=40, height=22, highlightthickness=0, bd=0, cursor="hand2")
        self._sp_role = "custom"
        self.app, self.value, self.command = app, bool(value), command
        self.bind("<Button-1>", self._click)

    def _click(self, _e):
        self.set(not self.value)
        if self.command:
            self.command(self.value)

    def set(self, v):
        self.value = bool(v)
        self.redraw()

    def apply_theme(self, t):
        self.configure(bg=t["ui_bg"])
        self.redraw()

    def redraw(self):
        t = self.app.theme
        self.delete("all")
        on = self.value
        track = t["accent"] if on else blend(t["input_bg"], t["ui_fg"], 0.18)
        self.create_line(11, 11, 29, 11, width=18, capstyle="round", fill=track)
        x = 29 if on else 11
        knob = contrast_text(t["accent"]) if on else t["ui_fg"]
        self.create_oval(x - 6, 5, x + 6, 17, fill=knob, outline="")


class Slider(tk.Canvas):
    def __init__(self, master, app, lo, hi, value, command=None, length=200):
        super().__init__(master, width=length, height=22, highlightthickness=0, bd=0, cursor="hand2")
        self._sp_role = "custom"
        self.app, self.lo, self.hi, self.value, self.command = app, lo, hi, value, command
        self.bind("<Button-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<Configure>", lambda e: self.redraw())
        bind_wheel(self, self._wheel)

    def _frac(self):
        return (self.value - self.lo) / float(self.hi - self.lo)

    def _drag(self, e):
        pad = 9
        w = max(1, self.winfo_width() - 2 * pad)
        frac = max(0.0, min(1.0, (e.x - pad) / float(w)))
        self._set(int(round(self.lo + frac * (self.hi - self.lo))))

    def _wheel(self, e):
        s = wheel_steps(e)
        if s:
            self._set(self.value - s)
        return "break"

    def _set(self, v):
        v = max(self.lo, min(self.hi, v))
        if v != self.value:
            self.value = v
            self.redraw()
            if self.command:
                self.command(v)

    def set(self, v):
        self.value = max(self.lo, min(self.hi, v))
        self.redraw()

    def apply_theme(self, t):
        self.configure(bg=t["ui_bg"])
        self.redraw()

    def redraw(self):
        t = self.app.theme
        self.delete("all")
        pad = 9
        w = max(1, self.winfo_width())
        x = pad + self._frac() * (w - 2 * pad)
        self.create_line(pad, 11, w - pad, 11, width=4, capstyle="round",
                         fill=blend(t["input_bg"], t["ui_fg"], 0.18))
        self.create_line(pad, 11, x, 11, width=4, capstyle="round", fill=t["accent"])
        self.create_oval(x - 7, 4, x + 7, 18, fill=t["fg"], outline=t["accent"], width=2)


class NumberField(tk.Frame):
    def __init__(self, master, app, value, lo, hi, command=None):
        super().__init__(master, bd=0, highlightthickness=0)
        self._sp_role = "bg"
        self.app, self.value, self.lo, self.hi, self.command = app, value, lo, hi, command
        self.var = tk.StringVar(value=str(value))
        make_button(app, self, "-", lambda: self.bump(-1), padx=8, pady=1).pack(side="left")
        self.entry = make_entry(app, self, self.var, width=4)
        self.entry.configure(justify="center")
        self.entry.pack(side="left", padx=4)
        make_button(app, self, "+", lambda: self.bump(1), padx=8, pady=1).pack(side="left")
        self.entry.bind("<Return>", lambda e: self.commit())
        self.entry.bind("<FocusOut>", lambda e: self.commit())
        bind_wheel(self.entry, lambda e: (self.bump(-wheel_steps(e)), "break")[1])

    def bump(self, d):
        self.commit(self.value + d)

    def commit(self, v=None):
        if v is None:
            try:
                v = int(self.var.get().strip())
            except ValueError:
                v = self.value
        v = max(self.lo, min(self.hi, v))
        self.var.set(str(v))
        if v != self.value:
            self.value = v
            if self.command:
                self.command(v)

    def set(self, v):
        self.value = v
        self.var.set(str(v))


class Dropdown(tk.Label):
    def __init__(self, master, app, options, value, command=None, width=None):
        super().__init__(master, font=app.ui_font, padx=10, pady=4, cursor="hand2",
                         highlightthickness=1, anchor="w")
        if width:
            self.configure(width=width)
        hoverable(app, self, "button")
        self.app, self.options, self.command = app, options, command
        self.value = value
        self.var = tk.StringVar(value=value)
        self._menu = None
        self.set(value)
        self.bind("<Button-1>", self._open)

    def set(self, v):
        self.value = v
        self.var.set(v)
        self.configure(text="%s   ▾" % v)

    def _open(self, _e=None):
        if self._menu is not None:
            try:
                self._menu.destroy()
            except tk.TclError:
                pass
        m = self._menu = tk.Menu(self, tearoff=0)
        m._sp_role = "menu"
        self.app.style_menu(m)
        opts = self.options() if callable(self.options) else self.options
        for o in opts:
            m.add_radiobutton(label=o, value=o, variable=self.var, command=lambda o=o: self._choose(o))
        try:
            m.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height())
        finally:
            m.grab_release()

    def _choose(self, o):
        self.set(o)
        if self.command:
            self.command(o)


class Chip(tk.Label):
    """Little on/off button used in the find bar (Aa, W, .*)."""

    def __init__(self, master, app, text, command, tip=None):
        super().__init__(master, text=text, font=app.ui_font_bold, padx=6, pady=2, cursor="hand2")
        self._sp_role = "custom"
        self.app, self.active = app, False
        self.bind("<Button-1>", lambda e: command())
        if tip:
            Tooltip(app, self, tip)

    def set(self, v):
        self.active = v
        self.apply_theme(self.app.theme)

    def apply_theme(self, t):
        if self.active:
            self.configure(bg=t["accent"], fg=contrast_text(t["accent"]))
        else:
            self.configure(bg=t["input_bg"], fg=t["ui_dim"])


# --------------------------------------------------------------------------
# Dialogs
# --------------------------------------------------------------------------

class Dialog(tk.Toplevel):
    def __init__(self, app, title, resizable=False):
        super().__init__(app.root)
        self.withdraw()
        self.app = app
        self._sp_role = "bg"
        self.title(title)
        self.transient(app.root)
        self.resizable(resizable, resizable)
        self.body = make_frame(self, padx=20, pady=16)
        self.body.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())
        app.dialogs.append(self)

    def show(self, modal=False, focus=None):
        self.app.paint_widget(self)
        self.update_idletasks()
        root = self.app.root
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = root.winfo_rootx() + (root.winfo_width() - w) // 2
        y = root.winfo_rooty() + (root.winfo_height() - h) // 3
        x = max(0, min(x, self.winfo_screenwidth() - w))
        y = max(0, min(y, self.winfo_screenheight() - h))
        self.geometry("+%d+%d" % (x, y))
        self.deiconify()
        if self.app.settings["topmost"]:
            try:
                self.attributes("-topmost", True)
            except tk.TclError:
                pass
        set_titlebar(self, self.app.theme)
        if modal:
            try:
                self.wait_visibility()
                self.grab_set()
            except tk.TclError:
                pass
        (focus or self).focus_set()

    def on_theme(self):
        pass

    def close(self):
        if self in self.app.dialogs:
            self.app.dialogs.remove(self)
        try:
            self.grab_release()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass


class PrefsWindow(Dialog):
    def __init__(self, app):
        super().__init__(app, "Preferences", resizable=True)
        self.controls = {}
        s = app.settings
        cols = make_frame(self.body)
        cols.pack(fill="both", expand=True)
        left, right = make_frame(cols), make_frame(cols)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 30))
        right.grid(row=0, column=1, sticky="nsew")
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=1)
        cols.rowconfigure(0, weight=1)
        self._row = {}

        # ---- look
        self.section(left, "LOOK")
        f = make_frame(left)
        dd = Dropdown(f, app, app.theme_names, s["theme"], app.set_theme, width=18)
        dd.pack(side="left")
        make_button(app, f, "Edit...", app.open_theme_editor, padx=10).pack(side="left", padx=(6, 0))
        self.controls["theme"] = dd
        self.row(left, "Theme", f)

        f = make_frame(left)
        pct = int(round(s["alpha"] * 100))
        self.alpha_lbl = make_label(app, f, "%d%%" % pct, role="dim", width=5, anchor="e")
        sl = Slider(f, app, 30, 100, pct, self._alpha, length=170)
        sl.pack(side="left")
        self.alpha_lbl.pack(side="left")
        self.controls["alpha"] = sl
        self.row(left, "Opacity", f)
        self.toggle_row(left, "Always on top", "topmost")

        # ---- font
        self.section(left, "EDITOR FONT")
        ff = make_frame(left)
        top = make_frame(ff)
        top.pack(fill="x")
        self.font_filter = tk.StringVar()
        fe = make_entry(app, top, self.font_filter, width=18)
        fe.pack(side="left")
        Tooltip(app, fe, "Type to filter fonts")
        self.mono = Toggle(top, app, s["monospace_only"], self._mono_changed)
        self.mono.pack(side="right")
        make_label(app, top, "Monospace only", role="dim").pack(side="right", padx=6)
        lf = make_frame(ff, role="custom")
        lf.apply_theme = lambda t, lf=lf: lf.configure(bg=t["input_bg"], highlightbackground=t["border"])
        lf.configure(highlightthickness=1)
        lf.pack(fill="both", expand=True, pady=(6, 0))
        self.lb = tk.Listbox(lf, height=8, activestyle="none", relief="flat", bd=0,
                             highlightthickness=0, exportselection=False, font=app.ui_font)
        self.lb._sp_role = "listbox"
        sb = FlatScrollbar(lf, app, "vertical", self.lb.yview, bg_key="input_bg")
        self.lb.configure(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        sb.pack(side="right", fill="y")
        self.lb.bind("<<ListboxSelect>>", self._font_picked)
        self.preview = tk.Label(ff, text="SlopPad 0O 1lI {}[]() => != ~", font=app.editor_font,
                                anchor="w", pady=8)
        self.preview._sp_role = "label"
        self.preview.pack(fill="x")
        self.wide_row(left, ff)
        self.font_filter.trace_add("write", lambda *a: self.fill_fonts())
        self.number_row(left, "Size", "font_size")
        self.toggle_row(left, "Bold", "font_bold")
        self.number_row(left, "Line spacing", "line_spacing")

        # ---- editing
        self.section(right, "EDITING")
        self.number_row(right, "Tab width", "tab_width")
        self.toggle_row(right, "Indent with spaces", "insert_spaces")
        self.toggle_row(right, "Auto-indent", "auto_indent")
        self.toggle_row(right, "Word wrap", "wrap")

        self.section(right, "DISPLAY")
        self.toggle_row(right, "Line numbers", "line_numbers")
        self.toggle_row(right, "Highlight current line", "highlight_line")
        self.toggle_row(right, "Block cursor", "block_cursor")
        self.toggle_row(right, "Blinking cursor", "cursor_blink")
        self.number_row(right, "Cursor width", "cursor_width")
        self.number_row(right, "Padding", "padding")
        self.toggle_row(right, "Status bar", "status_bar")

        self.section(right, "INTERFACE")
        self.number_row(right, "UI font size", "ui_font_size")
        self.toggle_row(right, "Use editor font for UI", "ui_use_editor_font")
        dd = Dropdown(right, app, ["LF", "CRLF"], s["default_newline"],
                      lambda v: app.set_setting("default_newline", v), width=6)
        self.controls["default_newline"] = dd
        self.row(right, "New file line endings", dd)
        self.toggle_row(right, "Reopen files on startup", "restore_session")

        # ---- buttons
        bar = make_frame(self.body)
        bar.pack(fill="x", pady=(18, 0))
        make_button(app, bar, "Open settings folder", app.open_config_folder).pack(side="left")
        make_button(app, bar, "Reset everything...", app.reset_settings).pack(side="left", padx=6)
        make_button(app, bar, "Done", self.close, kind="accent_button", padx=18).pack(side="right")

        self.fill_fonts()
        self.show()

    # layout helpers
    def _next(self, parent):
        r = self._row.get(parent, 0)
        self._row[parent] = r + 1
        return r

    def section(self, parent, title):
        r = self._next(parent)
        make_label(self.app, parent, title, role="header", font=self.app.ui_font_bold).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(16 if r else 0, 6))

    def row(self, parent, label, widget):
        r = self._next(parent)
        make_label(self.app, parent, label).grid(row=r, column=0, sticky="w", pady=4)
        widget.grid(row=r, column=1, sticky="e", pady=4, padx=(16, 0))
        parent.columnconfigure(1, weight=1)

    def wide_row(self, parent, widget):
        r = self._next(parent)
        widget.grid(row=r, column=0, columnspan=2, sticky="nsew", pady=4)
        parent.rowconfigure(r, weight=1)

    def toggle_row(self, parent, label, key):
        t = Toggle(parent, self.app, self.app.settings[key], lambda v, k=key: self.app.set_setting(k, v))
        self.controls[key] = t
        self.row(parent, label, t)

    def number_row(self, parent, label, key):
        lo, hi = NUMERIC_LIMITS[key]
        n = NumberField(parent, self.app, self.app.settings[key], lo, hi,
                        lambda v, k=key: self.app.set_setting(k, v))
        self.controls[key] = n
        self.row(parent, label, n)

    # behaviour
    def _alpha(self, pct):
        self.alpha_lbl.configure(text="%d%%" % pct)
        self.app.set_setting("alpha", pct / 100.0)

    def _mono_changed(self, v):
        self.app.set_setting("monospace_only", v)
        self.fill_fonts()

    def fill_fonts(self):
        q = self.font_filter.get().strip().lower()
        fams = self.app.mono_fonts() if self.mono.value else self.app.font_families()
        self.items = [f for f in fams if q in f.lower()]
        self.lb.delete(0, "end")
        for f in self.items:
            self.lb.insert("end", f)
        cur = self.app.editor_font.cget("family")
        if cur in self.items:
            i = self.items.index(cur)
            self.lb.selection_set(i)
            self.lb.see(i)

    def _font_picked(self, _e=None):
        sel = self.lb.curselection()
        if sel:
            self.app.set_setting("font_family", self.items[sel[0]])

    def sync(self, key, value):
        c = self.controls.get(key)
        if c is None:
            return
        if key == "alpha":
            pct = int(round(value * 100))
            c.set(pct)
            self.alpha_lbl.configure(text="%d%%" % pct)
        else:
            c.set(value)

    def close(self):
        self.app.prefs_window = None
        super().close()


class ThemeEditor(Dialog):
    def __init__(self, app):
        super().__init__(app, "Theme editor")
        self.orig_name = app.settings["theme"]
        self.work = dict(app.theme)
        self.saved = False
        custom = app.settings["custom_themes"]
        default_name = self.orig_name if self.orig_name in custom else self.orig_name + " (custom)"

        top = make_frame(self.body)
        top.pack(fill="x")
        make_label(app, top, "Theme name").pack(side="left")
        self.name_var = tk.StringVar(value=default_name)
        make_entry(app, top, self.name_var, width=30).pack(side="left", padx=10)
        make_label(app, self.body, "Click a swatch to pick a color, or type a hex code and press Enter. "
                   "Everything previews live.", role="dim", wraplength=620, justify="left").pack(
            fill="x", pady=(10, 12))

        grid = make_frame(self.body)
        grid.pack(fill="x")
        self.swatches, self.vars = {}, {}
        half = (len(THEME_KEYS) + 1) // 2
        for i, (key, label) in enumerate(THEME_KEYS):
            col, r = (0, i) if i < half else (1, i - half)
            base = col * 3
            sw = tk.Label(grid, width=4, cursor="hand2", relief="flat", highlightthickness=1)
            sw.grid(row=r, column=base, padx=((0 if col == 0 else 28), 8), pady=3, sticky="w")
            sw.bind("<Button-1>", lambda e, k=key: self.pick(k))
            make_label(app, grid, label, anchor="w").grid(row=r, column=base + 1, sticky="w")
            var = tk.StringVar(value=self.work[key])
            ent = make_entry(app, grid, var, width=9)
            ent.grid(row=r, column=base + 2, padx=(8, 0), sticky="e")
            ent.bind("<Return>", lambda e, k=key: self.commit_hex(k))
            ent.bind("<FocusOut>", lambda e, k=key: self.commit_hex(k))
            self.swatches[key], self.vars[key] = sw, var

        bar = make_frame(self.body)
        bar.pack(fill="x", pady=(18, 0))
        make_button(app, bar, "Import...", self.import_theme).pack(side="left")
        make_button(app, bar, "Export...", self.export_theme).pack(side="left", padx=6)
        make_button(app, bar, "Reset", self.reset).pack(side="left")
        if self.orig_name in custom:
            make_button(app, bar, "Delete", self.delete).pack(side="left", padx=6)
        make_button(app, bar, "Save theme", self.save, kind="accent_button", padx=18).pack(side="right")
        make_button(app, bar, "Cancel", self.close).pack(side="right", padx=6)
        self.refresh_swatches()
        self.show()

    def refresh_swatches(self):
        for k, sw in self.swatches.items():
            sw.configure(bg=self.work[k], highlightbackground=self.app.theme["border"],
                         highlightcolor=self.app.theme["border"])
            self.vars[k].set(self.work[k])

    def on_theme(self):
        self.refresh_swatches()

    def pick(self, key):
        res = colorchooser.askcolor(color=self.work[key], parent=self, title=dict(THEME_KEYS)[key])
        if res and res[1]:
            self.set_color(key, res[1])

    def commit_hex(self, key):
        v = norm_hex(self.vars[key].get())
        if v and v != self.work[key]:
            self.set_color(key, v)
        elif not v:
            self.vars[key].set(self.work[key])

    def set_color(self, key, value):
        v = norm_hex(value)
        if not v:
            return
        self.work[key] = v
        self.app.preview_theme(self.work)

    def reset(self):
        self.work = dict(self.app.resolve_theme(self.orig_name))
        self.app.preview_theme(self.work)

    def import_theme(self):
        path = filedialog.askopenfilename(parent=self, title="Import theme",
                                          filetypes=[("Theme files", "*.json"), ("All files", "*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            colors = data.get("colors", data) if isinstance(data, dict) else None
            if not isinstance(colors, dict) or not any(norm_hex(colors.get(k)) for k, _ in THEME_KEYS):
                raise ValueError("No SlopPad colors found in that file.")
        except Exception as e:
            self.app.error("Couldn't import theme", str(e), parent=self)
            return
        self.work = complete_theme(colors)
        name = data.get("name") if isinstance(data.get("name"), str) else None
        self.name_var.set(name or os.path.splitext(os.path.basename(path))[0])
        self.app.preview_theme(self.work)

    def export_theme(self):
        self.app.export_theme(self.name_var.get().strip() or "My theme", self.work, parent=self)

    def delete(self):
        name = self.orig_name
        if self.app.ask("Delete theme", 'Delete the theme "%s"?' % name,
                        [("Delete", True, "accent_button"), ("Cancel", None, "button")], parent=self):
            self.app.settings["custom_themes"].pop(name, None)
            self.saved = True
            self.app.set_theme(DEFAULT_THEME)
            self.close()

    def save(self):
        name = self.name_var.get().strip() or "My theme"
        if name in BUILTIN_THEMES:
            name += " (custom)"
        self.app.settings["custom_themes"][name] = dict(self.work)
        self.saved = True
        self.app.set_theme(name)
        self.app.flash('Saved theme "%s"' % name)
        self.close()

    def close(self):
        self.app.theme_editor = None
        if self in self.app.dialogs:
            self.app.dialogs.remove(self)
        if not self.saved:
            self.app.set_theme(self.app.settings["theme"])  # undo the live preview
        super().close()


# --------------------------------------------------------------------------
# Editor tab
# --------------------------------------------------------------------------

class EditorTab:
    def __init__(self, app, path=None):
        self.app = app
        self.path = path
        self.encoding, self.bom = "UTF-8", False
        self.newline = app.settings["default_newline"]
        self.version = 0
        self.shown_modified = False
        self._gutter_pending = False
        self._gutter_width = 0
        self._gutter_anchor = None
        app.untitled_counter += 1
        self.untitled_no = app.untitled_counter

        f = self.frame = tk.Frame(app.editor_area, bd=0, highlightthickness=0)
        f._sp_role = "custom"
        f.apply_theme = self.apply_theme
        self.gutter = tk.Canvas(f, width=40, highlightthickness=0, bd=0)
        t = self.text = tk.Text(f, undo=True, autoseparators=True, maxundo=-1, bd=0, relief="flat",
                                highlightthickness=0, font=app.editor_font, wrap="none",
                                exportselection=True, width=1, height=1)
        t._sp_editor = True
        install_proxy(t)
        self.vbar = FlatScrollbar(f, app, "vertical", t.yview)
        self.hbar = FlatScrollbar(f, app, "horizontal", t.xview)
        t.configure(yscrollcommand=self._yscroll, xscrollcommand=self.hbar.set)
        self.gutter.grid(row=0, column=0, sticky="ns")
        t.grid(row=0, column=1, sticky="nsew")
        self.vbar.grid(row=0, column=2, sticky="ns")
        self.hbar.grid(row=1, column=1, sticky="ew")
        f.rowconfigure(0, weight=1)
        f.columnconfigure(1, weight=1)

        t.tag_configure("curline")
        t.tag_configure("match")
        t.tag_configure("curmatch")
        t.tag_lower("curline")
        t.tag_raise("sel")
        try:
            t.configure(insertunfocussed="hollow")
        except tk.TclError:
            pass

        t.bindtags((str(t), "SlopKeys") + t.bindtags()[1:])
        t.bind("<<SlopChange>>", lambda e: app.on_text_change(self))
        t.bind("<<SlopCursor>>", lambda e: app.on_cursor(self))
        t.bind("<<Selection>>", lambda e: app.on_cursor(self))
        t.bind("<Configure>", lambda e: self.schedule_gutter())
        t.bind("<Tab>", self.on_tab)
        t.bind("<Shift-Tab>", self.on_shift_tab)
        try:
            t.bind("<ISO_Left_Tab>", self.on_shift_tab)
        except tk.TclError:
            pass
        t.bind("<Return>", self.on_return)
        t.bind("<KP_Enter>", self.on_return)
        t.bind("<BackSpace>", self.on_backspace)
        t.bind("<Home>", self.on_home)
        t.bind("<<Paste>>", self.paste)
        t.bind("<Escape>", lambda e: app.findbar.hide() if app.findbar.visible else None)
        for seq, d in (("<Alt-Up>", -1), ("<Alt-Down>", 1)):
            t.bind(seq, lambda e, d=d: (self.move_lines(d), "break")[1])
        if IS_MAC:
            for seq, d in (("<Option-Up>", -1), ("<Option-Down>", 1)):
                try:
                    t.bind(seq, lambda e, d=d: (self.move_lines(d), "break")[1])
                except tk.TclError:
                    pass
        t.bind(RIGHT_CLICK, self.context_menu)
        if IS_MAC:
            t.bind("<Control-Button-1>", self.context_menu)
        zoom_seqs = ["<Control-MouseWheel>"]
        if IS_X11:
            zoom_seqs += ["<Control-Button-4>", "<Control-Button-5>"]
        if IS_MAC:
            zoom_seqs += ["<Command-MouseWheel>"]
        for seq in zoom_seqs:
            t.bind(seq, self._zoom_wheel)

        bind_wheel(self.gutter, self._gutter_wheel)
        self.gutter.bind("<Button-1>", self._gutter_press)
        self.gutter.bind("<B1-Motion>", self._gutter_drag)

        self.apply_settings()
        self.apply_theme(app.theme)

    # ---- basics
    def title(self):
        return os.path.basename(self.path) if self.path else "Untitled-%d" % self.untitled_no

    def is_modified(self):
        try:
            return bool(self.text.tk.getboolean(self.text.edit_modified()))
        except tk.TclError:
            return False

    def set_modified(self, v):
        self.text.edit_modified(bool(v))
        self.app.refresh_modified(self)

    def is_pristine(self):
        return not self.path and not self.is_modified() and self.text.compare("end-1c", "==", "1.0")

    def content(self):
        return self.text.get("1.0", "end-1c")

    def set_content(self, content):
        t = self.text
        t.delete("1.0", "end")
        t.insert("1.0", content)
        t.edit_reset()
        t.edit_modified(False)
        t.mark_set("insert", "1.0")
        t.see("1.0")

    def destroy(self):
        w = str(self.text)
        self.frame.destroy()
        try:
            self.app.root.tk.call("rename", w, "")
        except tk.TclError:
            pass

    # ---- settings / theme
    def apply_settings(self):
        s = self.app.settings
        t = self.text
        ls = s["line_spacing"]
        t.configure(
            wrap="word" if s["wrap"] else "none",
            insertwidth=s["cursor_width"],
            insertontime=600,
            insertofftime=300 if s["cursor_blink"] else 0,
            padx=s["padding"], pady=max(2, s["padding"] // 2),
            spacing1=ls // 2, spacing3=ls - ls // 2, spacing2=ls,
            tabs=(self.app.editor_font.measure(" " * s["tab_width"]),),
        )
        try:
            t.configure(blockcursor=s["block_cursor"], tabstyle="wordprocessor")
        except tk.TclError:
            pass
        if s["line_numbers"]:
            self.gutter.grid()
        else:
            self.gutter.grid_remove()
        if s["wrap"]:
            self.hbar.grid_remove()
        else:
            self.hbar.grid()
        self._gutter_width = 0
        self.update_curline()
        self.schedule_gutter()

    def apply_theme(self, th):
        t = self.text
        self.frame.configure(bg=th["bg"])
        t.configure(bg=th["bg"], fg=th["fg"], insertbackground=th["cursor"],
                    selectbackground=th["selection_bg"], selectforeground=th["selection_fg"],
                    inactiveselectbackground=th["selection_bg"])
        t.tag_configure("curline", background=th["current_line"])
        t.tag_configure("match", background=th["match_bg"])
        t.tag_configure("curmatch", background=th["current_match_bg"],
                        foreground=contrast_text(th["current_match_bg"]))
        self.gutter.configure(bg=th["gutter_bg"])
        self.vbar.apply_theme(th)
        self.hbar.apply_theme(th)
        self.schedule_gutter()

    # ---- gutter
    def _yscroll(self, first, last):
        self.vbar.set(first, last)
        self.schedule_gutter()

    def schedule_gutter(self):
        if not self._gutter_pending:
            self._gutter_pending = True
            self.text.after_idle(self.redraw_gutter)

    def redraw_gutter(self):
        self._gutter_pending = False
        c, t = self.gutter, self.text
        try:
            c.delete("all")
        except tk.TclError:
            return
        if not self.app.settings["line_numbers"]:
            return
        th = self.app.theme
        font = self.app.editor_font
        last = int(t.index("end-1c").split(".")[0])
        width = font.measure("9" * max(3, len(str(last)))) + 22
        if width != self._gutter_width:
            self._gutter_width = width
            c.configure(width=width)
        cur = int(t.index("insert").split(".")[0])
        ascent = font.metrics("ascent")
        idx = t.index("@0,0")
        if not idx.endswith(".0"):
            idx = t.index(idx + " linestart +1line")
        guard = 0
        while guard < 2000:
            guard += 1
            ln = int(idx.split(".")[0])
            if ln > last:
                break
            d = t.dlineinfo(idx)
            if d is None:
                break
            y = d[1] + d[4] - ascent
            c.create_text(width - 12, y, anchor="ne", text=str(ln), font=font,
                          fill=th["gutter_active"] if ln == cur else th["gutter_fg"])
            idx = "%d.0" % (ln + 1)

    def _gutter_wheel(self, e):
        s = wheel_steps(e)
        if s:
            self.text.yview_scroll(s * 3, "units")
        return "break"

    def _gutter_line(self, e):
        return int(self.text.index("@0,%d" % e.y).split(".")[0])

    def _gutter_press(self, e):
        ln = self._gutter_line(e)
        self._gutter_anchor = ln
        self._select_lines(ln, ln)

    def _gutter_drag(self, e):
        if self._gutter_anchor is not None:
            ln = self._gutter_line(e)
            self._select_lines(min(ln, self._gutter_anchor), max(ln, self._gutter_anchor))

    def _select_lines(self, a, b):
        t = self.text
        t.tag_remove("sel", "1.0", "end")
        t.tag_add("sel", "%d.0" % a, "%d.0+1line" % b)
        t.mark_set("insert", "%d.0+1line" % b)
        t.focus_set()

    # ---- current line
    def update_curline(self):
        t = self.text
        t.tag_remove("curline", "1.0", "end")
        if self.app.settings["highlight_line"] and not t.tag_ranges("sel"):
            t.tag_add("curline", "insert linestart", "insert linestart+1line")

    # ---- editing helpers
    def _unit(self):
        s = self.app.settings
        return " " * s["tab_width"] if s["insert_spaces"] else "\t"

    def _sel_lines(self):
        t = self.text
        if t.tag_ranges("sel"):
            first, last = t.index("sel.first"), t.index("sel.last")
            a, b = int(first.split(".")[0]), int(last.split(".")[0])
            if b > a and last.endswith(".0"):
                b -= 1
            return a, b, True
        ln = int(t.index("insert").split(".")[0])
        return ln, ln, False

    def _reselect(self, a, b):
        t = self.text
        t.tag_remove("sel", "1.0", "end")
        t.tag_add("sel", "%d.0" % a, "%d.end" % b)
        t.mark_set("insert", "%d.end" % b)

    def indent(self, a, b):
        t, unit = self.text, self._unit()
        with undo_block(t):
            for ln in range(a, b + 1):
                if t.get("%d.0" % ln, "%d.end" % ln).strip():
                    t.insert("%d.0" % ln, unit)
        self._reselect(a, b)

    def dedent(self, a, b, reselect):
        t, tw = self.text, self.app.settings["tab_width"]
        with undo_block(t):
            for ln in range(a, b + 1):
                line = t.get("%d.0" % ln, "%d.end" % ln)
                if line.startswith("\t"):
                    n = 1
                else:
                    n = min(len(line) - len(line.lstrip(" ")), tw)
                if n:
                    t.delete("%d.0" % ln, "%d.%d" % (ln, n))
        if reselect:
            self._reselect(a, b)

    def on_tab(self, _e=None):
        t, s = self.text, self.app.settings
        if t.tag_ranges("sel"):
            a, b, _ = self._sel_lines()
            if a != b or t.get("sel.first", "sel.last").endswith("\n"):
                self.indent(a, b)
                return "break"
            t.delete("sel.first", "sel.last")
        if s["insert_spaces"]:
            col = int(t.index("insert").split(".")[1])
            t.insert("insert", " " * (s["tab_width"] - col % s["tab_width"]))
        else:
            t.insert("insert", "\t")
        t.see("insert")
        return "break"

    def on_shift_tab(self, _e=None):
        a, b, had = self._sel_lines()
        self.dedent(a, b, had)
        return "break"

    def on_return(self, _e=None):
        t, s = self.text, self.app.settings
        if not s["auto_indent"]:
            return None
        left = t.get("insert linestart", "insert")
        indent = re.match(r"[ \t]*", left).group(0)
        if left.rstrip().endswith((":", "{", "[", "(")):
            indent += self._unit()
        with undo_block(t):
            if t.tag_ranges("sel"):
                t.delete("sel.first", "sel.last")
            t.insert("insert", "\n" + indent)
        t.see("insert")
        return "break"

    def on_backspace(self, _e=None):
        t, s = self.text, self.app.settings
        if t.tag_ranges("sel") or not s["insert_spaces"]:
            return None
        left = t.get("insert linestart", "insert")
        if len(left) >= 2 and left.strip(" ") == "":
            n = len(left) % s["tab_width"] or s["tab_width"]
            t.delete("insert-%dc" % n, "insert")
            return "break"
        return None

    def on_home(self, _e=None):
        t = self.text
        line = t.get("insert linestart", "insert lineend")
        first = len(line) - len(line.lstrip(" \t"))
        col = int(t.index("insert").split(".")[1])
        target = 0 if col == first else first
        t.tag_remove("sel", "1.0", "end")
        t.mark_set("insert", "insert linestart+%dc" % target)
        t.see("insert")
        return "break"

    def paste(self, _e=None):
        t = self.text
        try:
            data = t.clipboard_get()
        except tk.TclError:
            return "break"
        data = data.replace("\r\n", "\n").replace("\r", "\n")
        with undo_block(t):
            if t.tag_ranges("sel"):
                t.delete("sel.first", "sel.last")
            t.insert("insert", data)
        t.see("insert")
        return "break"

    def cut(self):
        self.text.event_generate("<<Cut>>")

    def copy(self):
        self.text.event_generate("<<Copy>>")

    def undo(self):
        try:
            self.text.edit_undo()
        except tk.TclError:
            pass
        self.text.see("insert")
        self.app.on_text_change(self)

    def redo(self):
        try:
            self.text.edit_redo()
        except tk.TclError:
            pass
        self.text.see("insert")
        self.app.on_text_change(self)

    def select_all(self):
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "end-1c")

    def select_line(self):
        a, b, _ = self._sel_lines()
        self._select_lines(a, b)

    def duplicate(self):
        t = self.text
        with undo_block(t):
            if t.tag_ranges("sel"):
                data = t.get("sel.first", "sel.last")
                end = t.index("sel.last")
                t.insert(end, data)
            else:
                line = t.get("insert linestart", "insert lineend")
                t.insert("insert lineend", "\n" + line)
                t.mark_set("insert", "insert+1line")
        t.see("insert")

    def delete_line(self):
        t = self.text
        a, b, _ = self._sel_lines()
        last = int(t.index("end-1c").split(".")[0])
        with undo_block(t):
            if b < last:
                t.delete("%d.0" % a, "%d.0" % (b + 1))
            elif a > 1:
                t.delete("%d.end" % (a - 1), "%d.end" % b)
            else:
                t.delete("1.0", "end-1c")
        t.tag_remove("sel", "1.0", "end")
        t.see("insert")

    def move_lines(self, d):
        t = self.text
        a, b, had = self._sel_lines()
        last = int(t.index("end-1c").split(".")[0])
        if (d < 0 and a <= 1) or (d > 0 and b >= last):
            return
        ins_line, ins_col = map(int, t.index("insert").split("."))
        block = t.get("%d.0" % a, "%d.end" % b)
        with undo_block(t):
            if d < 0:
                above = t.get("%d.0" % (a - 1), "%d.end" % (a - 1))
                t.delete("%d.0" % (a - 1), "%d.end" % b)
                t.insert("%d.0" % (a - 1), block + "\n" + above)
            else:
                below = t.get("%d.0" % (b + 1), "%d.end" % (b + 1))
                t.delete("%d.0" % a, "%d.end" % (b + 1))
                t.insert("%d.0" % a, below + "\n" + block)
        if had:
            t.tag_remove("sel", "1.0", "end")
            t.tag_add("sel", "%d.0" % (a + d), "%d.end" % (b + d))
        t.mark_set("insert", "%d.%d" % (ins_line + d, ins_col))
        t.see("insert")

    def delete_word(self, forward=False):
        t, app = self.text, self.app
        if t.tag_ranges("sel"):
            t.delete("sel.first", "sel.last")
            return
        if forward:
            right = t.get("insert", "insert lineend")
            if not right:
                t.delete("insert")
                return
            m = re.match(r"\s*(?:\w+|[^\w\s]+)?", right)
            t.delete("insert", "insert+%dc" % app.tk_len(m.group(0) or right[:1]))
        else:
            left = t.get("insert linestart", "insert")
            if not left:
                t.delete("insert-1c")
                return
            m = re.search(r"(?:\w+|[^\w\s]+)?\s*$", left)
            t.delete("insert-%dc" % app.tk_len(m.group(0) or left[-1:]), "insert")

    def change_case(self, upper):
        t = self.text
        if not t.tag_ranges("sel"):
            return
        a, b = t.index("sel.first"), t.index("sel.last")
        s = t.get(a, b)
        new = s.upper() if upper else s.lower()
        if new != s:
            with undo_block(t):
                t.delete(a, b)
                t.insert(a, new)
            t.tag_add("sel", a, "%s+%dc" % (a, self.app.tk_len(new)))

    def trim_trailing(self):
        t = self.text
        last = int(t.index("end-1c").split(".")[0])
        count = 0
        with undo_block(t):
            for ln in range(1, last + 1):
                line = t.get("%d.0" % ln, "%d.end" % ln)
                stripped = line.rstrip(" \t")
                if len(stripped) != len(line):
                    t.delete("%d.%d" % (ln, self.app.tk_len(stripped)), "%d.end" % ln)
                    count += 1
        self.app.flash("Trimmed %d line%s" % (count, "" if count == 1 else "s"))

    def context_menu(self, e):
        self.text.focus_set()
        m = self.app.ctx_menu
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()
        return "break"

    def _zoom_wheel(self, e):
        s = wheel_steps(e)
        if s:
            self.app.zoom(-1 if s > 0 else 1)
        return "break"


# --------------------------------------------------------------------------
# Tab bar
# --------------------------------------------------------------------------

class TabBar(tk.Frame):
    def __init__(self, app):
        super().__init__(app.root, bd=0, highlightthickness=0)
        self.app = app
        self._sp_role = "custom"
        self.items = {}
        self.plus = make_button(app, self, "+", app.new_tab, kind="flat_button", padx=12, pady=0,
                                font=app.ui_font_big, tip="New tab (%sN)" % MOD_TXT)
        self.plus.pack(side="right", fill="y")
        self.canvas = tk.Canvas(self, height=30, highlightthickness=0, bd=0)
        self.canvas._sp_role = "custom"
        self.canvas.apply_theme = lambda t: self.canvas.configure(bg=t["ui_bg"])
        self.canvas.pack(side="left", fill="x", expand=True)
        self.inner = make_frame(self.canvas)
        self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._sync)
        bind_wheel(self.canvas, self._wheel)
        self.canvas.bind("<Double-Button-1>", lambda e: app.new_tab())
        self._menu = None

    def apply_theme(self, t):
        self.configure(bg=t["ui_bg"])
        self.refresh_all()

    def _sync(self, _e=None):
        w, h = self.inner.winfo_reqwidth(), self.inner.winfo_reqheight()
        self.canvas.configure(scrollregion=(0, 0, w, h), height=h)

    def _wheel(self, e):
        s = wheel_steps(e)
        if s:
            self.canvas.xview_scroll(s * 3, "units")
        return "break"

    def rebuild(self):
        for child in self.inner.winfo_children():
            child.destroy()
        self.items = {}
        ui = self.app.ui_font
        for tab in self.app.tabs:
            f = tk.Frame(self.inner, bd=0, highlightthickness=0, cursor="hand2")
            bar = tk.Frame(f, height=2, bd=0)
            bar.pack(side="top", fill="x")
            row = tk.Frame(f, bd=0)
            row.pack(side="top", fill="both")
            lbl = tk.Label(row, text=tab.title(), font=ui, padx=12, pady=6, cursor="hand2")
            lbl.pack(side="left")
            close = tk.Label(row, text="×", width=2, font=self.app.ui_font_big, cursor="hand2")
            close.pack(side="left", padx=(0, 6))
            sep = tk.Frame(self.inner, width=1, bd=0)
            f.pack(side="left", fill="y")
            sep.pack(side="left", fill="y")
            item = {"frame": f, "bar": bar, "row": row, "label": lbl, "close": close, "sep": sep,
                    "hover": False, "chover": False}
            self.items[tab] = item
            for w in (f, row, lbl, bar):
                w.bind("<Button-1>", lambda e, t=tab: self.app.select_tab(t))
                w.bind(MIDDLE_CLICK, lambda e, t=tab: self.app.close_tab(t))
                w.bind(RIGHT_CLICK, lambda e, t=tab: self.tab_menu(e, t))
                bind_wheel(w, self._wheel)
            for w in (f, row, lbl, bar, close):
                w.bind("<Enter>", lambda e, t=tab: self._hover(t), add="+")
                w.bind("<Leave>", lambda e, t=tab: self.after(10, lambda: self._hover(t)), add="+")
            close.bind("<ButtonRelease-1>", lambda e, t=tab: self.app.close_tab(t))
            Tooltip(self.app, lbl, tab.path or "Not saved yet")
        self.refresh_all()
        self.inner.update_idletasks()
        self._sync()

    def _hover(self, tab):
        it = self.items.get(tab)
        if not it:
            return
        try:
            x, y = self.winfo_pointerxy()
            under = self.winfo_containing(x, y)
        except (tk.TclError, KeyError):
            under = None
        parts = (it["frame"], it["row"], it["label"], it["bar"], it["close"])
        hover, chover = under in parts, under is it["close"]
        if hover != it["hover"] or chover != it["chover"]:
            it["hover"], it["chover"] = hover, chover
            self.refresh(tab)

    def refresh_all(self):
        for tab in list(self.items):
            self.refresh(tab)

    def refresh(self, tab):
        it = self.items.get(tab)
        if not it:
            return
        t = self.app.theme
        active = tab is self.app.current
        bg = t["tab_active_bg"] if active else (t["ui_hover"] if it["hover"] else t["ui_bg"])
        fg = t["tab_active_fg"] if active else (t["ui_fg"] if it["hover"] else t["ui_dim"])
        try:
            for k in ("frame", "row", "label", "close"):
                it[k].configure(bg=bg)
            it["bar"].configure(bg=t["accent"] if active else bg)
            it["label"].configure(fg=fg, text=tab.title())
            if it["chover"]:
                it["close"].configure(text="×", fg=t["accent"])
            elif tab.is_modified():
                it["close"].configure(text="●", fg=t["accent"] if active else t["ui_dim"])
            else:
                it["close"].configure(text="×", fg=fg if (active or it["hover"]) else bg)
            it["sep"].configure(bg=t["border"])
        except tk.TclError:
            pass

    def ensure_visible(self, tab):
        it = self.items.get(tab)
        if not it:
            return
        self.update_idletasks()
        total = max(1, self.inner.winfo_reqwidth())
        cw = self.canvas.winfo_width()
        if total <= cw:
            self.canvas.xview_moveto(0)
            return
        x, w = it["frame"].winfo_x(), it["frame"].winfo_width()
        left = self.canvas.canvasx(0)
        if x < left:
            self.canvas.xview_moveto(x / float(total))
        elif x + w > left + cw:
            self.canvas.xview_moveto((x + w - cw) / float(total))

    def tab_menu(self, e, tab):
        if self._menu is not None:
            try:
                self._menu.destroy()
            except tk.TclError:
                pass
        app = self.app
        m = self._menu = tk.Menu(self, tearoff=0)
        m._sp_role = "menu"
        app.style_menu(m)
        m.add_command(label="Close", command=lambda: app.close_tab(tab))
        m.add_command(label="Close others", command=lambda: app.close_others(tab))
        m.add_separator()
        state = "normal" if tab.path else "disabled"
        m.add_command(label="Copy path", state=state, command=lambda: app.copy_text(tab.path or ""))
        m.add_command(label="Open containing folder", state=state,
                      command=lambda: open_in_file_manager(os.path.dirname(tab.path)))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()


# --------------------------------------------------------------------------
# Find / replace bar
# --------------------------------------------------------------------------

class FindBar(tk.Frame):
    def __init__(self, app):
        super().__init__(app.root, bd=0, highlightthickness=0)
        self.app = app
        self._sp_role = "bg"
        self.visible = False
        self.case = self.regex = self.word = False
        self.matches, self.cur = [], -1
        self.scan_tab, self.scan_version = None, -1
        self.anchor = "1.0"
        self.truncated = False

        make_frame(self, role="sep", height=1).pack(fill="x", side="top")
        r1 = self.row1 = make_frame(self, padx=10, pady=6)
        r1.pack(fill="x")
        self.row2 = make_frame(self, padx=10, pady=0)

        make_label(app, r1, "Find", role="dim", width=8, anchor="w").pack(side="left")
        self.find_var = tk.StringVar()
        self.find_entry = make_entry(app, r1, self.find_var, width=34)
        self.find_entry.pack(side="left")
        self.chips = {}
        for key, txt, tip in (("case", "Aa", "Match case"), ("word", "W", "Whole word"),
                              ("regex", ".*", "Regular expression")):
            c = Chip(r1, app, txt, lambda k=key: self.toggle(k), tip)
            c.pack(side="left", padx=(6 if key == "case" else 2, 0))
            self.chips[key] = c
        self.count_lbl = make_label(app, r1, "", role="dim", width=16, anchor="w")
        self.count_lbl.pack(side="left", padx=10)
        make_button(app, r1, "↑", lambda: self.step(-1), padx=8, pady=1,
                    tip="Previous match (Shift+Enter)").pack(side="left")
        make_button(app, r1, "↓", lambda: self.step(1), padx=8, pady=1,
                    tip="Next match (Enter)").pack(side="left", padx=4)
        make_button(app, r1, "×", self.hide, kind="flat_button", padx=8, pady=0,
                    font=app.ui_font_big, tip="Close (Esc)").pack(side="right")
        self.toggle_btn = make_button(app, r1, "Replace", lambda: self.show(not self.replace_mode),
                                      kind="flat_button", padx=8, pady=1, tip="Show replace (%sH)" % MOD_TXT)
        self.toggle_btn.pack(side="right", padx=4)

        r2 = self.row2
        make_label(app, r2, "Replace", role="dim", width=8, anchor="w").pack(side="left")
        self.repl_var = tk.StringVar()
        self.repl_entry = make_entry(app, r2, self.repl_var, width=34)
        self.repl_entry.pack(side="left")
        make_button(app, r2, "Replace", self.replace_one, padx=10, pady=1).pack(side="left", padx=(10, 4))
        make_button(app, r2, "Replace all", self.replace_all, padx=10, pady=1).pack(side="left")
        self.replace_mode = False

        self.find_var.trace_add("write", lambda *a: app.schedule("find", 120, lambda: self.rescan(True)))
        for ent in (self.find_entry, self.repl_entry):
            ent.bindtags((str(ent), "SlopKeys") + ent.bindtags()[1:])
            ent.bind("<Escape>", lambda e: self.hide())
        for seq in ("<Return>", "<KP_Enter>"):
            self.find_entry.bind(seq, lambda e: (self.step(1), "break")[1])
            self.repl_entry.bind(seq, lambda e: (self.replace_one(), "break")[1])
        self.find_entry.bind("<Shift-Return>", lambda e: (self.step(-1), "break")[1])

    # ---- show / hide
    def show(self, replace=False):
        app = self.app
        tab = app.current
        if tab is None:
            return
        self.replace_mode = replace
        if replace:
            self.row2.pack(fill="x", pady=(0, 6))
        else:
            self.row2.pack_forget()
        self.toggle_btn.configure(text="Hide replace" if replace else "Replace")
        if not self.visible:
            self.pack(side="bottom", fill="x", before=app.editor_area)
            self.visible = True
        t = tab.text
        if t.tag_ranges("sel"):
            sel = t.get("sel.first", "sel.last")
            if sel and "\n" not in sel and len(sel) < 300:
                self.find_var.set(re.escape(sel) if self.regex else sel)
            self.anchor = t.index("sel.first")
        else:
            self.anchor = t.index("insert")
        self.find_entry.focus_set()
        self.find_entry.select_range(0, "end")
        self.find_entry.icursor("end")
        self.rescan(True)

    def hide(self):
        if not self.visible:
            return
        self.pack_forget()
        self.visible = False
        tab = self.app.current
        keep = None
        if tab is not None and tab is self.scan_tab and self.matches and 0 <= self.cur < len(self.matches) \
                and tab.version == self.scan_version:
            keep = self.matches[self.cur]
        for tb in self.app.tabs:
            tb.text.tag_remove("match", "1.0", "end")
            tb.text.tag_remove("curmatch", "1.0", "end")
        self.matches, self.cur = [], -1
        if tab is not None:
            if keep:
                tab.text.tag_remove("sel", "1.0", "end")
                tab.text.tag_add("sel", keep[0], keep[1])
                tab.text.mark_set("insert", keep[1])
            tab.text.focus_set()

    def toggle(self, key):
        setattr(self, key, not getattr(self, key))
        self.chips[key].set(getattr(self, key))
        self.rescan(True)

    # ---- searching
    def compile(self):
        pat = self.find_var.get()
        if not pat:
            return None
        p = pat if self.regex else re.escape(pat)
        if self.word:
            p = r"(?<!\w)(?:" + p + r")(?!\w)"
        flags = re.MULTILINE | (0 if self.case else re.IGNORECASE)
        try:
            return re.compile(p, flags)
        except re.error:
            return False

    def set_count(self, text, error=False):
        t = self.app.theme
        self.count_lbl.configure(text=text, fg=blend(t["ui_dim"], "#ff4d4d", 0.75) if error else t["ui_dim"])

    def _update_count(self):
        if not self.matches:
            return
        self.set_count("%d of %d%s" % (self.cur + 1, len(self.matches), "+" if self.truncated else ""))

    def rescan(self, navigate=False):
        tab = self.app.current
        if not self.visible or tab is None:
            return
        if self.scan_tab is not None and self.scan_tab is not tab:
            try:
                self.scan_tab.text.tag_remove("match", "1.0", "end")
                self.scan_tab.text.tag_remove("curmatch", "1.0", "end")
            except tk.TclError:
                pass
        t = tab.text
        t.tag_remove("match", "1.0", "end")
        t.tag_remove("curmatch", "1.0", "end")
        self.scan_tab, self.scan_version = tab, tab.version
        self.matches, self.cur, self.truncated = [], -1, False
        rx = self.compile()
        if rx is None:
            self.set_count("")
            return
        if rx is False:
            self.set_count("Invalid regex", error=True)
            return
        content = t.get("1.0", "end-1c")
        conv = IndexConverter(content, self.app.utf16)
        for m in rx.finditer(content):
            if m.end() == m.start():
                continue
            self.matches.append((conv(m.start()), conv(m.end()), m))
            if len(self.matches) >= 50000:
                self.truncated = True
                break
        if not self.matches:
            self.set_count("No results", error=True)
            return
        flat = []
        for s, e, _ in self.matches:
            flat.extend((s, e))
        for i in range(0, len(flat), 1000):
            t.tag_add("match", *flat[i:i + 1000])
        self.cur = self._nearest(self.anchor)
        self._show_current(scroll=navigate)

    def _nearest(self, anchor):
        t = self.scan_tab.text
        lo, hi = 0, len(self.matches)
        while lo < hi:
            mid = (lo + hi) // 2
            if t.compare(self.matches[mid][0], "<", anchor):
                lo = mid + 1
            else:
                hi = mid
        return lo if lo < len(self.matches) else 0

    def _show_current(self, scroll):
        t = self.scan_tab.text
        t.tag_remove("curmatch", "1.0", "end")
        s, e, _ = self.matches[self.cur]
        t.tag_add("curmatch", s, e)
        if scroll:
            t.see(e)
            t.see(s)
        self._update_count()

    def _stale(self):
        tab = self.app.current
        return tab is not self.scan_tab or tab is None or tab.version != self.scan_version

    def step(self, d):
        if not self.visible:
            self.show()
            return
        if self._stale() or not self.matches:
            self.rescan(False)
        if not self.matches:
            self.app.root.bell()
            return
        self.cur = (self.cur + d) % len(self.matches) if self.cur >= 0 else 0
        s, e, _ = self.matches[self.cur]
        self.anchor = s
        self.scan_tab.text.mark_set("insert", e)
        self._show_current(scroll=True)

    def replacement(self, m):
        repl = self.repl_var.get()
        return m.expand(repl) if self.regex else repl

    def replace_one(self):
        if not self.replace_mode:
            self.show(True)
        if self._stale() or not self.matches:
            self.rescan(False)
        if not self.matches:
            self.app.root.bell()
            return
        s, e, m = self.matches[self.cur]
        try:
            rep = self.replacement(m)
        except (re.error, IndexError) as ex:
            self.set_count("Bad replace: %s" % ex, error=True)
            return
        t = self.scan_tab.text
        with undo_block(t):
            t.delete(s, e)
            t.insert(s, rep)
        self.anchor = t.index("%s+%dc" % (s, self.app.tk_len(rep)))
        self.scan_tab.version += 1
        self.rescan(True)

    def replace_all(self):
        tab = self.app.current
        rx = self.compile()
        if tab is None or not rx:
            return
        t = tab.text
        content = t.get("1.0", "end-1c")
        try:
            new, n = rx.subn(self.replacement, content)
        except (re.error, IndexError) as ex:
            self.set_count("Bad replace: %s" % ex, error=True)
            return
        if not n:
            self.set_count("No results", error=True)
            return
        pos, y = t.index("insert"), t.yview()[0]
        with undo_block(t):
            t.delete("1.0", "end")
            t.insert("1.0", new)
        t.mark_set("insert", pos)
        t.yview_moveto(y)
        tab.version += 1
        self.rescan(False)
        self.set_count("Replaced %d" % n)
        self.app.flash("Replaced %d match%s" % (n, "" if n == 1 else "es"))


# --------------------------------------------------------------------------
# The app
# --------------------------------------------------------------------------

class App:
    def __init__(self, files):
        self.settings = Settings()
        if IS_WIN:
            try:
                import ctypes
                try:
                    ctypes.windll.shcore.SetProcessDpiAwareness(1)
                except Exception:
                    ctypes.windll.user32.SetProcessDPIAware()
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
            except Exception:
                pass
        self.root = tk.Tk(className="SlopPad")
        self.root.withdraw()
        self.root.report_callback_exception = self.on_error
        self.root.option_add("*tearOff", False)
        self.utf16 = self._detect_utf16()
        self.tabs, self.current, self.dialogs = [], None, []
        self.untitled_counter = 0
        self.zoom_delta = 0
        self._jobs = {}
        self._families = None
        self._mono = None
        self._showing_error = False
        self.prefs_window = None
        self.theme_editor = None
        self._menus = []
        self.theme = self.resolve_theme(self.settings["theme"])

        self.setup_fonts()
        self.build_ui()
        self.install_shortcuts()
        self.apply_theme()
        self.restore_geometry()

        opened = 0
        for p in files:
            if self.open_path(p, quiet=False, select=True):
                opened += 1
        if not files and self.settings["restore_session"]:
            for p in self.settings["session"]:
                if os.path.isfile(p) and self.open_path(p, quiet=True):
                    opened += 1
        if not self.tabs:
            self.new_tab()
        self.select_tab(self.tabs[0] if not files else self.tabs[-1])

        self.apply_window_settings()
        self.root.deiconify()
        if self.settings["maximized"]:
            self._set_maximized()
        set_titlebar(self.root, self.theme)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        if IS_MAC:
            try:
                self.root.createcommand("tk::mac::Quit", self.quit)
                self.root.createcommand("tk::mac::ShowPreferences", self.open_prefs)
            except tk.TclError:
                pass
        if self.settings.load_error:
            self.root.after(300, lambda: self.error(
                "Settings were reset", "Your settings file couldn't be read, so SlopPad started fresh.",
                detail="A copy was saved as settings.json.broken\n\n" + self.settings.load_error))

    def _detect_utf16(self):
        try:
            n = int(self.root.tk.call("string", "length", "\U0001F600"))
            back = self.root.tk.call("string", "range", "a\U0001F600b", 0, "end")
            return n == 2 and len(str(back)) == 3
        except Exception:
            return False

    def tk_len(self, s):
        if self.utf16 and re.search("[\U00010000-\U0010FFFF]", s):
            return len(s.encode("utf-16-le")) // 2
        return len(s)

    def run(self):
        self.root.mainloop()

    # ---- scheduling
    def schedule(self, key, delay, fn):
        job = self._jobs.pop(key, None)
        if job:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass

        def run():
            self._jobs.pop(key, None)
            fn()

        self._jobs[key] = self.root.after(max(1, delay), run)

    def save_settings_soon(self):
        self.schedule("save-settings", 700, self.save_settings)

    def save_settings(self):
        try:
            self.settings.save()
        except Exception as e:
            self._log("Could not save settings: %s" % e)

    # ---- fonts
    def font_families(self):
        if self._families is None:
            # "@" fonts are vertical CJK variants on Windows; color emoji fonts can crash Tk on Linux
            self._families = sorted({f for f in tkfont.families(self.root)
                                     if not f.startswith("@") and "emoji" not in f.lower()},
                                    key=str.lower)
        return self._families

    def mono_fonts(self):
        if self._mono is None:
            res = []
            for fam in self.font_families():
                try:
                    f = tkfont.Font(root=self.root, family=fam, size=10)
                    if f.metrics("fixed"):
                        res.append(fam)
                except tk.TclError:
                    pass
            self._mono = res or self.font_families()
        return self._mono

    def _pick_default_font(self):
        fams = {f.lower(): f for f in self.font_families()}
        for cand in ("JetBrains Mono", "Cascadia Code", "Cascadia Mono", "Fira Code", "SF Mono",
                     "Menlo", "Consolas", "Hack", "Source Code Pro", "DejaVu Sans Mono",
                     "Noto Sans Mono", "Ubuntu Mono", "Liberation Mono", "Courier New"):
            if cand.lower() in fams:
                return fams[cand.lower()]
        return tkfont.nametofont("TkFixedFont").actual("family")

    def setup_fonts(self):
        s = self.settings
        fam = s["font_family"]
        if not fam or fam not in self.font_families():
            fam = self._pick_default_font()
        self.editor_font = tkfont.Font(root=self.root, family=fam, size=s["font_size"],
                                       weight="bold" if s["font_bold"] else "normal")
        self.base_ui_family = tkfont.nametofont("TkDefaultFont").actual("family")
        self.ui_font = tkfont.Font(root=self.root, family=self.base_ui_family, size=s["ui_font_size"])
        self.ui_font_bold = tkfont.Font(root=self.root, family=self.base_ui_family,
                                        size=s["ui_font_size"], weight="bold")
        self.ui_font_big = tkfont.Font(root=self.root, family=self.base_ui_family,
                                       size=s["ui_font_size"] + 3)
        self.update_ui_font()

    def update_editor_font(self):
        s = self.settings
        fam = s["font_family"] or self.editor_font.cget("family")
        size = max(6, min(96, s["font_size"] + self.zoom_delta))
        self.editor_font.configure(family=fam, size=size, weight="bold" if s["font_bold"] else "normal")
        for tab in self.tabs:
            tab.apply_settings()
        self.update_status()

    def update_ui_font(self):
        s = self.settings
        fam = self.editor_font.cget("family") if s["ui_use_editor_font"] else self.base_ui_family
        size = s["ui_font_size"]
        self.ui_font.configure(family=fam, size=size)
        self.ui_font_bold.configure(family=fam, size=size, weight="bold")
        self.ui_font_big.configure(family=fam, size=size + 3)
        if hasattr(self, "tabbar"):
            self.tabbar.after_idle(self.tabbar._sync)

    # ---- UI
    def build_ui(self):
        r = self.root
        r.minsize(420, 260)
        self.menubar = make_frame(r)
        self.menubar.pack(side="top", fill="x")
        self.build_menus()
        make_frame(r, role="sep", height=1).pack(side="top", fill="x")
        self.tabbar = TabBar(self)
        self.tabbar.pack(side="top", fill="x")
        make_frame(r, role="sep", height=1).pack(side="top", fill="x")
        self.build_status()
        if self.settings["status_bar"]:
            self.status.pack(side="bottom", fill="x")
        self.findbar = FindBar(self)
        self.editor_area = make_frame(r)
        self.editor_area.pack(side="top", fill="both", expand=True)
        self.update_icon()

    def _menu(self, parent=None, **kw):
        m = tk.Menu(parent or self.root, tearoff=0, **kw)
        m._sp_role = "menu"
        self._menus.append(m)
        return m

    def style_menu(self, m):
        t = self.theme
        try:
            m.configure(bg=t["input_bg"], fg=t["ui_fg"], activebackground=t["selection_bg"],
                        activeforeground=t["selection_fg"], selectcolor=t["accent"],
                        disabledforeground=t["ui_dim"], activeborderwidth=0, bd=1, relief="solid",
                        font=self.ui_font)
        except tk.TclError:
            pass

    def build_menus(self):
        s = self.settings
        self.vars = {}
        for key in ("wrap", "line_numbers", "highlight_line", "status_bar", "topmost"):
            self.vars[key] = tk.BooleanVar(value=s[key])
        self.var_theme = tk.StringVar(value=s["theme"])
        self.var_alpha = tk.IntVar(value=int(round(s["alpha"] * 100)))

        def chk(m, label, key, accel=None):
            m.add_checkbutton(label=label, variable=self.vars[key], accelerator=accel,
                              command=lambda: self.set_setting(key, self.vars[key].get()))

        M = MOD_TXT
        fm = self._menu()
        fm.add_command(label="New tab", accelerator=M + "N", command=self.new_tab)
        fm.add_command(label="Open...", accelerator=M + "O", command=self.open_dialog)
        self.recent_menu = self._menu(fm, postcommand=self.fill_recent)
        fm.add_cascade(label="Open recent", menu=self.recent_menu)
        fm.add_command(label="Reload from disk", command=self.reload_current)
        fm.add_separator()
        fm.add_command(label="Save", accelerator=M + "S", command=lambda: self.save_tab(self.current))
        fm.add_command(label="Save as...", accelerator=M + "Shift+S",
                       command=lambda: self.save_tab(self.current, save_as=True))
        fm.add_command(label="Save all", command=self.save_all)
        fm.add_separator()
        fm.add_command(label="Close tab", accelerator=M + "W", command=lambda: self.close_tab(self.current))
        fm.add_command(label="Quit", accelerator=M + "Q", command=self.quit)

        em = self._menu()
        cur = lambda name: (lambda: getattr(self.current, name)() if self.current else None)
        em.add_command(label="Undo", accelerator=M + "Z", command=cur("undo"))
        em.add_command(label="Redo", accelerator=M + "Y", command=cur("redo"))
        em.add_separator()
        em.add_command(label="Cut", accelerator=M + "X", command=cur("cut"))
        em.add_command(label="Copy", accelerator=M + "C", command=cur("copy"))
        em.add_command(label="Paste", accelerator=M + "V", command=cur("paste"))
        em.add_command(label="Select all", accelerator=M + "A", command=cur("select_all"))
        em.add_command(label="Select line", accelerator=M + "L", command=cur("select_line"))
        em.add_separator()
        em.add_command(label="Find...", accelerator=M + "F", command=lambda: self.findbar.show(False))
        em.add_command(label="Replace...", accelerator=M + "H", command=lambda: self.findbar.show(True))
        em.add_command(label="Go to line...", accelerator=M + "G", command=self.goto_line)
        em.add_separator()
        em.add_command(label="Duplicate line", accelerator=M + "D", command=cur("duplicate"))
        em.add_command(label="Delete line", accelerator=M + "Shift+K", command=cur("delete_line"))
        em.add_command(label="Move line up", accelerator=ALT_TXT + "Up", command=lambda: self.current.move_lines(-1))
        em.add_command(label="Move line down", accelerator=ALT_TXT + "Down",
                       command=lambda: self.current.move_lines(1))
        em.add_separator()
        em.add_command(label="UPPERCASE selection", command=lambda: self.current.change_case(True))
        em.add_command(label="lowercase selection", command=lambda: self.current.change_case(False))
        em.add_command(label="Trim trailing whitespace", command=cur("trim_trailing"))

        vm = self._menu()
        chk(vm, "Word wrap", "wrap", None if IS_MAC else "Alt+Z")
        chk(vm, "Line numbers", "line_numbers")
        chk(vm, "Highlight current line", "highlight_line")
        chk(vm, "Status bar", "status_bar")
        vm.add_separator()
        vm.add_command(label="Zoom in", accelerator=M + "+", command=lambda: self.zoom(1))
        vm.add_command(label="Zoom out", accelerator=M + "-", command=lambda: self.zoom(-1))
        vm.add_command(label="Reset zoom", accelerator=M + "0", command=lambda: self.zoom(0))
        vm.add_separator()
        am = self._menu(vm)
        for p in range(100, 20, -10):
            am.add_radiobutton(label="%d%%" % p, value=p, variable=self.var_alpha,
                               command=lambda p=p: self.set_setting("alpha", p / 100.0))
        vm.add_cascade(label="Opacity", menu=am)
        chk(vm, "Always on top", "topmost")
        vm.add_command(label="Full screen", accelerator="F11", command=self.toggle_fullscreen)

        self.theme_menu = self._menu(postcommand=self.fill_theme_menu)

        sm = self._menu()
        sm.add_command(label="Preferences...", accelerator=M + ",", command=self.open_prefs)
        sm.add_command(label="Theme editor...", command=self.open_theme_editor)
        sm.add_separator()
        sm.add_command(label="Open settings folder", command=self.open_config_folder)
        sm.add_command(label="Reset everything...", command=self.reset_settings)

        hm = self._menu()
        hm.add_command(label="Keyboard shortcuts", accelerator="F1", command=self.show_shortcuts)
        hm.add_command(label="About SlopPad", command=self.show_about)

        for name, menu in (("File", fm), ("Edit", em), ("View", vm), ("Theme", self.theme_menu),
                           ("Settings", sm), ("Help", hm)):
            b = tk.Label(self.menubar, text=name, font=self.ui_font, padx=10, pady=4)
            hoverable(self, b, "flat_button")
            b.bind("<Button-1>", lambda e, m=menu, b=b: self.post_menu(m, b))
            b.pack(side="left")

        ctx = self.ctx_menu = self._menu()
        ctx.add_command(label="Undo", command=cur("undo"))
        ctx.add_command(label="Redo", command=cur("redo"))
        ctx.add_separator()
        ctx.add_command(label="Cut", command=cur("cut"))
        ctx.add_command(label="Copy", command=cur("copy"))
        ctx.add_command(label="Paste", command=cur("paste"))
        ctx.add_separator()
        ctx.add_command(label="Select all", command=cur("select_all"))
        ctx.add_command(label="Find...", command=lambda: self.findbar.show(False))

    def post_menu(self, m, b):
        try:
            m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
        finally:
            m.grab_release()

    def fill_recent(self):
        rm = self.recent_menu
        rm.delete(0, "end")
        rec = self.settings["recent"]
        if not rec:
            rm.add_command(label="(nothing yet)", state="disabled")
            return
        for p in rec:
            label = p if len(p) <= 70 else "..." + p[-67:]
            rm.add_command(label=label, command=lambda p=p: self.open_path(p))
        rm.add_separator()
        rm.add_command(label="Clear list", command=self.clear_recent)

    def clear_recent(self):
        self.settings["recent"] = []
        self.save_settings_soon()

    def fill_theme_menu(self):
        m = self.theme_menu
        m.delete(0, "end")
        self.var_theme.set(self.settings["theme"])
        for name in BUILTIN_THEMES:
            m.add_radiobutton(label=name, value=name, variable=self.var_theme,
                              command=lambda n=name: self.set_theme(n))
        custom = sorted(self.settings["custom_themes"], key=str.lower)
        if custom:
            m.add_separator()
            for name in custom:
                m.add_radiobutton(label=name, value=name, variable=self.var_theme,
                                  command=lambda n=name: self.set_theme(n))
        m.add_separator()
        m.add_command(label="Theme editor...", command=self.open_theme_editor)
        m.add_command(label="Import theme...", command=self.import_theme_file)
        m.add_command(label="Export current theme...",
                      command=lambda: self.export_theme(self.settings["theme"], self.theme))

    def build_status(self):
        st = self.status = make_frame(self.root)
        make_frame(st, role="sep", height=1).pack(side="top", fill="x")
        row = make_frame(st, padx=6, pady=2)
        row.pack(fill="x")
        self.st_pos = make_label(self, row, "Ln 1, Col 1", role="dim", padx=6)
        self.st_pos.pack(side="left")
        self.st_sel = make_label(self, row, "", role="dim", padx=6)
        self.st_sel.pack(side="left")
        self.st_msg = make_label(self, row, "", role="header", padx=10)
        self.st_msg.pack(side="left")
        self.st_enc = make_button(self, row, "UTF-8", self.encoding_menu, kind="dim_button", padx=8, pady=1,
                                  tip="File encoding (click to change)")
        self.st_enc.pack(side="right")
        self.st_eol = make_button(self, row, "LF", self.eol_menu, kind="dim_button", padx=8, pady=1,
                                  tip="Line endings (click to change)")
        self.st_eol.pack(side="right")
        self.st_indent = make_button(self, row, "Spaces: 4", self.indent_menu, kind="dim_button", padx=8,
                                     pady=1, tip="Indentation (click to change)")
        self.st_indent.pack(side="right")
        self.st_zoom = make_button(self, row, "", lambda: self.zoom(0), kind="dim_button", padx=8, pady=1,
                                   tip="Zoom (click to reset)")
        self.st_zoom.pack(side="right")
        self.st_words = make_label(self, row, "", role="dim", padx=8)
        self.st_words.pack(side="right")
        self._status_menu = None

    def _popup_from(self, widget, fill):
        if self._status_menu is not None:
            try:
                self._status_menu.destroy()
            except tk.TclError:
                pass
        m = self._status_menu = tk.Menu(self.root, tearoff=0)
        m._sp_role = "menu"
        self.style_menu(m)
        fill(m)
        m.update_idletasks()
        try:
            m.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() - m.winfo_reqheight())
        finally:
            m.grab_release()

    def eol_menu(self):
        tab = self.current
        if not tab:
            return
        var = tk.StringVar(value=tab.newline)

        def fill(m):
            for nl, desc in (("LF", "LF  (Linux / macOS)"), ("CRLF", "CRLF  (Windows)"), ("CR", "CR  (old Mac)")):
                m.add_radiobutton(label=desc, value=nl, variable=var, command=lambda nl=nl: self.set_newline(nl))
            m._var = var

        self._popup_from(self.st_eol, fill)

    def set_newline(self, nl):
        tab = self.current
        if tab and tab.newline != nl:
            tab.newline = nl
            tab.set_modified(True)
            self.update_status()

    def encoding_menu(self):
        tab = self.current
        if not tab:
            return
        cur = "UTF-8 with BOM" if (tab.encoding == "UTF-8" and tab.bom) else tab.encoding
        var = tk.StringVar(value=cur)

        def fill(m):
            m.add_command(label="Save with encoding:", state="disabled")
            for enc in ENCODINGS:
                m.add_radiobutton(label=enc, value=enc, variable=var, command=lambda e=enc: self.set_encoding(e))
            m._var = var

        self._popup_from(self.st_enc, fill)

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

    def indent_menu(self):
        s = self.settings
        var = tk.StringVar(value="spaces" if s["insert_spaces"] else "tabs")
        wvar = tk.IntVar(value=s["tab_width"])

        def fill(m):
            m.add_radiobutton(label="Indent with spaces", value="spaces", variable=var,
                              command=lambda: self.set_setting("insert_spaces", True))
            m.add_radiobutton(label="Indent with tabs", value="tabs", variable=var,
                              command=lambda: self.set_setting("insert_spaces", False))
            m.add_separator()
            for w in (2, 4, 8):
                m.add_radiobutton(label="Width: %d" % w, value=w, variable=wvar,
                                  command=lambda w=w: self.set_setting("tab_width", w))
            m._vars = (var, wvar)

        self._popup_from(self.st_indent, fill)

    # ---- theming
    def theme_names(self):
        return list(BUILTIN_THEMES) + sorted(self.settings["custom_themes"], key=str.lower)

    def resolve_theme(self, name):
        custom = self.settings["custom_themes"]
        if name in custom:
            return complete_theme(custom[name])
        if name in BUILTIN_THEMES:
            return complete_theme(BUILTIN_THEMES[name])
        return complete_theme(BUILTIN_THEMES[DEFAULT_THEME])

    def set_theme(self, name):
        if name not in BUILTIN_THEMES and name not in self.settings["custom_themes"]:
            name = DEFAULT_THEME
        self.settings["theme"] = name
        self.var_theme.set(name)
        self.theme = self.resolve_theme(name)
        self.apply_theme()
        self._sync_dialogs("theme", name)
        self.save_settings_soon()

    def preview_theme(self, colors):
        self.theme = complete_theme(colors)
        self.apply_theme()

    def apply_theme(self):
        t = self.theme
        self.root.configure(bg=t["ui_bg"])
        self.paint_widget(self.root)
        for m in self._menus:
            self.style_menu(m)
        self.update_icon()
        set_titlebar(self.root, t)
        for d in list(self.dialogs):
            set_titlebar(d, t)
            d.on_theme()
        if hasattr(self, "findbar"):
            for c in self.findbar.chips.values():
                c.apply_theme(t)

    def paint_widget(self, w, recurse=True):
        t = self.theme
        r = getattr(w, "_sp_role", None)
        try:
            if r == "bg":
                w.configure(bg=t["ui_bg"])
            elif r == "sep":
                w.configure(bg=t["border"])
            elif r == "label":
                w.configure(bg=t["ui_bg"], fg=t["ui_fg"])
            elif r in ("dim", "dim_button"):
                w.configure(bg=t["ui_bg"], fg=t["ui_dim"])
            elif r == "header":
                w.configure(bg=t["ui_bg"], fg=t["accent"])
            elif r == "flat_button":
                w.configure(bg=t["ui_bg"], fg=t["ui_fg"])
            elif r == "button":
                w.configure(bg=t["input_bg"], fg=t["ui_fg"], highlightbackground=t["border"],
                            highlightcolor=t["border"])
            elif r == "accent_button":
                w.configure(bg=t["accent"], fg=contrast_text(t["accent"]),
                            highlightbackground=t["accent"], highlightcolor=t["accent"])
            elif r == "entry":
                w.configure(bg=t["input_bg"], fg=t["fg"], insertbackground=t["cursor"],
                            highlightbackground=t["border"], highlightcolor=t["accent"],
                            selectbackground=t["selection_bg"], selectforeground=t["selection_fg"])
            elif r == "listbox":
                w.configure(bg=t["input_bg"], fg=t["ui_fg"], selectbackground=t["accent"],
                            selectforeground=contrast_text(t["accent"]))
            elif r == "code":
                w.configure(bg=t["input_bg"], fg=t["fg"], insertbackground=t["cursor"],
                            selectbackground=t["selection_bg"], selectforeground=t["selection_fg"],
                            highlightbackground=t["border"], highlightcolor=t["border"])
            elif r == "menu":
                self.style_menu(w)
            elif r == "custom":
                w.apply_theme(t)
        except tk.TclError:
            pass
        if recurse:
            try:
                kids = w.winfo_children()
            except tk.TclError:
                kids = []
            for c in kids:
                self.paint_widget(c)

    def update_icon(self):
        t = self.theme
        try:
            img = tk.PhotoImage(master=self.root, width=32, height=32)
            img.put("#000000", to=(0, 0, 32, 32))
            acc = t["accent"]
            for rect in ((0, 0, 32, 2), (0, 30, 32, 32), (0, 0, 2, 32), (30, 0, 32, 32)):
                img.put(acc, to=rect)
            img.put(acc, to=(7, 8, 25, 11))
            light = blend(acc, "#ffffff", 0.55)
            img.put(light, to=(7, 14, 21, 16))
            img.put(light, to=(7, 19, 24, 21))
            img.put(light, to=(7, 24, 16, 26))
            self.icon_img = img
            self.root.iconphoto(True, img)
        except tk.TclError:
            pass

    # ---- settings
    def set_setting(self, key, value):
        self.settings[key] = value
        if key in self.vars:
            self.vars[key].set(value)
        if key == "alpha":
            self.var_alpha.set(int(round(value * 100)))
        self.apply_setting(key)
        self._sync_dialogs(key, value)
        self.save_settings_soon()

    def _sync_dialogs(self, key, value):
        for d in list(self.dialogs):
            if hasattr(d, "sync"):
                try:
                    d.sync(key, value)
                except tk.TclError:
                    pass

    def apply_setting(self, key):
        if key in ("font_family", "font_size", "font_bold"):
            self.update_editor_font()
            if self.settings["ui_use_editor_font"]:
                self.update_ui_font()
        elif key in ("ui_font_size", "ui_use_editor_font"):
            self.update_ui_font()
        elif key in ("alpha", "topmost"):
            self.apply_window_settings()
        elif key == "status_bar":
            if self.settings["status_bar"]:
                before = self.findbar if self.findbar.visible else self.editor_area
                self.status.pack(side="bottom", fill="x", before=before)
            else:
                self.status.pack_forget()
        elif key in ("default_newline", "restore_session", "monospace_only", "theme"):
            pass
        else:
            for tab in self.tabs:
                tab.apply_settings()
            self.update_status()

    def apply_window_settings(self):
        s = self.settings
        try:
            self.root.attributes("-alpha", s["alpha"])
        except tk.TclError:
            pass
        try:
            self.root.attributes("-topmost", bool(s["topmost"]))
        except tk.TclError:
            pass

    def reset_settings(self):
        parent = self.prefs_window or self.root
        ok = self.ask("Reset everything?",
                      "Put every setting back to default?",
                      [("Reset", True, "accent_button"), ("Cancel", None, "button")],
                      detail="Your custom themes and recent files are kept.", parent=parent)
        if not ok:
            return
        keep = {k: self.settings[k] for k in ("custom_themes", "recent", "session", "geometry", "maximized")}
        self.settings.data = copy.deepcopy(DEFAULT_SETTINGS)
        self.settings.data.update(keep)
        self.zoom_delta = 0
        for k, v in self.vars.items():
            v.set(self.settings[k])
        fam = self._pick_default_font()
        self.settings["font_family"] = ""
        self.editor_font.configure(family=fam)
        self.update_editor_font()
        self.update_ui_font()
        self.apply_window_settings()
        self.apply_setting("status_bar")
        self.set_theme(DEFAULT_THEME)
        for key in DEFAULT_SETTINGS:
            self._sync_dialogs(key, self.settings[key])
        if self.prefs_window:
            self.prefs_window.fill_fonts()
        self.flash("Settings reset")

    def open_config_folder(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        if not open_in_file_manager(CONFIG_DIR):
            self.info("Settings folder", CONFIG_DIR)

    def zoom(self, d):
        if d == 0:
            self.zoom_delta = 0
        else:
            size = self.settings["font_size"] + self.zoom_delta + d
            if 6 <= size <= 96:
                self.zoom_delta += d
        self.update_editor_font()

    def toggle_fullscreen(self):
        try:
            v = not bool(self.root.attributes("-fullscreen"))
            self.root.attributes("-fullscreen", v)
        except tk.TclError:
            pass

    # ---- windows / dialogs
    def open_prefs(self):
        if self.prefs_window is not None and self.prefs_window.winfo_exists():
            self.prefs_window.lift()
            self.prefs_window.focus_set()
            return
        self.prefs_window = PrefsWindow(self)

    def open_theme_editor(self):
        if self.theme_editor is not None and self.theme_editor.winfo_exists():
            self.theme_editor.lift()
            return
        self.theme_editor = ThemeEditor(self)

    def ask(self, title, message, buttons, detail=None, parent=None, default=0):
        """buttons: list of (label, value, kind). First one is the default for Enter."""
        d = Dialog(self, title)
        if parent is not None and parent is not self.root:
            d.transient(parent)
        result = {"v": None}
        make_label(self, d.body, message, font=self.ui_font_bold, wraplength=440, justify="left",
                   anchor="w").pack(fill="x")
        if detail:
            make_label(self, d.body, detail, role="dim", wraplength=440, justify="left",
                       anchor="w").pack(fill="x", pady=(6, 0))
        row = make_frame(d.body)
        row.pack(fill="x", pady=(18, 0))

        def choose(v):
            result["v"] = v
            d.close()

        for label, value, kind in buttons:
            make_button(self, row, label, lambda v=value: choose(v), kind=kind, padx=14).pack(
                side="right", padx=(6, 0))
        d.bind("<Return>", lambda e: choose(buttons[default][1]))
        d.show(modal=True)
        d.wait_window()
        return result["v"]

    def info(self, title, message, detail=None, parent=None):
        self.ask(title, message, [("OK", True, "accent_button")], detail=detail, parent=parent)

    def error(self, title, message, detail=None, parent=None):
        self.ask(title, message, [("OK", True, "accent_button")], detail=detail, parent=parent)

    def ask_save(self, tab):
        self.select_tab(tab)
        return self.ask("Unsaved changes", 'Save changes to "%s"?' % tab.title(),
                        [("Save", "save", "accent_button"), ("Don't save", "discard", "button"),
                         ("Cancel", None, "button")],
                        detail="If you don't save, your changes will be lost.")

    def goto_line(self):
        tab = self.current
        if not tab:
            return
        t = tab.text
        last = int(t.index("end-1c").split(".")[0])
        d = Dialog(self, "Go to line")
        make_label(self, d.body, "Line number (1 - %d), or line:column" % last, role="dim").pack(anchor="w")
        var = tk.StringVar(value=t.index("insert").split(".")[0])
        e = make_entry(self, d.body, var, width=24)
        e.pack(fill="x", pady=(8, 0))

        def go(_e=None):
            m = re.match(r"^\s*(\d+)\s*(?:[:,.]\s*(\d+))?\s*$", var.get())
            if not m:
                self.root.bell()
                return
            ln = max(1, min(last, int(m.group(1))))
            col = max(0, int(m.group(2) or 1) - 1)
            t.tag_remove("sel", "1.0", "end")
            t.mark_set("insert", "%d.0+%dc" % (ln, col) if col else "%d.0" % ln)
            if int(t.index("insert").split(".")[0]) != ln:
                t.mark_set("insert", "%d.end" % ln)
            t.see("insert")
            d.close()
            t.focus_set()

        e.bind("<Return>", go)
        e.select_range(0, "end")
        d.show(modal=True, focus=e)

    def show_shortcuts(self):
        d = Dialog(self, "Keyboard shortcuts")
        M = MOD_TXT
        rows = [
            ("New tab / Open / Save", M + "N  /  " + M + "O  /  " + M + "S"),
            ("Save as", M + "Shift+S"), ("Close tab / Quit", M + "W  /  " + M + "Q"),
            ("Next / previous tab", M + "Tab  /  " + M + "Shift+Tab"),
            ("Find / Replace", M + "F  /  " + M + "H"), ("Next / previous match", "Enter / Shift+Enter  (or F3)"),
            ("Go to line", M + "G"), ("Undo / Redo", M + "Z  /  " + M + "Y"),
            ("Select line", M + "L"), ("Duplicate line", M + "D"), ("Delete line", M + "Shift+K"),
            ("Move line up / down", ALT_TXT + "Up  /  " + ALT_TXT + "Down"),
            ("Indent / unindent", "Tab  /  Shift+Tab"), ("Delete word", M + "Backspace  /  " + M + "Delete"),
            ("Zoom", M + "+  /  " + M + "-  /  " + M + "0  (or " + M + "scroll)"),
            ("Word wrap", "Alt+Z"), ("Full screen", "F11"), ("Preferences", M + ","),
        ]
        g = make_frame(d.body)
        g.pack()
        for i, (desc, keys) in enumerate(rows):
            make_label(self, g, desc, anchor="w").grid(row=i, column=0, sticky="w", pady=2)
            make_label(self, g, keys, role="header", anchor="w").grid(row=i, column=1, sticky="w", padx=(24, 0))
        make_button(self, d.body, "Close", d.close, kind="accent_button", padx=18).pack(anchor="e", pady=(16, 0))
        d.show()

    def show_about(self):
        d = Dialog(self, "About SlopPad")
        make_label(self, d.body, APP_NAME, role="header", font=self.ui_font_big).pack(anchor="w")
        make_label(self, d.body, "Version %s" % VERSION, role="dim").pack(anchor="w")
        make_label(self, d.body, "A text editor vibe-coded by Claude for slopware.\n"
                                 "The human who ships it has never read the code. Use accordingly.",
                   justify="left", anchor="w").pack(anchor="w", pady=(10, 10))
        link = make_label(self, d.body, REPO_URL, role="header", cursor="hand2")
        link.pack(anchor="w")
        link.bind("<Button-1>", lambda e: webbrowser.open(REPO_URL))
        info = "Python %s  |  Tk %s  |  %s\nSettings: %s" % (
            platform.python_version(), self.root.tk.call("info", "patchlevel"), platform.platform(), SETTINGS_PATH)
        make_label(self, d.body, info, role="dim", justify="left", anchor="w").pack(anchor="w", pady=(12, 0))
        make_button(self, d.body, "Close", d.close, kind="accent_button", padx=18).pack(anchor="e", pady=(16, 0))
        d.show()

    def import_theme_file(self):
        path = filedialog.askopenfilename(parent=self.root, title="Import theme",
                                          filetypes=[("Theme files", "*.json"), ("All files", "*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            colors = data.get("colors", data) if isinstance(data, dict) else None
            if not isinstance(colors, dict) or not any(norm_hex(colors.get(k)) for k, _ in THEME_KEYS):
                raise ValueError("No SlopPad colors found in that file.")
            name = data.get("name") if isinstance(data.get("name"), str) else None
            name = (name or os.path.splitext(os.path.basename(path))[0]).strip() or "Imported theme"
            if name in BUILTIN_THEMES:
                name += " (imported)"
        except Exception as e:
            self.error("Couldn't import theme", str(e))
            return
        self.settings["custom_themes"][name] = complete_theme(colors)
        self.set_theme(name)
        self.flash('Imported "%s"' % name)

    def export_theme(self, name, colors, parent=None):
        safe = re.sub(r'[\\/:*?"<>|]+', "_", name) or "theme"
        path = filedialog.asksaveasfilename(parent=parent or self.root, title="Export theme",
                                            initialfile=safe + ".json", defaultextension=".json",
                                            filetypes=[("Theme files", "*.json")])
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
        tab = EditorTab(self, path)
        self.tabs.append(tab)
        self.tabbar.rebuild()
        if select:
            self.select_tab(tab)
        return tab

    def select_tab(self, tab):
        if tab is None or tab not in self.tabs:
            return
        if self.current is not tab:
            if self.current is not None:
                try:
                    self.current.frame.pack_forget()
                except tk.TclError:
                    pass
            self.current = tab
            tab.frame.pack(fill="both", expand=True)
            self.tabbar.refresh_all()
            self.tabbar.after_idle(lambda: self.tabbar.ensure_visible(tab))
            if self.findbar.visible:
                self.findbar.anchor = tab.text.index("insert")
                self.findbar.rescan(False)
        tab.text.focus_set()
        tab.schedule_gutter()
        self.update_title()
        self.update_status()
        self.schedule("words", 50, self.update_words)

    def cycle_tab(self, d):
        if len(self.tabs) > 1 and self.current in self.tabs:
            i = self.tabs.index(self.current)
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
        idx = self.tabs.index(tab)
        self.tabs.remove(tab)
        was_current = self.current is tab
        if was_current:
            self.current = None
        if self.findbar.scan_tab is tab:
            self.findbar.scan_tab = None
        tab.destroy()
        if not self.tabs:
            self.new_tab()
        else:
            self.tabbar.rebuild()
            if was_current:
                self.select_tab(self.tabs[min(idx, len(self.tabs) - 1)])
        self.update_session()
        return True

    def close_others(self, keep):
        for tab in [t for t in self.tabs if t is not keep]:
            if not self.close_tab(tab):
                break
        self.select_tab(keep)

    def refresh_modified(self, tab):
        tab.shown_modified = tab.is_modified()
        self.tabbar.refresh(tab)
        if tab is self.current:
            self.update_title()

    def update_title(self):
        tab = self.current
        if not tab:
            self.root.title(APP_NAME)
            return
        mark = "● " if tab.is_modified() else ""
        where = "  (%s)" % os.path.dirname(tab.path) if tab.path else ""
        self.root.title("%s%s%s - %s" % (mark, tab.title(), where, APP_NAME))

    # ---- events from editors
    def on_text_change(self, tab):
        tab.version += 1
        tab.schedule_gutter()
        if tab.is_modified() != tab.shown_modified:
            self.refresh_modified(tab)
        if tab is self.current:
            self.schedule("status", 15, self.update_status)
            self.schedule("words", 400, self.update_words)
            if self.findbar.visible:
                self.schedule("find", 250, lambda: self.findbar.rescan(False))

    def on_cursor(self, tab):
        tab.update_curline()
        tab.schedule_gutter()
        if tab is self.current:
            self.schedule("status", 15, self.update_status)

    def update_status(self):
        tab = self.current
        if not tab:
            return
        t = tab.text
        try:
            line, col = t.index("insert").split(".")
            self.st_pos.configure(text="Ln %s, Col %d" % (line, int(col) + 1))
            if t.tag_ranges("sel"):
                n = int(t.tk.call(str(t), "count", "-chars", "sel.first", "sel.last") or 0)
                a = int(t.index("sel.first").split(".")[0])
                b = int(t.index("sel.last").split(".")[0])
                lines = b - a + 1
                self.st_sel.configure(text="(%d selected%s)" % (n, ", %d lines" % lines if lines > 1 else ""))
            else:
                self.st_sel.configure(text="")
        except tk.TclError:
            return
        s = self.settings
        self.st_enc.configure(text="UTF-8 BOM" if (tab.encoding == "UTF-8" and tab.bom) else tab.encoding)
        self.st_eol.configure(text=tab.newline)
        self.st_indent.configure(text=("Spaces: %d" if s["insert_spaces"] else "Tab size: %d") % s["tab_width"])
        if self.zoom_delta:
            self.st_zoom.configure(text="Zoom %+d" % self.zoom_delta)
            if not self.st_zoom.winfo_ismapped():
                self.st_zoom.pack(side="right", before=self.st_indent)
        else:
            self.st_zoom.pack_forget()

    def update_words(self):
        tab = self.current
        if not tab:
            return
        try:
            content = tab.content()
        except tk.TclError:
            return
        if len(content) > 3000000:
            self.st_words.configure(text="%d chars" % len(content))
            return
        words = len(content.split())
        self.st_words.configure(text="%d word%s, %d chars" % (words, "" if words == 1 else "s", len(content)))

    def flash(self, msg):
        self.st_msg.configure(text=msg)
        self.schedule("flash", 2600, lambda: self.st_msg.configure(text=""))

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
        paths = filedialog.askopenfilenames(parent=self.root, title="Open", initialdir=self._last_dir())
        if isinstance(paths, str):
            paths = self.root.tk.splitlist(paths)
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
            # opening a path that doesn't exist yet = new file with that name
            tab = self._target_tab(path)
            self.tabbar.rebuild()
            if select:
                self.select_tab(tab)
            self.flash("New file (not saved yet)")
            return tab
        try:
            size = os.path.getsize(path)
            if size > 50 * 1024 * 1024 and not quiet:
                if not self.ask("Big file", "%s is %.0f MB." % (os.path.basename(path), size / 1048576.0),
                                [("Open anyway", True, "accent_button"), ("Cancel", None, "button")],
                                detail="Tk text widgets get slow with huge files."):
                    return None
            try:
                content, enc, bom, nl = read_text_file(path)
            except BinaryFileError:
                if quiet or not self.ask("Binary file?", "%s doesn't look like a text file." % os.path.basename(path),
                                         [("Open anyway", True, "accent_button"), ("Cancel", None, "button")],
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
        tab.shown_modified = False
        self.add_recent(path)
        self.tabbar.rebuild()
        if select:
            self.select_tab(tab)
        self.update_session()
        return tab

    def _target_tab(self, path):
        cur = self.current
        if cur is not None and cur.is_pristine():
            cur.path = path
            return cur
        tab = EditorTab(self, path)
        self.tabs.append(tab)
        return tab

    def reload_current(self):
        tab = self.current
        if not tab or not tab.path or not os.path.exists(tab.path):
            self.root.bell()
            return
        if tab.is_modified() and not self.ask("Reload?", "Throw away your changes and reload from disk?",
                                              [("Reload", True, "accent_button"), ("Cancel", None, "button")]):
            return
        try:
            content, enc, bom, nl = read_text_file(tab.path, force=True)
        except OSError as e:
            self.error("Couldn't reload", str(e))
            return
        ins = tab.text.index("insert")
        tab.encoding, tab.bom, tab.newline = enc, bom, nl or tab.newline
        tab.set_content(content)
        tab.text.mark_set("insert", ins)
        tab.text.see("insert")
        self.refresh_modified(tab)
        self.flash("Reloaded")

    def save_tab(self, tab, save_as=False):
        if tab is None:
            return False
        path = tab.path
        if save_as or not path:
            initialdir = os.path.dirname(path) if path else self._last_dir()
            path = filedialog.asksaveasfilename(parent=self.root, title="Save as",
                                                initialfile=tab.title() if tab.path else "untitled.txt",
                                                initialdir=initialdir)
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
                            [("Save as UTF-8", True, "accent_button"), ("Cancel", None, "button")]):
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
        self.tabbar.rebuild()
        self.add_recent(tab.path)
        self.update_session()
        self.update_title()
        self.update_status()
        self.flash("Saved ✓")
        return True

    def save_all(self):
        for tab in list(self.tabs):
            if tab.is_modified() or not tab.path:
                if tab.path or not tab.is_pristine():
                    self.select_tab(tab)
                    if not self.save_tab(tab):
                        return

    def copy_text(self, s):
        self.root.clipboard_clear()
        self.root.clipboard_append(s)
        self.flash("Copied")

    # ---- geometry
    def restore_geometry(self):
        r = self.root
        m = re.match(r"^(\d+)x(\d+)(?:([+-]-?\d+)([+-]-?\d+))?$", self.settings["geometry"] or "")
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        if not m:
            r.geometry("1100x720")
            return
        w = max(420, min(int(m.group(1)), sw))
        h = max(260, min(int(m.group(2)), sh))
        pos = ""
        if m.group(3):
            x = int(m.group(3).replace("+-", "-"))
            y = int(m.group(4).replace("+-", "-"))
            if 0 <= x < sw - 100 and 0 <= y < sh - 100:
                pos = "+%d+%d" % (x, y)
        r.geometry("%dx%d%s" % (w, h, pos))

    def _is_maximized(self):
        try:
            if IS_X11:
                return bool(self.root.attributes("-zoomed"))
            return self.root.state() == "zoomed"
        except tk.TclError:
            return False

    def _set_maximized(self):
        try:
            if IS_X11:
                self.root.attributes("-zoomed", True)
            else:
                self.root.state("zoomed")
        except tk.TclError:
            pass

    def store_window_state(self):
        try:
            fullscreen = bool(self.root.attributes("-fullscreen"))
        except tk.TclError:
            fullscreen = False
        maxed = self._is_maximized()
        self.settings["maximized"] = maxed
        if not maxed and not fullscreen and self.root.state() == "normal":
            self.settings["geometry"] = self.root.geometry()

    # ---- shortcuts
    def install_shortcuts(self):
        r = self.root
        r.bind_class("SlopKeys", "<%s-KeyPress>" % MOD, self.on_mod_key)
        r.bind("<%s-KeyPress>" % MOD, self.on_mod_key)
        for seq, fn in (("<F11>", self.toggle_fullscreen), ("<F1>", self.show_shortcuts),
                        ("<F3>", lambda: self.findbar.step(1)), ("<Shift-F3>", lambda: self.findbar.step(-1))):
            r.bind_class("SlopKeys", seq, lambda e, fn=fn: (fn(), "break")[1])
            r.bind(seq, lambda e, fn=fn: fn())
        if not IS_MAC:
            r.bind_class("SlopKeys", "<Alt-z>",
                         lambda e: (self.set_setting("wrap", not self.settings["wrap"]), "break")[1])

    def on_mod_key(self, e):
        try:
            if e.widget.winfo_toplevel() is not self.root:
                return None
        except (tk.TclError, AttributeError, KeyError):
            return None
        k = (e.keysym or "").lower()
        shift = bool(e.state & 0x1)
        w = e.widget
        tab = self.current
        editor = getattr(w, "_sp_editor", False) and tab is not None and w is tab.text

        actions = {
            "n": self.new_tab,
            "o": self.open_dialog,
            "s": (lambda: self.save_tab(tab, save_as=True)) if shift else (lambda: self.save_tab(tab)),
            "w": lambda: self.close_tab(tab),
            "q": self.quit,
            "f": lambda: self.findbar.show(False),
            "h": lambda: self.findbar.show(True),
            "g": self.goto_line,
            "comma": self.open_prefs,
            "tab": lambda: self.cycle_tab(-1 if shift else 1),
            "iso_left_tab": lambda: self.cycle_tab(-1),
            "next": lambda: self.cycle_tab(1),
            "prior": lambda: self.cycle_tab(-1),
            "plus": lambda: self.zoom(1), "equal": lambda: self.zoom(1), "kp_add": lambda: self.zoom(1),
            "minus": lambda: self.zoom(-1), "underscore": lambda: self.zoom(-1),
            "kp_subtract": lambda: self.zoom(-1),
            "0": lambda: self.zoom(0), "kp_0": lambda: self.zoom(0), "kp_insert": lambda: self.zoom(0),
        }
        if editor:
            actions.update({
                "a": tab.select_all,
                "z": tab.redo if shift else tab.undo,
                "y": tab.redo,
                "d": tab.duplicate,
                "l": tab.select_line,
                "v": tab.paste,
                "backspace": lambda: tab.delete_word(False),
                "delete": lambda: tab.delete_word(True),
            })
            if shift:
                actions["k"] = tab.delete_line
            if not IS_MAC:  # swallow Tk's emacs-style keys that would surprise people
                for key in ("t", "k", "i", "b", "e", "p"):
                    actions.setdefault(key, lambda: None)
        elif isinstance(w, tk.Entry) and k == "a":
            w.select_range(0, "end")
            w.icursor("end")
            return "break"
        fn = actions.get(k)
        if fn is None:
            return None
        fn()
        return "break"

    # ---- errors
    def _log(self, text):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write("\n[%s] SlopPad %s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), VERSION, text))
        except Exception:
            pass

    def on_error(self, exc, val, tb):
        text = "".join(traceback.format_exception(exc, val, tb))
        sys.stderr.write(text)
        self._log(text)
        if self._showing_error:
            return
        self._showing_error = True
        try:
            d = Dialog(self, "Something broke")
            make_label(self, d.body, "SlopPad hit an error. Screenshot this for the bug report:",
                       font=self.ui_font_bold, anchor="w").pack(fill="x")
            box = tk.Text(d.body, width=90, height=14, font=self.editor_font, relief="flat", bd=6,
                          highlightthickness=1, wrap="none")
            box._sp_role = "code"
            box.insert("1.0", "SlopPad %s | Python %s | Tk %s | %s\n\n%s" % (
                VERSION, platform.python_version(), self.root.tk.call("info", "patchlevel"),
                platform.platform(), text))
            box.configure(state="disabled")
            box.pack(fill="both", expand=True, pady=(10, 0))
            row = make_frame(d.body)
            row.pack(fill="x", pady=(12, 0))
            make_button(self, row, "Close", d.close, kind="accent_button", padx=18).pack(side="right")
            make_button(self, row, "Copy error", lambda: self.copy_text(box.get("1.0", "end-1c"))).pack(
                side="right", padx=6)
            make_label(self, row, "Also saved to " + LOG_PATH, role="dim").pack(side="left")
            d.show()
            d.wait_window()
        except Exception:
            pass
        finally:
            self._showing_error = False

    # ---- quit
    def quit(self):
        for tab in list(self.tabs):
            if tab.is_modified():
                ans = self.ask_save(tab)
                if ans is None:
                    return
                if ans == "save" and not self.save_tab(tab):
                    return
        self.store_window_state()
        self.settings["session"] = [t.path for t in self.tabs if t.path]
        self.save_settings()
        self.root.destroy()


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
    if not IS_X11:
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
            "StartupWMClass=Sloppad\n" % (sys.executable, script))
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
    if not IS_X11:
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


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print("usage: sloppad.py [file ...]\n"
              "       sloppad.py --install     add SlopPad to your Linux app menu / Open With\n"
              "       sloppad.py --uninstall   remove that again\n\n"
              "A vibe-coded text editor. Part of slopware: " + REPO_URL)
        return 0
    if argv and argv[0] == "--install":
        return install_launcher()
    if argv and argv[0] == "--uninstall":
        return uninstall_launcher()
    if argv and argv[0] in ("-V", "--version"):
        print("%s %s" % (APP_NAME, VERSION))
        return 0
    app = App(argv)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
