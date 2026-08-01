"""Test arayuzu (Tkinter, koyu tema).

Amaci farkli videolari hizlica denemek: ayarlari degistir, tek karenin
onizlemesine bak, begenirsen tam dosyayi uret. Onizleme uretimdekiyle ayni
paleti kullanir, yani ekranda gordugun Excel'de de o sekilde cikar.

Agir isler (kirpma analizi, mozaik, dosya yazimi) ayri bir is parcaciginda
calisir; sonuclar kuyruk uzerinden ana parcaciga tasinir. Tkinter yalnizca
ana parcaciktan guvenle cagrilabilir.

Arayuz metinleri Ingilizce, kod yorumlari Turkce.

    python -m excelvid.gui
"""

from __future__ import annotations

import os
import queue
import threading
import traceback
from pathlib import Path
from tkinter import (
    BOTH,
    DISABLED,
    END,
    HORIZONTAL,
    LEFT,
    NORMAL,
    RIGHT,
    X,
    BooleanVar,
    Canvas,
    IntVar,
    StringVar,
    Tk,
    filedialog,
    messagebox,
    ttk,
)

import numpy as np
from PIL import Image, ImageTk

from . import convert, pipeline, player, render, theme

ASSETS = Path(__file__).resolve().parent.parent / "assets"
ICON_ICO = ASSETS / "icon.ico"
ICON_PNG = ASSETS / "icon.png"

PREVIEW_PALETTE_FRAMES = 8
VIDEO_SUFFIXES = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".mpg", ".mpeg")

# Onizleme alaninin en az kaplamasi gereken yer; pencere alt siniri
# hesaplanirken kullaniliyor.
MIN_CANVAS_W = 560
MIN_CANVAS_H = 320

# Cerceve kenarliklari winfo_reqheight toplamina tam yansimiyor; olculen fark
# birkac piksel. Yazi tipi/DPI degisiminde de buyuyebilecegi icin pay birakiyoruz.
FIT_MARGIN = 16


