"""Karakter glif'lerinin kapladigi murekkep oranini olcer.

Bir hucreye hangi karakteri koyacagimiza karar verirken, karakterin gercekten
ne kadar koyu gorundugunu bilmemiz gerekir. Bunu tahmin etmek yerine karakteri
Pillow ile render edip piksel sayiyoruz.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Excel'de sorun cikarmayan, gorsel olarak ayirt edilebilir ASCII kumesi.
# '=' '+' '-' '@' formul olarak yorumlanabildigi icin disarida biraktik
# (write_string ile yazsak da kullanici hucreyi elle duzenlerse sorun olur).
DEFAULT_CHARSET = " .'`,:;_!i1lIrxvcnuoazjftJYUCLQ0OZSGmwqpdbkhVXAKE*ND#RPHM&W8%B$"

WINDOWS_FONT_DIR = Path(r"C:\Windows\Fonts")
DEFAULT_FONT = "consola.ttf"  # Consolas: monospace, her Windows'ta var


@dataclass(frozen=True)
class GlyphTable:
    """Karakterler ve normalize edilmis kapsama oranlari (0..1, artan sirada)."""

    chars: str
    coverage: np.ndarray  # (n,) float32, artan sirali

    def nearest(self, target: np.ndarray) -> np.ndarray:
        """Hedef kapsama oranlarina en yakin karakterlerin indekslerini dondurur.

        target: herhangi bir sekilde (0..1) float dizi.
        """
        flat = np.clip(target.ravel(), 0.0, 1.0)
        # coverage artan sirali oldugu icin ikili arama yeterli
        pos = np.searchsorted(self.coverage, flat)
        pos = np.clip(pos, 1, len(self.coverage) - 1)
        left = self.coverage[pos - 1]
        right = self.coverage[pos]
        idx = np.where(flat - left <= right - flat, pos - 1, pos)
        return idx.reshape(target.shape).astype(np.int32)


def _font_path(font: str) -> Path:
    p = Path(font)
    if p.exists():
        return p
    candidate = WINDOWS_FONT_DIR / font
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Yazi tipi bulunamadi: {font}")


def measure(
    charset: str = DEFAULT_CHARSET,
    font: str = DEFAULT_FONT,
    font_size: int = 11,
    cell_px: tuple[int, int] = (20, 20),
    supersample: int = 6,
) -> GlyphTable:
    """Her karakteri hucre boyutunda render edip murekkep oranini olcer.

    Ayni kapsamaya sahip karakterlerden yalnizca biri tutulur; boylece
    en-yakin aramasi gereksiz adaylarla sismez.
    """
    fpath = _font_path(font)
    pil_font = ImageFont.truetype(str(fpath), font_size * supersample)
    w = cell_px[0] * supersample
    h = cell_px[1] * supersample

    raw: dict[str, float] = {}
    for ch in charset:
        img = Image.new("L", (w, h), 255)
        draw = ImageDraw.Draw(img)
        # Hucrede ortalanmis sekilde ciz (Excel'de de ortali hizalayacagiz)
        draw.text((w / 2, h / 2), ch, font=pil_font, fill=0, anchor="mm")
        ink = 1.0 - (np.asarray(img, dtype=np.float32) / 255.0).mean()
        raw[ch] = ink

    max_ink = max(raw.values())
    if max_ink <= 0:
        raise ValueError("Hicbir karakter murekkep birakmadi; yazi tipini kontrol et.")

    # Normalize et ve kapsamaya gore benzersizlestir
    seen: dict[float, str] = {}
    for ch, ink in sorted(raw.items(), key=lambda kv: kv[1]):
        key = round(ink / max_ink, 3)
        seen.setdefault(key, ch)

    ordered = sorted(seen.items())
    covs = np.array([k for k, _ in ordered], dtype=np.float32)
    chars = "".join(v for _, v in ordered)
    return GlyphTable(chars=chars, coverage=covs)
