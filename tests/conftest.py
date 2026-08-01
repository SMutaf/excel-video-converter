"""Test verisi.

Depoya ikili dosya koymuyoruz; test videosu ve goruntusu her calistirmada
sentetik olarak uretiliyor. Boylece veri deterministik oluyor, codec/kaynak
lisansi derdi olmuyor ve testler her makinede ayni sonucu veriyor.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

FRAMES = 12
W, H = 96, 72
FPS = 12.0

# Ozne: beyaz zeminde saga dogru ilerleyen koyu bir kare
SUBJECT = (40, 60, 180)  # BGR
SUBJECT_SIZE = 20


def _frame(i: int) -> np.ndarray:
    """i. karenin BGR goruntusu. Ozne yatayda kayar, zemin sabit beyaz."""
    img = np.full((H, W, 3), 255, dtype=np.uint8)
    x = 8 + i * 4
    y = H // 2 - SUBJECT_SIZE // 2
    img[y : y + SUBJECT_SIZE, x : x + SUBJECT_SIZE] = SUBJECT
    # Ic detay: karakter secimi test edilebilsin diye yariya kadar aciklastir
    img[y : y + SUBJECT_SIZE // 2, x : x + SUBJECT_SIZE] = (200, 210, 230)
    return img


@pytest.fixture(scope="session")
def frames_bgr() -> list[np.ndarray]:
    return [_frame(i) for i in range(FRAMES)]


@pytest.fixture(scope="session")
def frames_rgb(frames_bgr) -> list[np.ndarray]:
    return [cv2.cvtColor(f, cv2.COLOR_BGR2RGB) for f in frames_bgr]


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory, frames_bgr) -> Path:
    """Sentetik test klibi (mp4v). Sabit kamera, tek hareketli ozne."""
    path = tmp_path_factory.mktemp("data") / "sample.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    if not writer.isOpened():
        pytest.skip("mp4v kodlayici yok")
    for f in frames_bgr:
        writer.write(f)
    writer.release()
    if not path.exists() or path.stat().st_size == 0:
        pytest.skip("test videosu yazilamadi")
    return path


@pytest.fixture(scope="session")
def sample_image(tmp_path_factory, frames_bgr) -> Path:
    path = tmp_path_factory.mktemp("data") / "sample.png"
    cv2.imwrite(str(path), frames_bgr[FRAMES // 2])
    return path


@pytest.fixture(scope="session")
def flat_image() -> np.ndarray:
    """Tek renk RGB goruntu - duz hucre bastirmasini test etmek icin."""
    return np.full((64, 64, 3), (30, 120, 70), dtype=np.uint8)
