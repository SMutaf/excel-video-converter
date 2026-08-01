"""Hucre geometrisi ve izgara olculeri.

Bunlar kirilirsa Excel'de goruntu yamulur ya da oynatma kadraji kayar; ikisi de
gozle fark edilmesi zor, sessizce bozulan seyler.
"""

from __future__ import annotations

import pytest

from excelvid import render, writer


def test_cells_are_square():
    """Excel'de sutun genisligi karakter, satir yuksekligi punto biriminde.

    Normal stil icin genislik_px = 7*w + 5 ve yukseklik_px = pt * 96/72.
    Ikisi esit olmazsa goruntu yatay/dikey gerilir.
    """
    width_px = 7 * writer.COL_WIDTH_CHARS + 5
    height_px = writer.ROW_HEIGHT_PT * 96 / 72
    assert width_px == pytest.approx(height_px)
    assert height_px == pytest.approx(20.0)


@pytest.mark.parametrize(
    "src_w,src_h,cols,expected_rows",
    [
        (100, 100, 64, 64),  # kare
        (854, 480, 64, 36),  # yatay 16:9
        (311, 454, 64, 93),  # dansci videosunun kirpilmis olcusu
        (480, 854, 48, 85),  # dikey
    ],
)
def test_grid_size_preserves_aspect(src_w, src_h, cols, expected_rows):
    n_cols, n_rows = render.grid_size(src_w, src_h, cols)
    assert n_cols == cols
    assert n_rows == expected_rows


def test_grid_size_never_zero_rows():
    """Cok genis kaynaklarda satir sayisi sifira dusmemeli."""
    _, rows = render.grid_size(4000, 10, 16)
    assert rows >= 1
