"""Koyu tema.

ttk'nin varsayilan Windows temasi ("vista") renk degisikliklerini yok sayar -
widget'lari isletim sistemi ciziyor. Renkleri kendimiz belirleyebilmek icin
"clam" temasi temel aliniyor.
"""

from __future__ import annotations

import ctypes
import math
import time
from tkinter import ttk

# Yuzeyler koyudan aciga
BG = "#0d0f12"  # pencere zemini
SURFACE = "#15181d"  # panel
SURFACE_HI = "#1c2027"  # girdi alanlari
BORDER = "#2a2f38"
BORDER_HI = "#3a414d"

FG = "#e8eaed"  # ana metin
MUTED = "#8b929e"  # ikincil metin
ACCENT = "#c9a961"  # vurgu (soguk siyahin yaninda sicak duruyor)
ACCENT_DIM = "#8a7541"
DANGER = "#e06c6c"

FONT = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_SMALL = ("Segoe UI", 8)
FONT_MONO = ("Consolas", 9)


def apply(root) -> ttk.Style:
    """Koyu temayi kurar ve Style nesnesini dondurur."""
    root.configure(bg=BG)
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=BG, foreground=FG, font=FONT, borderwidth=0)

    style.configure("TFrame", background=BG)
    style.configure("Surface.TFrame", background=SURFACE)

    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Surface.TLabel", background=SURFACE, foreground=FG)
    style.configure("Muted.TLabel", background=SURFACE, foreground=MUTED, font=FONT_SMALL)
    style.configure("Path.TLabel", background=SURFACE_HI, foreground=MUTED, font=FONT_MONO)
    style.configure("Head.TLabel", background=SURFACE, foreground=ACCENT, font=FONT_BOLD)
    style.configure("Warn.TLabel", background=SURFACE, foreground=ACCENT, font=FONT_SMALL)

    style.configure(
        "TLabelframe", background=SURFACE, bordercolor=BORDER, relief="solid", borderwidth=1
    )
    style.configure("TLabelframe.Label", background=SURFACE, foreground=ACCENT, font=FONT_BOLD)

    style.configure(
        "TButton",
        background=SURFACE_HI,
        foreground=FG,
        bordercolor=BORDER,
        borderwidth=1,
        focuscolor=BORDER,
        padding=(10, 6),
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("pressed", BORDER), ("active", BORDER), ("disabled", SURFACE)],
        foreground=[("disabled", "#4d545e")],
        bordercolor=[("active", BORDER_HI)],
    )

    style.configure(
        "Accent.TButton",
        background=ACCENT_DIM,
        foreground="#12140f",
        bordercolor=ACCENT_DIM,
        font=FONT_BOLD,
    )
    style.map(
        "Accent.TButton",
        background=[("pressed", ACCENT_DIM), ("active", ACCENT), ("disabled", SURFACE)],
        foreground=[("disabled", "#4d545e"), ("active", "#12140f")],
    )

    for widget in ("TEntry", "TSpinbox"):
        style.configure(
            widget,
            fieldbackground=SURFACE_HI,
            background=SURFACE_HI,
            foreground=FG,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            insertcolor=FG,
            arrowcolor=MUTED,
            borderwidth=1,
            padding=4,
        )
        style.map(
            widget,
            bordercolor=[("focus", ACCENT_DIM)],
            fieldbackground=[("disabled", SURFACE)],
            foreground=[("disabled", "#4d545e"), ("invalid", DANGER)],
        )

    style.configure(
        "TCheckbutton", background=SURFACE, foreground=FG, indicatorcolor=SURFACE_HI
    )
    style.map(
        "TCheckbutton",
        background=[("active", SURFACE)],
        indicatorcolor=[("selected", ACCENT), ("pressed", ACCENT_DIM)],
    )

    # clam'da kaydiricinin tutamagi -background, oluk -troughcolor kullanir
    style.configure(
        "Horizontal.TScale",
        background=ACCENT,
        troughcolor=SURFACE_HI,
        bordercolor=BORDER,
        lightcolor=ACCENT,
        darkcolor=ACCENT_DIM,
        gripcount=0,
    )
    style.map("Horizontal.TScale", background=[("active", "#dcbe7a"), ("disabled", BORDER)])

    style.configure(
        "Horizontal.TProgressbar",
        background=ACCENT,
        troughcolor=SURFACE_HI,
        bordercolor=BORDER,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        thickness=14,
    )

    style.configure(
        "Treeview",
        background=SURFACE,
        fieldbackground=SURFACE,
        foreground=MUTED,
        bordercolor=SURFACE,
        lightcolor=SURFACE,
        darkcolor=SURFACE,
        borderwidth=0,
        relief="flat",
        font=FONT_MONO,
        rowheight=19,
    )
    style.map("Treeview", background=[("selected", SURFACE_HI)], foreground=[("selected", FG)])

    style.configure("TSeparator", background=BORDER)

    return style


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _lerp(a: str, b: str, t: float) -> str:
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return "#{:02x}{:02x}{:02x}".format(
        round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t)
    )


