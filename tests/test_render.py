"""Goruntu -> hucre donusumu ve karakter secimi."""

from __future__ import annotations

import numpy as np
import pytest

from excelvid import glyphs, quantize, render


def test_glyph_table_is_sorted_and_starts_with_space():
    table = glyphs.measure()
    assert table.chars[0] == " "
    assert table.coverage[0] == pytest.approx(0.0, abs=1e-6)
    assert np.all(np.diff(table.coverage) > 0), "kapsama artan sirali olmali"
    assert len(table.chars) == len(table.coverage)


def test_glyph_nearest_maps_extremes():
    table = glyphs.measure()
    idx = table.nearest(np.array([0.0, 1.0]))
    assert idx[0] == 0
    assert idx[1] == len(table.chars) - 1


def test_glyph_nearest_keeps_shape():
    table = glyphs.measure()
    target = np.zeros((5, 7), dtype=np.float32)
    assert table.nearest(target).shape == (5, 7)


def test_flat_cells_get_no_character(flat_image):
    """Duz renkli alanda karakter yazilmamali.

    Esik olmasa JPEG/kodlayici gurultusu koyu/acik ayrimini rastgele bolup
    bos zemine karakter basardi.
    """
    grid = render.image_to_cells(flat_image, 8, 8)
    assert np.all(grid.coverage == 0.0)
    assert np.array_equal(grid.fill_rgb, grid.font_rgb)


def test_split_cell_reports_half_coverage():
    """Ust yarisi koyu, alt yarisi acik tek hucre -> kapsama ~0.5."""
    img = np.zeros((8, 8, 3), dtype=np.uint8)
    img[:4] = (10, 10, 10)
    img[4:] = (240, 240, 240)
    grid = render.image_to_cells(img, 1, 1, sub=4, flat_threshold=1.0)
    assert grid.coverage[0, 0] == pytest.approx(0.5)
    assert grid.font_rgb[0, 0].max() < 50, "koyu grup yazi rengi olmali"
    assert grid.fill_rgb[0, 0].min() > 200, "acik grup dolgu rengi olmali"


def test_coverage_resolution_is_bounded_by_sub():
    """sub x sub ornekleme, kapsamanin alabilecegi deger sayisini sinirlar."""
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
    for sub in (2, 4):
        grid = render.image_to_cells(img, 8, 8, sub=sub, flat_threshold=0.0)
        assert len(np.unique(grid.coverage)) <= sub * sub + 1


def test_palette_size_and_exact_mapping():
    rng = np.random.default_rng(1)
    samples = rng.integers(0, 255, (5000, 3), dtype=np.uint8)
    palette = quantize.build_palette(samples, n_colors=8)
    assert len(palette) <= 8
    # Palet renkleri kendilerine eslenmeli
    idx = quantize.map_to_palette(palette, palette)
    assert np.array_equal(idx, np.arange(len(palette)))


def test_palette_rejects_oversized_request():
    with pytest.raises(ValueError):
        quantize.build_palette(np.zeros((10, 3), dtype=np.uint8), n_colors=64)
