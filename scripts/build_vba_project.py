"""Oynatici VBA'sini bir kez derleyip `excelvid/vbaProject.bin` olarak saklar.

Bu script Excel gerektiren **tek** adimdir ve yalnizca VBA kaynagi degistiginde
calistirilir. Uretilen ikili dosya repoda durur; gunluk kullanimda video ->
.xlsm donusumu XlsxWriter ile yapilir ve Excel'e hic ihtiyac duyulmaz.

Gereksinim: Excel > Secenekler > Guven Merkezi > Makro Ayarlari >
"VBA proje nesne modeline guvenilen erisim" isaretli olmali.

    python scripts/build_vba_project.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from excelvid import excel_com, player_vba  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "excelvid" / "vbaProject.bin"
MODULE_NAME = "Player"
FILM_SHEET = "film"


def main() -> None:
    tmp_dir = Path(tempfile.mkdtemp(prefix="excelvid_vba_"))
    xlsm = tmp_dir / "template.xlsm"
    try:
        with excel_com.excel_app(visible=False) as xl:
            wb = xl.Workbooks.Add()
            try:
                # Hedef dosyayla ayni sayfa yapisi: VBA projesi baska bir
                # calisma kitabina gomulecegi icin belge modulleri ortussun.
                wb.Worksheets(1).Name = FILM_SHEET
                if wb.Worksheets.Count < 2:
                    wb.Worksheets.Add(After=wb.Worksheets(wb.Worksheets.Count))
                wb.Worksheets(2).Name = player_vba.CFG_SHEET

                # Belge modullerinin kod adlarini dile bagli olmaktan cikar
                # (Turkce Excel'de "BuCalismaKitabi"/"Sayfa1" oluyor). XlsxWriter
                # tarafinda ayni adlar verilecek; eslesmezlerse Excel iki takim
                # belge modulu birden tasiyor ve hayalet moduller kaliyor.
                project = wb.VBProject
                project.VBComponents(wb.CodeName).Name = "ThisWorkbook"
                project.VBComponents(wb.Worksheets(1).CodeName).Name = "Sheet1"
                project.VBComponents(wb.Worksheets(2).CodeName).Name = "Sheet2"

                excel_com.inject_module(wb, MODULE_NAME, player_vba.PLAYER_SOURCE)
                excel_com.save_as_xlsm(wb, xlsm)
                print(f"Sablon yazildi: {xlsm}")
            finally:
                wb.Close(False)

        with zipfile.ZipFile(xlsm) as z:
            names = [n for n in z.namelist() if n.endswith("vbaProject.bin")]
            if not names:
                raise RuntimeError("Sablonda vbaProject.bin bulunamadi.")
            data = z.read(names[0])

        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_bytes(data)
        print(f"Yazildi: {OUT}  ({len(data) / 1024:.1f} KB)")
        print("Artik uretim Excel'siz calisir.")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
