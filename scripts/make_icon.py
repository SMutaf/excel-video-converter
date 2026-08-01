"""app.jpg'den uygulama simgesi uretir.

Kaynak, beyaz zemin uzerinde yuvarlatilmis kose kareden olusan bir tile.
Yapilanlar:

1. Tile disindaki beyaz, kenarlardan tasma doldurma ile bulunur. Duz "beyaz
   olani sil" yaklasimi ortadaki beyaz kalbi de delerdi; tasma doldurma
   yalnizca disariya bagli beyazi secer.
2. Sag alt kosedeki Gemini filigrani bulunup cevresindeki duz bant rengiyle
   kapatilir.
3. JPEG halkalanmasi kenarlari bozmadan yumusatilir.
4. Tile renkleri disariya sizdirilir; yoksa kucultme sirasinda LANCZOS
   saydam bolgedeki beyazi kenara ceker ve simgenin cevresinde beyaz hale
   olusur.
5. Saydam arka planli PNG ve cok boyutlu ICO yazilir.

    python scripts/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "assets"
SRC = OUT_DIR / "icon-source.jpg"

WHITE_MIN = 226  # bunun ustundeki tum kanallar "beyaz" sayilir
# Filigran her zaman sag alt kosede duruyor ve orasi tek parca duz bir bant.
# Aramayi bu bolgeyle sinirlamak sart: tum goruntuye bakan genel bir "zeminden
# sapan lekeleri bul" yaklasimi yuvarlak koseleri ve kalbin konturunu da leke
# sayip tasarimi bozuyordu.
WM_ROI = 0.76  # bolgenin sag/alt kenardan orani
WM_DEV_THR = 20  # bant renginden sapma esigi
WM_MIN_AREA = 80  # bunun altindaki sapmalar JPEG gurultusu
EDGE_ERODE = 2  # kenardaki beyaz karisimi piksellerini disla
BLEED = 10  # tile renginin disariya sizdirilma mesafesi
PNG_SIZE = 512
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def tile_mask(rgb: np.ndarray) -> np.ndarray:
    """Disariya bagli beyazi eleyerek tile maskesini dondurur."""
    h, w = rgb.shape[:2]
    white = (rgb.min(axis=2) > WHITE_MIN).astype(np.uint8)
    flood = white.copy()
    helper = np.zeros((h + 2, w + 2), np.uint8)
    for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if flood[y, x]:
            cv2.floodFill(flood, helper, (x, y), 2)
    return flood != 2


def bleed_outward(rgb: np.ndarray, mask: np.ndarray, steps: int) -> np.ndarray:
    """Tile renklerini maske disina dogru genisletir."""
    out = rgb.copy()
    cur = mask.astype(np.uint8)
    k = np.ones((3, 3), np.uint8)
    for _ in range(steps):
        grown = cv2.dilate(cur, k)
        ring = (grown > 0) & (cur == 0)
        if not ring.any():
            break
        out[ring] = cv2.dilate(out, k)[ring]
        cur = grown
    return out


def remove_watermark(rgb: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, list]:
    """Sag alt kosedeki filigrani, bulundugu bandin duz rengiyle kapatir."""
    h, w = rgb.shape[:2]
    ry, rx = int(h * WM_ROI), int(w * WM_ROI)
    roi = rgb[ry:, rx:].astype(np.int16)
    roi_tile = mask[ry:, rx:]
    if not roi_tile.any():
        return rgb, []

    band = np.median(roi[roi_tile], axis=0)
    dev = np.abs(roi - band).max(axis=2)
    anomaly = ((dev > WM_DEV_THR) & roi_tile).astype(np.uint8)

    n, labels, stats, _ = cv2.connectedComponentsWithStats(anomaly, 8)
    removed = []
    patch = np.zeros_like(anomaly)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area >= WM_MIN_AREA:
            patch[labels == i] = 1
            removed.append((int(rx + x), int(ry + y), int(bw), int(bh), int(area)))

    # Kenar yumusatmasi da gitsin diye lekeyi biraz buyut
    patch = cv2.dilate(patch, np.ones((9, 9), np.uint8)).astype(bool)
    out = rgb.copy()
    region = out[ry:, rx:]
    region[patch] = band.astype(np.uint8)
    out[ry:, rx:] = region
    print(f"Filigran bolgesi: x>{rx}, y>{ry}  bant rengi {band.astype(int).tolist()}")
    return out, removed


def main() -> None:
    rgb = np.asarray(Image.open(SRC).convert("RGB"))
    print(f"Kaynak: {SRC.name}  {rgb.shape[1]}x{rgb.shape[0]}")

    mask = tile_mask(rgb)
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    print(f"Tile: x {cols[0]}-{cols[-1]}, y {rows[0]}-{rows[-1]} "
          f"({cols[-1] - cols[0] + 1}x{rows[-1] - rows[0] + 1})")

    # Filigran tespitinden once disariyi doldur ki kose civarindaki medyan
    # beyazla kirlenmesin
    filled = bleed_outward(rgb, mask, BLEED)
    cleaned, removed = remove_watermark(filled, mask)
    if removed:
        for x, y, bw, bh, area in removed:
            print(f"Temizlenen leke: ({x},{y}) {bw}x{bh}, {area} px")
    else:
        print("Leke bulunamadi")

    # JPEG halkalanmasini kenarlari koruyarak yumusat
    cleaned = cv2.bilateralFilter(cleaned, 9, 45, 9)

    # Kenardaki beyaz karisimli pikselleri disla, alfayi hafifce yumusat
    core = cv2.erode(mask.astype(np.uint8) * 255, np.ones((EDGE_ERODE * 2 + 1,) * 2, np.uint8))
    alpha = cv2.GaussianBlur(core, (0, 0), 1.2)

    rgba = np.dstack([bleed_outward(cleaned, mask, BLEED), alpha])

    # Kirp ve bozmadan kare tuvale ortala (tile 824x887, yani tam kare degil)
    y0, y1 = rows[0], rows[-1] + 1
    x0, x1 = cols[0], cols[-1] + 1
    crop = rgba[y0:y1, x0:x1]
    ch, cw = crop.shape[:2]
    side = max(ch, cw)
    canvas = np.zeros((side, side, 4), dtype=np.uint8)
    oy, ox = (side - ch) // 2, (side - cw) // 2
    canvas[oy : oy + ch, ox : ox + cw] = crop
    # Saydam kenarlarda beyaz hale olusmasin diye RGB'yi disariya sizdir
    canvas[..., :3] = bleed_outward(canvas[..., :3], canvas[..., 3] > 0, BLEED)
    print(f"Kirpma: {cw}x{ch} -> {side}x{side} kare tuval")

    master = Image.fromarray(canvas, "RGBA")
    OUT_DIR.mkdir(exist_ok=True)

    png_path = OUT_DIR / "icon.png"
    master.resize((PNG_SIZE, PNG_SIZE), Image.LANCZOS).save(png_path)
    print(f"Yazildi: {png_path}")

    ico_path = OUT_DIR / "icon.ico"
    master.resize((256, 256), Image.LANCZOS).save(
        ico_path, format="ICO", sizes=[(s, s) for s in ICO_SIZES]
    )
    print(f"Yazildi: {ico_path}")

    with Image.open(ico_path) as check:
        print("ICO boyutlari:", sorted(check.ico.sizes()))
    with Image.open(png_path) as check:
        a = np.asarray(check)[..., 3]
        print(f"PNG alfa: saydam {int((a == 0).sum())} px, opak {int((a == 255).sum())} px")


if __name__ == "__main__":
    main()
