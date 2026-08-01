"""Video -> .xlsm donusumunun ortak mantigi.

CLI ve GUI ayni yolu kullansin diye burada topluyoruz; ilerleme bildirimi
disaridan verilen bir callback ile yapiliyor, boylece modul arayuzden bagimsiz
kaliyor.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import pipeline, player, video

Progress = Callable[[str], None]


def _noop(_: str) -> None:
    pass


class Reporter:
    """Metin gunlugu + 0..1 arasi genel ilerleme bildirir.

    Her adim kendi icinde 0'dan basladigini bilir; genel yuzdeye cevirmeyi
    `phase` ile belirlenen araliga gore burasi yapar. Boylece adimlarin
    genel ilerlemedeki agirligini tek yerden ayarlayabiliyoruz.
    """

    def __init__(
        self,
        on_log: Progress = _noop,
        on_progress: Callable[[float, str], None] | None = None,
    ) -> None:
        self.on_log = on_log
        self.on_progress = on_progress
        self._lo = 0.0
        self._hi = 1.0
        self._label = ""

    def log(self, msg: str) -> None:
        self.on_log(msg)

    def phase(self, label: str, lo: float, hi: float) -> None:
        self._label, self._lo, self._hi = label, lo, hi
        if self.on_progress:
            self.on_progress(lo, label)

    def tick(self, done: int, total: int) -> None:
        if not self.on_progress or total <= 0:
            return
        frac = self._lo + (self._hi - self._lo) * min(1.0, done / total)
        self.on_progress(frac, self._label)

    def done(self) -> None:
        if self.on_progress:
            self.on_progress(1.0, "Done")


# Adimlarin genel ilerlemedeki paylari. Excel yazimi acik ara en uzun adim.
PHASES = {
    "background": (0.00, 0.08),
    "bbox": (0.08, 0.26),
    "read": (0.26, 0.40),
    "mosaic": (0.40, 0.56),
    "write": (0.56, 0.92),
    "excel": (0.92, 1.00),
}


# (en az, en cok) - arayuz ve CLI ayni sinirlari kullansin diye burada
LIMITS = {
    "cols": (16, 200),
    "colors": (2, 32),
    "sub": (2, 12),
    "fps": (0.0, 120.0),
    "max_frames": (0, 100_000),
}


@dataclass
class Settings:
    cols: int = 64
    colors: int = 32
    fps: float = 0.0  # 0 = kaynakla ayni
    max_frames: int = 0  # 0 = tumu
    autocrop: bool = True
    sub: int = 4  # hucre basina ornekleme (sub x sub piksel)

    def clamped(self) -> tuple["Settings", list[str]]:
        """Sinir disi degerleri kirpar ve neyi degistirdigini bildirir."""
        notes: list[str] = []
        values = {
            "cols": self.cols,
            "colors": self.colors,
            "sub": self.sub,
            "fps": self.fps,
            "max_frames": self.max_frames,
        }
        for name, value in values.items():
            lo, hi = LIMITS[name]
            new = min(max(value, lo), hi)
            if new != value:
                notes.append(f"{name}: {value} -> {new} (allowed {lo}-{hi})")
                values[name] = new
        return (
            Settings(
                cols=int(values["cols"]),
                colors=int(values["colors"]),
                fps=float(values["fps"]),
                max_frames=int(values["max_frames"]),
                autocrop=self.autocrop,
                sub=int(values["sub"]),
            ),
            notes,
        )


def max_supported_cols(crop_width: int, sub: int) -> int:
    """Kaynagin buyutme yapmadan besleyebilecegi en yuksek sutun sayisi.

    Her hucre sub x sub piksel orneklendigi icin sutun basina sub piksel gerekir.
    """
    return max(1, crop_width // sub)


@dataclass
class Analysis:
    info: video.VideoInfo
    box: video.BBox | None
    step: int
    effective_fps: float

    @property
    def n_frames(self) -> int:
        return (self.info.frame_count + self.step - 1) // self.step


class UnreadableVideoError(ValueError):
    """Dosya video olarak acilamadi ya da icinde kare yok."""


def analyze(src: str | Path, settings: Settings, reporter: Reporter | None = None) -> Analysis:
    """Video bilgisi, kirpma kutusu ve kare atlama adimini hesaplar.

    Kirpma kutusu videoyu bastan sona okur; pahali oldugu icin cagiran taraf
    sonucu onbellege almak isteyebilir.
    """
    rep = reporter or Reporter()
    try:
        info = video.probe(src)
    except OSError as exc:
        raise UnreadableVideoError(str(exc)) from exc

    if info.frame_count <= 0:
        raise UnreadableVideoError("No readable frames in this file.")
    if info.fps <= 0:
        raise UnreadableVideoError("Could not read the video frame rate (0 fps).")

    rep.log(
        f"Video: {info.width}x{info.height}, {info.fps:.2f} fps, "
        f"{info.frame_count} frames, {info.duration:.2f} s"
    )

    target_fps = settings.fps if settings.fps > 0 else info.fps
    step = max(1, round(info.fps / target_fps)) if target_fps > 0 else 1
    effective_fps = info.fps / step
    if step > 1:
        rep.log(f"Frame skip: every {step}th frame -> {effective_fps:.2f} fps")

    box = None
    if settings.autocrop:
        rep.phase("Building background model", *PHASES["background"])
        rep.log("Building background model...")
        bg = video.background_model(src, tick=rep.tick)

        rep.phase("Locating subject", *PHASES["bbox"])
        rep.log("Locating subject...")
        box = video.subject_bbox(src, bg, tick=rep.tick)

        pct = 100 * box.width * box.height / (info.width * info.height)
        rep.log(
            f"Crop: ({box.x0},{box.y0})-({box.x1},{box.y1}) = "
            f"{box.width}x{box.height} ({pct:.0f}% of frame)"
        )

    return Analysis(info=info, box=box, step=step, effective_fps=effective_fps)


def read_frames(
    src: str | Path,
    analysis: Analysis,
    settings: Settings,
    reporter: Reporter | None = None,
) -> list[np.ndarray]:
    rep = reporter or Reporter()
    expected = analysis.n_frames
    if settings.max_frames:
        expected = min(expected, settings.max_frames)

    frames: list[np.ndarray] = []
    for f in video.read_frames(src, stride=analysis.step):
        frames.append(analysis.box.crop(f) if analysis.box else f)
        rep.tick(len(frames), expected)
        if settings.max_frames and len(frames) >= settings.max_frames:
            break
    rep.log(f"Frames read: {len(frames)}")
    return frames


def sample_frames(
    src: str | Path,
    analysis: Analysis,
    count: int,
    include: int | None = None,
) -> tuple[list[np.ndarray], int]:
    """Palet icin videoya yayilmis birkac kare alir.

    include verilirse o kare de listeye eklenir ve indeksi dondurulur; onizleme
    boylece uretimdekiyle ayni paleti kullanir.
    """
    total = analysis.info.frame_count
    wanted = sorted({int(round(i * (total - 1) / max(1, count - 1))) for i in range(count)})
    if include is not None:
        wanted = sorted(set(wanted) | {include})

    frames: list[np.ndarray] = []
    picked: list[int] = []
    target_pos = -1
    for i, f in enumerate(video.read_frames(src)):
        if i in wanted:
            frames.append(analysis.box.crop(f) if analysis.box else f)
            picked.append(i)
        if i >= wanted[-1]:
            break
    if include is not None and include in picked:
        target_pos = picked.index(include)
    return frames, target_pos


def convert(
    src: str | Path,
    out: str | Path,
    settings: Settings,
    reporter: Reporter | None = None,
    analysis: Analysis | None = None,
) -> dict:
    """Videodan oynatilabilir .xlsm uretir."""
    rep = reporter or Reporter()
    if analysis is None:
        analysis = analyze(src, settings, rep)

    rep.phase("Reading frames", *PHASES["read"])
    frames = read_frames(src, analysis, settings, rep)
    if not frames:
        raise UnreadableVideoError("Could not read any frames from the video.")

    rep.phase("Building mosaic", *PHASES["mosaic"])
    rep.log("Building mosaic...")
    mosaic = pipeline.build(
        frames, cols=settings.cols, colors=settings.colors, sub=settings.sub, tick=rep.tick
    )
    rep.log(f"Grid: {mosaic.cols} x {mosaic.rows} = {mosaic.cols * mosaic.rows} cells")

    rep.phase("Writing Excel file", *PHASES["write"])
    rep.log("Writing Excel file (longest step)...")
    result = player.build(mosaic, out, fps=analysis.effective_fps, tick=rep.tick)

    rep.phase("Embedding player", *PHASES["excel"])
    rep.log(
        f"Done: {result['path']} ({result['size_mb']:.1f} MB, "
        f"{result['formats']} unique formats)"
    )
    rep.done()
    result["fps"] = analysis.effective_fps
    result["cells"] = mosaic.cols * mosaic.rows
    result["grid"] = f"{mosaic.cols}x{mosaic.rows}"
    result["frames"] = mosaic.n_frames
    return result
