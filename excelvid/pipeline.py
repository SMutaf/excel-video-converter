"""Kare dizisini paylasilan palet + karakter tablosuna cevirir.

Palet ve karakter tablosu tum kareler icin **ortak** uretilir. Kare basina
palet cikarsaydik sabit duran bolgelerin rengi kareler arasinda titrerdi.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import glyphs, quantize, render


@dataclass
class Mosaic:
    palette: np.ndarray  # (k, 3) uint8
    chars: str  # glif tablosu
    fill_idx: np.ndarray  # (F, rows, cols) int32 - palet indeksi
    font_idx: np.ndarray  # (F, rows, cols) int32
    char_idx: np.ndarray  # (F, rows, cols) int32 - chars icindeki indeks

    @property
    def n_frames(self) -> int:
        return self.fill_idx.shape[0]

    @property
    def rows(self) -> int:
        return self.fill_idx.shape[1]

    @property
    def cols(self) -> int:
        return self.fill_idx.shape[2]

    def static_chars(self) -> np.ndarray:
        """Tum kareler icin tek bir karakter izgarasi (kapsamalarin ortalamasi).

        Karakterleri sabit tutan oynatma stratejisi bunu kullanir: her karede
        yalnizca renk degisir, metin katmani ayni kalir.
        """
        table = glyphs.GlyphTable(self.chars, _coverage_of(self.chars))
        # char_idx zaten kapsamaya gore sirali oldugundan indeks ortalamasi
        # kapsama ortalamasina yakin; yine de kapsama uzerinden gidiyoruz.
        cov = table.coverage[self.char_idx].mean(axis=0)
        return table.nearest(cov)


_COVERAGE_CACHE: dict[str, np.ndarray] = {}


def _coverage_of(chars: str) -> np.ndarray:
    cov = _COVERAGE_CACHE.get(chars)
    if cov is None:
        table = glyphs.measure()
        if table.chars != chars:
            raise ValueError("Glyph table mismatch")
        cov = table.coverage
        _COVERAGE_CACHE[chars] = cov
    return cov


def build(
    frames_rgb: list[np.ndarray],
    cols: int,
    colors: int = 32,
    sub: int = 4,
    palette_sample_frames: int = 24,
    tick=None,
) -> Mosaic:
    """Kare listesini Mosaic'e cevirir. Tum kareler ayni boyutta olmali."""
    if not frames_rgb:
        raise ValueError("Frame list is empty")

    h, w = frames_rgb[0].shape[:2]
    n_cols, n_rows = render.grid_size(w, h, cols)

    # Toplam is: her kare icin izgara + iki renk eslemesi + karakter secimi
    total = len(frames_rgb) * 2
    done = 0

    grids = []
    for f in frames_rgb:
        grids.append(render.image_to_cells(f, n_cols, n_rows, sub=sub))
        done += 1
        if tick:
            tick(done, total)

    # Paleti karelerin bir alt kumesinden cikar; hepsini kullanmak KMeans'i
    # yavaslatir, kazanc ise ihmal edilebilir.
    step = max(1, len(grids) // palette_sample_frames)
    sample = np.concatenate(
        [g.fill_rgb.reshape(-1, 3) for g in grids[::step]]
        + [g.font_rgb.reshape(-1, 3) for g in grids[::step]]
    )
    palette = quantize.build_palette(sample, n_colors=colors)

    table = glyphs.measure()
    _COVERAGE_CACHE[table.chars] = table.coverage

    fill_list, font_list, char_list = [], [], []
    for g in grids:
        fill_list.append(quantize.map_to_palette(g.fill_rgb, palette))
        font_list.append(quantize.map_to_palette(g.font_rgb, palette))
        char_list.append(table.nearest(g.coverage))
        done += 1
        if tick:
            tick(done, total)

    fill = np.stack(fill_list)
    font = np.stack(font_list)
    char = np.stack(char_list)

    return Mosaic(
        palette=palette,
        chars=table.chars,
        fill_idx=fill.astype(np.int32),
        font_idx=font.astype(np.int32),
        char_idx=char.astype(np.int32),
    )

