"""Uretilen calisma kitabinin yapisi.

Excel gerektirmez: .xlsm bir zip oldugu icin icerigi dogrudan okunuyor.
"""

from __future__ import annotations

import zipfile

import numpy as np
import pytest

from excelvid import pipeline, player, player_vba, writer


@pytest.fixture(scope="module")
def mosaic(frames_rgb):
    return pipeline.build(frames_rgb, cols=16, colors=8)


def test_vba_source_has_no_unresolved_placeholders():
    """VBA artik sablon degil, sabit kaynak.

    Eskiden sabitler str.format ile gomuluyordu ve VBA'daki "{ESC}" ifadesi
    yer tutucu sanilip hataya yol aciyordu. Kaynakta yer tutucu kalmamali.
    """
    src = player_vba.PLAYER_SOURCE
    assert "%" not in src.split("Option Explicit")[0]
    for name in ("%N_ROWS%", "%N_COLS%", "%N_FRAMES%", "%FPS%", "%SHEET%"):
        assert name not in src
    assert '"{ESC}"' in src, "ESC kisayolu kaydi kaybolmus"


def test_vba_reads_config_from_sheet():
    src = player_vba.PLAYER_SOURCE
    assert 'CFG_SHEET As String = "cfg"' in src
    for cell in player_vba.CFG_CELLS.values():
        assert f'Range("{cell}")' in src


def test_strip_writes_frames_and_config(tmp_path, mosaic):
    out = tmp_path / "film.xlsx"
    info = writer.write_strip(
        str(out),
        mosaic.fill_idx,
        mosaic.font_idx,
        mosaic.char_idx,
        mosaic.palette,
        mosaic.chars,
        fps=12.0,
    )
    assert out.exists()
    assert info["frames"] == mosaic.n_frames
    assert info["rows"] == mosaic.rows and info["cols"] == mosaic.cols
    assert info["formats"] <= len(mosaic.palette) ** 2

    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert any("worksheets/sheet1.xml" in n for n in names)
        workbook = z.read("xl/workbook.xml").decode("utf-8")
    assert 'name="film"' in workbook
    assert f'name="{player_vba.CFG_SHEET}"' in workbook
    assert 'state="hidden"' in workbook, "cfg sayfasi gizli olmali"


def test_strip_row_layout_is_contiguous(tmp_path, mosaic):
    """Kare i, i*rows satirindan baslamali - oynatici bu varsayima dayaniyor."""
    out = tmp_path / "rows.xlsx"
    writer.write_strip(
        str(out),
        mosaic.fill_idx,
        mosaic.font_idx,
        mosaic.char_idx,
        mosaic.palette,
        mosaic.chars,
        fps=12.0,
    )
    with zipfile.ZipFile(out) as z:
        sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    # Son satirin numarasi kare sayisi * satir sayisi olmali
    last_row = max(
        int(part.split('"')[0])
        for part in sheet.split('<row r="')[1:]
    )
    assert last_row == mosaic.n_frames * mosaic.rows


def test_embedding_vba_produces_xlsm(tmp_path, mosaic):
    if not player.VBA_PROJECT.exists():
        pytest.skip("vbaProject.bin uretilmemis")
    out = tmp_path / "film.xlsm"
    writer.write_strip(
        str(out),
        mosaic.fill_idx,
        mosaic.font_idx,
        mosaic.char_idx,
        mosaic.palette,
        mosaic.chars,
        fps=12.0,
        vba_project=str(player.VBA_PROJECT),
    )
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    assert any(n.endswith("vbaProject.bin") for n in names)


def test_player_requires_xlsm_extension(tmp_path, mosaic):
    with pytest.raises(ValueError):
        player.build(mosaic, tmp_path / "wrong.xlsx", fps=12.0)


def test_format_cache_stays_under_limit(mosaic):
    """Benzersiz bicim sayisi palet x palet ile sinirli kalmali.

    XLSX'in 64.000 bicim limitine yaklasmamamizin sebebi bu; palet 32 renkle
    sinirli oldugu icin en fazla 1024 kombinasyon olusabilir.
    """
    combos = {
        (int(f), int(o))
        for f, o in zip(mosaic.fill_idx.ravel(), mosaic.font_idx.ravel())
    }
    assert len(combos) <= len(mosaic.palette) ** 2
    assert len(combos) < writer.XLSX_FORMAT_LIMIT


def test_palette_hex_format():
    assert writer._hex(np.array([0, 128, 255])) == "#0080FF"
