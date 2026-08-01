"""XLSX cikti yazimi.

Hucre geometrisi notu: Excel'de sutun genisligi "karakter" biriminde, satir
yuksekligi punto cinsindendir. Normal stil (Calibri 11) icin
    genislik_px = 7 * w + 5
    yukseklik_px = pt * 96 / 72
Kare hucre icin 15pt (=20px) satira karsilik w = 15/7 = 2.142857 gerekir.
Hucre yazi tipini Consolas yapmak bu birimi degistirmez, cunku birim
calisma kitabinin Normal stiline baglidir.
"""

from __future__ import annotations

import numpy as np
import xlsxwriter

from .player_vba import CFG_CELLS, CFG_SHEET

ROW_HEIGHT_PT = 15.0
COL_WIDTH_CHARS = 15.0 / 7.0  # kare hucre
XLSX_FORMAT_LIMIT = 64_000


def _hex(rgb: np.ndarray) -> str:
    return "#{:02X}{:02X}{:02X}".format(int(rgb[0]), int(rgb[1]), int(rgb[2]))


def write_strip(
    path: str,
    fill_idx: np.ndarray,
    font_idx: np.ndarray,
    char_idx: np.ndarray,
    palette: np.ndarray,
    glyph_chars: str,
    sheet_name: str = "film",
    font_name: str = "Consolas",
    font_size: int = 11,
    fps: float = 25.0,
    vba_project: str | None = None,
    tick=None,
) -> dict:
    """Tum kareleri tek sayfaya alt alta yazar (oynatma = pencere kaydirma).

    fill_idx/font_idx/char_idx: (F, rows, cols)

    vba_project verilirse oynatici makrosu dosyaya gomulur ve cikti .xlsm olur;
    bu yol Excel'e hic ihtiyac duymaz.
    """
    n_frames, rows, cols = fill_idx.shape
    wb = xlsxwriter.Workbook(path, {"constant_memory": False})
    ws = wb.add_worksheet(sheet_name)
    ws.hide_gridlines(2)
    ws.set_column(0, cols - 1, COL_WIDTH_CHARS)
    ws.set_default_row(ROW_HEIGHT_PT)

    # Oynatici olculeri kaynak koduna degil bu sayfaya yazilir; boylece VBA
    # sabit kalir ve onceden derlenmis haliyle gomulebilir.
    cfg = wb.add_worksheet(CFG_SHEET)
    values = {
        "rows": rows,
        "cols": cols,
        "frames": n_frames,
        "fps": float(fps),
        "sheet": sheet_name,
    }
    for key, cell in CFG_CELLS.items():
        row_idx = int(cell[1:]) - 1
        cfg.write_string(row_idx, 0, key)
        cfg.write(row_idx, 1, values[key])
    cfg.hide()

    if vba_project:
        # Gomulu projenin belge modulleriyle ayni kod adlari; eslesmezse Excel
        # her iki takimi da tasir ve hayalet moduller kalir.
        wb.set_vba_name("ThisWorkbook")
        ws.set_vba_name("Sheet1")
        cfg.set_vba_name("Sheet2")

    cache: dict[tuple[int, int], object] = {}

    def fmt_for(fi: int, fo: int):
        key = (fi, fo)
        f = cache.get(key)
        if f is None:
            if len(cache) >= XLSX_FORMAT_LIMIT:
                raise RuntimeError("XLSX unique-format limit exceeded; reduce the palette size.")
            f = wb.add_format(
                {
                    "bg_color": _hex(palette[fi]),
                    "font_color": _hex(palette[fo]),
                    "font_name": font_name,
                    "font_size": font_size,
                    "align": "center",
                    "valign": "vcenter",
                }
            )
            cache[key] = f
        return f

    for i in range(n_frames):
        base = i * rows
        for r in range(rows):
            fi_row = fill_idx[i, r]
            fo_row = font_idx[i, r]
            ch_row = char_idx[i, r]
            for c in range(cols):
                f = fmt_for(int(fi_row[c]), int(fo_row[c]))
                ch = glyph_chars[int(ch_row[c])]
                if ch == " ":
                    ws.write_blank(base + r, c, None, f)
                else:
                    ws.write_string(base + r, c, ch, f)
        if tick:
            tick(i + 1, n_frames)

    if vba_project:
        wb.add_vba_project(vba_project)

    wb.close()
    return {"frames": n_frames, "rows": rows, "cols": cols, "formats": len(cache)}


def write_still(
    path: str,
    fill_idx: np.ndarray,
    font_idx: np.ndarray,
    char_idx: np.ndarray,
    palette: np.ndarray,
    glyph_chars: str,
    zoom: int = 40,
    font_name: str = "Consolas",
    font_size: int = 11,
) -> dict:
    """Tek kareyi .xlsx olarak yazar. Donus: olcum bilgileri."""
    rows, cols = fill_idx.shape
    wb = xlsxwriter.Workbook(path, {"constant_memory": False})
    ws = wb.add_worksheet("frame")
    ws.hide_gridlines(2)
    ws.set_zoom(zoom)
    ws.set_column(0, cols - 1, COL_WIDTH_CHARS)
    for r in range(rows):
        ws.set_row(r, ROW_HEIGHT_PT)

    cache: dict[tuple[int, int], object] = {}

    def fmt_for(fi: int, fo: int):
        key = (fi, fo)
        f = cache.get(key)
        if f is None:
            if len(cache) >= XLSX_FORMAT_LIMIT:
                raise RuntimeError("XLSX unique-format limit exceeded; reduce the palette size.")
            f = wb.add_format(
                {
                    "bg_color": _hex(palette[fi]),
                    "font_color": _hex(palette[fo]),
                    "font_name": font_name,
                    "font_size": font_size,
                    "align": "center",
                    "valign": "vcenter",
                }
            )
            cache[key] = f
        return f

    for r in range(rows):
        for c in range(cols):
            f = fmt_for(int(fill_idx[r, c]), int(font_idx[r, c]))
            ch = glyph_chars[int(char_idx[r, c])]
            if ch == " ":
                ws.write_blank(r, c, None, f)
            else:
                ws.write_string(r, c, ch, f)

    wb.close()
    return {"rows": rows, "cols": cols, "formats": len(cache)}

