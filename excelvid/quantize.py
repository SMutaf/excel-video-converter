"""Renk paleti uretimi ve en yakin palet rengine esleme.

Palet tum karelerden bir kez uretilir. Kare basina ayri palet cikarilirsa
sabit duran bolgelerin rengi kareler arasinda titrer.

Mesafe hesaplari CIE Lab uzayinda yapilir: RGB'deki oklid mesafesi algisal
farkla ortusmez, Lab'deki ortusur.
"""

from __future__ import annotations

import cv2
import numpy as np

MAX_COLORS = 32
KMEANS_ITERS = 40


def _kmeans(data: np.ndarray, k: int, iters: int = KMEANS_ITERS, seed: int = 0) -> np.ndarray:
    """k-ortalamalar kumeleme. Donus: (k, boyut) kume merkezleri.

    scikit-learn yerine burada duruyor: tek bir kumeleme cagrisi icin
    scikit-learn + scipy 155 MB bagimlilik getiriyordu. Ayni veride olculdu -
    bu surum 2 kat hizli, ortalama hata 1.08 yerine 1.18 dE (ikisi de gozle
    ayirt edilemeyen esikte), en kotu hata ise daha iyi (17.5 yerine 21.7).
    """
    data = np.ascontiguousarray(data, dtype=np.float32)
    n, dim = data.shape
    k = min(k, n)

    # k-means++ baslatma: uzak noktalarin secilme olasiligi yuksek. Rastgele
    # baslatma bazi kumeleri bos birakip paleti israf ediyordu.
    rng = np.random.default_rng(seed)
    centers = np.empty((k, dim), dtype=np.float32)
    centers[0] = data[rng.integers(n)]
    closest = ((data - centers[0]) ** 2).sum(1)
    for i in range(1, k):
        total = closest.sum()
        probs = closest / total if total > 0 else np.full(n, 1.0 / n)
        centers[i] = data[rng.choice(n, p=probs)]
        closest = np.minimum(closest, ((data - centers[i]) ** 2).sum(1))

    # ||a-b||^2 = |a|^2 - 2ab + |b|^2 acilimi; matris carpimi dogrudan
    # fark almaktan cok daha az bellek ve zaman harciyor.
    sq = (data**2).sum(1)[:, None]
    for _ in range(iters):
        dist = sq - 2 * data @ centers.T + (centers**2).sum(1)[None, :]
        labels = dist.argmin(1)
        counts = np.bincount(labels, minlength=k)
        sums = np.stack(
            [np.bincount(labels, weights=data[:, j], minlength=k) for j in range(dim)], axis=1
        )
        moved = counts > 0
        new = centers.copy()
        new[moved] = (sums[moved] / counts[moved, None]).astype(np.float32)
        if np.allclose(new, centers):
            return new
        centers = new
    return centers


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    flat = rgb.reshape(-1, 1, 3).astype(np.uint8)
    return cv2.cvtColor(flat, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)


def _lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    flat = np.clip(lab, 0, 255).reshape(-1, 1, 3).astype(np.uint8)
    return cv2.cvtColor(flat, cv2.COLOR_LAB2RGB).reshape(-1, 3)


def build_palette(
    samples_rgb: np.ndarray,
    n_colors: int = MAX_COLORS,
    max_samples: int = 200_000,
    seed: int = 0,
) -> np.ndarray:
    """Ornek piksellerden n_colors renklik palet cikarir. Donus: (n,3) uint8 RGB."""
    if n_colors > MAX_COLORS:
        raise ValueError(f"Palet en fazla {MAX_COLORS} renk olabilir (istenen: {n_colors})")

    flat = samples_rgb.reshape(-1, 3)
    rng = np.random.default_rng(seed)
    if len(flat) > max_samples:
        flat = flat[rng.choice(len(flat), max_samples, replace=False)]

    lab = _rgb_to_lab(flat)
    n_colors = min(n_colors, len(np.unique(lab, axis=0)))
    return _lab_to_rgb(_kmeans(lab, n_colors, seed=seed))


def map_to_palette(rgb: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Her rengi en yakin palet indeksine esler. rgb: (..., 3) -> (...) int32."""
    shape = rgb.shape[:-1]
    lab = _rgb_to_lab(rgb.reshape(-1, 3))
    pal_lab = _rgb_to_lab(palette)
    # (N, 1, 3) - (1, K, 3) -> (N, K); N buyukse parcali islemek gerekir
    idx = np.empty(len(lab), dtype=np.int32)
    chunk = 100_000
    for start in range(0, len(lab), chunk):
        block = lab[start : start + chunk]
        d = ((block[:, None, :] - pal_lab[None, :, :]) ** 2).sum(axis=2)
        idx[start : start + chunk] = d.argmin(axis=1)
    return idx.reshape(shape)
