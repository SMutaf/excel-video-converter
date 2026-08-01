"""Uretilen .xlsm dosyasina gomulen oynatici VBA'si.

Bu kaynak **sabittir** - video basina degismez. Izgara olculeri ve kare hizi
gizli "cfg" sayfasindaki hucrelerden okunur. Boylece VBA bir kez derlenip
`vbaProject.bin` olarak saklanabiliyor ve uretim sirasinda Excel'e hic ihtiyac
kalmiyor (bkz. scripts/build_vba_project.py).

Oynatma sirasinda hicbir hucre boyanmaz; tum kareler uretim zamaninda tek
sayfaya alt alta cizilmistir ve oynatma yalnizca pencereyi kaydirmaktir.

Kadraj: pencerenin tam olarak bir karelik satiri gostermesi gerekiyor, yoksa
alt kenarda bir sonraki karenin ust seridi gorunur. Zoom'u ekrana gore secip
ardindan pencere yuksekligini tam katina getirerek cozuyoruz.
"""

from __future__ import annotations

# Ayarlarin okundugu gizli sayfa ve hucreler. writer.write_strip ile birebir
# ayni olmak zorunda; degistirirsen vbaProject.bin'i yeniden uretmen gerekir.
CFG_SHEET = "cfg"
CFG_CELLS = {
    "rows": "B1",
    "cols": "B2",
    "frames": "B3",
    "fps": "B4",
    "sheet": "B5",
}

