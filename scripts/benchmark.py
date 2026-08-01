"""Oynatma stratejilerini gercek Excel'de olcer.

Projenin asil riski oynatma hizi. Uc strateji karsilastiriliyor:

  cf     : gizli izgaraya tek seferde dizi yazimi + kosullu bicimlendirme
  sheets : onceden boyanmis sayfalar arasinda gecis
  cells  : hucre hucre Interior.Color (referans, naif)

Excel *gorunur* olarak acilir; gizli calistirilirsa ekran cizimi olmadigi
icin olcum gercekci olmaz.

Kullanim:
    python scripts/benchmark.py samples/dancer.mp4 --cols 96 --frames 25
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import typer
import xlsxwriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from excelvid import excel_com, glyphs, pipeline, vba_src, video, writer  # noqa: E402

app = typer.Typer(add_completion=False)

OUT = Path("out/bench")


def _bgr_long(rgb: np.ndarray) -> int:
    """Excel Interior.Color BGR sirasinda long bekler."""
    return int(rgb[0]) + int(rgb[1]) * 256 + int(rgb[2]) * 65536


def _geometry(ws, rows: int, cols: int, zoom: int) -> None:
    ws.hide_gridlines(2)
    ws.set_zoom(zoom)
    ws.set_column(0, cols - 1, writer.COL_WIDTH_CHARS)
    for r in range(rows):
        ws.set_row(r, writer.ROW_HEIGHT_PT)


def build_cf_workbook(m: pipeline.Mosaic, path: Path, zoom: int, cf_font: bool) -> None:
    """CF stratejisi: metin sabit, renk her karede dizi yazimiyla degisiyor."""
    wb = xlsxwriter.Workbook(str(path))
    view = wb.add_worksheet("view")
    _geometry(view, m.rows, m.cols, zoom)

    base = wb.add_format(
        {"font_name": "Consolas", "font_size": 11, "align": "center", "valign": "vcenter"}
    )
    static = m.static_chars()
    for r in range(m.rows):
        for c in range(m.cols):
            ch = m.chars[int(static[r, c])]
            if ch == " ":
                view.write_blank(r, c, None, base)
            else:
                view.write_string(r, c, ch, base)

    # Dolgu kurallari: px!A1 = k  ->  palet[k]
    for k, rgb in enumerate(m.palette):
        view.conditional_format(
            0, 0, m.rows - 1, m.cols - 1,
            {
                "type": "formula",
                "criteria": f"=px!A1={k}",
                "format": wb.add_format({"bg_color": writer._hex(rgb)}),
            },
        )
    if cf_font:
        for k, rgb in enumerate(m.palette):
            view.conditional_format(
                0, 0, m.rows - 1, m.cols - 1,
                {
                    "type": "formula",
                    "criteria": f"=fc!A1={k}",
                    "format": wb.add_format({"font_color": writer._hex(rgb)}),
                },
            )

    px = wb.add_worksheet("px")
    for r in range(m.rows):
        px.write_row(r, 0, m.fill_idx[0, r].tolist())
    px.hide()

    data = wb.add_worksheet("data")
    for f in range(m.n_frames):
        for r in range(m.rows):
            data.write_row(f * m.rows + r, 0, m.fill_idx[f, r].tolist())
    data.hide()

    if cf_font:
        fc = wb.add_worksheet("fc")
        for r in range(m.rows):
            fc.write_row(r, 0, m.font_idx[0, r].tolist())
        fc.hide()
        dataf = wb.add_worksheet("dataf")
        for f in range(m.n_frames):
            for r in range(m.rows):
                dataf.write_row(f * m.rows + r, 0, m.font_idx[f, r].tolist())
        dataf.hide()

    pal = wb.add_worksheet("pal")
    for k, rgb in enumerate(m.palette):
        pal.write_number(k, 0, _bgr_long(rgb))
    pal.hide()

    view.activate()
    wb.close()


def build_sheets_workbook(m: pipeline.Mosaic, path: Path, zoom: int) -> None:
    """Sayfa stratejisi: her kare tam bicimlendirilmis ayri bir sayfa."""
    wb = xlsxwriter.Workbook(str(path))
    cache: dict[tuple[int, int], object] = {}

    def fmt_for(fi: int, fo: int):
        key = (fi, fo)
        f = cache.get(key)
        if f is None:
            f = wb.add_format(
                {
                    "bg_color": writer._hex(m.palette[fi]),
                    "font_color": writer._hex(m.palette[fo]),
                    "font_name": "Consolas",
                    "font_size": 11,
                    "align": "center",
                    "valign": "vcenter",
                }
            )
            cache[key] = f
        return f

    for i in range(m.n_frames):
        ws = wb.add_worksheet(f"f{i + 1}")
        _geometry(ws, m.rows, m.cols, zoom)
        for r in range(m.rows):
            for c in range(m.cols):
                f = fmt_for(int(m.fill_idx[i, r, c]), int(m.font_idx[i, r, c]))
                ch = m.chars[int(m.char_idx[i, r, c])]
                if ch == " ":
                    ws.write_blank(r, c, None, f)
                else:
                    ws.write_string(r, c, ch, f)
    wb.close()


def build_strip_workbook(m: pipeline.Mosaic, path: Path, zoom: int) -> None:
    """Serit stratejisi: tum kareler tek sayfada alt alta, oynatma = kaydirma."""
    wb = xlsxwriter.Workbook(str(path))
    ws = wb.add_worksheet("strip")
    ws.hide_gridlines(2)
    ws.set_zoom(zoom)
    ws.set_column(0, m.cols - 1, writer.COL_WIDTH_CHARS)
    ws.set_default_row(writer.ROW_HEIGHT_PT)

    cache: dict[tuple[int, int], object] = {}

    def fmt_for(fi: int, fo: int):
        key = (fi, fo)
        f = cache.get(key)
        if f is None:
            f = wb.add_format(
                {
                    "bg_color": writer._hex(m.palette[fi]),
                    "font_color": writer._hex(m.palette[fo]),
                    "font_name": "Consolas",
                    "font_size": 11,
                    "align": "center",
                    "valign": "vcenter",
                }
            )
            cache[key] = f
        return f

    for i in range(m.n_frames):
        base = i * m.rows
        for r in range(m.rows):
            for c in range(m.cols):
                f = fmt_for(int(m.fill_idx[i, r, c]), int(m.font_idx[i, r, c]))
                ch = m.chars[int(m.char_idx[i, r, c])]
                if ch == " ":
                    ws.write_blank(base + r, c, None, f)
                else:
                    ws.write_string(base + r, c, ch, f)
    wb.close()


def run_macro(path: Path, macro: str, *args) -> int:
    with excel_com.excel_app(visible=True) as xl:
        wb = xl.Workbooks.Open(str(path.resolve()))
        try:
            xl.WindowState = -4137  # xlMaximized
            excel_com.inject_module(wb, "Bench", vba_src.BENCH_MODULE)
            time.sleep(0.5)  # pencerenin yerlesmesini bekle
            return int(xl.Run(macro, *args))
        finally:
            wb.Close(False)


@app.command()
def main(
    src: Path = typer.Argument(Path("samples/dancer.mp4")),
    cols: int = typer.Option(96, "--cols"),
    frames: int = typer.Option(25, "--frames"),
    colors: int = typer.Option(32, "--colors"),
    zoom: int = typer.Option(40, "--zoom"),
    cf_font: bool = typer.Option(True, "--cf-font/--no-cf-font", help="Yazi rengini de canlandir"),
    naive_frames: int = typer.Option(3, "--naive-frames", help="Naif olcumde kare sayisi"),
    strategies: str = typer.Option("cf,sheets,strip,cells", "--strategies", help="Virgulle ayrilmis"),
    chars: bool = typer.Option(True, "--chars/--no-chars", help="Metin katmani (kapatinca sadece renk)"),
) -> None:
    wanted = {s.strip() for s in strategies.split(",") if s.strip()}
    OUT.mkdir(parents=True, exist_ok=True)

    info = video.probe(src)
    typer.echo(f"Video: {info.width}x{info.height}, {info.fps:.2f} fps, {info.frame_count} kare")

    bg = video.background_model(src)
    box = video.subject_bbox(src, bg)
    typer.echo(f"Kirpma: {box.width}x{box.height}")

    raw = []
    for i, f in enumerate(video.read_frames(src)):
        if i >= frames:
            break
        raw.append(box.crop(f))

    t0 = time.perf_counter()
    m = pipeline.build(raw, cols=cols, colors=colors)
    typer.echo(
        f"Izgara: {m.cols} x {m.rows} = {m.cols * m.rows} hucre, "
        f"{m.n_frames} kare  (uretim {time.perf_counter() - t0:.1f} sn)"
    )

    if not chars:
        # chars[0] her zaman bosluk (kapsama tablosu artan sirali)
        m.char_idx[:] = 0
        typer.echo("Metin katmani kapali: hucreler yalnizca renkle boyaniyor")

    cf_path = OUT / f"cf_{cols}.xlsx"
    sh_path = OUT / f"sheets_{cols}.xlsx"
    st_path = OUT / f"strip_{cols}.xlsx"

    def report_build(label: str, path: Path, fn) -> None:
        t = time.perf_counter()
        fn()
        typer.echo(
            f"{label} dosyasi: {path.stat().st_size / 1e6:.1f} MB "
            f"({time.perf_counter() - t:.1f} sn)"
        )

    if {"cf", "cells"} & wanted:
        report_build("cf", cf_path, lambda: build_cf_workbook(m, cf_path, zoom, cf_font))
    if "sheets" in wanted:
        report_build("sheets", sh_path, lambda: build_sheets_workbook(m, sh_path, zoom))
    if "strip" in wanted:
        report_build("strip", st_path, lambda: build_strip_workbook(m, st_path, zoom))

    results: dict[str, float] = {}

    if "cf" in wanted:
        ms = run_macro(cf_path, "BenchCF", m.n_frames, m.rows, m.cols, cf_font)
        results["cf"] = ms / m.n_frames

    if "sheets" in wanted:
        ms = run_macro(sh_path, "BenchSheets", m.n_frames)
        results["sheets"] = ms / m.n_frames

    if "strip" in wanted:
        ms = run_macro(st_path, "BenchScroll", m.n_frames, m.rows)
        results["strip"] = ms / m.n_frames

    if "cells" in wanted:
        ms = run_macro(cf_path, "BenchCells", naive_frames, m.rows, m.cols)
        results["cells"] = ms / naive_frames

    typer.echo("")
    typer.echo(f"{'strateji':<10}{'ms/kare':>10}{'fps':>10}")
    for name, per_frame in results.items():
        fps = 1000.0 / per_frame if per_frame > 0 else float("inf")
        typer.echo(f"{name:<10}{per_frame:>10.1f}{fps:>10.1f}")


if __name__ == "__main__":
    app()
