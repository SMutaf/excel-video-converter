"""Goruntuyu hucre izgarasina cevirir.

Her hucre iki renk tasir: dolgu (arka plan) ve yazi rengi (on plan). Hucreye
dusen pikselleri parlakliga gore ikiye ayirip her gruba bir renk veriyoruz;
karakter de koyu grubun kapladigi orani temsil ediyor. Boylece tek hucre
icinde alt-detay (kenar, kontur) korunuyor - duz ortalama alsaydik goruntu
bulaniklasirdi.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Rec. 709 luma katsayilari
_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


@dataclass
class CellGrid:
    """Bir karenin hucre gosterimi."""

    fill_rgb: np.ndarray  # (rows, cols, 3) uint8 - arka plan rengi
    font_rgb: np.ndarray  # (rows, cols, 3) uint8 - yazi rengi
    coverage: np.ndarray  # (rows, cols) float32 - koyu piksel orani (0..1)

    @property
    def shape(self) -> tuple[int, int]:
        return self.fill_rgb.shape[:2]


def grid_size(src_w: int, src_h: int, cols: int, cell_aspect: float = 1.0) -> tuple[int, int]:
    """Kaynak en-boy oranini koruyacak (cols, rows) hesaplar.

    cell_aspect: hucre genisligi / yuksekligi. Hucreleri kare tuttugumuz icin
    varsayilan 1.0, ama Excel'de dar sutun kullanilirsa buradan telafi edilir.
    """
    rows = max(1, round(cols * (src_h / src_w) * cell_aspect))
    return cols, rows


def image_to_cells(
    img_rgb: np.ndarray, cols: int, rows: int, sub: int = 4, flat_threshold: float = 6.0
) -> CellGrid:
    """Goruntuyu (rows, cols) izgaraya boler.

    sub: hucre basina orneklenen alt-piksel kenar uzunlugu (sub x sub).
    flat_threshold: hucre ici parlaklik standart sapmasi bunun altindaysa hucre
        "duz" sayilir; karakter yazilmaz. Esik olmadan duz zeminde JPEG
        gurultusu rastgele karakter uretir - hem cirkin gorunur hem de Excel'in
        en pahali isi metin cizmek oldugu icin oynatmayi yavaslatir.
    """
    small = cv2.resize(img_rgb, (cols * sub, rows * sub), interpolation=cv2.INTER_AREA)
    # (rows, sub, cols, sub, 3) -> (rows, cols, sub*sub, 3)
    blocks = (
        small.reshape(rows, sub, cols, sub, 3)
        .transpose(0, 2, 1, 3, 4)
        .reshape(rows, cols, sub * sub, 3)
        .astype(np.float32)
    )

    luma = blocks @ _LUMA  # (rows, cols, n)
    threshold = luma.mean(axis=2, keepdims=True)
    dark = luma < threshold  # (rows, cols, n) bool

    n_dark = dark.sum(axis=2)
    n_total = blocks.shape[2]
    coverage = (n_dark / n_total).astype(np.float32)

    dark_f = dark[..., None].astype(np.float32)
    sum_dark = (blocks * dark_f).sum(axis=2)
    sum_light = (blocks * (1.0 - dark_f)).sum(axis=2)

    n_light = n_total - n_dark
    mean_all = blocks.mean(axis=2)

    # Tek renkli hucrelerde gruplardan biri bos kalir; o durumda iki rengi de
    # ortalamaya esitleyip karakteri bosluga birakiyoruz.
    with np.errstate(invalid="ignore", divide="ignore"):
        font_rgb = np.where(n_dark[..., None] > 0, sum_dark / np.maximum(n_dark, 1)[..., None], mean_all)
        fill_rgb = np.where(n_light[..., None] > 0, sum_light / np.maximum(n_light, 1)[..., None], mean_all)

    # Duz hucreleri tek renge indir, karakteri bosluga birak
    flat = luma.std(axis=2) < flat_threshold
    coverage = np.where(flat, 0.0, coverage).astype(np.float32)
    flat3 = flat[..., None]
    fill_rgb = np.where(flat3, mean_all, fill_rgb)
    font_rgb = np.where(flat3, mean_all, font_rgb)

    return CellGrid(
        fill_rgb=np.clip(fill_rgb, 0, 255).astype(np.uint8),
        font_rgb=np.clip(font_rgb, 0, 255).astype(np.uint8),
        coverage=coverage,
    )


def preview(grid: CellGrid, chars: np.ndarray, glyph_chars: str, cell_px: int = 12) -> np.ndarray:
    """Excel'i acmadan sonucu gormek icin izgarayi bir goruntuye render eder."""
    from PIL import Image, ImageDraw, ImageFont

    from .glyphs import DEFAULT_FONT, _font_path

    rows, cols = grid.shape
    img = Image.new("RGB", (cols * cell_px, rows * cell_px))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(_font_path(DEFAULT_FONT)), int(cell_px * 0.85))

    for r in range(rows):
        for c in range(cols):
            x0, y0 = c * cell_px, r * cell_px
            draw.rectangle([x0, y0, x0 + cell_px, y0 + cell_px], fill=tuple(int(v) for v in grid.fill_rgb[r, c]))
            ch = glyph_chars[chars[r, c]]
            if ch != " ":
                draw.text(
                    (x0 + cell_px / 2, y0 + cell_px / 2),
                    ch,
                    font=font,
                    fill=tuple(int(v) for v in grid.font_rgb[r, c]),
                    anchor="mm",
                )
    return np.asarray(img)
