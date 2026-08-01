"""Oynatilabilir .xlsm uretimi.

Oynatici VBA'si onceden derlenmis `vbaProject.bin` olarak gomulur; boylece
dosya tamamen XlsxWriter ile yazilir ve **uretim sirasinda Excel'e ihtiyac
duyulmaz**. Izgara olculeri ve kare hizi VBA kaynagina degil, dosyadaki gizli
"cfg" sayfasina yazilir (bkz. writer.write_strip).

vbaProject.bin yoksa `scripts/build_vba_project.py` ile bir kez uretilmelidir.
"""

from __future__ import annotations

from pathlib import Path

from . import pipeline, writer

SHEET_NAME = "film"
VBA_PROJECT = Path(__file__).resolve().parent / "vbaProject.bin"


class MissingVbaProjectError(RuntimeError):
    """Onceden derlenmis oynatici makrosu bulunamadi."""


def build(
    mosaic: pipeline.Mosaic,
    out_path: str | Path,
    fps: float,
    tick=None,
) -> dict:
    """Mosaic'ten oynatilabilir .xlsm uretir."""
    out = Path(out_path).resolve()
    if out.suffix.lower() != ".xlsm":
        raise ValueError("Output file must have the .xlsm extension")
    if not VBA_PROJECT.exists():
        raise MissingVbaProjectError(
            f"Player macro not found at {VBA_PROJECT}. "
            "Run 'python scripts/build_vba_project.py' once to create it."
        )
    out.parent.mkdir(parents=True, exist_ok=True)

    info = writer.write_strip(
        str(out),
        mosaic.fill_idx,
        mosaic.font_idx,
        mosaic.char_idx,
        mosaic.palette,
        mosaic.chars,
        sheet_name=SHEET_NAME,
        fps=fps,
        vba_project=str(VBA_PROJECT),
        tick=tick,
    )

    info["path"] = str(out)
    info["size_mb"] = out.stat().st_size / 1e6
    return info
