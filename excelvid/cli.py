"""Komut satiri arayuzu."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import typer

from . import convert, glyphs, quantize, render, video, writer

app = typer.Typer(add_completion=False, help="Goruntu/video -> Excel mozaigi")


def _convert(
    rgb: np.ndarray,
    out: Path,
    cols: int,
    colors: int,
    zoom: int,
    preview: bool,
) -> None:
    """Tek RGB goruntuyu .xlsx (+ .png on izleme) olarak yazar."""
    h, w = rgb.shape[:2]
    n_cols, n_rows = render.grid_size(w, h, cols)
    typer.echo(f"Izgara: {n_cols} x {n_rows} = {n_cols * n_rows} hucre")

    grid = render.image_to_cells(rgb, n_cols, n_rows)
    table = glyphs.measure()

    both = np.concatenate([grid.fill_rgb.reshape(-1, 3), grid.font_rgb.reshape(-1, 3)])
    palette = quantize.build_palette(both, n_colors=colors)
    fill_idx = quantize.map_to_palette(grid.fill_rgb, palette)
    font_idx = quantize.map_to_palette(grid.font_rgb, palette)
    char_idx = table.nearest(grid.coverage)

    out.parent.mkdir(parents=True, exist_ok=True)
    info = writer.write_still(
        str(out), fill_idx, font_idx, char_idx, palette, table.chars, zoom=zoom
    )
    typer.echo(
        f"Yazildi: {out}  ({out.stat().st_size / 1e6:.2f} MB, "
        f"{info['formats']} benzersiz bicim, {len(palette)} renk)"
    )

    if preview:
        quantized = render.CellGrid(
            fill_rgb=palette[fill_idx],
            font_rgb=palette[font_idx],
            coverage=grid.coverage,
        )
        png = out.with_suffix(".png")
        img = render.preview(quantized, char_idx, table.chars)
        cv2.imwrite(str(png), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        typer.echo(f"On izleme: {png}")


@app.command()
def image(
    src: Path = typer.Argument(..., help="Kaynak goruntu"),
    out: Path = typer.Option(Path("out/still.xlsx"), "--out", "-o"),
    cols: int = typer.Option(96, "--cols", help="Izgara sutun sayisi"),
    colors: int = typer.Option(32, "--colors", help="Palet boyutu (max 32)"),
    zoom: int = typer.Option(40, "--zoom", help="Excel yakinlastirma yuzdesi"),
    preview: bool = typer.Option(True, "--preview/--no-preview"),
) -> None:
    """Tek goruntuden .xlsx mozaik uretir."""
    bgr = cv2.imread(str(src), cv2.IMREAD_COLOR)
    if bgr is None:
        raise typer.BadParameter(f"Goruntu okunamadi: {src}")
    _convert(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), out, cols, colors, zoom, preview)


@app.command()
def frame(
    src: Path = typer.Argument(..., help="Kaynak video"),
    index: int = typer.Option(0, "--index", "-i", help="Kare numarasi"),
    out: Path = typer.Option(Path("out/frame.xlsx"), "--out", "-o"),
    cols: int = typer.Option(96, "--cols"),
    colors: int = typer.Option(32, "--colors"),
    zoom: int = typer.Option(40, "--zoom"),
    autocrop: bool = typer.Option(True, "--autocrop/--no-autocrop", help="Ozneye kirp"),
    preview: bool = typer.Option(True, "--preview/--no-preview"),
) -> None:
    """Videodan tek kare alip mozaige cevirir (kalite testi icin)."""
    info = video.probe(src)
    typer.echo(
        f"Video: {info.width}x{info.height}, {info.fps:.2f} fps, "
        f"{info.frame_count} kare, {info.duration:.2f} sn"
    )

    cap = cv2.VideoCapture(str(src))
    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, bgr = cap.read()
    cap.release()
    if not ok:
        raise typer.BadParameter(f"Kare okunamadi: {index}")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    if autocrop:
        bg = video.background_model(src)
        box = video.subject_bbox(src, bg)
        typer.echo(
            f"Kirpma: ({box.x0},{box.y0})-({box.x1},{box.y1}) "
            f"= {box.width}x{box.height} "
            f"(karenin %{100 * box.width * box.height / (info.width * info.height):.0f}'i)"
        )
        rgb = box.crop(rgb)

    _convert(rgb, out, cols, colors, zoom, preview)


@app.command("video")
def video_cmd(
    src: Path = typer.Argument(..., help="Kaynak video"),
    out: Path = typer.Option(Path("out/film.xlsm"), "--out", "-o"),
    cols: int = typer.Option(64, "--cols", help="Izgara sutun sayisi"),
    colors: int = typer.Option(32, "--colors"),
    fps: float = typer.Option(0.0, "--fps", help="Hedef kare hizi (0 = kaynakla ayni)"),
    max_frames: int = typer.Option(0, "--max-frames", help="0 = tumu"),
    autocrop: bool = typer.Option(True, "--autocrop/--no-autocrop"),
    sub: int = typer.Option(4, "--sub", help="Hucre basina ornekleme (sub x sub piksel)"),
) -> None:
    """Videodan oynatilabilir .xlsm uretir."""
    settings, notes = convert.Settings(
        cols=cols, colors=colors, fps=fps, max_frames=max_frames, autocrop=autocrop, sub=sub
    ).clamped()
    for note in notes:
        typer.echo(f"Uyari: {note}")

    convert.convert(src, out, settings, reporter=convert.Reporter(on_log=typer.echo))
    typer.echo("Excel'de ac, makrolari etkinlestir, Ctrl+Shift+P ile oynat, ESC ile durdur.")


if __name__ == "__main__":
    app()