class App(ttk.Frame):
    def __init__(self, master: Tk) -> None:
        super().__init__(master, padding=12, style="TFrame")
        self.master.title("Excel Video Converter")
        self.pack(fill=BOTH, expand=True)

        self.queue: queue.Queue = queue.Queue()
        self.busy = False
        self.src: Path | None = None
        self.analysis: convert.Analysis | None = None
        self.analysis_key: tuple | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.last_output: Path | None = None

        # Ilk kullanimda hangi dugmeye basilacagini gostermek icin nefes efekti;
        # kullanici bir kez tiklayinca bir daha calismaz.
        self.used_browse = False
        self.used_build = False

        self._build_ui()
        self._build_pulses()
        self._sync_enabled()
        self.after_idle(self._fit_window)
        self.after(80, self._pump)

    def _build_pulses(self) -> None:
        style = ttk.Style(self)
        self.pulse_browse = theme.make_pulse(self.btn_browse, style, "normal")
        self.pulse_build = theme.make_pulse(self.btn_build, style, "accent")

    def _fit_window(self) -> None:
        """Pencere alt sinirini panelin gercek yuksekliginden turetir.

        Sabit bir minsize vermek yazi tipi/DPI degisince yetmiyordu; panel
        kirpilip alttaki dugme yariya iniyordu. Widget'lara kendi istedikleri
        olcuyu sorup pencereyi ona gore sinirliyoruz.
        """
        self.update_idletasks()
        pad = 12 * 2  # cerceve dolgusu

        need_h = (
            self.path_box.winfo_reqheight()
            + 10  # ust satir alt bosluk
            + max(self.side.winfo_reqheight(), MIN_CANVAS_H + self.prog.winfo_reqheight() + 10)
            + 12  # metrik ust boslugu
            + self.metrics.winfo_reqheight()
            + pad
            + FIT_MARGIN
        )
        need_w = self.side.winfo_reqwidth() + 12 + MIN_CANVAS_W + pad

        self.master.minsize(need_w, need_h)
        if (
            self.master.winfo_width() < need_w
            or self.master.winfo_height() < need_h
        ):
            self.master.geometry(f"{max(need_w, 1180)}x{max(need_h, 780)}")

    # ------------------------------------------------------------------ duzen
    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        # --- ust satir: video sec + adres -----------------------------------
        self.btn_browse = ttk.Button(self, text="Choose video...", command=self.on_browse)
        self.btn_browse.grid(row=0, column=0, sticky="ew", padx=(0, 12), pady=(0, 10))

        self.path_box = ttk.Frame(self, style="Surface.TFrame", padding=(10, 8))
        self.path_box.grid(row=0, column=1, sticky="ew", pady=(0, 10))
        self.path_var = StringVar(value="No video selected yet")
        ttk.Label(self.path_box, textvariable=self.path_var, style="Path.TLabel").pack(
            anchor="w", fill=X
        )

        # --- sol sutun: ayarlar ---------------------------------------------
        self.side = ttk.Labelframe(self, text=" Settings ", padding=12)
        self.side.grid(row=1, column=0, rowspan=2, sticky="ns", padx=(0, 12))
        self._build_settings(self.side)

        # --- sag: onizleme ---------------------------------------------------
        self.canvas = Canvas(
            self, bg=theme.SURFACE, highlightthickness=1, highlightbackground=theme.BORDER
        )
        self.canvas.grid(row=1, column=1, sticky="nsew")
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas_hint()

        # --- ilerleme --------------------------------------------------------
        self.prog = ttk.Frame(self, style="Surface.TFrame", padding=(10, 8))
        self.prog.grid(row=2, column=1, sticky="ew", pady=(10, 0))
        self.prog.columnconfigure(0, weight=1)

        self.progress_value = IntVar(value=0)
        ttk.Progressbar(
            self.prog, mode="determinate", maximum=1000, variable=self.progress_value
        ).grid(row=0, column=0, sticky="ew")
        self.progress_text = StringVar(value="Ready")
        ttk.Label(
            self.prog, textvariable=self.progress_text, style="Muted.TLabel", width=32, anchor="e"
        ).grid(row=0, column=1, padx=(10, 0))

        # --- alt: cikti metrikleri ------------------------------------------
        self.metrics = ttk.Labelframe(self, text=" Output metrics ", padding=(1, 4))
        self.metrics.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.log = ttk.Treeview(self.metrics, columns=("m",), show="", height=7)
        self.log.column("m", anchor="w")
        self.log.pack(fill=X, padx=6, pady=4)

    def _build_settings(self, side: ttk.Labelframe) -> None:
        self.cols = IntVar(value=64)
        self.colors = IntVar(value=32)
        self.sub = IntVar(value=4)
        self.max_frames = IntVar(value=0)
        self.fps = StringVar(value="0")
        self.autocrop = BooleanVar(value=True)

        row = 0
        row = self._int_field(side, "Columns", self.cols, "cols", row)
        row = self._int_field(side, "Colors", self.colors, "colors", row)
        row = self._int_field(side, "Sampling (sub)", self.sub, "sub", row)
        row = self._int_field(side, "Frame limit (0 = all)", self.max_frames, "max_frames", row)
        row = self._float_field(side, "Target fps (0 = source)", self.fps, row)

        ttk.Checkbutton(
            side, text="Auto-crop to subject", variable=self.autocrop,
            command=self._on_autocrop_toggle,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 2))
        row += 1

        self.warn_var = StringVar(value="")
        ttk.Label(
            side, textvariable=self.warn_var, style="Warn.TLabel", wraplength=210, justify=LEFT
        ).grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1

        ttk.Separator(side, orient=HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=8
        )
        row += 1

        ttk.Label(side, text="SOURCE", style="Head.TLabel").grid(
            row=row, column=0, columnspan=2, sticky="w"
        )
        row += 1
        self.info_var = StringVar(value="-")
        ttk.Label(
            side, textvariable=self.info_var, style="Muted.TLabel", justify=LEFT, wraplength=210
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 0))
        row += 1

        ttk.Separator(side, orient=HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=8
        )
        row += 1

        ttk.Label(side, text="Preview frame", style="Muted.TLabel").grid(
            row=row, column=0, columnspan=2, sticky="w"
        )
        row += 1
        scale_row = ttk.Frame(side, style="Surface.TFrame")
        scale_row.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(2, 8))
        self.frame_idx = IntVar(value=0)
        self.frame_scale = ttk.Scale(
            scale_row, from_=0, to=0, orient=HORIZONTAL, variable=self.frame_idx,
            command=lambda _v: self.frame_idx.set(int(float(_v))),
        )
        self.frame_scale.pack(side=LEFT, fill=X, expand=True)
        self.frame_label = StringVar(value="0")
        ttk.Label(
            scale_row, textvariable=self.frame_label, style="Muted.TLabel", width=6, anchor="e"
        ).pack(side=RIGHT)
        self.frame_idx.trace_add(
            "write", lambda *_: self.frame_label.set(str(int(self.frame_idx.get())))
        )
        row += 1

        self.btn_preview = ttk.Button(side, text="Preview", command=self.on_preview)
        self.btn_preview.grid(row=row, column=0, columnspan=2, sticky="ew", pady=2)
        row += 1
        self.btn_build = ttk.Button(
            side, text="Build Excel file", style="Accent.TButton", command=self.on_build
        )
        self.btn_build.grid(row=row, column=0, columnspan=2, sticky="ew", pady=2)
        row += 1
        self.btn_open = ttk.Button(side, text="Open in Excel", command=self.on_open)
        self.btn_open.grid(row=row, column=0, columnspan=2, sticky="ew", pady=2)

    # ------------------------------------------------------- girdi dogrulama
    def _int_field(self, parent, label: str, var: IntVar, key: str, row: int) -> int:
        lo, hi = convert.LIMITS[key]
        ttk.Label(parent, text=label, style="Surface.TLabel").grid(
            row=row, column=0, sticky="w", pady=3
        )
        spin = ttk.Spinbox(
            parent, from_=lo, to=hi, textvariable=var, width=7,
            validate="key", validatecommand=(self.register(self._only_digits), "%P"),
        )
        spin.grid(row=row, column=1, sticky="e", pady=3)
        spin.bind("<FocusOut>", lambda _e, v=var, k=key: self._clamp_int(v, k))
        return row + 1

    def _float_field(self, parent, label: str, var: StringVar, row: int) -> int:
        ttk.Label(parent, text=label, style="Surface.TLabel").grid(
            row=row, column=0, sticky="w", pady=3
        )
        entry = ttk.Entry(
            parent, textvariable=var, width=9,
            validate="key", validatecommand=(self.register(self._only_decimal), "%P"),
        )
        entry.grid(row=row, column=1, sticky="e", pady=3)
        entry.bind("<FocusOut>", lambda _e: self._clamp_fps())
        return row + 1

    @staticmethod
    def _only_digits(proposed: str) -> bool:
        """Yalnizca rakam kabul et; bos birakmaya izin ver (kullanici siliyordur)."""
        return proposed == "" or proposed.isdigit()

    @staticmethod
    def _only_decimal(proposed: str) -> bool:
        if proposed in ("", ".", ","):
            return True
        try:
            float(proposed.replace(",", "."))
        except ValueError:
            return False
        return True

    def _clamp_int(self, var: IntVar, key: str) -> None:
        lo, hi = convert.LIMITS[key]
        try:
            value = int(var.get())
        except Exception:
            value = lo
        clamped = min(max(value, lo), hi)
        if clamped != value:
            self._log(f"{key}: {value} out of range, set to {clamped} (allowed {lo}-{hi})")
        var.set(clamped)
        self._update_warning()

    def _clamp_fps(self) -> None:
        lo, hi = convert.LIMITS["fps"]
        try:
            value = float(self.fps.get().replace(",", "."))
        except ValueError:
            value = 0.0
        self.fps.set(f"{min(max(value, lo), hi):g}")

    def _update_warning(self) -> None:
        """Sutun sayisi kaynagin besleyebileceginin ustundeyse uyar."""
        if not self.analysis or not self.analysis.box:
            self.warn_var.set("")
            return
        limit = convert.max_supported_cols(self.analysis.box.width, int(self.sub.get() or 4))
        before = self.warn_var.get()
        if int(self.cols.get() or 0) > limit:
            self.warn_var.set(
                f"Warning: this source only feeds {limit} columns with real pixels. "
                "Above that, part of the detail is interpolated."
            )
        else:
            self.warn_var.set("")

        # Uyari metni paneli uzatabilir; alt siniri yeniden hesapla ki
        # en alttaki dugme kirpilmasin.
        if before != self.warn_var.get():
            self.after_idle(self._fit_window)

    def _on_autocrop_toggle(self) -> None:
        self.analysis = None
        self.analysis_key = None
        self._update_warning()

    # ------------------------------------------------------------------ olaylar
    def on_browse(self) -> None:
        self.used_browse = True
        self._sync_pulse()

        path = filedialog.askopenfilename(
            title="Choose video",
            filetypes=[
                ("Video files", " ".join(f"*{s}" for s in VIDEO_SUFFIXES)),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        candidate = Path(path)
        if not candidate.is_file():
            messagebox.showerror("Not a file", "The selected path is not a file.")
            return
        if candidate.stat().st_size == 0:
            messagebox.showerror("Empty file", "The selected file is empty.")
            return

        # Uzanti guvenilir degil (elimizdeki ornek .undefined uzantiliydi ve
        # gecerli bir MP4'tu), o yuzden karar OpenCV'nin acabilmesine birakiliyor.
        self.src = candidate
        self.path_var.set(str(candidate))
        self.analysis = None
        self.analysis_key = None
        self.last_output = None
        self._log(f"Selected: {candidate.name}")
        self._start(self._work_analyze)

    def on_preview(self) -> None:
        if not self._ready():
            return
        self._start(self._work_preview)

    def on_build(self) -> None:
        self.used_build = True
        self._sync_pulse()
        if not self._ready():
            return

        out = filedialog.asksaveasfilename(
            title="Output file",
            defaultextension=".xlsm",
            initialfile=f"{self.src.stem}.xlsm",
            filetypes=[("Excel macro-enabled workbook", "*.xlsm")],
        )
        if not out:
            return

        target = Path(out)
        if target.suffix.lower() != ".xlsm":
            target = target.with_suffix(".xlsm")
        if not self._writable(target):
            return
        self._start(lambda: self._work_build(target))

    def _writable(self, target: Path) -> bool:
        """Yazma iznini ve dosyanin Excel'de acik olmadigini onceden dogrula."""
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Cannot create folder", str(exc))
            return False
        if target.exists():
            try:
                with target.open("ab"):
                    pass
            except PermissionError:
                messagebox.showerror(
                    "File is locked",
                    f"{target.name} is currently open in another program "
                    "(most likely Excel). Close it and try again.",
                )
                return False
            except OSError as exc:
                messagebox.showerror("Cannot write file", str(exc))
                return False
        return True

    def on_open(self) -> None:
        if self.last_output and self.last_output.exists():
            os.startfile(str(self.last_output))

    # ------------------------------------------------------------------ isler
    def _settings(self) -> convert.Settings:
        def as_int(var: IntVar, key: str) -> int:
            lo, hi = convert.LIMITS[key]
            try:
                return min(max(int(var.get()), lo), hi)
            except Exception:
                return lo

        try:
            fps = float(self.fps.get().replace(",", "."))
        except ValueError:
            fps = 0.0

        return convert.Settings(
            cols=as_int(self.cols, "cols"),
            colors=as_int(self.colors, "colors"),
            sub=as_int(self.sub, "sub"),
            max_frames=as_int(self.max_frames, "max_frames"),
            fps=max(0.0, fps),
            autocrop=bool(self.autocrop.get()),
        )

    def _reporter(self) -> convert.Reporter:
        return convert.Reporter(
            on_log=self._post_log,
            on_progress=lambda frac, label: self.queue.put(("progress", (frac, label))),
        )

    def _ensure_analysis(self, settings: convert.Settings) -> convert.Analysis:
        """Kirpma analizi videoyu bastan sona okur; ayarlar degismedikce tekrarlama."""
        key = (str(self.src), settings.autocrop, settings.fps)
        if self.analysis is None or self.analysis_key != key:
            self.analysis = convert.analyze(self.src, settings, self._reporter())
            self.analysis_key = key
            self.queue.put(("analysis", self.analysis))
        return self.analysis

    def _work_analyze(self) -> None:
        self._ensure_analysis(self._settings())

    def _work_preview(self) -> None:
        settings = self._settings()
        analysis = self._ensure_analysis(settings)

        wanted = min(int(self.frame_idx.get()) * analysis.step, analysis.info.frame_count - 1)
        self._post_log(f"Preparing preview of frame {wanted}...")
        self.queue.put(("progress", (0.5, "Building preview")))

        frames, pos = convert.sample_frames(
            self.src, analysis, PREVIEW_PALETTE_FRAMES, include=wanted
        )
        if not frames:
            raise convert.UnreadableVideoError("Could not read a frame for the preview.")
        mosaic = pipeline.build(
            frames, cols=settings.cols, colors=settings.colors, sub=settings.sub
        )

        pos = max(0, pos)
        grid = render.CellGrid(
            fill_rgb=mosaic.palette[mosaic.fill_idx[pos]],
            font_rgb=mosaic.palette[mosaic.font_idx[pos]],
            coverage=np.zeros(1, dtype=np.float32),
        )
        self.queue.put(("preview", (grid, mosaic.char_idx[pos], mosaic.chars, mosaic)))

    def _work_build(self, out: Path) -> None:
        settings = self._settings()
        analysis = self._ensure_analysis(settings)
        result = convert.convert(self.src, out, settings, self._reporter(), analysis=analysis)
        self.queue.put(("built", result))

    # ------------------------------------------------------------- is parcacigi
    def _start(self, fn) -> None:
        if self.busy:
            self._log("Wait for the current operation to finish.")
            return
        self.busy = True
        self._sync_enabled()
        self.progress_value.set(0)
        self.progress_text.set("Starting...")

        def runner() -> None:
            try:
                fn()
            except convert.UnreadableVideoError as exc:
                self.queue.put((
                    "error",
                    ("Cannot read video",
                     f"{exc}\n\nThe file may be corrupt or the codec unsupported. "
                     "Try another file."),
                ))
            except player.MissingVbaProjectError as exc:
                self.queue.put(("error", ("Player macro missing", str(exc))))
            except PermissionError as exc:
                self.queue.put((
                    "error",
                    ("Cannot write file",
                     f"{exc}\n\nThe output file may be open in Excel. Close it and try again."),
                ))
            except Exception as exc:
                self.queue.put(
                    ("error", (type(exc).__name__, f"{exc}\n\n{traceback.format_exc()}"))
                )
            finally:
                self.queue.put(("idle", None))

        threading.Thread(target=runner, daemon=True).start()

    def _post_log(self, msg: str) -> None:
        self.queue.put(("log", msg))

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "progress":
                    frac, label = payload
                    self.progress_value.set(int(frac * 1000))
                    self.progress_text.set(f"{label}  {frac * 100:.0f}%")
                elif kind == "analysis":
                    self._apply_analysis(payload)
                elif kind == "preview":
                    self._draw_preview(*payload)
                elif kind == "built":
                    self._apply_built(payload)
                elif kind == "error":
                    title, detail = payload
                    self._log(f"ERROR: {title}")
                    self.progress_text.set("Failed")
                    self.progress_value.set(0)
                    messagebox.showerror(title, detail)
                elif kind == "idle":
                    self.busy = False
                    self._sync_enabled()
                    if self.progress_text.get().startswith("Starting"):
                        self.progress_text.set("Ready")
        except queue.Empty:
            pass
        self.after(80, self._pump)

    # ------------------------------------------------------------------ cizim
    def _apply_analysis(self, analysis: convert.Analysis) -> None:
        n = analysis.n_frames
        self.frame_scale.configure(to=max(0, n - 1))
        self.frame_idx.set(min(int(self.frame_idx.get()), max(0, n - 1)))

        crop = f"{analysis.box.width}x{analysis.box.height}" if analysis.box else "no crop"
        width = analysis.box.width if analysis.box else analysis.info.width
        limit = convert.max_supported_cols(width, int(self.sub.get() or 4))
        self.info_var.set(
            f"{analysis.info.width}x{analysis.info.height} source\n"
            f"{analysis.info.fps:.2f} fps, {analysis.info.duration:.1f} s\n"
            f"frames to process: {n}\n"
            f"crop: {crop}\n"
            f"output fps: {analysis.effective_fps:.2f}\n"
            f"suggested max columns: {limit}"
        )
        self._update_warning()
        self._sync_enabled()

    def _apply_built(self, result: dict) -> None:
        self.last_output = Path(result["path"])
        self._log(
            f"Output: {self.last_output.name} | {result['grid']} = {result['cells']} cells | "
            f"{result['frames']} frames | {result['fps']:.2f} fps | "
            f"{result['size_mb']:.1f} MB | {result['formats']} formats"
        )
        self._log("Press Ctrl+Shift+P in Excel to play, ESC to stop.")
        self.progress_text.set("Done  100%")
        self._sync_enabled()

        if messagebox.askyesno(
            "File ready",
            f"{self.last_output.name} has been created.\n\n"
            "TO PLAY:   Ctrl + Shift + P\n"
            "TO STOP:   ESC\n\n"
            "Click 'Enable Content' in the yellow bar when the file opens; "
            "playback will not work until macros are enabled.\n\n"
            "Open it in Excel now?",
            icon=messagebox.INFO,
        ):
            self.on_open()

    def _canvas_hint(self) -> None:
        self.canvas.delete("all")
        w = max(self.canvas.winfo_width(), 100)
        h = max(self.canvas.winfo_height(), 100)
        self.canvas.create_text(
            w // 2, h // 2,
            text="Choose a video, adjust settings, then Preview",
            fill=theme.MUTED, font=("Segoe UI", 11),
        )

    def _on_canvas_resize(self, _event) -> None:
        if self.photo is None:
            self._canvas_hint()

    def _draw_preview(self, grid, char_idx, chars, mosaic) -> None:
        cw = max(self.canvas.winfo_width(), 50)
        ch = max(self.canvas.winfo_height(), 50)
        rows, cols = grid.fill_rgb.shape[:2]
        cell = max(3, min(cw // cols, ch // rows))

        img = Image.fromarray(render.preview(grid, char_idx, chars, cell_px=cell))
        # Karakterlerin okunabilmesi icin hucre en az 3 piksel ciziliyor; bu
        # taban yuzunden yuksek sutun sayilarinda goruntu tuvali asabiliyor,
        # o yuzden cizimden sonra sigacak sekilde kuculuyoruz.
        if img.width > cw - 8 or img.height > ch - 8:
            img.thumbnail((max(1, cw - 8), max(1, ch - 8)), Image.LANCZOS)
        self.photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, image=self.photo)

        used = len(np.unique(char_idx))
        self._log(
            f"Preview: {mosaic.cols}x{mosaic.rows} = {mosaic.cols * mosaic.rows} cells | "
            f"{len(mosaic.palette)} colors | {used}/{len(mosaic.chars)} characters used"
        )
        self.progress_text.set("Preview ready")
        self.progress_value.set(1000)

    def _sync_enabled(self) -> None:
        has_video = self.src is not None
        state = DISABLED if (self.busy or not has_video) else NORMAL
        self.btn_preview.configure(state=state)
        self.btn_build.configure(state=state)
        ready = self.last_output is not None and self.last_output.exists() and not self.busy
        self.btn_open.configure(state=NORMAL if ready else DISABLED)
        self._sync_pulse()

    def _sync_pulse(self) -> None:
        """Sirasi gelen ve henuz kullanilmamis dugmeyi nefes aldirir."""
        want_browse = not self.used_browse and not self.busy
        # Uret dugmesi ancak tiklanabilir hale geldiginde dikkat cekmeli
        want_build = not self.used_build and not self.busy and self.src is not None

        for pulse, want in ((self.pulse_browse, want_browse), (self.pulse_build, want_build)):
            if want and not pulse.running:
                pulse.start()
            elif not want and pulse.running:
                pulse.stop()

    def _log(self, msg: str) -> None:
        self.log.insert("", END, values=(msg,))
        children = self.log.get_children()
        if len(children) > 300:
            self.log.delete(children[0])
        self.log.see(children[-1])

    def _ready(self) -> bool:
        if self.src is None:
            messagebox.showinfo("No video", "Choose a video first.")
            return False
        if not self.src.exists():
            messagebox.showerror("File missing", f"{self.src} no longer exists.")
            self.src = None
            self._sync_enabled()
            return False
        return True


def _set_taskbar_identity() -> None:
    """Gorev cubugunda Python'un ikonu yerine bizimki gorunsun.

    Windows, pencereleri AppUserModelID'ye gore grupluyor; belirtilmezse
    pythonw.exe'nin kimligi kullaniliyor ve ikon da ondan aliniyor. Pencere
    olusturulmadan once cagrilmali.
    """
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("excelvid.converter")
    except Exception:
        pass


def _apply_icon(root: Tk) -> None:
    """Pencere ikonunu ayarlar; ICO yoksa PNG'ye duser."""
    if ICON_ICO.exists():
        try:
            root.iconbitmap(default=str(ICON_ICO))
            return
        except Exception:
            pass
    if ICON_PNG.exists():
        try:
            image = ImageTk.PhotoImage(file=str(ICON_PNG))
            root.iconphoto(True, image)
            root._icon_ref = image  # cop toplayici almasin diye referans tut
        except Exception:
            pass


def main() -> None:
    _set_taskbar_identity()
    root = Tk()
    _apply_icon(root)
    theme.apply(root)
    App(root)
    theme.dark_titlebar(root)
    root.mainloop()


if __name__ == "__main__":
    main()
