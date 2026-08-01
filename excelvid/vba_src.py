"""Calisma kitabina enjekte edilen VBA kaynaklari.

Zamanlama icin winmm.dll'deki timeGetTime kullaniliyor. VBA'nin yerlesik
Timer fonksiyonu gece yarisindan beri gecen saniyeyi ~10 ms cozunurlukle
verir; kare basina 20-50 ms olcecegimiz icin yetersiz.

Application.OnTime bilincli olarak kullanilmiyor: cozunurlugu 1 saniye,
yani kare hizi kontrolu icin uygun degil.
"""

from __future__ import annotations

# Hedef Excel x64 oldugu icin Declare satirlari PtrSafe olmak zorunda.
_TIMER_DECL = """
#If VBA7 Then
    Private Declare PtrSafe Function timeGetTime Lib "winmm.dll" () As Long
#Else
    Private Declare Function timeGetTime Lib "winmm.dll" () As Long
#End If
"""

BENCH_MODULE = (
    """Option Explicit
"""
    + _TIMER_DECL
    + '''
' --- Strateji 1: kosullu bicimlendirme + tek seferde dizi yazimi -------------
' Her karede yalnizca palet indekslerini iceren gizli izgaraya yaziyoruz;
' renklendirmeyi Excel'in kendi CF motoru yapiyor.
Public Function BenchCF(ByVal nFrames As Long, ByVal nRows As Long, _
                        ByVal nCols As Long, ByVal withFont As Boolean) As Long
    Dim shData As Worksheet, shPx As Worksheet, shFc As Worksheet
    Dim i As Long, t0 As Long

    Set shData = ThisWorkbook.Worksheets("data")
    Set shPx = ThisWorkbook.Worksheets("px")
    ThisWorkbook.Worksheets("view").Activate

    Application.ScreenUpdating = True
    Application.Calculation = xlCalculationAutomatic

    t0 = timeGetTime
    For i = 0 To nFrames - 1
        shPx.Range(shPx.Cells(1, 1), shPx.Cells(nRows, nCols)).Value2 = _
            shData.Range(shData.Cells(i * nRows + 1, 1), _
                         shData.Cells((i + 1) * nRows, nCols)).Value2
        If withFont Then
            Set shFc = ThisWorkbook.Worksheets("fc")
            shFc.Range(shFc.Cells(1, 1), shFc.Cells(nRows, nCols)).Value2 = _
                ThisWorkbook.Worksheets("dataf").Range( _
                    ThisWorkbook.Worksheets("dataf").Cells(i * nRows + 1, 1), _
                    ThisWorkbook.Worksheets("dataf").Cells((i + 1) * nRows, nCols)).Value2
        End If
        DoEvents
    Next i
    BenchCF = timeGetTime - t0
End Function

' --- Strateji 2: onceden boyanmis sayfalar arasinda gecis --------------------
' Boyama maliyeti uretim zamanina kayiyor; oynatma sadece sayfa degistirmek.
Public Function BenchSheets(ByVal nFrames As Long) As Long
    Dim i As Long, t0 As Long
    Application.ScreenUpdating = True
    t0 = timeGetTime
    For i = 1 To nFrames
        ThisWorkbook.Worksheets("f" & i).Activate
        DoEvents
    Next i
    BenchSheets = timeGetTime - t0
End Function

' --- Strateji 4: tek sayfada dikey serit + pencere kaydirma ------------------
' Kareler alt alta onceden boyanmis; oynatma sadece gorunumu kaydirmak.
Public Function BenchScroll(ByVal nFrames As Long, ByVal nRows As Long) As Long
    Dim i As Long, t0 As Long
    ThisWorkbook.Worksheets("strip").Activate
    Application.ScreenUpdating = True
    t0 = timeGetTime
    For i = 0 To nFrames - 1
        ActiveWindow.ScrollRow = i * nRows + 1
        DoEvents
    Next i
    BenchScroll = timeGetTime - t0
End Function

' --- Strateji 3: hucre hucre Interior.Color (referans olcum) -----------------
' Naif yaklasim. Digerleriyle karsilastirmak icin var, kullanilmasi icin degil.
Public Function BenchCells(ByVal nFrames As Long, ByVal nRows As Long, _
                           ByVal nCols As Long) As Long
    Dim shView As Worksheet, shData As Worksheet, shPal As Worksheet
    Dim arr As Variant, pal() As Long
    Dim i As Long, r As Long, c As Long, k As Long, t0 As Long

    Set shView = ThisWorkbook.Worksheets("view")
    Set shData = ThisWorkbook.Worksheets("data")
    Set shPal = ThisWorkbook.Worksheets("pal")
    shView.Activate

    ReDim pal(0 To 63)
    For k = 0 To 63
        If Len(shPal.Cells(k + 1, 1).Value) = 0 Then Exit For
        pal(k) = CLng(shPal.Cells(k + 1, 1).Value)
    Next k

    t0 = timeGetTime
    For i = 0 To nFrames - 1
        arr = shData.Range(shData.Cells(i * nRows + 1, 1), _
                           shData.Cells((i + 1) * nRows, nCols)).Value2
        For r = 1 To nRows
            For c = 1 To nCols
                shView.Cells(r, c).Interior.Color = pal(CLng(arr(r, c)))
            Next c
        Next r
        DoEvents
    Next i
    BenchCells = timeGetTime - t0
End Function
'''
)