class Pulse:
    """Bir dugmeyi nefes alir gibi yanip sondurur.

    ttk dugmelerinin rengi widget'ta degil stilde durur, o yuzden her dugmeye
    kendi stil adi veriliyor ve animasyon o stili guncelliyor. Stil adi
    "<ad>.TButton" bicimindeyse temel stilin tum durum eslemelerini (hover,
    disabled) miras alir.

    Amac dikkat cekmek: kullanici bir kez tikladiktan sonra `stop` cagrilir ve
    dugme sabit gorunume doner.
    """

    def __init__(
        self,
        widget: ttk.Widget,
        style: ttk.Style,
        style_name: str,
        base_style: str,
        colors: dict[str, tuple[str, str]],
        period_ms: int = 1800,
        interval_ms: int = 60,
    ) -> None:
        self.widget = widget
        self.style = style
        self.style_name = style_name
        self.base_style = base_style
        self.colors = colors
        self.period = period_ms / 1000.0
        self.interval = interval_ms
        self._job: str | None = None
        self._t0 = 0.0

    @property
    def running(self) -> bool:
        return self._job is not None

    def start(self) -> None:
        if self._job is not None:
            return
        self._t0 = time.monotonic()
        self._tick()

    def stop(self) -> None:
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        try:
            self.widget.configure(style=self.base_style)
        except Exception:
            pass

    def _tick(self) -> None:
        # 0 -> 1 -> 0 arasi yumusak gidis gelis
        elapsed = (time.monotonic() - self._t0) % self.period
        phase = (1.0 - math.cos(2.0 * math.pi * elapsed / self.period)) / 2.0
        try:
            self.style.configure(
                self.style_name,
                **{opt: _lerp(a, b, phase) for opt, (a, b) in self.colors.items()},
            )
            self.widget.configure(style=self.style_name)
            self._job = self.widget.after(self.interval, self._tick)
        except Exception:
            self._job = None


def make_pulse(widget: ttk.Widget, style: ttk.Style, kind: str) -> Pulse:
    """Hazir iki nefes efekti: normal dugme ve vurgulu dugme."""
    if kind == "accent":
        return Pulse(
            widget,
            style,
            "Pulse.Accent.TButton",
            "Accent.TButton",
            {"background": (ACCENT_DIM, "#f0d391"), "bordercolor": (ACCENT_DIM, "#f0d391")},
        )
    return Pulse(
        widget,
        style,
        "Pulse.TButton",
        "TButton",
        {
            "background": (SURFACE_HI, "#2e3542"),
            "bordercolor": (BORDER, ACCENT),
            "foreground": (FG, ACCENT),
        },
    )


def dark_titlebar(window) -> None:
    """Windows 11'de baslik cubugunu koyu yapar. Desteklenmiyorsa sessizce gecer."""
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE, eski yapilarda 19
        for attr in (20, 19):
            ok = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
            )
            if ok == 0:
                return
    except Exception:
        pass