PLAYER_SOURCE = r'''Option Explicit

Private Const CFG_SHEET As String = "cfg"

#If VBA7 Then
    Private Declare PtrSafe Function timeGetTime Lib "winmm.dll" () As Long
    Private Declare PtrSafe Sub SleepMs Lib "kernel32" Alias "Sleep" (ByVal ms As Long)
#Else
    Private Declare Function timeGetTime Lib "winmm.dll" () As Long
    Private Declare Sub SleepMs Lib "kernel32" Alias "Sleep" (ByVal ms As Long)
#End If

' cfg sayfasindan okunan ayarlar
Private mRows As Long
Private mCols As Long
Private mFrames As Long
Private mFps As Double
Private mSheet As String

Private mStop As Boolean
Private mPlaying As Boolean

' Geri yuklemek icin saklanan arayuz durumu
Private mOldFormulaBar As Boolean
Private mOldStatusBar As Boolean
Private mOldHeadings As Boolean
Private mOldTabs As Boolean
Private mOldVScroll As Boolean
Private mOldHScroll As Boolean
Private mOldZoom As Long
Private mOldState As Long
Private mOldHeight As Double
Private mOldWidth As Double
Private mSaved As Boolean

Public Sub Auto_Open()
    Application.OnKey "^+p", "Play"
End Sub

Private Sub LoadConfig()
    Dim cfg As Worksheet
    Set cfg = ThisWorkbook.Worksheets(CFG_SHEET)
    mRows = CLng(cfg.Range("B1").Value)
    mCols = CLng(cfg.Range("B2").Value)
    mFrames = CLng(cfg.Range("B3").Value)
    mFps = CDbl(cfg.Range("B4").Value)
    mSheet = CStr(cfg.Range("B5").Value)
    If mRows < 1 Or mCols < 1 Or mFrames < 1 Or mFps <= 0 Then
        Err.Raise vbObjectError + 1, "Player", "cfg sayfasindaki ayarlar gecersiz."
    End If
End Sub

' Kadraji ekrana oturtur: once zoom, sonra pencere yuksekligini tam kat yapar.
Private Sub SetupWindow()
    Dim cellPt As Double, zoomPct As Long
    Dim fitH As Double, fitW As Double
    Dim maxH As Double, maxW As Double
    Dim scrH As Double, scrW As Double
    Dim i As Long, delta As Double

    Worksheets(mSheet).Activate

    If Not mSaved Then
        mOldFormulaBar = Application.DisplayFormulaBar
        mOldStatusBar = Application.DisplayStatusBar
        mOldHeadings = ActiveWindow.DisplayHeadings
        mOldTabs = ActiveWindow.DisplayWorkbookTabs
        mOldVScroll = ActiveWindow.DisplayVerticalScrollBar
        mOldHScroll = ActiveWindow.DisplayHorizontalScrollBar
        mOldZoom = ActiveWindow.Zoom
        mOldState = Application.WindowState
        mSaved = True
    End If

    Application.DisplayFormulaBar = False
    Application.DisplayStatusBar = False
    ' Serit menu ~180 piksel yer kapliyor; gizleyince zoom belirgin buyuyor.
    On Error Resume Next
    Application.ExecuteExcel4Macro "SHOW.TOOLBAR(""Ribbon"",False)"
    On Error GoTo 0
    ActiveWindow.DisplayHeadings = False
    ActiveWindow.DisplayWorkbookTabs = False
    ActiveWindow.DisplayVerticalScrollBar = False
    ActiveWindow.DisplayHorizontalScrollBar = False

    Application.WindowState = xlNormal
    mOldHeight = Application.Height
    mOldWidth = Application.Width

    ' Zoom'u ekranin tamamina gore sec: once pencereyi buyutup kullanilabilir
    ' alani olcuyoruz, sonra normale donup tam kat olcuye getiriyoruz.
    ' Olcumu normal pencerede yapsaydik zoom, o anki pencere boyutuna takilirdi.
    Application.WindowState = xlMaximized
    DoEvents
    maxH = Application.UsableHeight
    maxW = Application.UsableWidth
    ' Buyutulmus haldeki pencere olculeri = ekranin kullanilabilir alani.
    ' Sonda pencereyi ortalamak icin lazim.
    scrH = Application.Height
    scrW = Application.Width
    Application.WindowState = xlNormal
    DoEvents

    ' Hucre kenari %100 zoom'da 15 punto (kare hucre). %1'lik pay, pencere
    ' cercevesinin ekrani tasirmamasi icin.
    cellPt = 15#
    fitH = (maxH * 0.99) / (mRows * cellPt)
    fitW = (maxW * 0.99) / (mCols * cellPt)
    zoomPct = Int(WorksheetFunction.Min(fitH, fitW) * 100)
    If zoomPct < 10 Then zoomPct = 10
    If zoomPct > 400 Then zoomPct = 400
    ActiveWindow.Zoom = zoomPct

    ' Pencereyi tam bir kare gosterecek olcuye getir. Kullanilabilir alan ile
    ' pencere olcusu arasindaki fark (kenarlik, seritler) sabit olmadigi icin
    ' birkac adimda yaklasiyoruz.
    For i = 1 To 6
        delta = (mRows * cellPt * zoomPct / 100#) - ActiveWindow.UsableHeight
        If Abs(delta) < 0.5 Then Exit For
        Application.Height = Application.Height + delta
    Next i
    For i = 1 To 6
        delta = (mCols * cellPt * zoomPct / 100#) - ActiveWindow.UsableWidth
        If Abs(delta) < 0.5 Then Exit For
        Application.Width = Application.Width + delta
    Next i

    ' Pencereyi ekrana ortala. Yoksa yeniden boyutlandirdiktan sonra Excel'in
    ' eski konumunda kalip ekranin altindan tasabiliyor.
    Application.Top = WorksheetFunction.Max(0, (scrH - Application.Height) / 2)
    Application.Left = WorksheetFunction.Max(0, (scrW - Application.Width) / 2)
End Sub

Private Sub RestoreWindow()
    On Error Resume Next
    Application.ExecuteExcel4Macro "SHOW.TOOLBAR(""Ribbon"",True)"
    If mSaved Then
        Application.DisplayFormulaBar = mOldFormulaBar
        Application.DisplayStatusBar = mOldStatusBar
        ActiveWindow.DisplayHeadings = mOldHeadings
        ActiveWindow.DisplayWorkbookTabs = mOldTabs
        ActiveWindow.DisplayVerticalScrollBar = mOldVScroll
        ActiveWindow.DisplayHorizontalScrollBar = mOldHScroll
        ActiveWindow.Zoom = mOldZoom
        Application.Height = mOldHeight
        Application.Width = mOldWidth
        Application.WindowState = mOldState
        mSaved = False
    End If
    Application.OnKey "{ESC}"
    On Error GoTo 0
End Sub

Public Sub StopPlay()
    mStop = True
End Sub

' Kadraji kurup tek bir karede durur. Cerceveleme kontrolu icin.
Public Sub ShowFrame(ByVal idx As Long)
    LoadConfig
    SetupWindow
    If idx < 0 Then idx = 0
    If idx > mFrames - 1 Then idx = mFrames - 1
    ActiveWindow.ScrollRow = idx * mRows + 1
End Sub

' Arayuzu oynatma oncesi haline dondurur.
Public Sub Restore()
    RestoreWindow
End Sub

' Kadrajin dogrulugunu sayisal olarak bildirir.
Public Function FrameReport() As String
    LoadConfig
    FrameReport = "zoom=" & ActiveWindow.Zoom & _
                  " usableH=" & Format(ActiveWindow.UsableHeight, "0.0") & _
                  " gerekenH=" & Format(mRows * 15# * ActiveWindow.Zoom / 100#, "0.0") & _
                  " usableW=" & Format(ActiveWindow.UsableWidth, "0.0") & _
                  " gerekenW=" & Format(mCols * 15# * ActiveWindow.Zoom / 100#, "0.0") & _
                  " gorunenSatir=" & Format(ActiveWindow.UsableHeight / (15# * ActiveWindow.Zoom / 100#), "0.00") & _
                  " kareSatir=" & mRows
End Function

' Sonsuz dongude oynatir (ESC ile durur).
Public Sub Play()
    PlayInternal True
End Sub

' Tek tur oynatip biter. Olcum ve kontrol icin.
Public Sub PlayOnce()
    PlayInternal False
End Sub

Private Sub PlayInternal(ByVal loopForever As Boolean)
    Dim i As Long, t0 As Long, elapsed As Long
    Dim due As Double, frameMs As Double

    If mPlaying Then Exit Sub
    mPlaying = True
    mStop = False

    On Error GoTo CleanUp
    LoadConfig
    SetupWindow
    Application.OnKey "{ESC}", "StopPlay"
    Application.ScreenUpdating = True

    frameMs = 1000# / mFps

    Do
        t0 = timeGetTime
        For i = 0 To mFrames - 1
            ActiveWindow.ScrollRow = i * mRows + 1

            ' Kare hizini sabitle. Cizim hedeften uzun surerse bekleme
            ' atlanir; yani video yavaslamaz, kare suresi uzar.
            due = (i + 1) * frameMs
            Do
                DoEvents
                If mStop Then Exit Do
                elapsed = timeGetTime - t0
                If elapsed >= due Then Exit Do
                If due - elapsed > 2 Then SleepMs 1
            Loop

            If mStop Then Exit For
        Next i
        If mStop Then Exit Do
        If Not loopForever Then Exit Do
    Loop

CleanUp:
    RestoreWindow
    mPlaying = False
End Sub
'''
