"""Video okuma, arka plan modeli ve ozne kirpmasi.

Kaynak videolarda ozne genelde karenin kucuk bir kismini kaplar. Tum kareyi
izgaraya verirsek sutunlarin cogu bos zemine, paletin cogu da o zeminin
tonlarina gider. Bu yuzden once oznenin tum video boyunca gezdigi alani
buluyor, izgarayi o alana ayirilyoruz.

Kirpma kutusu kare basina degil, tum kareler icin **tek** hesaplanir; kare
basina kirpsaydik izgara oznenin etrafinda kayar, kamera sarsiliyormus gibi
gorunurdu.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import cv2
import numpy as np

# Ilerleme bildirimi: (islenen, toplam)
Tick = Callable[[int, int], None]


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: float
    frame_count: int

    @property
    def duration(self) -> float:
        return self.frame_count / self.fps if self.fps else 0.0


@dataclass(frozen=True)
class BBox:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    def crop(self, img: np.ndarray) -> np.ndarray:
        return img[self.y0 : self.y1, self.x0 : self.x1]


def probe(path: str | Path) -> VideoInfo:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise OSError(f"Could not open video: {path}")
    try:
        return VideoInfo(
            width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            fps=float(cap.get(cv2.CAP_PROP_FPS)),
            frame_count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        )
    finally:
        cap.release()


def read_frames(path: str | Path, stride: int = 1) -> Iterator[np.ndarray]:
    """Kareleri RGB olarak sirayla verir."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise OSError(f"Could not open video: {path}")
    try:
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % stride == 0:
                yield cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            i += 1
    finally:
        cap.release()


def background_model(path: str | Path, samples: int = 40, tick: Tick | None = None) -> np.ndarray:
    """Sabit kameralı videoda arka plani karelerin medyani olarak tahmin eder.

    Medyan kullaniyoruz cunku ortalama, oznenin gectigi yerlerde hayalet birakir.
    """
    info = probe(path)
    stride = max(1, info.frame_count // samples)
    expected = max(1, info.frame_count // stride)
    frames = []
    for f in read_frames(path, stride=stride):
        frames.append(f)
        if tick:
            tick(len(frames), expected)
    if not frames:
        raise ValueError("Could not read any frames from the video")
    return np.median(np.stack(frames), axis=0).astype(np.uint8)


def subject_bbox(
    path: str | Path,
    background: np.ndarray,
    threshold: int = 18,
    min_area_ratio: float = 0.0002,
    pad_ratio: float = 0.05,
    tick: Tick | None = None,
) -> BBox:
    """Oznenin tum karelerde kapladigi alanin birlesim kutusunu dondurur.

    threshold: arka plandan sapma esigi (0-255).
    min_area_ratio: gurultuyu elemek icin, satir/sutun basina minimum dolu oran.
    pad_ratio: kutunun etrafina birakilan bosluk (kutu kenarina gore).
    """
    h, w = background.shape[:2]
    bg = background.astype(np.int16)
    acc = np.zeros((h, w), dtype=bool)

    total = max(1, probe(path).frame_count)
    seen = 0
    for frame in read_frames(path):
        diff = np.abs(frame.astype(np.int16) - bg).max(axis=2)
        acc |= diff > threshold
        seen += 1
        if tick:
            tick(seen, total)

    # Tek piksellik gurultuyu at
    acc_u8 = (acc.astype(np.uint8)) * 255
    acc_u8 = cv2.morphologyEx(acc_u8, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = acc_u8 > 0

    if not mask.any():
        return BBox(0, 0, w, h)

    min_cells = max(1, int(min_area_ratio * h * w))
    rows = np.where(mask.sum(axis=1) >= min_cells)[0]
    cols = np.where(mask.sum(axis=0) >= min_cells)[0]
    if len(rows) == 0 or len(cols) == 0:
        rows = np.where(mask.any(axis=1))[0]
        cols = np.where(mask.any(axis=0))[0]

    y0, y1 = int(rows[0]), int(rows[-1]) + 1
    x0, x1 = int(cols[0]), int(cols[-1]) + 1

    pad_x = int((x1 - x0) * pad_ratio)
    pad_y = int((y1 - y0) * pad_ratio)
    return BBox(
        x0=max(0, x0 - pad_x),
        y0=max(0, y0 - pad_y),
        x1=min(w, x1 + pad_x),
        y1=min(h, y1 + pad_y),
    )
