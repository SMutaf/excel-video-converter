"""Excel COM yardimcilari.

VBA modullerini calisma kitabina enjekte edip makro calistirmak icin.
Bunun calismasi Guven Merkezi'ndeki "VBA proje nesne modeline guvenilen
erisim" ayarinin acik olmasini gerektirir.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pythoncom
import win32com.client

XL_OPEN_XML_ADDIN = 55
XL_OPEN_XML_WORKBOOK_MACRO_ENABLED = 52
VB_EXT_COMPONENT_MODULE = 1


class VbomAccessError(RuntimeError):
    pass


@contextmanager
def excel_app(visible: bool = False) -> Iterator["win32com.client.CDispatch"]:
    pythoncom.CoInitialize()
    app = win32com.client.DispatchEx("Excel.Application")
    app.Visible = visible
    app.DisplayAlerts = False
    try:
        yield app
    finally:
        try:
            app.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()


def inject_module(workbook, name: str, code: str) -> None:
    """Calisma kitabina standart bir VBA modulu ekler."""
    try:
        project = workbook.VBProject
    except Exception as exc:  # pragma: no cover - ortama bagli
        raise VbomAccessError(
            "Cannot access the VBA project object model. Enable it in "
            "Excel > Options > Trust Center > Trust Center Settings > "
            "Macro Settings > 'Trust access to the VBA project object model'."
        ) from exc
    component = project.VBComponents.Add(VB_EXT_COMPONENT_MODULE)
    component.Name = name
    component.CodeModule.AddFromString(code)


def save_as_xlsm(workbook, path: str | Path) -> None:
    target = Path(path).resolve()
    if target.exists():
        target.unlink()
    workbook.SaveAs(str(target), FileFormat=XL_OPEN_XML_WORKBOOK_MACRO_ENABLED)
